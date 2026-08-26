"""ADP 移液空气泵交互式 RS485 控制脚本。

设备 ID 默认 02。
按手册推荐流程执行：
    空气中首次回吸 30uL -> 移动 Tip 进入液体 -> 吸入 600uL
    -> 抬离液面后二次回吸 -> 分 3 次排液，每次 200uL。
每次吸液和排液都必须在终端输入命令后才执行。

终端命令：
    init       初始化回原点
    tip        查询 Tip 有无
    air        在空气中首次回吸 30uL
    asp        吸液 600uL
    tail       二次回吸空气
    disp       排液 200uL
    flush      排液至 0，用于最后清空 Tip
    status     查询运行状态
    reset      重置当前吸排流程状态
    help       显示命令帮助
    quit       退出
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

try:
    import serial
except ImportError:  # pragma: no cover
    serial = None


DEFAULT_ADDRESS = "02"
DEFAULT_BAUDRATE = 115200
ASPIRATE_UL = 600
DISPENSE_BATCH_UL = 200
DISPENSE_BATCH_COUNT = 3
FIRST_AIR_UL = 30
ASPIRATE_SPEED_UL_S = 500
DISPENSE_SPEED_UL_S = 1000

STATE_TEXT = {
    "00": "运行中",
    "01": "运行完成",
    "02": "异常停止",
    "03": "探测到液面",
    "04": "行程内未探测到液面",
    "05": "超过ADP可用容积/行程保护",
    "06": "吸液阻塞报警",
    "07": "排液阻塞报警",
    "09": "吸液空吸报警",
    "15": "气路异常报警",
    "3D": "温度异常报警",
    "46": "褪Tip失败",
    "FF": "其它异常报警",
}


class ADPError(RuntimeError):
    pass


def crc16(data: bytes) -> int:
    """ASCII 协议 CRC-16，初值 0xFFFF，反射多项式 0xA001。"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def find_usb_serial_port() -> str | None:
    """自动查找 CH340、CP210x 或 FTDI 等 USB-RS485 串口。"""
    try:
        from serial.tools import list_ports
    except Exception:
        return None

    for info in list_ports.comports():
        text = f"{info.description} {info.hwid}".lower()
        if any(key in text for key in ("ch340", "usb-serial", "cp210x", "ftdi")):
            return info.device
    return None


def build_frame(command: str, address: str = DEFAULT_ADDRESS) -> bytes:
    payload = f">{address}{command}".encode("ascii")
    return payload + f"{crc16(payload):04X}".encode("ascii") + b"\r\n"


def parse_response(raw: bytes) -> str:
    text = raw.decode("ascii", errors="replace").strip()
    if not text.startswith(">"):
        raise ADPError(f"响应不是合法 ADP 帧：{text!r}")
    if len(text) < 7:
        raise ADPError(f"响应长度过短：{text!r}")

    body = text[:-4]
    crc_text = text[-4:]
    try:
        expected = int(crc_text, 16)
    except ValueError as exc:
        raise ADPError(f"响应 CRC 不是 4 位十六进制：{text!r}") from exc

    if crc16(body.encode("ascii")) != expected:
        raise ADPError(f"响应 CRC 校验失败：{text!r}")
    return body


@dataclass
class WorkflowState:
    remaining_batches: int = 0
    air_done: bool = False
    aspirated: bool = False


