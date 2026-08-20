# -*- coding: utf-8 -*-
"""大寰 PGI 系列电动夹爪 Modbus-RTU 驱动（RS485）。

通信：Modbus-RTU，从机地址 1，波特率 115200，8N1（出厂默认）。
寄存器（PGI 实测 + 手册）：
    命令寄存器 (写):  状态寄存器 (读):
    0x0100 初始化触发  0x0200 初始化状态(0/1/2)
    0x0101 力值(20-100)  0x0101 力值回显
    0x0102 速度(1-100)   —
    0x0103 位置(0-1000)  0x0202 当前位置
                        0x0204 运动/夹持状态

位置定义：0 = 全闭合（最小开口），1000 = 全张开（最大开口）
"""
import threading
import time

import minimalmodbus
import serial

# 命令寄存器（写）
REG_INIT_WRITE = 0x0100
REG_FORCE = 0x0101
REG_SPEED = 0x0102
REG_POS_WRITE = 0x0103

# 状态寄存器（读）
REG_INIT_READ = 0x0200
REG_POS_READ = 0x0202
REG_STATUS = 0x0204

# 参数范围
FORCE_MIN, FORCE_MAX = 20, 100
SPEED_MIN, SPEED_MAX = 1, 100
POSITION_MIN, POSITION_MAX = 0, 1000

# 默认通信参数
DEFAULT_SLAVE = 1
DEFAULT_BAUD = 115200

# 夹持状态
GRASP_MOVING, GRASP_DONE, GRASP_DETECTED = 0, 1, 2


def _clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))


