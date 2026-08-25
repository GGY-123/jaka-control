# -*- coding: utf-8 -*-
"""ADP pipette RS485 ASCII controller, based on the local ADP protocol notes."""
import os
import threading
import time

import serial
from serial.tools import list_ports


STATE_TEXT = {
    "00": "运行中", "01": "运行完成", "02": "异常停止", "03": "探测到液面",
    "04": "未探测到液面", "05": "超过容积/行程", "06": "吸液阻塞",
    "07": "排液阻塞", "09": "吸液空吸", "15": "气路异常", "3D": "温度异常",
    "46": "褪 Tip 失败", "FF": "其它异常",
}


class ADPError(RuntimeError):
    pass


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def find_port():
    for info in list_ports.comports():
        text = f"{info.description} {info.hwid}".lower()
        if any(key in text for key in ("ch340", "usb-serial", "cp210x", "ftdi")):
            return info.device
    return ""


class ADPPipette:
    def __init__(self):
        self.port = os.environ.get("ADP_PORT", "")
        self.address = os.environ.get("ADP_ADDRESS", "02")
        self.baudrate = int(os.environ.get("ADP_BAUD", "115200"))
        self.timeout = float(os.environ.get("ADP_TIMEOUT", "1.0"))
        self.ser = None
        self.lock = threading.RLock()
        self.initialized = False
        self.air_done = False
        self.aspirated = False
        self.remaining_batches = 0
        self.last_status = ""
        self.last_error = None

    def info(self):
        return {"connected": self.ser is not None, "port": self.port or find_port(),
                "address": self.address, "baudrate": self.baudrate,
                "initialized": self.initialized, "remaining_batches": self.remaining_batches,
                "last_status": self.last_status, "last_error": self.last_error}

    def connect(self, port=None, address=None, baudrate=None):
        with self.lock:
            if self.ser is not None:
                return self.info()
            self.port = (port or self.port or find_port()).strip()
            if address:
                self.address = address.strip()
            if baudrate:
                self.baudrate = int(baudrate)
            if not self.port:
                raise ADPError("未找到 USB-RS485 串口，请手动填写串口")
            try:
                self.ser = serial.Serial(self.port, self.baudrate, serial.EIGHTBITS,
                                         serial.PARITY_NONE, serial.STOPBITS_ONE,
                                         timeout=self.timeout, write_timeout=self.timeout)
                self.send("A")
                self.last_error = None
                return self.info()
            except Exception as exc:
                self.disconnect()
                raise ADPError(f"移液枪串口连接失败: {exc}") from exc

    def disconnect(self):
        with self.lock:
            if self.ser is not None:
                self.ser.close()
            self.ser = None
            self.initialized = False
            self.air_done = False
            self.aspirated = False
            self.remaining_batches = 0
            return self.info()

    def _frame(self, command):
        payload = f">{self.address}{command}".encode("ascii")
        return payload + f"{crc16(payload):04X}".encode("ascii") + b"\r\n"

    def send(self, command):
        if self.ser is None:
            raise ADPError("移液枪未连接")
        self.ser.reset_input_buffer()
        self.ser.write(self._frame(command))
        self.ser.flush()
        raw = self.ser.read_until(b"\n")
        if not raw.endswith(b"\n"):
            raise ADPError(f"等待移液枪响应超时，收到: {raw.hex(' ').upper() or '空'}")
        text = raw.decode("ascii", errors="replace").strip()
        if not text.startswith(">") or len(text) < 7:
            raise ADPError(f"移液枪响应格式错误: {text!r}")
        body, crc_text = text[:-4], text[-4:]
        try:
            valid = crc16(body.encode("ascii")) == int(crc_text, 16)
        except ValueError:
            valid = False
        if not valid:
            raise ADPError(f"移液枪响应 CRC 校验失败: {text!r}")
        self.last_status = body[4:6] if len(body) >= 6 else ""
        return body

    def _wait_done(self, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.03)
            status = self.send("d")[4:6]
            self.last_status = status
            if status == "01":
                return
            if status != "00":
                raise ADPError(f"移液枪状态异常: {status} ({STATE_TEXT.get(status, '未知')})")
        raise ADPError("等待移液枪动作完成超时")

    def _accepted(self, body, label):
        status = body[4:6]
        if status == "01":
            return
        if status == "00":
            raise ADPError(f"{label}被拒绝：设备正在运行")
        raise ADPError(f"{label}失败: {status} ({STATE_TEXT.get(status, '未知')})")

    def initialize(self):
        with self.lock:
            self.send("G")
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                time.sleep(0.03)
                status = self.send("g")[4:6]
                if status == "01":
                    self.initialized = True
                    self.air_done = False
                    self.aspirated = False
                    self.remaining_batches = 0
                    return self.info()
                if status not in ("00", "03"):
                    raise ADPError(f"初始化失败: {status} ({STATE_TEXT.get(status, '未知')})")
            raise ADPError("移液枪初始化超时")

    def check_tip(self):
        with self.lock:
            if not self.initialized:
                raise ADPError("请先初始化移液枪")
            status = self.send("q")[4:6]
            if status != "01":
                raise ADPError("未检测到 Tip，请先安装 Tip")
            return self.info()

    def action(self, name):
        with self.lock:
            if not self.initialized:
                raise ADPError("请先初始化移液枪")
            if name == "air":
                self.check_tip(); self.send("4%04X" % 500); self.send("B%04X" % 1000)
                self.send("M"); self._wait_done(); self.air_done = True
            elif name == "aspirate":
                if not self.air_done: raise ADPError("请先执行空气回吸")
                self.check_tip(); self._accepted(self.send("n%04X" % 600), "吸液"); self._wait_done()
                self.aspirated = True; self.remaining_batches = 3
            elif name == "tail":
                if not self.aspirated: raise ADPError("请先吸液")
                self._accepted(self.send("P"), "二次回吸"); self._wait_done()
            elif name == "dispense":
                if self.remaining_batches <= 0: raise ADPError("没有可排出的液体批次")
                self._accepted(self.send("p%04X" % 200), "排液"); self._wait_done(); self.remaining_batches -= 1
            elif name == "flush":
                self._accepted(self.send("p0000"), "排空"); self._wait_done(); self.remaining_batches = 0
            elif name == "status":
                self.send("d")
            else:
                raise ADPError(f"未知移液动作: {name}")
            self.last_error = None
            return self.info()


pipette = ADPPipette()