class ADPController:
    def __init__(
        self,
        port: str,
        address: str = DEFAULT_ADDRESS,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = 1.0,
    ) -> None:
        if serial is None:
            raise ADPError("缺少 pyserial，请先运行：python -m pip install pyserial")
        self.port = port
        self.address = address
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: serial.Serial | None = None

    def open(self) -> None:
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            write_timeout=self.timeout,
        )

    def close(self) -> None:
        if self.ser is not None:
            self.ser.close()
            self.ser = None

    def __enter__(self) -> "ADPController":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def send(self, command: str) -> str:
        if self.ser is None:
            raise ADPError("串口未打开")
        frame = build_frame(command, self.address)
        print(
            f"发送: {frame.decode('ascii').replace(chr(13), '<CR>').replace(chr(10), '<LF>')}"
        )
        self.ser.reset_input_buffer()
        self.ser.write(frame)
        self.ser.flush()

        raw = self.ser.read_until(b"\n")
        if not raw.endswith(b"\n"):
            raise ADPError(
                f"等待 ADP 响应超时，最近收到的数据：{raw.hex(' ').upper() or '空'}"
            )
        body = parse_response(raw)
        print(f"响应: {body}")
        return body

    def query_version(self) -> str:
        body = self.send("A")
        return body[3:]

    def initialize(self, timeout: float = 30.0) -> None:
        print("执行初始化回原点...")
        self.send("G")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.03)
            body = self.send("g")
            status = body[4:6]
            if status == "01":
                print("初始化完成")
                return
            if status == "02":
                raise ADPError("初始化回原点失败，请手动取下 Tip 后重试")
            if status == "03":
                print("设备当前未初始化，等待回原点...")
            elif status != "00":
                raise ADPError(f"初始化状态码异常：{status}")
        raise ADPError("初始化回原点超时")

    def check_initialized(self) -> None:
        body = self.send("g")
        status = body[4:6]
        if status == "01":
            return
        if status == "03":
            raise ADPError("设备尚未初始化，请先输入 init")
        raise ADPError(f"设备初始化状态异常：{status}")

    def check_tip(self) -> None:
        body = self.send("q")
        status = body[4:6]
        if status == "02":
            raise ADPError("检测到没有 Tip，请先安装 Tip")
        if status != "01":
            raise ADPError(f"查询 Tip 状态失败：{status}")
        print("Tip 状态正常")

    def set_aspirate_speed(self, speed_ul_s: int) -> None:
        if not 0 <= speed_ul_s <= 0xFFFF:
            raise ADPError(f"吸液速度超出范围：{speed_ul_s}")
        self.send(f"4{speed_ul_s:04X}")

    def set_dispense_speed(self, speed_ul_s: int) -> None:
        if not 0 <= speed_ul_s <= 0xFFFF:
            raise ADPError(f"排液速度超出范围：{speed_ul_s}")
        self.send(f"B{speed_ul_s:04X}")

    def set_first_air_volume(self, volume_ul: int) -> None:
        if not 0 < volume_ul <= 0xFFFF:
            raise ADPError(f"首次回吸空气量超出范围：{volume_ul}")
        body = self.send("j")
        data = body[4:]
        if len(data) != 24:
            raise ADPError(f"查询首次回吸空气量响应格式异常：{body}")
        new_data = f"{volume_ul:04X}" + data[4:]
        self.send(f"J{new_data}")
        print(f"首次回吸空气量已设为 {volume_ul}uL")

    def first_air(self) -> None:
        response = self.send("M")
        self._ensure_action_accepted(response, "首次回吸空气")
        self.wait_done()
        print("首次回吸空气完成")

    def aspirate(self, volume_ul: int) -> None:
        if not 0 < volume_ul <= 0xFFFF:
            raise ADPError(f"吸液量必须为 1~65535 uL，当前值：{volume_ul}")
        response = self.send(f"n{volume_ul:04X}")
        self._ensure_action_accepted(response, "吸液")
        self.wait_done()
        print(f"吸液完成：{volume_ul} uL")

    def second_air(self) -> None:
        response = self.send("P")
        self._ensure_action_accepted(response, "二次回吸空气")
        self.wait_done()
        print("二次回吸空气完成")

    def dispense(self, volume_ul: int) -> None:
        if not 0 <= volume_ul <= 0xFFFF:
            raise ADPError(f"排液量必须为 0~65535 uL，当前值：{volume_ul}")
        response = self.send(f"p{volume_ul:04X}")
        self._ensure_action_accepted(response, "排液")
        self.wait_done()
        print(f"排液完成：{volume_ul} uL")

    def flush_all(self) -> None:
        response = self.send("p0000")
        self._ensure_action_accepted(response, "排液至0")
        self.wait_done()
        print("排液至 0 完成")

    def wait_done(self, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.03)
            body = self.send("d")
            status = body[4:6]
            if status == "01":
                return
            if status != "00":
                raise ADPError(f"ADP 状态异常：{status}（{STATE_TEXT.get(status, '未知')}）")
        raise ADPError("等待 ADP 完成超时")

    def _ensure_action_accepted(self, response: str, action_name: str) -> None:
        status = response[4:6]
        if status == "01":
            return
        if status == "02":
            raise ADPError(f"{action_name}指令被拒绝：超过 ADP 可用容积或行程保护")
        if status == "00":
            raise ADPError(f"{action_name}指令被拒绝：设备正在运行，请等待完成后再发送")
        raise ADPError(f"{action_name}指令响应异常：{status}")


def print_help() -> None:
    print(
        """
可用命令:
  init        初始化回原点
  tip         查询 Tip 有无
  air         在空气中执行首次回吸 30uL
  asp         吸液 600uL（0.6mL），吸液前请将 Tip 放入液体
  tail        吸液后将 Tip 抬离液面，再执行二次回吸空气
  disp        排液 200uL（0.2mL）
  flush       排液至 0，最后清空 Tip
  status      查询运行状态
  reset       重置当前吸排流程状态
  help        显示本帮助
  quit        退出
"""
    )