class PGIGripper:
    def __init__(self, sim=False):
        self.sim = sim
        self.dev = None
        self.port = None
        self.slave = DEFAULT_SLAVE
        self.baud = DEFAULT_BAUD
        self.connected = False
        self.initialized = False
        self.lock = threading.Lock()
        # 模拟状态
        self._force = 30
        self._speed = 50
        self._pos = 0.0
        self._target = 0
        self._moving = False
        self._init_state = 0  # 0/1/2

    # ---------- 连接 ----------
    def connect(self, port, slave=DEFAULT_SLAVE, baud=DEFAULT_BAUD):
        with self.lock:
            if self.connected:
                return {"connected": True, "port": self.port, "sim": self.sim}
            if self.sim:
                self.port = port or "SIM"
                self.slave = slave
                self.baud = baud
                self.connected = True
                self._init_state = 0
                return {"connected": True, "port": self.port, "sim": True}
            if not port:
                raise ValueError("未指定串口")
            dev = minimalmodbus.Instrument(port, slave)
            dev.serial.baudrate = baud
            dev.serial.bytesize = 8
            dev.serial.parity = serial.PARITY_NONE
            dev.serial.stopbits = 1
            dev.serial.timeout = 0.5
            dev.mode = minimalmodbus.MODE_RTU
            self.dev = dev
            self.port = port
            self.slave = slave
            self.baud = baud
            self.connected = True
            self.initialized = False
            return {"connected": True, "port": port, "slave": slave, "baud": baud}

    def disconnect(self):
        with self.lock:
            if not self.connected:
                return {"connected": False}
            if not self.sim and self.dev:
                try:
                    self.dev.serial.close()
                except Exception:
                    pass
            self.connected = False
            self.initialized = False
            self.dev = None
            return {"connected": False}

    # ---------- 底层读写 ----------
    def _write(self, addr, value):
        self.dev.write_register(addr, value, functioncode=6)

    def _read(self, addr):
        return self.dev.read_register(addr, functioncode=3)

    # ---------- 初始化 ----------
    def initialize(self, wait=True, timeout=5.0):
        if not self.connected:
            raise RuntimeError("夹爪未连接")
        with self.lock:
            if self.sim:
                self._init_state = 1
            else:
                self._write(REG_INIT_WRITE, 1)
        # 等待初始化完成（读状态寄存器 0x0200）
        t0 = time.time()
        st = 0
        while time.time() - t0 < timeout:
            if self.sim:
                time.sleep(0.1)
                st = 2 if time.time() - t0 > 1.5 else 1
                with self.lock:
                    self._init_state = st
            else:
                with self.lock:
                    try:
                        st = self._read(REG_INIT_READ)
                    except Exception:
                        st = 0
            if st == 2:
                break
            if not wait:
                break
            time.sleep(0.1)
        self.initialized = st == 2
        return {"initialized": self.initialized, "state": st}

    # ---------- 参数设置 ----------
    def set_force(self, force):
        if not self.connected:
            raise RuntimeError("夹爪未连接")
        force = _clamp(force, FORCE_MIN, FORCE_MAX)
        with self.lock:
            if self.sim:
                self._force = force
            else:
                self._write(REG_FORCE, force)
        return {"force": force}

    def set_speed(self, speed):
        if not self.connected:
            raise RuntimeError("夹爪未连接")
        speed = _clamp(speed, SPEED_MIN, SPEED_MAX)
        with self.lock:
            if self.sim:
                self._speed = speed
            else:
                self._write(REG_SPEED, speed)
        return {"speed": speed}

    # ---------- 位置 / 开合 ----------
    def move_to(self, position, wait=True, timeout=10.0):
        if not self.connected:
            raise RuntimeError("夹爪未连接")
        position = _clamp(position, POSITION_MIN, POSITION_MAX)
        with self.lock:
            self._target = position
            self._moving = True
            if not self.sim:
                self._write(REG_POS_WRITE, position)
        # 等待到位（读 0x0202 位置 / 0x0204 状态）
        reached = None
        st = GRASP_MOVING
        if wait:
            t0 = time.time()
            last_pos = -1
            stable_count = 0
            while time.time() - t0 < timeout:
                if self.sim:
                    elapsed = time.time() - t0
                    dur = max(0.3, min(2.5, abs(position - self._pos) / max(self._speed, 1) * 0.5))
                    r = min(1.0, elapsed / dur) if dur > 0 else 1.0
                    with self.lock:
                        self._pos = self._pos + (position - self._pos) * r
                    if r >= 1.0:
                        with self.lock:
                            self._pos = float(position)
                            self._moving = False
                        st = GRASP_DONE
                        reached = True
                        break
                    time.sleep(0.05)
                else:
                    try:
                        pos = self._read(REG_POS_READ)
                    except Exception:
                        pos = last_pos
                    # 位置稳定判定：连续3次读数变化<2单位
                    if abs(pos - last_pos) < 2:
                        stable_count += 1
                    else:
                        stable_count = 0
                    last_pos = pos
                    # 到位条件：位置接近目标 或 位置稳定
                    if abs(pos - position) <= 10:
                        st = GRASP_DONE
                        reached = True
                        break
                    if stable_count >= 5 and abs(pos - position) <= 200:
                        st = GRASP_DONE
                        reached = True
                        break
                    time.sleep(0.1)
            if self.sim and reached is None:
                with self.lock:
                    self._pos = float(position)
                    self._moving = False
                st = GRASP_DONE
                reached = True
            if reached is None:
                # 超时但夹爪可能已到位：用最后位置判断
                if last_pos >= 0 and abs(last_pos - position) <= 200:
                    st = GRASP_DONE
                    reached = True
                else:
                    self._moving = False
                    reached = False
        return {"position": position, "reached": reached, "state": st}

    def open(self, wait=True):
        """张开夹爪：移动到最大位置(1000)，全开口"""
        return self.move_to(POSITION_MAX, wait=wait)

    def close(self, wait=True):
        """闭合夹爪：移动到最小位置(0)，全闭口"""
        return self.move_to(POSITION_MIN, wait=wait)

    # ---------- 状态 ----------
    def status(self):
        base = {"connected": self.connected, "sim": self.sim,
                "ranges": {"force": [FORCE_MIN, FORCE_MAX],
                           "speed": [SPEED_MIN, SPEED_MAX],
                           "position": [POSITION_MIN, POSITION_MAX]}}
        if not self.connected:
            base["initialized"] = False
            return base
        if self.sim:
            with self.lock:
                return {**base, "port": self.port,
                        "initialized": self._init_state == 2,
                        "init_state": self._init_state,
                        "force": self._force, "speed": self._speed,
                        "position": round(self._pos, 1), "target": self._target,
                        "moving": self._moving,
                        "grasp_state": GRASP_MOVING if self._moving else GRASP_DONE}
        with self.lock:
            try:
                init_st = self._read(REG_INIT_READ)
                cur_pos = self._read(REG_POS_READ)
                raw_st = self._read(REG_STATUS)
                force = self._read(REG_FORCE)
            except Exception as e:
                return {**base, "port": self.port, "initialized": self.initialized,
                        "error": str(e)}
        low2 = raw_st & 0x03
        moving = low2 == GRASP_MOVING
        return {**base, "port": self.port,
                "initialized": init_st == 2, "init_state": init_st,
                "force": force, "speed": None,
                "position": cur_pos, "moving": moving,
                "grasp_state": low2}
