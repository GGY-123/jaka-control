"""ADP 移液空气泵 RS485 通信检查脚本。

默认设备 ID 为 02。
只发送 `A` 查询软件版本，不执行初始化、吸液、排液或褪 Tip。

用法：
    python adp_rs485_check.py
    python adp_rs485_check.py --address 02
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import serial
except ImportError:  # pragma: no cover
    serial = None


DEFAULT_ADDRESS = "02"
DEFAULT_BAUDRATE = 115200


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


def build_query_frame(address: str) -> bytes:
    payload = f">{address}A".encode("ascii")
    return payload + f"{crc16(payload):04X}".encode("ascii") + b"\r\n"


def parse_response(raw: bytes) -> str:
    text = raw.decode("ascii", errors="replace").strip()
    if not text.startswith(">"):
        raise ValueError(f"响应不是合法 ADP 帧：{text!r}")
    if len(text) < 7:
        raise ValueError(f"响应长度过短：{text!r}")

    body = text[:-4]
    crc_text = text[-4:]
    expected = int(crc_text, 16)
    if crc16(body.encode("ascii")) != expected:
        raise ValueError(f"响应 CRC 校验失败：{text!r}")
    return body


def check_once(ser: serial.Serial, address: str) -> tuple[str | None, str | None]:
    frame = build_query_frame(address)
    print(
        f"发送: {frame.decode('ascii').replace(chr(13), '<CR>').replace(chr(10), '<LF>')} "
        f"hex={frame.hex(' ').upper()}"
    )
    try:
        ser.reset_input_buffer()
        ser.write(frame)
        ser.flush()
    except Exception as exc:
        return None, f"串口发送异常：{exc}"

    raw = ser.read_until(b"\n")
    if not raw.endswith(b"\n"):
        return None, f"未收到响应，原始数据：{raw.hex(' ').upper() or '空'}"

    print(f"收到: {raw.decode('ascii', errors='replace').strip()}")
    try:
        body = parse_response(raw)
    except ValueError as exc:
        return None, str(exc)
    return body, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只检查电脑与 ADP 能否通过 RS485 通信，不执行任何移液动作",
    )
    parser.add_argument("--port", default=None, help="USB-RS485 串口号；不填时自动查找")
    parser.add_argument("--address", default=DEFAULT_ADDRESS, help=f"ADP 地址，默认 {DEFAULT_ADDRESS}")
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE, help="波特率，默认 115200")
    parser.add_argument("--count", type=int, default=3, help="连续查询次数，默认 3")
    parser.add_argument("--interval", type=float, default=1.0, help="每次查询间隔秒数，默认 1.0")
    parser.add_argument("--timeout", type=float, default=1.0, help="单次等待响应超时秒数，默认 1.0")
    parser.add_argument("--list-ports", action="store_true", help="列出电脑当前串口后退出")
    parser.add_argument("--forever", action="store_true", help="持续重复发送 A 查询，按 Ctrl+C 停止")
    args = parser.parse_args()

    if serial is None:
        print("缺少 pyserial，请先运行：python -m pip install pyserial", file=sys.stderr)
        return 2

    if args.list_ports:
        try:
            from serial.tools import list_ports
        except Exception as exc:
            print(f"无法枚举串口: {exc}", file=sys.stderr)
            return 2
        for info in list_ports.comports():
            print(f"{info.device}\t{info.description}\t{info.hwid}")
        return 0

    port = args.port or find_usb_serial_port()
    if port is None:
        print("没有自动找到 USB-RS485 串口，请用 --list-ports 查看实际 COM 口，再用 --port 指定。", file=sys.stderr)
        return 1

    print(f"串口: {port}")
    print(f"参数: {args.baudrate} bps, 8N1, 地址 {args.address}")
    print("说明: 只发送 A 查询软件版本，不执行初始化或移液动作。")

    try:
        ser = serial.Serial(
            port=port,
            baudrate=args.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=args.timeout,
            write_timeout=args.timeout,
        )
    except Exception as exc:
        print(f"串口打开失败: {exc}", file=sys.stderr)
        print("请确认 COM 口正确，且其他软件没有占用该串口。", file=sys.stderr)
        return 1

    try:
        attempt = 0
        while True:
            attempt += 1
            if not args.forever and attempt > args.count:
                break
            if args.forever:
                print(f"\n第 {attempt} 次查询")
            else:
                print(f"\n第 {attempt}/{args.count} 次查询")

            body, error = check_once(ser, args.address)
            if body is not None:
                print(f"通信正常，设备地址 {args.address}，软件版本：{body[3:]}")
                return 0

            print(f"查询失败: {error}", file=sys.stderr)
            time.sleep(args.interval)

        print("\n通信失败。请依次检查：485A/485B 是否接反、设备地址、波特率、供电、共地、COM 口占用。", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已停止发送。", file=sys.stderr)
        return 0
    finally:
        ser.close()


if __name__ == "__main__":
    sys.exit(main())