def handle_air(adp: ADPController, state: WorkflowState) -> None:
    adp.check_initialized()
    adp.check_tip()
    print("执行首次回吸空气，Tip 必须暴露在空气中，不能放在液体里。")
    adp.set_aspirate_speed(ASPIRATE_SPEED_UL_S)
    adp.set_dispense_speed(DISPENSE_SPEED_UL_S)
    adp.set_first_air_volume(FIRST_AIR_UL)
    adp.first_air()
    state.air_done = True
    print("首次回吸完成。请将 Tip 移动到液面位置，再输入 asp 吸液。")


def handle_aspirate(adp: ADPController, state: WorkflowState) -> None:
    if not state.air_done:
        print("请先输入 air，在空气中完成首次回吸。")
        return
    if state.remaining_batches > 0:
        print("上一次吸液还未排完，请继续输入 disp，或输入 reset 后重新开始。")
        return

    adp.check_initialized()
    adp.check_tip()
    print("执行吸液，Tip 此时应已进入液体。")
    adp.aspirate(ASPIRATE_UL)
    state.aspirated = True
    state.remaining_batches = DISPENSE_BATCH_COUNT
    print(
        f"吸液完成。可先将 Tip 抬离液面，再输入 tail 二次回吸；"
        f"之后输入 disp 排液，共 {DISPENSE_BATCH_COUNT} 次，每次 {DISPENSE_BATCH_UL}uL。"
    )


def handle_second_air(adp: ADPController, state: WorkflowState) -> None:
    if not state.aspirated:
        print("请先输入 air 首次回吸，再输入 asp 吸液。")
        return
    print("执行二次回吸空气，Tip 应已抬离液面。")
    adp.second_air()
    print("二次回吸完成，可输入 disp 排液。")


def handle_dispense(adp: ADPController, state: WorkflowState) -> None:
    if state.remaining_batches <= 0:
        print("当前没有可排批次，请先输入 air，再将 Tip 放入液体并输入 asp。")
        return
    adp.dispense(DISPENSE_BATCH_UL)
    state.remaining_batches -= 1
    print(f"本批排液完成，剩余 {state.remaining_batches} 批。")
    if state.remaining_batches == 0:
        print("三批已排完。如需彻底排空，可输入 flush。")


def handle_flush(adp: ADPController, state: WorkflowState) -> None:
    adp.flush_all()
    state.remaining_batches = 0


def handle_status(adp: ADPController) -> None:
    body = adp.send("d")
    status = body[4:6]
    print(f"当前状态: {status}（{STATE_TEXT.get(status, '未知')}）")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ADP 交互式吸排液控制，默认设备 ID 02",
    )
    parser.add_argument("--port", default=None, help="USB-RS485 串口号；不填时自动查找")
    parser.add_argument("--address", default=DEFAULT_ADDRESS, help=f"ADP 地址，默认 {DEFAULT_ADDRESS}")
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE, help="波特率，默认 115200")
    parser.add_argument("--timeout", type=float, default=1.0, help="等待响应超时秒数，默认 1.0")
    args = parser.parse_args()

    port = args.port or find_usb_serial_port()
    if port is None:
        print("没有自动找到 USB-RS485 串口，请用 --port 指定，例如 --port COM5。", file=sys.stderr)
        return 1

    print(f"串口: {port}")
    print(f"参数: {args.baudrate} bps, 8N1, 地址 {args.address}")

    try:
        with ADPController(
            port=port,
            address=args.address,
            baudrate=args.baudrate,
            timeout=args.timeout,
        ) as adp:
            version = adp.query_version()
            print(f"通信正常，软件版本：{version}")
            print_help()

            state = WorkflowState()
            while True:
                try:
                    raw_command = input("ADP> ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break

                if raw_command in ("quit", "exit", "q"):
                    break
                if raw_command in ("help", "h", "?"):
                    print_help()
                elif raw_command == "init":
                    adp.initialize()
                elif raw_command == "tip":
                    adp.check_tip()
                elif raw_command in ("air", "first-air"):
                    handle_air(adp, state)
                elif raw_command in ("asp", "aspirate"):
                    handle_aspirate(adp, state)
                elif raw_command in ("tail", "second-air"):
                    handle_second_air(adp, state)
                elif raw_command in ("disp", "dispense"):
                    handle_dispense(adp, state)
                elif raw_command in ("flush", "empty"):
                    handle_flush(adp, state)
                elif raw_command == "status":
                    handle_status(adp)
                elif raw_command == "reset":
                    state.remaining_batches = 0
                    state.air_done = False
                    state.aspirated = False
                    print("已重置当前吸排流程状态。")
                else:
                    print("未知命令，输入 help 查看可用命令。")
        return 0
    except ADPError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
