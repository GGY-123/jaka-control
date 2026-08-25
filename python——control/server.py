# -*- coding: utf-8 -*-
import os
import json
import time
import math
import re
import signal
import subprocess
import sys
import threading
import datetime
import uuid
import traceback
from collections import deque
from typing import List, Optional

# The dashboard venv is intentionally lightweight; ROS2's generated actions use
# Ubuntu's system numpy package. Make it visible even when server.py is started manually.
SYSTEM_DIST_PACKAGES = "/usr/lib/python3/dist-packages"
if os.path.isdir(SYSTEM_DIST_PACKAGES) and SYSTEM_DIST_PACKAGES not in sys.path:
    sys.path.append(SYSTEM_DIST_PACKAGES)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from jaka_arm import JakaArm
from gripper import (
    PGIGripper, FORCE_MIN, FORCE_MAX, SPEED_MIN, SPEED_MAX,
    POSITION_MIN, POSITION_MAX, DEFAULT_SLAVE, DEFAULT_BAUD,
)
from pipette import pipette, ADPError

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
POINTS_FILE = os.path.join(DATA_DIR, "points.json")
FLOWS_FILE = os.path.join(DATA_DIR, "flows.json")
SIM = os.environ.get("JAKA_SIM", "0") == "1"
DEFAULT_IP = os.environ.get("JAKA_IP", "10.5.5.100")
# 夹爪：默认真实模式；若 GRIPPER_SIM=1 则强制仿真
GRIPPER_SIM = os.environ.get("GRIPPER_SIM", "0") == "1"
GRIPPER_PORT = os.environ.get("GRIPPER_PORT", "/dev/ttyUSB1")
GRIPPER_SLAVE = int(os.environ.get("GRIPPER_SLAVE", "1"))
GRIPPER_BAUD = int(os.environ.get("GRIPPER_BAUD", "115200"))
ZERG_ROOT = os.environ.get(
    "ZERG_ROOT",
    os.path.abspath(os.path.join(DATA_DIR, "..", "..", "ZERG-SDK")),
)
ZERG_INTERFACES_PYTHON = os.path.join(
    ZERG_ROOT, "install", "zerg_interfaces", "local", "lib", "python3.10", "dist-packages"
)
if os.path.isdir(ZERG_INTERFACES_PYTHON) and ZERG_INTERFACES_PYTHON not in sys.path:
    sys.path.append(ZERG_INTERFACES_PYTHON)

MOVE_TYPES = {"joint", "linear", "linear_z", "circular"}
COORD_BASE, COORD_JOINT, COORD_TOOL = 0, 1, 2
ABS, INCR = 0, 1
ORANGE_CAPPING_END_3_LINEAR_SPEED = 1.0
MANUAL_POINT_MOTION_PROFILES = {
    "p_abfac73e": {"move_type": "linear", "speed": ORANGE_CAPPING_END_3_LINEAR_SPEED},
    "p_1c109aae": {"move_type": "linear", "speed": ORANGE_CAPPING_END_3_LINEAR_SPEED},
}


# ---------------- 数据存储 ----------------
def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_points():
    return _load(POINTS_FILE, [])


def save_points(points):
    _save(POINTS_FILE, points)


def manual_motion_profile_for_target(target):
    points_by_id = {point["id"]: point for point in load_points()}
    for point_id, profile in MANUAL_POINT_MOTION_PROFILES.items():
        point = points_by_id.get(point_id)
        if point and any(
            len(target) == len(values)
            and all(math.isclose(actual, expected, abs_tol=1e-6) for actual, expected in zip(target, values))
            for values in (point["pose"], point["joints"])
        ):
            return point, profile
    return None, None


def load_flows():
    return _load(FLOWS_FILE, [])


def save_flows(flows):
    _save(FLOWS_FILE, flows)


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------- Pydantic 校验模型 ----------------
class ConnectReq(BaseModel):
    ip: str = Field(..., min_length=7)


class JogReq(BaseModel):
    axis: int = Field(0, ge=0, le=5)
    move_mode: int = Field(1, ge=0, le=2)
    coord: int = Field(0, ge=0, le=2)
    vel: float = Field(..., ge=-200, le=200)
    pos_cmd: float = 0.0


class MoveReq(BaseModel):
    move_type: str = Field("linear")
    target: List[float] = Field(..., min_length=6, max_length=6)
    move_mode: int = Field(0, ge=0, le=1)
    is_block: bool = True
    speed: float = Field(50, gt=0, le=500)
    acc: Optional[float] = None
    tol: Optional[float] = None
    mid_pos: Optional[List[float]] = Field(None, min_length=6, max_length=6)


class PointReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    note: str = ""
    pose: Optional[List[float]] = Field(None, min_length=6, max_length=6)
    joints: Optional[List[float]] = Field(None, min_length=6, max_length=6)


class PointUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=40)
    note: Optional[str] = None
    pose: Optional[List[float]] = Field(None, min_length=6, max_length=6)
    joints: Optional[List[float]] = Field(None, min_length=6, max_length=6)


class RenameReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)


class GripperAction(BaseModel):
    type: str = Field("none", pattern="^(none|initialize|open|close|move_to|set_force|set_speed)$")
    position: Optional[int] = Field(None, ge=POSITION_MIN, le=POSITION_MAX)
    force: Optional[int] = Field(None, ge=FORCE_MIN, le=FORCE_MAX)
    speed: Optional[int] = Field(None, ge=SPEED_MIN, le=SPEED_MAX)
    delay: float = Field(0.0, ge=0, le=30)


class FlowSegment(BaseModel):
    point_id: str
    move_type: str = Field("linear")
    speed: float = Field(50, gt=0, le=3000)
    acc: float = Field(100, gt=0, le=5000)
    tol: float = Field(0.1, ge=0, le=50)
    wait_after_arrival: float = Field(0.0, ge=0, le=60)
    gripper: Optional[GripperAction] = None


class FlowReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    segments: List[FlowSegment] = Field(..., min_length=1)
    note: str = ""


class FlowControlReq(BaseModel):
    action: str = Field(..., pattern="^(pause|resume|stop)$")


class CoordinationControlReq(BaseModel):
    action: str = Field(..., pattern="^(pause|resume|stop)$")


class PipetteConnectReq(BaseModel):
    port: Optional[str] = None
    address: str = Field("02", min_length=1, max_length=2)
    baudrate: int = Field(115200, ge=1200, le=921600)


class PipetteActionReq(BaseModel):
    action: str = Field(..., pattern="^(air|aspirate|tail|dispense|flush|status)$")


class GripperConnectReq(BaseModel):
    port: Optional[str] = None
    slave: int = Field(DEFAULT_SLAVE, ge=1, le=247)
    baud: int = Field(DEFAULT_BAUD, ge=1200, le=115200)


class GripperMoveReq(BaseModel):
    position: int = Field(..., ge=POSITION_MIN, le=POSITION_MAX)
    wait: bool = True
    timeout: float = Field(10.0, gt=0, le=30)


class GripperParamsReq(BaseModel):
    force: Optional[int] = Field(None, ge=FORCE_MIN, le=FORCE_MAX)
    speed: Optional[int] = Field(None, ge=SPEED_MIN, le=SPEED_MAX)


class GripperInitReq(BaseModel):
    wait: bool = True
    timeout: float = Field(5.0, gt=0, le=30)


class ZergEnableReq(BaseModel):
    enabled: bool


class ZergGripReq(BaseModel):
    speed_mm_s: float = Field(20.0, ge=1.0, le=100.0)
    current_a: float = Field(0.5, ge=0.1, le=0.5)


class ZergRotateReq(BaseModel):
    angle_deg: float = Field(..., ge=-36000.0, le=36000.0)
    speed_deg_s: float = Field(90.0, ge=1.0, le=1080.0)
    current_a: float = Field(0.5, ge=0.2, le=1.0)


# ---------------- 机械臂控制器（真机 / 模拟） ----------------
class Robot:
    def __init__(self):
        self.sim = SIM
        self.arm = None
        self.ip = None
        self.connected = False
        self.powered = False
        self.enabled = False
        self.lock = threading.Lock()
        # 模拟初始位姿
        self.sim_joints = [0.0, 1.57, 0.0, 1.57, 0.0, 0.0]
        self.sim_tcp = [0.0, 0.0, 400.0, math.pi, 0.0, 0.0]
        self.sim_motion = False
        self._abort = False

    # ---- 连接 ----
    def connect(self, ip):
        with self.lock:
            if self.connected:
                return {"connected": True, "ip": self.ip, "powered": self.powered, "enabled": self.enabled}
            if self.sim:
                self.ip = ip
                self.connected = True
                self.powered = False
                self.enabled = False
                return {"connected": True, "ip": ip, "sim": True, "powered": False, "enabled": False}
            self.arm = JakaArm(ip)
            self.ip = ip
            code = self.arm.login()[0]
            if code != 0:
                self.arm = None
                raise HTTPException(400, f"登录失败 code={code}")
            self.connected = True
            self.powered = False
            self.enabled = False
            return {"connected": True, "ip": ip, "powered": False, "enabled": False}

    def disconnect(self):
        with self.lock:
            if not self.connected:
                return {"connected": False}
            if not self.sim and self.arm:
                try:
                    if self.enabled:
                        self.arm.disable()
                    if self.powered:
                        self.arm.power_off()
                    self.arm.logout()
                except Exception:
                    pass
            self.connected = False
            self.powered = False
            self.enabled = False
            self.arm = None
            return {"connected": False}

    # ---- 电源 / 使能 ----
    def power_on(self):
        if not self.connected:
            raise HTTPException(400, "机械臂未连接")
        if self.powered:
            return {"powered": True, "enabled": self.enabled}
        if self.sim:
            self.powered = True
            return {"powered": True, "enabled": self.enabled}
        code = self.arm.power_on()[0]
        if code != 0:
            raise HTTPException(400, f"上电失败 code={code}")
        self.powered = True
        return {"powered": True, "enabled": self.enabled}

    def power_off(self):
        if not self.connected:
            raise HTTPException(400, "机械臂未连接")
        if not self.powered:
            return {"powered": False, "enabled": False}
        if self.sim:
            self.powered = False
            self.enabled = False
            return {"powered": False, "enabled": False}
        if self.enabled:
            self.arm.disable()
            self.enabled = False
        code = self.arm.power_off()[0]
        if code != 0:
            raise HTTPException(400, f"下电失败 code={code}")
        self.powered = False
        return {"powered": False, "enabled": False}

    def enable(self):
        if not self.connected:
            raise HTTPException(400, "机械臂未连接")
        if not self.powered:
            raise HTTPException(400, "请先上电")
        if self.enabled:
            return {"powered": True, "enabled": True}
        if self.sim:
            self.enabled = True
            return {"powered": True, "enabled": True}
        code = self.arm.enable()[0]
        if code != 0:
            raise HTTPException(400, f"使能失败 code={code}")
        self.enabled = True
        # 使能后设置全局速率为100%，解除可能的全局限速
        try:
            self.arm.set_rapidrate(1.0)
        except Exception as e:
            print(f"[警告] set_rapidrate(1.0) 失败: {e}")
        return {"powered": True, "enabled": True}

    def disable(self):
        if not self.connected:
            raise HTTPException(400, "机械臂未连接")
        if not self.enabled:
            return {"powered": self.powered, "enabled": False}
        if self.sim:
            self.enabled = False
            return {"powered": self.powered, "enabled": False}
        code = self.arm.disable()[0]
        if code != 0:
            raise HTTPException(400, f"失能失败 code={code}")
        self.enabled = False
        return {"powered": self.powered, "enabled": False}

    # ---- 状态 ----
    def status(self):
        if not self.connected:
            return {"connected": False, "sim": self.sim, "powered": False, "enabled": False}
        if self.sim:
            return {
                "connected": True, "sim": True, "ip": self.ip,
                "powered": self.powered, "enabled": self.enabled,
                "tcp": [round(v, 3) for v in self.sim_tcp],
                "joints": [round(v, 3) for v in self.sim_joints],
                "in_motion": self.sim_motion, "drag_mode": False,
            }
        arm = self.arm
        tcp = list(arm.get_tcp_position()[1]) if arm else [0] * 6
        joints = list(arm.get_joint_position()[1]) if arm else [0] * 6
        in_pos = arm.is_in_pos()[1] if arm else True
        drag = arm.is_in_drag_mode()[1] if arm else 0
        return {
            "connected": True, "sim": False, "ip": self.ip,
            "powered": self.powered, "enabled": self.enabled,
            "tcp": [round(v, 3) for v in tcp],
            "joints": [round(v, 3) for v in joints],
            "in_motion": not bool(in_pos), "drag_mode": bool(drag),
        }

    # ---- 手动 jog ----
    def jog(self, axis, move_mode, coord, vel, pos_cmd=0):
        if not self.connected:
            raise HTTPException(400, "机械臂未连接")
        if not self.enabled:
            raise HTTPException(400, "机械臂未使能")
        if self.sim:
            self.sim_motion = True
            self._sim_jog_step(axis, move_mode, coord, vel)
            return {"ok": True}
        self.arm.jog(axis, move_mode, coord, vel, pos_cmd)
        return {"ok": True}

    def jog_stop(self, joint_num=-1):
        if not self.connected:
            return {"ok": False}
        if self.sim:
            self.sim_motion = False
            return {"ok": True}
        self.arm.jog_stop(joint_num)
        return {"ok": True}

    # ---- 运动到目标 ----
    def move(self, move_type, target, move_mode=ABS, is_block=True,
             speed=50, acc=None, tol=None, mid_pos=None):
        if not self.connected:
            raise HTTPException(400, "机械臂未连接")
        if not self.enabled:
            raise HTTPException(400, "机械臂未使能")
        if move_type not in MOVE_TYPES:
            raise HTTPException(400, f"非法运动方式: {move_type}")
        if self.sim:
            self._sim_move(target, move_type, speed, is_block)
            return {"ok": True}
        if move_type == "joint":
            result = self.arm.joint_move(target, move_mode, is_block, speed)
        elif move_type == "linear":
            if acc is not None and tol is not None:
                result = self.arm.linear_move_extend(target, move_mode, is_block, speed, acc, tol)
            else:
                result = self.arm.linear_move(target, move_mode, is_block, speed)
        else:  # circular
            if mid_pos is None:
                raise HTTPException(400, "圆弧运动需要中间点 mid_pos")
            a = acc if acc is not None else 50
            t = tol if tol is not None else 0.1
            result = self.arm.circular_move(target, mid_pos, move_mode, is_block, speed, a, t)
        if not isinstance(result, (tuple, list)) or not result or result[0] != 0:
            raise RuntimeError(f"{move_type} SDK 返回失败: {result!r}")
        return {"ok": True}

    def motion_abort(self):
        if not self.connected:
            return {"ok": False}
        if self.sim:
            self._abort = True
            self.sim_motion = False
            return {"ok": True}
        self.arm.motion_abort()
        return {"ok": True}

    # ---- 模拟运动 ----
    def _sim_jog_step(self, axis, move_mode, coord, vel):
        step = vel * 0.2
        if coord == COORD_JOINT:
            self.sim_joints[axis] += step
        else:
            self.sim_tcp[axis] += step

    def _sim_move(self, target, move_type, speed, is_block):
        self.sim_motion = True
        self._abort = False
        if move_type == "joint":
            start = list(self.sim_joints)
            dur = min(5.0, max(0.2, max(abs(t - s) for t, s in zip(target, start)) / max(speed, 0.01)))
        else:
            start = list(self.sim_tcp)
            dist = math.sqrt(sum((target[i] - start[i]) ** 2 for i in range(3)))
            dur = min(5.0, max(0.2, dist / max(speed, 1)))
        steps = max(1, int(dur / 0.05))
        for i in range(1, steps + 1):
            if self._abort:
                break
            r = i / steps
            if move_type == "joint":
                self.sim_joints = [s + (t - s) * r for s, t in zip(start, target)]
            else:
                self.sim_tcp = [s + (t - s) * r for s, t in zip(start, target)]
            time.sleep(0.05)
        if not self._abort:
            if move_type == "joint":
                self.sim_joints = list(target)
            else:
                self.sim_tcp = list(target)
        self.sim_motion = False


# ---------------- 流程执行器 ----------------
class FlowRunner:
    def __init__(self, robot, gripper):
        self.robot = robot
        self.gripper = gripper
        self.status = "idle"  # idle / running / paused / stopped
        self.flow = None
        self.index = -1
        self.thread = None
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.stop_flag = False
        self.error = None

    def state(self):
        return {"status": self.status, "index": self.index,
                "flow_id": self.flow["id"] if self.flow else None,
                "segments": len(self.flow["segments"]) if self.flow else 0,
                "error": self.error}

    def run(self, flow):
        if self.status == "running":
            raise HTTPException(400, "已有流程在执行")
        self.flow = flow
        self.index = -1
        self.stop_flag = False
        self.error = None
        self.pause_event.set()
        self.status = "running"
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def control(self, action):
        if action == "pause":
            if self.status != "running":
                raise HTTPException(400, "流程未在运行")
            self.pause_event.clear()
            self.status = "paused"
        elif action == "resume":
            if self.status != "paused":
                raise HTTPException(400, "流程未暂停")
            self.pause_event.set()
            self.status = "running"
        elif action == "stop":
            if self.status not in ("running", "paused"):
                raise HTTPException(400, "流程未在执行")
            self.stop_flag = True
            self.pause_event.set()
            self.robot.motion_abort()
            self.status = "stopped"
        return self.state()

    def _worker(self):
        points = {p["id"]: p for p in load_points()}
        try:
            prev_pose = None
            for i, seg in enumerate(self.flow["segments"]):
                if self.stop_flag:
                    break
                self.index = i
                pt = points.get(seg["point_id"])
                if not pt:
                    continue
                target = pt.get("pose") or [0] * 6
                if seg["move_type"] == "circular":
                    mid = prev_pose if prev_pose else target
                    self.robot.move("circular", target, ABS, True,
                                    seg["speed"], seg["acc"], seg["tol"], mid_pos=mid)
                elif seg["move_type"] == "joint":
                    jt = pt.get("joints") or target
                    self.robot.move("joint", jt, ABS, True, min(seg["speed"], 3.14))
                elif seg["move_type"] == "linear_z":
                    current = list(self.robot.status().get("tcp") or target)
                    current[2] = target[2]
                    self.robot.move("linear", current, ABS, True,
                                    seg["speed"], seg["acc"], seg["tol"])
                else:
                    self.robot.move("linear", target, ABS, True,
                                    seg["speed"], seg["acc"], seg["tol"])
                prev_pose = target
                # 机械臂到位后等待指定时间（点位到达后等待）
                wait_arrival = seg.get("wait_after_arrival", 0)
                if wait_arrival and wait_arrival > 0:
                    print(f"[流程] 点位 {pt.get('name', '')} 到位，等待 {wait_arrival}s")
                    t0 = time.time()
                    while time.time() - t0 < wait_arrival:
                        if self.stop_flag:
                            break
                        # 暂停时阻塞等待 resume；恢复后重置 t0 以保证剩余等待时间完整
                        if not self.pause_event.is_set():
                            self.pause_event.wait()
                            t0 = time.time()
                        time.sleep(0.05)
                # 夹爪动作（带闭合状态验证）
                self._exec_gripper(seg.get("gripper"), seg)
                # 段间暂停点
                while not self.pause_event.is_set():
                    if self.stop_flag:
                        break
                    time.sleep(0.05)
        except Exception as e:
            point_name = "未知点位"
            try:
                point_name = points.get(
                    self.flow["segments"][self.index]["point_id"], {}
                ).get("name", point_name)
            except Exception:
                pass
            self.error = f"第 {self.index + 1} 步（{point_name}）失败: {e!r}"
            print(f"[流程错误] {self.error}", flush=True)
            traceback.print_exc()
            self.status = "stopped"
            self.flow = None
        finally:
            if self.status == "running":
                self.status = "idle"
            elif self.status == "stopped":
                self.status = "idle"
                self.flow = None

    def _exec_gripper(self, action_dict, seg=None):
        """执行单段夹爪动作（机械臂到位后调用），闭合/张开动作完成后验证夹爪状态。"""
        if not action_dict or action_dict.get("type", "none") == "none":
            return
        g = self.gripper
        if not g.connected:
            raise HTTPException(400, "夹爪未连接，无法执行流程中的夹爪动作")
        action = GripperAction(**action_dict)
        if action.force is not None:
            g.set_force(action.force)
        if action.speed is not None:
            g.set_speed(action.speed)
        t = action.type
        executed_action = None
        if t == "initialize":
            g.initialize(wait=True, timeout=5.0)
            executed_action = "initialize"
        elif t == "open":
            g.open(wait=True)
            executed_action = "open"
        elif t == "close":
            g.close(wait=True)
            executed_action = "close"
        elif t == "move_to":
            if action.position is None:
                raise HTTPException(400, "夹爪 move_to 动作未指定 position")
            g.move_to(action.position, wait=True)
            executed_action = "move_to"
        elif t in ("set_force", "set_speed"):
            pass
        # 动作后延时（满足时序要求）
        if action.delay and action.delay > 0:
            time.sleep(action.delay)
        # 闭合/张开动作完成后验证夹爪状态，防止未完全到位就移动
        if executed_action in ("close", "open", "move_to"):
            self._verify_gripper_settled(executed_action, action, timeout=3.0)

    def _verify_gripper_settled(self, action_type, action, timeout=3.0):
        """验证夹爪已完全到位（非运动中），否则等待。"""
        g = self.gripper
        t0 = time.time()
        while time.time() - t0 < timeout:
            st = g.status()
            if not st.get("moving"):
                pos = st.get("position", 0)
                force = st.get("force", 0)
                print(f"[夹爪] {action_type} 已稳定: position={pos}, force={force}")
                return
            time.sleep(0.1)
        print(f"[夹爪] {action_type} 等待超时({timeout}s)，继续执行")


class ZergSdkBridge:
    """Direct Z-ERG-20C control. No ROS2 node, service, or Action is involved."""

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.sdk_source = os.path.join(self.root, "zerg_sdk")
        self.port = os.environ.get(
        "ZERG_PORT", 
        "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
        )
        self.baudrate = int(os.environ.get("ZERG_BAUD", "115200"))
        self.slave_id = int(os.environ.get("ZERG_SLAVE", "1"))
        self.timeout = float(os.environ.get("ZERG_SERIAL_TIMEOUT", "1.0"))
        self._gripper = None
        self._error = None
        self._logs = deque(maxlen=80)
        self._connected_at = None
        self._lock = threading.RLock()

    def _sdk(self):
        if not os.path.isfile(os.path.join(self.sdk_source, "zerg_sdk", "__init__.py")):
            raise RuntimeError(f"ZERG Python SDK not found: {self.sdk_source}")
        if self.sdk_source not in sys.path:
            sys.path.insert(0, self.sdk_source)
        from zerg_sdk import ByteOrder, ZergGripper
        return ByteOrder, ZergGripper

    def _connect(self):
        if self._gripper is not None:
            return self._gripper
        byte_order, gripper_class = self._sdk()
        self._gripper = gripper_class.open(
            self.port,
            baudrate=self.baudrate,
            slave_id=self.slave_id,
            timeout=self.timeout,
            byte_order=byte_order.BIG,
        )
        self._connected_at = _now()
        self._error = None
        self._logs.append(
            f"Direct SDK connected: {self.port} @ {self.baudrate}, id={self.slave_id}, timeout={self.timeout}s"
        )
        return self._gripper

    def _disconnect(self):
        if self._gripper is not None:
            try:
                self._gripper.close()
            finally:
                self._gripper = None
        self._connected_at = None

    def status(self):
        sdk_ok = os.path.isfile(os.path.join(self.sdk_source, "zerg_sdk", "__init__.py"))
        connected = self._gripper is not None
        return {
            "environment_ok": sdk_ok,
            "workspace": f"Direct SDK: {self.port} @ {self.baudrate}, id={self.slave_id}",
            "driver_managed": connected,
            "driver_running": connected,
            "actions": {"open": connected, "close": connected, "rotate": connected},
            "ready": connected,
            "error": self._error,
            "logs": list(self._logs)[-20:],
            "started_at": self._connected_at,
        }

    def start_driver(self):
        with self._lock:
            try:
                self._connect()
                return {**self.status(), "message": "ZERG 已通过直接 SDK 连接"}
            except Exception as exc:
                self._error = str(exc)
                self._logs.append(f"Connect failed: {exc}")
                raise RuntimeError(self._error) from exc

    def stop_driver(self):
        with self._lock:
            self._disconnect()
            self._logs.append("Direct SDK serial connection closed")
            return {**self.status(), "message": "ZERG 串口已断开"}

    def initialize(self):
        return self._call("initialize", lambda gripper: gripper.initialize())

    def enable(self, enabled):
        label = "enable" if enabled else "disable"
        return self._call(label, lambda gripper: gripper.enable_motor(enabled))

    def action(self, action, speed=None, current=None, angle=None):
        if action == "open":
            return self._call(action, lambda g: g.command_grip(20.0, speed, current))
        if action == "close":
            return self._call(action, lambda g: g.command_grip(0.0, speed, current))
        if action == "rotate":
            return self._call(
                action,
                lambda g: g.command_rotation(angle, relative=True, speed_deg_s=speed, current_a=current),
            )
        raise RuntimeError(f"Unknown ZERG SDK action: {action}")

    def _call(self, label, callback):
        with self._lock:
            try:
                callback(self._connect())
                message = f"Direct SDK command accepted: {label}"
                self._error = None
                self._logs.append(message)
                return {"ok": True, "action": label, "output": message}
            except Exception as exc:
                self._error = str(exc)
                self._logs.append(f"{label} failed: {exc}")
                self._disconnect()
                raise RuntimeError(self._error) from exc


class ZergRosBridge:
    """Z-ERG-20C control through the ROS2 driver, Service, and Actions."""

    ACTIONS = {
        "open": ("/zerg_driver/open", "zerg_interfaces/action/OpenGripper"),
        "close": ("/zerg_driver/close", "zerg_interfaces/action/CloseGripper"),
        "rotate": ("/zerg_driver/rotate", "zerg_interfaces/action/RotateMotor"),
    }

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.install_setup = os.path.join(self.root, "install", "setup.bash")
        self.port = os.environ.get(
        "ZERG_PORT", 
        "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
        )
        self.baudrate = int(os.environ.get("ZERG_BAUD", "115200"))
        self.slave_id = int(os.environ.get("ZERG_SLAVE", "1"))
        self._env = None
        self._driver = None
        self._started_at = None
        self._logs = deque(maxlen=80)
        self._lock = threading.RLock()
        self._node = None
        self._executor = None
        self._action_clients = {}
        self._service_clients = {}
        self._client_error = None

    def _ensure_clients(self):
        """Keep one ROS node alive so button clicks do not rediscover ROS graph."""
        if self._node is not None:
            return
        try:
            import rclpy
            from rclpy.action import ActionClient
            from rclpy.executors import MultiThreadedExecutor
            from std_srvs.srv import SetBool, Trigger
            from zerg_interfaces.action import CloseGripper, OpenGripper, RotateMotor

            if not rclpy.ok():
                rclpy.init(args=None)
            self._node = rclpy.create_node("dashboard_zerg_action_client")
            self._executor = MultiThreadedExecutor(num_threads=2)
            self._executor.add_node(self._node)
            self._action_clients = {
                "open": ActionClient(self._node, OpenGripper, "/zerg_driver/open"),
                "close": ActionClient(self._node, CloseGripper, "/zerg_driver/close"),
                "rotate": ActionClient(self._node, RotateMotor, "/zerg_driver/rotate"),
            }
            self._service_clients = {
                "/zerg_driver/initialize": (Trigger, self._node.create_client(Trigger, "/zerg_driver/initialize")),
                "/zerg_driver/enable": (SetBool, self._node.create_client(SetBool, "/zerg_driver/enable")),
            }
            threading.Thread(target=self._executor.spin, daemon=True).start()
            self._logs.append("Persistent ROS2 ActionClient started")
        except Exception as exc:
            if self._executor is not None:
                self._executor.shutdown()
            if self._node is not None:
                self._node.destroy_node()
            self._node = None
            self._executor = None
            self._action_clients = {}
            self._service_clients = {}
            self._client_error = str(exc)
            self._logs.append(f"Persistent ROS2 client unavailable: {exc}")
            raise RuntimeError(f"ROS2 客户端加载失败: {exc}") from exc

    @staticmethod
    def _wait_future(future, timeout):
        done = threading.Event()
        future.add_done_callback(lambda _future: done.set())
        if not done.wait(timeout):
            raise RuntimeError("ROS2 请求超时")
        return future.result()

    def _ros_env(self):
        if self._env is not None:
            return self._env
        if not os.path.isfile(self.install_setup):
            raise RuntimeError(f"ZERG ROS 工作区未编译: {self.install_setup}")
        command = (
            "source /opt/ros/humble/setup.bash && "
            f"source {self.install_setup!r} && env -0"
        )
        result = subprocess.run(
            ["bash", "-lc", command], capture_output=True, timeout=8, check=False
        )
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"加载 ROS2 环境失败: {message}")
        env = os.environ.copy()
        for item in result.stdout.split(b"\0"):
            if b"=" in item:
                key, value = item.split(b"=", 1)
                env[key.decode(errors="replace")] = value.decode(errors="replace")
        sdk_source = os.path.join(self.root, "zerg_sdk")
        env["PYTHONPATH"] = sdk_source + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
        self._env = env
        return env

    def _run(self, args, timeout=8):
        try:
            return subprocess.run(
                args, cwd=self.root, env=self._ros_env(), capture_output=True,
                text=True, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            def as_text(value):
                return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")
            raise RuntimeError(f"ROS2 命令超时: {(as_text(exc.stdout) + as_text(exc.stderr)).strip()}") from exc

    def _actions(self):
        result = self._run(["ros2", "action", "list", "-t"], timeout=4)
        if result.returncode != 0:
            return {}, (result.stderr or result.stdout).strip()
        available = {}
        for line in result.stdout.splitlines():
            match = re.match(r"^(\S+)\s+\[(.+)]$", line.strip())
            if match:
                available[match.group(1)] = match.group(2)
        return available, ""

    def status(self):
        if self._driver is not None and self._driver.poll() is not None:
            self._driver = None
            self._started_at = None
        try:
            self._ensure_clients()
            actions = {name: client.server_is_ready() for name, client in self._action_clients.items()}
            error, environment_ok = self._client_error, True
        except Exception as exc:
            actions = {name: False for name in self.ACTIONS}
            error, environment_ok = str(exc), False
        return {
            "environment_ok": environment_ok,
            "workspace": f"ROS2: {self.port} @ {self.baudrate}, id={self.slave_id}",
            "driver_managed": self._driver is not None,
            "driver_running": self._driver is not None or any(actions.values()),
            "actions": actions,
            "ready": all(actions.values()),
            "error": error or None,
            "logs": list(self._logs)[-20:],
            "started_at": self._started_at,
        }

    def _read_driver_output(self, process):
        if process.stdout is not None:
            for line in process.stdout:
                self._logs.append(line.rstrip())

    def start_driver(self):
        with self._lock:
            current = self.status()
            if current["ready"]:
                return {**current, "message": "ZERG ROS 驱动已运行"}
            if self._driver is not None:
                return {**current, "message": "ZERG ROS 驱动正在启动"}
            command = [
                "ros2", "run", "zerg_ros2_driver", "zerg_driver", "--ros-args",
                "-p", f"port:={self.port}", "-p", f"baudrate:={self.baudrate}",
                "-p", f"slave_id:={self.slave_id}",
            ]
            self._logs.clear()
            self._driver = subprocess.Popen(
                command, cwd=self.root, env=self._ros_env(), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, start_new_session=True, bufsize=1,
            )
            self._started_at = _now()
            threading.Thread(target=self._read_driver_output, args=(self._driver,), daemon=True).start()
            return {**self.status(), "message": "ZERG ROS 驱动启动命令已发送"}

    def stop_driver(self):
        with self._lock:
            if self._driver is None:
                return {**self.status(), "message": "驱动不是由本页面启动，未停止外部进程"}
            try:
                os.killpg(self._driver.pid, signal.SIGINT)
                self._driver.wait(timeout=6)
            except subprocess.TimeoutExpired:
                os.killpg(self._driver.pid, signal.SIGTERM)
            finally:
                self._driver = None
                self._started_at = None
            return {**self.status(), "message": "ZERG ROS 驱动已停止"}

    def cleanup_stale_drivers(self):
        """Stop only stale ZERG ROS driver processes started by this user."""
        with self._lock:
            if self._driver is not None:
                raise RuntimeError("请先停止本页面管理的驱动")
            result = subprocess.run(
                ["ps", "-u", str(os.getuid()), "-o", "pid=,args="],
                capture_output=True, text=True, check=False,
            )
            pids = []
            for line in result.stdout.splitlines():
                fields = line.strip().split(maxsplit=1)
                if len(fields) != 2:
                    continue
                pid_text, args = fields
                if "zerg_ros2_driver" in args and "zerg_driver" in args:
                    try:
                        pids.append(int(pid_text))
                    except ValueError:
                        pass
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
            if pids:
                time.sleep(1.0)
            self._logs.append(f"Cleaned stale ZERG driver PIDs: {pids or 'none'}")
            return {**self.status(), "message": f"已清理旧 ZERG 驱动：{len(pids)} 个"}

    def service(self, service_name, service_type, request):
        with self._lock:
            self._ensure_clients()
            entry = self._service_clients.get(service_name)
            if entry is None:
                raise RuntimeError(f"未配置 ROS2 Service: {service_name}")
            service_class, client = entry
            if not client.service_is_ready() and not client.wait_for_service(timeout_sec=1.0):
                raise RuntimeError(f"Service 不可用: {service_name}")
            message = service_class.Request()
            if service_name == "/zerg_driver/enable":
                message.data = "true" in request.lower()
            response = self._wait_future(client.call_async(message), 8.0)
            output = f"success={response.success}; message={response.message}"
            if not response.success:
                raise RuntimeError(output)
            return {"ok": True, "output": output}

    def action(self, action, goal, timeout):
        with self._lock:
            self._ensure_clients()
            client = self._action_clients.get(action)
            if client is None:
                raise RuntimeError(f"未知 ZERG Action: {action}")
            if not client.server_is_ready() and not client.wait_for_server(timeout_sec=1.0):
                raise RuntimeError("ZERG Action Server 不可用")
            if action in ("open", "close"):
                from zerg_interfaces.action import CloseGripper, OpenGripper
                goal_msg = OpenGripper.Goal() if action == "open" else CloseGripper.Goal()
                goal_msg.speed_mm_s = float(re.search(r"speed_mm_s:\s*([0-9.]+)", goal).group(1))
                goal_msg.current_a = float(re.search(r"current_a:\s*([0-9.]+)", goal).group(1))
            else:
                from zerg_interfaces.action import RotateMotor
                goal_msg = RotateMotor.Goal()
                goal_msg.angle_deg = float(re.search(r"angle_deg:\s*(-?[0-9.]+)", goal).group(1))
                goal_msg.speed_deg_s = float(re.search(r"speed_deg_s:\s*([0-9.]+)", goal).group(1))
                goal_msg.current_a = float(re.search(r"current_a:\s*([0-9.]+)", goal).group(1))
            handle = self._wait_future(client.send_goal_async(goal_msg), 3.0)
            if not handle.accepted:
                raise RuntimeError("ZERG Action Goal 被拒绝")
            result = self._wait_future(handle.get_result_async(), timeout).result
            output = f"success={result.success}; message={result.message}"
            if not result.success:
                raise RuntimeError(output)
            return {"ok": True, "action": action, "output": output}


class CoordinatedWorkflowRunner:
    """Strictly serial A5 + Mini + ZERG sequence for the recorded tube workflow."""

    A5_IP = os.environ.get("COORD_A5_IP", "192.168.1.102")
    MINI_IP = os.environ.get("COORD_MINI_IP", "192.168.1.103")

    def __init__(self, a5, end_gripper, zerg_bridge):
        self.a5 = a5
        self.end_gripper = end_gripper
        self.zerg = zerg_bridge
        self.status = "idle"
        self.index = -1
        self.current_step = ""
        self.error = None
        self.logs = deque(maxlen=120)
        self.thread = None
        self.stop_flag = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.mini_arm = None
        self._lock = threading.RLock()

    def state(self):
        return {
            "status": self.status,
            "index": self.index,
            "steps": len(self._steps()),
            "current_step": self.current_step,
            "error": self.error,
            "logs": list(self.logs)[-30:],
            "a5_ip": self.A5_IP,
            "mini_ip": self.MINI_IP,
        }

    def _steps(self):
        return [
            "A5：夹取点", "末端夹爪：闭合", "A5：夹取点上方",
            "A5：过渡点1", "A5：过渡点2", "旋转夹爪：张开",
            "A5：旋转夹爪上方", "旋转夹爪：闭合（0.5 A）", "A5：拔盖点",
            "A5：旋转夹爪上方向后移动", "JAKA Mini：八段试管流程",
            "A5：过渡点1", "A5：过渡点2", "A5：旋转夹爪上方",
            "旋转夹爪：逆时针 360 度", "旋转夹爪：张开", "A5：紫色终点上方",
            "A5：紫色终点", "A5：过渡点1", "A5：橙色试管1夹取点上方",
            "A5：橙色试管1夹取点", "末端夹爪：闭合（速度25）",
            "A5：橙色试管1夹取点上方", "A5：旋转夹爪上方", "A5：旋转夹爪中",
            "旋转夹爪：闭合（0.5 A）", "末端夹爪：张开", "A5：旋转夹爪上方",
            "A5：橙色盖1上方", "A5：橙色盖1", "末端夹爪：闭合",
            "A5：橙色盖1上方", "A5：旋转夹爪上方", "A5：盖盖子过渡",
            "A5：橙色盖到试管上（慢）", "A5：TCP RZ 顺时针 90 度",
            "旋转夹爪：逆时针 360 度", "旋转夹爪：张开", "A5：旋转夹爪上方",
            "A5：试管盒终点1上方", "A5：试管盒终点1（慢）", "末端夹爪：张开",
            "A5：试管盒终点1上方", "A5：过渡点1",
        ]

    def start(self):
        with self._lock:
            if self.status in ("running", "paused"):
                raise HTTPException(400, "协同流程正在执行")
            if not self.a5.connected or self.a5.ip != self.A5_IP:
                raise HTTPException(400, f"请先连接并使能 A5（{self.A5_IP}）")
            if not self.a5.powered or not self.a5.enabled:
                raise HTTPException(400, "A5 必须已上电并使能")
            if not self.end_gripper.connected or not self.end_gripper.initialized:
                raise HTTPException(400, "末端夹爪必须已连接并初始化")
            if not self.zerg.status().get("ready"):
                raise HTTPException(400, "旋转夹爪 ROS2 Action 未就绪；请先启动、初始化并启用电机")
            self.index = -1
            self.current_step = ""
            self.error = None
            self.logs.clear()
            self.stop_flag = False
            self.pause_event.set()
            self.status = "running"
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
            return self.state()

    def control(self, action):
        with self._lock:
            if action == "pause":
                if self.status != "running":
                    raise HTTPException(400, "协同流程未在运行")
                self.pause_event.clear()
                self.status = "paused"
            elif action == "resume":
                if self.status != "paused":
                    raise HTTPException(400, "协同流程未暂停")
                self.pause_event.set()
                self.status = "running"
            elif action == "stop":
                if self.status not in ("running", "paused"):
                    raise HTTPException(400, "协同流程未在执行")
                self.stop_flag = True
                self.pause_event.set()
                self.a5.motion_abort()
                if self.mini_arm is not None:
                    try:
                        self.mini_arm.motion_abort()
                    except Exception:
                        pass
                self.status = "stopped"
            return self.state()

    def _checkpoint(self, label):
        if self.stop_flag:
            raise RuntimeError("流程已停止")
        while not self.pause_event.is_set():
            if self.stop_flag:
                raise RuntimeError("流程已停止")
            time.sleep(0.05)
        self.index += 1
        self.current_step = label
        self.logs.append(f"[{self.index + 1}/{len(self._steps())}] {label}")
        print(f"[协同流程] {self.logs[-1]}", flush=True)

    @staticmethod
    def _require_ok(label, result):
        if not isinstance(result, (tuple, list)) or not result or result[0] != 0:
            raise RuntimeError(f"{label} SDK 返回失败: {result!r}")

    def _point(self, point_id):
        point = next((p for p in load_points() if p["id"] == point_id), None)
        if point is None:
            raise RuntimeError(f"缺少点位: {point_id}")
        return point

    def _a5_move(self, point_id, move_type, speed, acc=100.0, tol=0.1):
        point = self._point(point_id)
        target = point["joints"] if move_type == "joint" else point["pose"]
        self.a5.move(move_type, target, ABS, True, speed, acc, tol)
        # The SDK's blocking flag only waits for command acceptance on some
        # controller versions. Confirm the controller reports in-position
        # before allowing a gripper or the next robot to act.
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if self.stop_flag:
                raise RuntimeError("流程已停止")
            if not self.a5.status().get("in_motion", False):
                time.sleep(0.15)
                if not self.a5.status().get("in_motion", False):
                    return
            time.sleep(0.05)
        raise RuntimeError(f"A5 点位 {self._point(point_id).get('name', point_id)} 到位确认超时")

    def _end_gripper(self, action, *, speed=None):
        if speed is not None:
            self.end_gripper.set_speed(speed)
        if action == "open":
            self.end_gripper.open(wait=True)
        else:
            self.end_gripper.close(wait=True)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self.stop_flag:
                raise RuntimeError("流程已停止")
            if not self.end_gripper.status().get("moving"):
                return
            time.sleep(0.1)
        raise RuntimeError(f"末端夹爪{action}等待超时")

    def _zerg_action(self, action, *, speed, current, angle=None):
        if action == "rotate":
            goal = f"{{angle_deg: {angle}, speed_deg_s: {speed}, current_a: {current}}}"
            timeout = min(180.0, max(25.0, abs(angle) / speed + 10.0))
        else:
            goal = f"{{speed_mm_s: {speed}, current_a: {current}}}"
            timeout = 25.0
        self.zerg.action(action, goal, timeout)

    def _mini_flow(self):
        mini = JakaArm(self.MINI_IP)
        self.mini_arm = mini
        logged_in = False
        try:
            self._require_ok("Mini 登录", mini.login())
            logged_in = True
            self._require_ok("Mini 上电", mini.power_on())
            self._require_ok("Mini 使能", mini.enable())
            mini_steps = [
                ("jaka_home", "joint", math.radians(10)),
                ("jaka_tube_above", "joint", math.radians(10)),
                ("jaka_tube_lower", "linear_z", 30.0),
                ("jaka_tube_above", "linear_z", 30.0),
                ("jaka_point_4", "joint", math.radians(10)),
                ("jaka_point_5", "joint", math.radians(10)),
                ("jaka_point_6", "joint", math.radians(10)),
                ("jaka_home", "joint", math.radians(10)),
            ]
            for point_id, motion, speed in mini_steps:
                if self.stop_flag:
                    raise RuntimeError("流程已停止")
                point = self._point(point_id)
                if motion == "joint":
                    self._require_ok("Mini 关节运动", mini.joint_move(point["joints"], ABS, True, speed))
                else:
                    result = mini.get_actual_tcp_position()
                    current = list(result[1]) if result and result[0] == 0 else list(mini.get_tcp_position()[1])
                    current[2] = point["pose"][2]
                    self._require_ok("Mini Z 直线运动", mini.linear_move_extend(current, ABS, True, speed, 100.0, 0.1))
                time.sleep(1.0)
        finally:
            self.mini_arm = None
            if logged_in:
                try:
                    mini.logout()
                except Exception:
                    pass

    def _a5_rotate_rz_clockwise_90(self):
        status = self.a5.status()
        pose = list(status.get("tcp") or [])
        if len(pose) != 6:
            raise RuntimeError("无法读取 A5 当前 TCP 位姿")
        pose[5] += math.pi / 2
        self.a5.move("linear", pose, ABS, True, 15.0, 50.0, 0.1)

    def _worker(self):
        try:
            self._checkpoint("A5：夹取点")
            self._a5_move("p_d7b19939", "linear", 30.0)
            self._checkpoint("末端夹爪：闭合")
            self._end_gripper("close")
            # Let the gripper establish a stable hold before lifting the tube.
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                if self.stop_flag:
                    raise RuntimeError("流程已停止")
                time.sleep(0.05)
            self._checkpoint("A5：夹取点上方")
            self._a5_move("p_0d029508", "linear", 30.0)
            self._checkpoint("A5：过渡点1")
            self._a5_move("p_5d256a0d", "joint", 0.5)
            self._checkpoint("A5：过渡点2")
            self._a5_move("p_5f102e2f", "joint", 0.5)
            self._checkpoint("旋转夹爪：张开")
            self._zerg_action("open", speed=20.0, current=0.5)
            self._checkpoint("A5：旋转夹爪上方")
            self._a5_move("p_6d9b3168", "joint", 0.5)
            self._checkpoint("旋转夹爪：闭合（0.5 A）")
            self._zerg_action("close", speed=20.0, current=0.5)
            self._checkpoint("A5：拔盖点")
            self._a5_move("p_b1a776de", "linear", 20.0)
            self._checkpoint("A5：旋转夹爪上方向后移动")
            self._a5_move("p_c181a223", "joint", 0.5)
            self._checkpoint("JAKA Mini：八段试管流程")
            self._mini_flow()
            self._checkpoint("A5：过渡点1")
            self._a5_move("p_5d256a0d", "joint", 0.5)
            self._checkpoint("A5：过渡点2")
            self._a5_move("p_5f102e2f", "joint", 0.5)
            self._checkpoint("A5：旋转夹爪上方")
            self._a5_move("p_6d9b3168", "joint", 0.5)
            self._checkpoint("旋转夹爪：逆时针 360 度")
            self._zerg_action("rotate", angle=-360.0, speed=90.0, current=0.5)
            self._checkpoint("旋转夹爪：张开")
            self._zerg_action("open", speed=20.0, current=0.5)
            self._checkpoint("A5：紫色终点上方")
            self._a5_move("p_6f434a73", "joint", 0.5)
            self._checkpoint("A5：紫色终点")
            self._a5_move("p_59352ab4", "linear", 20.0)
            self._checkpoint("A5：过渡点1")
            self._a5_move("p_5d256a0d", "joint", 0.5)
            self._checkpoint("A5：橙色试管1夹取点上方")
            self._a5_move("p_e0c000b2", "joint", 0.5)
            self._checkpoint("A5：橙色试管1夹取点")
            self._a5_move("p_fb790c15", "linear", 20.0)
            self._checkpoint("末端夹爪：闭合（速度25）")
            self._end_gripper("close", speed=25)
            self._checkpoint("A5：橙色试管1夹取点上方")
            self._a5_move("p_e0c000b2", "linear", 20.0)
            self._checkpoint("A5：旋转夹爪上方")
            self._a5_move("p_6d9b3168", "joint", 0.5)
            self._checkpoint("A5：旋转夹爪中")
            self._a5_move("p_fe0a2411", "linear", 20.0)
            self._checkpoint("旋转夹爪：闭合（0.5 A）")
            self._zerg_action("close", speed=20.0, current=0.5)
            self._checkpoint("末端夹爪：张开")
            self._end_gripper("open")
            self._checkpoint("A5：旋转夹爪上方")
            self._a5_move("p_6d9b3168", "linear", 20.0)
            self._checkpoint("A5：橙色盖1上方")
            self._a5_move("p_7a28748a", "joint", 0.5)
            self._checkpoint("A5：橙色盖1")
            self._a5_move("p_a1e054a5", "linear", 20.0)
            self._checkpoint("末端夹爪：闭合")
            self._end_gripper("close")
            self._checkpoint("A5：橙色盖1上方")
            self._a5_move("p_7a28748a", "linear", 20.0)
            self._checkpoint("A5：旋转夹爪上方")
            self._a5_move("p_6d9b3168", "joint", 0.5)
            self._checkpoint("A5：盖盖子过渡")
            self._a5_move("p_42b73120", "joint", 0.5)
            self._checkpoint("A5：橙色盖到试管上（慢）")
            self._a5_move("p_727c42d6", "linear", 15.0)
            self._checkpoint("A5：TCP RZ 顺时针 90 度")
            self._a5_rotate_rz_clockwise_90()
            self._checkpoint("旋转夹爪：逆时针 360 度")
            self._zerg_action("rotate", angle=-360.0, speed=90.0, current=0.5)
            self._checkpoint("旋转夹爪：张开")
            self._zerg_action("open", speed=20.0, current=0.5)
            self._checkpoint("A5：旋转夹爪上方")
            self._a5_move("p_6d9b3168", "joint", 0.5)
            self._checkpoint("A5：试管盒终点1上方")
            self._a5_move("p_6c52108f", "joint", 0.5)
            self._checkpoint("A5：试管盒终点1（慢）")
            self._a5_move("p_bb3339b4", "linear", 20.0)
            self._checkpoint("末端夹爪：张开")
            self._end_gripper("open")
            self._checkpoint("A5：试管盒终点1上方")
            self._a5_move("p_6c52108f", "linear", 20.0)
            self._checkpoint("A5：过渡点1")
            self._a5_move("p_5d256a0d", "joint", 0.5)
            self.logs.append("协同流程完成")
        except Exception as exc:
            if not self.stop_flag:
                self.error = f"第 {self.index + 1} 步（{self.current_step or '准备'}）失败: {exc!r}"
                self.logs.append(self.error)
                traceback.print_exc()
            self.a5.motion_abort()
        finally:
            self.mini_arm = None
            self.status = "idle"


class TransferSubflowRunner:
    """独立的取液子流程；不修改已保存的普通流程和 44 步协同流程。"""

    A5_IP = os.environ.get("COORD_A5_IP", "192.168.1.102")
    MINI_IP = os.environ.get("COORD_MINI_IP", "192.168.1.103")

    def __init__(self, a5, end_gripper, zerg_bridge, pipette_device):
        self.a5 = a5
        self.end_gripper = end_gripper
        self.zerg = zerg_bridge
        self.pipette = pipette_device
        self.status = "idle"
        self.index = -1
        self.current_step = ""
        self.error = None
        self.logs = deque(maxlen=100)
        self.thread = None
        self.stop_flag = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.mini_arm = None
        self._lock = threading.RLock()

    def _steps(self):
        return [
            "A5：夹取点上方", "A5：夹取点", "等待 1 秒", "末端夹爪：闭合",
            "A5：过渡点1", "A5：过渡点2", "A5：旋转夹爪上方",
            "A5：旋转夹爪夹取点", "旋转夹爪：闭合（0.5 A）",
            "A5：旋转夹爪上方", "A5：旋转夹爪上方向后移动",
            "JAKA Mini：Home", "JAKA Mini：试管上方", "等待 1 秒",
            "JAKA Mini：试管下方", "移液枪：吸液 600 uL", "JAKA Mini：试管上方",
            "JAKA Mini：Home",
            "A5：旋转夹爪上方", "A5：紫色放盖点（慢）", "旋转夹爪：张开", "A5：旋转夹爪上方",
            "A5：紫色终点上方", "A5：紫色终点", "末端夹爪：张开", "A5：紫色终点上方",
            "A5：夹取点上方",
        ]

    def used_point_ids(self):
        return {
            "p_0d029508", "p_d7b19939", "p_5d256a0d", "p_5f102e2f", "p_ed5f1653", "p_6d9b3168", "p_c181a223", "p_897b6cb2",
            "jaka_home", "jaka_tube_above", "jaka_tube_lower", "jaka_point_4", "jaka_point_5", "jaka_point_6",
            "p_6f434a73", "p_59352ab4",
        }

    def state(self):
        return {"status": self.status, "index": self.index, "steps": len(self._steps()),
                "current_step": self.current_step, "error": self.error,
                "logs": list(self.logs)[-30:], "a5_ip": self.A5_IP, "mini_ip": self.MINI_IP}

    def start(self):
        with self._lock:
            if self.status in ("running", "paused"):
                raise HTTPException(400, "取液子流程正在执行")
            if not self.a5.connected or self.a5.ip != self.A5_IP:
                raise HTTPException(400, f"请先连接并使能 A5（{self.A5_IP}）")
            if not self.a5.powered or not self.a5.enabled:
                raise HTTPException(400, "A5 必须已上电并使能")
            if not self.end_gripper.connected or not self.end_gripper.initialized:
                raise HTTPException(400, "末端夹爪必须已连接并初始化")
            if not self.zerg.status().get("ready"):
                raise HTTPException(400, "旋转夹爪 ROS2 Action 未就绪")
            info = self.pipette.info()
            if not info.get("connected") or not info.get("initialized"):
                raise HTTPException(400, "移液枪必须已连接并初始化")
            self.index, self.current_step, self.error = -1, "", None
            self.logs.clear(); self.stop_flag = False; self.pause_event.set(); self.status = "running"
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
            return self.state()

    def control(self, action):
        with self._lock:
            if action == "pause" and self.status == "running":
                self.pause_event.clear(); self.status = "paused"
            elif action == "resume" and self.status == "paused":
                self.pause_event.set(); self.status = "running"
            elif action == "stop" and self.status in ("running", "paused"):
                self.stop_flag = True; self.pause_event.set(); self.a5.motion_abort()
                if self.mini_arm is not None:
                    try: self.mini_arm.motion_abort()
                    except Exception: pass
                self.status = "stopped"
            else:
                raise HTTPException(400, f"无法执行流程控制: {action}")
            return self.state()

    def _checkpoint(self, label):
        if self.stop_flag: raise RuntimeError("流程已停止")
        while not self.pause_event.is_set():
            if self.stop_flag: raise RuntimeError("流程已停止")
            time.sleep(0.05)
        self.index += 1; self.current_step = label
        self.logs.append(f"[{self.index + 1}/{len(self._steps())}] {label}")
        print(f"[取液子流程] {self.logs[-1]}", flush=True)

    def _wait(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.stop_flag: raise RuntimeError("流程已停止")
            time.sleep(0.05)

    def _point(self, point_id):
        point = next((p for p in load_points() if p["id"] == point_id), None)
        if point is None: raise RuntimeError(f"缺少点位: {point_id}")
        return point

    def _move(self, arm, point_id, move_type, speed, acc=100.0):
        point = self._point(point_id)
        target = point["joints"] if move_type == "joint" else point["pose"]
        if arm is self.a5:
            # Robot.move() normalizes a successful SDK response to {"ok": True}.
            arm.move(move_type, target, ABS, True, speed, acc, 0.1)
        else:
            result = (arm.joint_move(target, ABS, True, speed) if move_type == "joint"
                      else arm.linear_move_extend(target, ABS, True, speed, acc, 0.1))
            if not isinstance(result, (tuple, list)) or not result or result[0] != 0:
                raise RuntimeError(f"{point.get('name', point_id)} SDK 返回失败: {result!r}")
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if self.stop_flag: raise RuntimeError("流程已停止")
            if arm is self.a5:
                moving = self.a5.status().get("in_motion", False)
            else:
                result = arm.is_in_pos(); moving = not bool(result[1]) if result and result[0] == 0 else False
            if not moving:
                time.sleep(0.2)
                return
            time.sleep(0.05)
        raise RuntimeError(f"{point.get('name', point_id)} 到位确认超时")

    def _close_end(self):
        self.end_gripper.close(wait=True); self._wait(1.0)

    def _wait_mini_arrival(self, mini, label, timeout=20.0):
        """Mini 的 SDK 阻塞返回后，继续向控制器确认已到位再执行下一步。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.stop_flag:
                raise RuntimeError("流程已停止")
            result = mini.is_in_pos()
            if not result or result[0] != 0:
                raise RuntimeError(f"Mini {label}到位状态读取失败: {result!r}")
            if bool(result[1]):
                time.sleep(0.2)
                verify = mini.is_in_pos()
                if verify and verify[0] == 0 and bool(verify[1]):
                    return
            time.sleep(0.05)
        raise RuntimeError(f"Mini {label}到位确认超时")

    def _zerg_close_hold(self):
        """A blocked close is expected when the rotating gripper has gripped a tube."""
        try:
            self.zerg.action("close", "{speed_mm_s: 20, current_a: 0.5}", 25)
        except RuntimeError as exc:
            if "gripper blocked before fully close" not in str(exc):
                raise
            self.logs.append("旋转夹爪检测到试管阻挡，按 0.5 A 夹持成功继续")
            self._wait(0.8)

    def _mini(self):
        mini = JakaArm(self.MINI_IP); self.mini_arm = mini; logged = False
        try:
            for label, point_id, motion, speed in [
                ("JAKA Mini：Home", "jaka_home", "joint", math.radians(10)),
                ("JAKA Mini：试管上方", "jaka_tube_above", "joint", math.radians(10)),
            ]:
                self._checkpoint(label); point = self._point(point_id)
                if not logged:
                    result = mini.login()
                    if not result or result[0] != 0: raise RuntimeError(f"Mini 登录失败: {result!r}")
                    logged = True
                    for name, fn in (("上电", mini.power_on), ("使能", mini.enable)):
                        result = fn()
                        if not result or result[0] != 0: raise RuntimeError(f"Mini {name}失败: {result!r}")
                if motion == "linear_z":
                    current = list(mini.get_actual_tcp_position()[1]); current[2] = point["pose"][2]
                    result = mini.linear_move_extend(current, ABS, True, speed, 100.0, 0.1)
                    if not result or result[0] != 0: raise RuntimeError(f"Mini Z 直线失败: {result!r}")
                    self._wait(0.2)
                else: self._move(mini, point_id, motion, speed)
            self._checkpoint("等待 1 秒"); self._wait(1)
            self._checkpoint("JAKA Mini：试管下方")
            point = self._point("jaka_tube_lower")
            current = list(mini.get_actual_tcp_position()[1]); current[2] = point["pose"][2]
            result = mini.linear_move_extend(current, ABS, True, 30.0, 100.0, 0.1)
            if not result or result[0] != 0: raise RuntimeError(f"Mini Z 直线失败: {result!r}")
            self._wait_mini_arrival(mini, "试管下方")
            self._checkpoint("移液枪：吸液 600 uL"); self.pipette.action("aspirate")
            self._checkpoint("JAKA Mini：试管上方"); self._move(mini, "jaka_tube_above", "joint", math.radians(10)); self._wait(0.5)
            self._checkpoint("JAKA Mini：Home"); self._move(mini, "jaka_home", "joint", math.radians(10))
        finally:
            self.mini_arm = None
            if logged:
                try: mini.logout()
                except Exception: pass

    def _worker(self):
        try:
            self._checkpoint("A5：夹取点上方"); self._move(self.a5, "p_0d029508", "linear", 30)
            self._checkpoint("A5：夹取点"); self._move(self.a5, "p_d7b19939", "linear", 20)
            self._checkpoint("等待 1 秒"); self._wait(1)
            self._checkpoint("末端夹爪：闭合"); self._close_end()
            for label, pid in (("A5：过渡点1", "p_5d256a0d"), ("A5：过渡点2", "p_5f102e2f"), ("A5：旋转夹爪上方", "p_ed5f1653"), ("A5：旋转夹爪夹取点", "p_6d9b3168")):
                self._checkpoint(label); self._move(self.a5, pid, "joint" if "过渡" in label or "上方" in label else "linear", 0.5 if "过渡" in label or "上方" in label else 15)
            self._checkpoint("旋转夹爪：闭合（0.5 A）"); self._zerg_close_hold()
            for label, pid in (("A5：旋转夹爪上方", "p_ed5f1653"), ("A5：旋转夹爪上方向后移动", "p_c181a223")):
                self._checkpoint(label); self._move(self.a5, pid, "joint", 0.5)
            self._mini()
            for label, pid, typ, speed in (("A5：旋转夹爪上方", "p_ed5f1653", "joint", 0.4), ("A5：紫色放盖点（慢）", "p_897b6cb2", "linear", 5), ("旋转夹爪：张开", None, None, None), ("A5：旋转夹爪上方", "p_ed5f1653", "joint", 0.5), ("A5：紫色终点上方", "p_6f434a73", "joint", 0.5), ("A5：紫色终点", "p_59352ab4", "linear", 15), ("末端夹爪：张开", None, None, None), ("A5：紫色终点上方", "p_6f434a73", "linear", 30), ("A5：夹取点上方", "p_0d029508", "joint", 0.5)):
                self._checkpoint(label)
                if label == "旋转夹爪：张开": self.zerg.action("open", "{speed_mm_s: 20, current_a: 0.5}", 25)
                elif label == "末端夹爪：张开": self.end_gripper.open(wait=True); self._wait(0.5)
                else: self._move(self.a5, pid, typ, speed)
            self.logs.append("取液子流程完成")
        except Exception as exc:
            if not self.stop_flag:
                self.error = f"第 {self.index + 1} 步（{self.current_step or '准备'}）失败: {exc!r}"; self.logs.append(self.error); traceback.print_exc()
            self.a5.motion_abort()
        finally:
            self.status = "idle"


class OrangeCappingSubflowRunner(TransferSubflowRunner):
    """连续处理三支橙色试管：开盖、Mini 滴液、盖回并放回。"""

    TUBES = (
        ("1", "p_e0c000b2", "p_fb790c15", "p_6c52108f", "p_bb3339b4"),
        ("2", "p_95cedfbe", "p_3e9d4016", "p_895df5a1", "p_31c341b1"),
        ("3", "p_8513b307", "p_75425b0b", "p_abfac73e", "p_1c109aae"),
    )

    def __init__(self, a5, end_gripper, zerg_bridge, pipette_device):
        super().__init__(a5, end_gripper, zerg_bridge, pipette_device)

    def used_point_ids(self):
        ids = {"p_0d029508", "p_ed5f1653", "p_c181a223", "p_476be453", "p_0f3d32f1",
               "p_56c8b56b", "jaka_home", "p_9655aa5f", "p_168a6f7e"}
        for _, tube_above, tube, end_above, end in self.TUBES:
            ids.update((tube_above, tube, end_above, end))
        return ids

    def _steps(self):
        steps = []
        for number, *_ in self.TUBES:
            prefix = f"橙色试管{number}"
            steps += [
                f"A5：{prefix}夹取点上方", f"A5：{prefix}夹取点", "末端夹爪：闭合", f"A5：{prefix}夹取点上方",
                "A5：旋转夹爪上方", "A5：橙色试管到旋转夹爪过渡点", "A5：橙色试管落到旋转夹爪点（慢）", "旋转夹爪：闭合（0.5 A）",
                "末端夹爪：保持闭合", "旋转夹爪顺时针 360 度 + A5 Z 上升 0.5 mm（1/2）", "旋转夹爪顺时针 360 度 + A5 Z 上升 0.5 mm（2/2）", "旋转夹爪：顺时针 360 度（3/3）",
                "A5：旋转夹爪上方", "A5：旋转夹爪上方向后移动", "JAKA Mini：Home", "JAKA Mini：滴橙色试管上方", "JAKA Mini：滴橙色试管点（慢）", "移液枪：滴液", "JAKA Mini：滴橙色试管上方", "JAKA Mini：Home",
                "A5：旋转夹爪上方", "A5：橙色试管盖盖子过渡点", "A5：过渡点下压 2 mm（慢）",
                "旋转夹爪：逆时针 360 度（1/2）", "旋转夹爪逆时针 360 度 + A5 Z 下探 1 mm（2/2）", "旋转夹爪：张开",
                "A5：旋转夹爪上方", f"A5：试管盒终点{number}上方", f"A5：试管盒终点{number}（慢）", "末端夹爪：张开", f"A5：试管盒终点{number}上方", "A5：夹取点上方",
            ]
        return steps

    def start(self):
        with self._lock:
            if self.status in ("running", "paused"):
                raise HTTPException(400, "橙色试管盖盖子流程正在执行")
            if not self.a5.connected or self.a5.ip != self.A5_IP:
                raise HTTPException(400, f"请先连接并使能 A5（{self.A5_IP}）")
            if not self.a5.powered or not self.a5.enabled:
                raise HTTPException(400, "A5 必须已上电并使能")
            if not self.end_gripper.connected or not self.end_gripper.initialized:
                raise HTTPException(400, "末端夹爪必须已连接并初始化")
            if not self.zerg.status().get("ready"):
                raise HTTPException(400, "旋转夹爪 ROS2 Action 未就绪")
            info = self.pipette.info()
            if not info.get("connected") or not info.get("initialized"):
                raise HTTPException(400, "移液枪必须已连接并初始化")
            missing = self.used_point_ids() - {point["id"] for point in load_points()}
            if missing:
                raise HTTPException(400, f"缺少流程点位: {', '.join(sorted(missing))}")
            self.index, self.current_step, self.error = -1, "", None
            self.logs.clear(); self.stop_flag = False; self.pause_event.set(); self.status = "running"
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
            return self.state()

    def _lower_a5_z(self, distance_mm=0.5):
        self._move_a5_z(-distance_mm, f"A5 Z 下探 {distance_mm:g} mm")

    def _raise_a5_z(self):
        self._move_a5_z(0.5, "A5 Z 上升")

    def _move_a5_z(self, delta_mm, label, speed_mm_s=5.0):
        pose = list(self.a5.status().get("tcp") or [])
        if len(pose) != 6:
            raise RuntimeError("无法读取 A5 当前 TCP 位姿")
        pose[2] += delta_mm
        self.a5.move("linear", pose, ABS, True, speed_mm_s, 30.0, 0.05)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if self.stop_flag: raise RuntimeError("流程已停止")
            if not self.a5.status().get("in_motion", False):
                self._wait(0.2)
                return
            time.sleep(0.05)
        raise RuntimeError(f"{label}到位确认超时")

    def _rotate_with_a5_z(self, *, angle_deg, z_delta_mm, label):
        """旋转夹爪与 A5 Z 轴同时动作，且两者均完成后才允许下一步。"""
        rotate_error = []

        def rotate():
            try:
                self.zerg.action(
                    "rotate",
                    f"{{angle_deg: {angle_deg}, speed_deg_s: 90, current_a: 0.5}}",
                    30,
                )
            except Exception as exc:
                rotate_error.append(exc)

        rotate_thread = threading.Thread(target=rotate, daemon=True)
        rotate_thread.start()
        # Give the Action client a brief chance to send its goal before the
        # A5 starts its synchronized Z move.
        time.sleep(0.1)
        # At 90 deg/s one full turn lasts about four seconds.  Match the
        # Z-motion duration to that turn so it moves throughout the rotation.
        z_speed = max(0.1, abs(z_delta_mm) * 90.0 / 360.0)
        self._move_a5_z(z_delta_mm, label, speed_mm_s=z_speed)
        rotate_thread.join(timeout=35.0)
        if rotate_thread.is_alive():
            raise RuntimeError("旋转夹爪旋转完成确认超时")
        if rotate_error:
            raise rotate_error[0]

    def _mini_dispense_orange(self):
        """Mini 只沿 Z 轴进入滴液点，避免改变已示教的滴液姿态。"""
        mini = JakaArm(self.MINI_IP)
        self.mini_arm = mini
        logged = False
        try:
            for name, fn in (("登录", mini.login), ("上电", mini.power_on), ("使能", mini.enable)):
                result = fn()
                if not result or result[0] != 0:
                    raise RuntimeError(f"Mini {name}失败: {result!r}")
                logged = True
            self._checkpoint("JAKA Mini：Home"); self._move(mini, "jaka_home", "joint", math.radians(10))
            self._checkpoint("JAKA Mini：滴橙色试管上方"); self._move(mini, "p_9655aa5f", "joint", math.radians(10))
            self._checkpoint("JAKA Mini：滴橙色试管点（慢）")
            point = self._point("p_168a6f7e")
            current = list(mini.get_actual_tcp_position()[1])
            current[2] = point["pose"][2]
            result = mini.linear_move_extend(current, ABS, True, 15.0, 80.0, 0.05)
            if not result or result[0] != 0:
                raise RuntimeError(f"Mini 滴液 Z 直线失败: {result!r}")
            self._wait_mini_arrival(mini, "滴橙色试管点")
            self._checkpoint("移液枪：滴液"); self.pipette.action("dispense")
            self._checkpoint("JAKA Mini：滴橙色试管上方")
            current[2] = self._point("p_9655aa5f")["pose"][2]
            result = mini.linear_move_extend(current, ABS, True, 15.0, 80.0, 0.05)
            if not result or result[0] != 0:
                raise RuntimeError(f"Mini 返回滴液上方 Z 直线失败: {result!r}")
            self._wait_mini_arrival(mini, "滴橙色试管上方")
            self._checkpoint("JAKA Mini：Home"); self._move(mini, "jaka_home", "joint", math.radians(10))
        finally:
            self.mini_arm = None
            if logged:
                try: mini.logout()
                except Exception: pass

    def _a5_step(self, label, point_id, move_type, speed):
        self._checkpoint(label)
        self._move(self.a5, point_id, move_type, speed)

    def _run_one_tube(self, tube):
        number, tube_above, tube_point, end_above, end_point = tube
        prefix = f"橙色试管{number}"
        self._a5_step(f"A5：{prefix}夹取点上方", tube_above, "joint", 0.45)
        self._a5_step(f"A5：{prefix}夹取点", tube_point, "linear", 30.0)
        self._checkpoint("末端夹爪：闭合"); self._close_end()
        self._a5_step(f"A5：{prefix}夹取点上方", tube_above, "linear", 45.0)
        self._a5_step("A5：旋转夹爪上方", "p_ed5f1653", "joint", 0.45)
        self._a5_step("A5：橙色试管到旋转夹爪过渡点", "p_476be453", "joint", 0.45)
        self._a5_step("A5：橙色试管落到旋转夹爪点（慢）", "p_0f3d32f1", "linear", 10.0)
        self._checkpoint("旋转夹爪：闭合（0.5 A）"); self._zerg_close_hold()
        self._checkpoint("末端夹爪：保持闭合")
        for turn in (1, 2, 3):
            if turn < 3:
                self._checkpoint(f"旋转夹爪顺时针 360 度 + A5 Z 上升 0.5 mm（{turn}/2）")
                self._rotate_with_a5_z(angle_deg=360, z_delta_mm=0.5, label="A5 Z 上升 0.5 mm")
            else:
                self._checkpoint("旋转夹爪：顺时针 360 度（3/3）")
                self.zerg.action("rotate", "{angle_deg: 360, speed_deg_s: 90, current_a: 0.5}", 30)
        self._a5_step("A5：旋转夹爪上方", "p_ed5f1653", "joint", 0.45)
        self._a5_step("A5：旋转夹爪上方向后移动", "p_c181a223", "joint", 0.45)
        self._mini_dispense_orange()
        self._a5_step("A5：旋转夹爪上方", "p_ed5f1653", "joint", 0.45)
        self._a5_step("A5：橙色试管盖盖子过渡点", "p_56c8b56b", "joint", 0.45)
        self._checkpoint("A5：过渡点下压 2 mm（慢）")
        self._lower_a5_z(2.0)
        self._checkpoint("旋转夹爪：逆时针 360 度（1/2）")
        self.zerg.action("rotate", "{angle_deg: -360, speed_deg_s: 90, current_a: 0.5}", 30)
        self._checkpoint("旋转夹爪逆时针 360 度 + A5 Z 下探 1 mm（2/2）")
        self._rotate_with_a5_z(angle_deg=-360, z_delta_mm=-1.0, label="A5 Z 下探 1 mm")
        self._checkpoint("旋转夹爪：张开")
        self.zerg.action("open", "{speed_mm_s: 20, current_a: 0.5}", 25)
        self._a5_step("A5：旋转夹爪上方", "p_ed5f1653", "joint", 0.45)
        self._a5_step(f"A5：试管盒终点{number}上方", end_above, "joint", 0.45)
        self._a5_step(f"A5：试管盒终点{number}（慢）", end_point, "linear", 30.0)
        self._checkpoint("末端夹爪：张开"); self.end_gripper.open(wait=True); self._wait(0.8)
        self._a5_step(f"A5：试管盒终点{number}上方", end_above, "linear", 45.0)
        self._a5_step("A5：夹取点上方", "p_0d029508", "joint", 0.45)

    def _worker(self):
        try:
            for tube in self.TUBES:
                self._run_one_tube(tube)
            self.logs.append("三个橙色试管盖盖子并放回完成")
        except Exception as exc:
            if not self.stop_flag:
                self.error = f"第 {self.index + 1} 步（{self.current_step or '准备'}）失败: {exc!r}"
                self.logs.append(self.error); traceback.print_exc()
            self.a5.motion_abort()
        finally:
            self.status = "idle"


class CombinedSubflowRunner:
    """按顺序运行紫色取液子流程和橙色三管盖盖子子流程。"""

    def __init__(self, transfer, orange):
        self.transfer = transfer
        self.orange = orange
        self.status = "idle"
        self.phase = ""
        self.error = None
        self.thread = None
        self.stop_flag = False
        self._lock = threading.RLock()

    def state(self):
        first = self.transfer.state()
        second = self.orange.state()
        if self.phase == "transfer":
            index = first["index"]
            current = first["current_step"]
        elif self.phase == "orange":
            index = len(self.transfer._steps()) + second["index"]
            current = second["current_step"]
        else:
            index, current = -1, ""
        logs = ["[总流程] 第 1 阶段：紫色试管取液"] + first["logs"]
        if self.phase == "orange" or second["logs"]:
            logs += ["[总流程] 第 2 阶段：橙色试管 1/2/3 盖盖并放回"] + second["logs"]
        return {"status": self.status, "index": index,
                "steps": len(self.transfer._steps()) + len(self.orange._steps()),
                "current_step": current, "error": self.error or first.get("error") or second.get("error"),
                "logs": logs[-40:], "a5_ip": self.orange.A5_IP, "mini_ip": self.transfer.MINI_IP,
                "phase": self.phase}

    def start(self):
        with self._lock:
            if self.status in ("running", "paused"):
                raise HTTPException(400, "总流程正在执行")
            self.error = None; self.phase = "starting"; self.stop_flag = False; self.status = "running"
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
            return self.state()

    def control(self, action):
        with self._lock:
            child = self.transfer if self.phase == "transfer" else self.orange
            if action == "pause":
                if self.status != "running": raise HTTPException(400, "总流程未在运行")
                child.control("pause"); self.status = "paused"
            elif action == "resume":
                if self.status != "paused": raise HTTPException(400, "总流程未暂停")
                child.control("resume"); self.status = "running"
            elif action == "stop":
                if self.status not in ("running", "paused"): raise HTTPException(400, "总流程未在执行")
                self.stop_flag = True
                if child.status in ("running", "paused"): child.control("stop")
                self.status = "stopped"
            else:
                raise HTTPException(400, f"未知总流程控制: {action}")
            return self.state()

    def _worker(self):
        try:
            self.phase = "transfer"
            self.transfer.start()
            self.transfer.thread.join()
            if self.stop_flag: raise RuntimeError("总流程已停止")
            if self.transfer.error: raise RuntimeError(f"紫色取液子流程失败: {self.transfer.error}")
            self.phase = "orange"
            self.orange.start()
            self.orange.thread.join()
            if self.stop_flag: raise RuntimeError("总流程已停止")
            if self.orange.error: raise RuntimeError(f"橙色盖盖子子流程失败: {self.orange.error}")
        except Exception as exc:
            self.error = str(exc)
            if not self.stop_flag: traceback.print_exc()
        finally:
            if self.error and self.status != "stopped": self.status = "idle"
            elif not self.error and not self.stop_flag: self.status = "idle"


robot = Robot()
gripper = PGIGripper(sim=GRIPPER_SIM)
runner = FlowRunner(robot, gripper)
zerg = ZergRosBridge(ZERG_ROOT)
coordinator = CoordinatedWorkflowRunner(robot, gripper, zerg)
transfer_subflow = TransferSubflowRunner(robot, gripper, zerg, pipette)
orange_capping_subflow = OrangeCappingSubflowRunner(robot, gripper, zerg, pipette)
combined_subflow = CombinedSubflowRunner(transfer_subflow, orange_capping_subflow)

print(f"[启动] 机械臂模拟={SIM}, 夹爪模拟={GRIPPER_SIM}, 默认串口={GRIPPER_PORT or '(未设置)'}")

# ---------------- FastAPI ----------------
app = FastAPI(title="JAKA 机械臂控制与点位管理系统")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/info")
def info():
    return {"sim": robot.sim, "default_ip": DEFAULT_IP,
            "move_types": list(MOVE_TYPES)}


@app.post("/api/connect")
def connect(req: ConnectReq):
    return robot.connect(req.ip)


@app.post("/api/disconnect")
def disconnect():
    return robot.disconnect()


@app.post("/api/power_on")
def power_on():
    return robot.power_on()


@app.post("/api/power_off")
def power_off():
    return robot.power_off()


@app.post("/api/enable")
def enable():
    return robot.enable()


@app.post("/api/disable")
def disable():
    return robot.disable()


@app.get("/api/status")
def status():
    return robot.status()


@app.post("/api/jog")
def jog(req: JogReq):
    return robot.jog(req.axis, req.move_mode, req.coord, req.vel, req.pos_cmd)


@app.post("/api/jog_stop")
def jog_stop():
    return robot.jog_stop()


@app.post("/api/move")
def move(req: MoveReq):
    point, profile = manual_motion_profile_for_target(req.target)
    if profile:
        print(
            f"[手动点位] {point['name']} -> {profile['move_type']} {profile['speed']}",
            flush=True,
        )
        return robot.move(
            profile["move_type"], point["pose"], req.move_mode, req.is_block,
            profile["speed"], 100.0, 0.1,
        )
    return robot.move(req.move_type, req.target, req.move_mode, req.is_block,
                     req.speed, req.acc, req.tol, req.mid_pos)


@app.post("/api/motion_abort")
def motion_abort():
    return robot.motion_abort()


# ---- 夹爪 ----
@app.get("/api/gripper/info")
def gripper_info():
    return {"sim": gripper.sim, "default_port": GRIPPER_PORT,
            "default_slave": DEFAULT_SLAVE, "default_baud": DEFAULT_BAUD,
            "connected": gripper.connected,
            "ranges": {"force": [FORCE_MIN, FORCE_MAX],
                       "speed": [SPEED_MIN, SPEED_MAX],
                       "position": [POSITION_MIN, POSITION_MAX]}}


@app.post("/api/gripper/connect")
def gripper_connect(req: GripperConnectReq):
    port = req.port if req.port else (GRIPPER_PORT or None)
    if not gripper.sim and not port:
        raise HTTPException(400, "非模拟模式需提供串口 port 或设置环境变量 GRIPPER_PORT")
    # Windows 端口名标准化：纯数字 → COMx
    if port and not gripper.sim and port.isdigit() and not port.upper().startswith("COM"):
        port = f"COM{port}"
    try:
        r = gripper.connect(port, req.slave, req.baud)
        if r.get("sim") and gripper.sim:
            print(f"[夹爪] 已连接(仿真)，端口={port}")
        else:
            print(f"[夹爪] 已连接(硬件)，端口={port}，从机={req.slave}，波特率={req.baud}")
        return r
    except Exception as e:
        raise HTTPException(400, f"夹爪连接失败: {e}")


@app.post("/api/gripper/disconnect")
def gripper_disconnect():
    return gripper.disconnect()


@app.post("/api/gripper/initialize")
def gripper_initialize(req: GripperInitReq):
    if not gripper.connected:
        raise HTTPException(400, "夹爪未连接")
    try:
        return gripper.initialize(wait=req.wait, timeout=req.timeout)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.post("/api/gripper/move")
def gripper_move(req: GripperMoveReq):
    if not gripper.connected:
        raise HTTPException(400, "夹爪未连接")
    try:
        return gripper.move_to(req.position, wait=req.wait, timeout=req.timeout)
    except Exception as e:
        raise HTTPException(400, f"位置移动失败: {e}")


@app.post("/api/gripper/open")
def gripper_open():
    if not gripper.connected:
        raise HTTPException(400, "夹爪未连接")
    try:
        return gripper.open(wait=True)
    except Exception as e:
        raise HTTPException(400, f"张开失败: {e}")


@app.post("/api/gripper/close")
def gripper_close():
    if not gripper.connected:
        raise HTTPException(400, "夹爪未连接")
    try:
        return gripper.close(wait=True)
    except Exception as e:
        raise HTTPException(400, f"闭合失败: {e}")


@app.post("/api/gripper/set_params")
def gripper_set_params(req: GripperParamsReq):
    if not gripper.connected:
        raise HTTPException(400, "夹爪未连接")
    r = {}
    try:
        if req.force is not None:
            r["force"] = gripper.set_force(req.force)["force"]
    except Exception as e:
        raise HTTPException(400, f"力值设置失败（尝试{req.force}）: {e}")
    try:
        if req.speed is not None:
            r["speed"] = gripper.set_speed(req.speed)["speed"]
    except Exception as e:
        raise HTTPException(400, f"速度设置失败（尝试{req.speed}）: {e}")
    return r


@app.get("/api/gripper/status")
def gripper_status():
    return gripper.status()


# ---- ADP 移液枪（RS485 ASCII） ----
@app.get("/api/pipette/info")
def pipette_info():
    return pipette.info()


@app.post("/api/pipette/connect")
def pipette_connect(req: PipetteConnectReq):
    try:
        return pipette.connect(req.port, req.address, req.baudrate)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/pipette/disconnect")
def pipette_disconnect():
    return pipette.disconnect()


@app.post("/api/pipette/initialize")
def pipette_initialize():
    try:
        return pipette.initialize()
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/pipette/tip")
def pipette_tip():
    try:
        return pipette.check_tip()
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/pipette/action")
def pipette_action(req: PipetteActionReq):
    try:
        return pipette.action(req.action)
    except Exception as exc:
        raise HTTPException(400, str(exc))


# ---- Z-ERG-20C 旋转夹爪（ROS2） ----
@app.get("/api/zerg/status")
def zerg_status():
    return zerg.status()


@app.post("/api/zerg/driver/start")
def zerg_driver_start():
    try:
        return zerg.start_driver()
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/zerg/driver/stop")
def zerg_driver_stop():
    try:
        return zerg.stop_driver()
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/zerg/driver/cleanup")
def zerg_driver_cleanup():
    try:
        return zerg.cleanup_stale_drivers()
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/zerg/initialize")
def zerg_initialize():
    try:
        return zerg.service(
            "/zerg_driver/initialize", "std_srvs/srv/Trigger", "{}"
        )
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/zerg/enable")
def zerg_enable(req: ZergEnableReq):
    try:
        value = "true" if req.enabled else "false"
        return zerg.service(
            "/zerg_driver/enable", "std_srvs/srv/SetBool", f"{{data: {value}}}"
        )
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/zerg/open")
def zerg_open(req: ZergGripReq):
    try:
        goal = f"{{speed_mm_s: {req.speed_mm_s}, current_a: {req.current_a}}}"
        return zerg.action("open", goal, timeout=25)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/zerg/close")
def zerg_close(req: ZergGripReq):
    try:
        goal = f"{{speed_mm_s: {req.speed_mm_s}, current_a: {req.current_a}}}"
        return zerg.action("close", goal, timeout=25)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/zerg/rotate")
def zerg_rotate(req: ZergRotateReq):
    try:
        goal = (
            f"{{angle_deg: {req.angle_deg}, speed_deg_s: {req.speed_deg_s}, "
            f"current_a: {req.current_a}}}"
        )
        timeout = min(180.0, max(25.0, abs(req.angle_deg) / req.speed_deg_s + 10.0))
        return zerg.action("rotate", goal, timeout=timeout)
    except Exception as exc:
        raise HTTPException(400, str(exc))


# ---- 点位 CRUD ----
@app.get("/api/points")
def get_points():
    return load_points()


@app.post("/api/points")
def create_point(req: PointReq):
    points = load_points()
    st = robot.status()
    if not st.get("connected"):
        raise HTTPException(400, "机械臂未连接，无法保存当前位姿")
    pose = req.pose if req.pose is not None else st["tcp"]
    joints = req.joints if req.joints is not None else st["joints"]
    pt = {
        "id": "p_" + uuid.uuid4().hex[:8],
        "name": req.name, "pose": pose, "joints": joints,
        "note": req.note, "created_at": _now(),
    }
    points.append(pt)
    save_points(points)
    return pt


@app.get("/api/points/motion-profiles")
def point_motion_profiles():
    return MANUAL_POINT_MOTION_PROFILES


@app.put("/api/points/{pid}")
def update_point(pid: str, req: PointUpdate):
    points = load_points()
    for p in points:
        if p["id"] == pid:
            if req.name is not None:
                p["name"] = req.name
            if req.note is not None:
                p["note"] = req.note
            if req.pose is not None:
                p["pose"] = req.pose
            if req.joints is not None:
                p["joints"] = req.joints
            save_points(points)
            return p
    raise HTTPException(404, "点位不存在")


@app.put("/api/points/{pid}/rename")
def rename_point(pid: str, req: RenameReq):
    points = load_points()
    for p in points:
        if p["id"] == pid:
            p["name"] = req.name
            save_points(points)
            return p
    raise HTTPException(404, "点位不存在")


@app.delete("/api/points/{pid}")
def delete_point(pid: str):
    points = load_points()
    new = [p for p in points if p["id"] != pid]
    if len(new) == len(points):
        raise HTTPException(404, "点位不存在")
    save_points(new)
    return {"ok": True}


@app.post("/api/points/{pid}/preview")
def preview_point(pid: str, req: MoveReq):
    points = load_points()
    pt = next((p for p in points if p["id"] == pid), None)
    if not pt:
        raise HTTPException(404, "点位不存在")
    target = pt["joints"] if req.move_type == "joint" else pt["pose"]
    return robot.move(req.move_type, target, ABS, True, req.speed, req.acc, req.tol, req.mid_pos)


# ---- 流程 CRUD ----
@app.get("/api/flows")
def get_flows():
    return load_flows()


@app.post("/api/flows/import-jaka-mini")
def import_jaka_mini_flow():
    """Import the recorded JAKA Mini test-tube sequence as editable GUI data."""
    point_specs = [
        ("jaka_home", "JAKA Mini Home", [190.972712, 31.600471, -76.560789, -347.103832, -47.04296, -14.510245], [-189.384103, -57.256261, 511.475167, -1.798224221, 1.473459247, 1.700034581]),
        ("jaka_tube_above", "试管上方", [196.428797, -20.81942, -38.1313, -352.665661, -28.338736, -3.775229], [-397.232719, -120.992397, 500.077252, 0.712961675, 1.503829645, -2.080071276]),
        ("jaka_tube_lower", "试管下方（只动Z）", [196.259882, -13.954338, -61.956525, -341.816662, -11.655997, -14.870047], [-397.287052, -120.141724, 450.399104, 0.746364762, 1.499581418, -2.046999138]),
        ("jaka_point_4", "点位4", [186.266444, -31.547569, -72.684675, -318.932141, 18.134805, -43.391928], [-472.821375, -12.936012, 312.909128, -1.662843042, 1.503522281, 1.382391395]),
        ("jaka_point_5", "点位5", [180.320094, -30.285515, -74.615522, -337.791546, 15.656014, -25.263113], [-469.478765, 19.714751, 312.90806, -1.662699984, 1.503515331, 1.382504988]),
        ("jaka_point_6", "点位6", [174.757578, -31.602501, -72.690168, -338.457592, 14.939156, -24.683584], [-470.273354, 64.399454, 312.589671, -1.662649138, 1.50350686, 1.292849945]),
    ]
    points = load_points()
    by_id = {p["id"]: p for p in points}
    for pid, name, joints_deg, pose in point_specs:
        by_id[pid] = {
            "id": pid,
            "name": name,
            "pose": pose,
            "joints": [math.radians(value) for value in joints_deg],
            "note": "从 JAKA Mini robot_points.json 导入",
            "created_at": _now(),
        }
    save_points(list(by_id.values()))

    flow_name = "JAKA Mini 试管点位流程"
    flows = load_flows()
    existing = next((f for f in flows if f["name"] == flow_name), None)
    if existing:
        return {"flow": existing, "created": False, "message": "该流程已存在，点位已更新"}
    def segment(pid, move_type, speed, wait=1.0):
        return {
            "point_id": pid, "move_type": move_type, "speed": speed,
            "acc": 100.0, "tol": 0.1, "wait_after_arrival": wait,
            "gripper": {"type": "none", "delay": 0},
        }
    flow = {
        "id": "f_" + uuid.uuid4().hex[:8],
        "name": flow_name,
        "segments": [
            segment("jaka_home", "joint", math.radians(10)),
            segment("jaka_tube_above", "joint", math.radians(10)),
            segment("jaka_tube_lower", "linear_z", 30.0),
            segment("jaka_tube_above", "linear_z", 30.0),
            segment("jaka_point_4", "joint", math.radians(10)),
            segment("jaka_point_5", "joint", math.radians(10)),
            segment("jaka_point_6", "joint", math.radians(10)),
            segment("jaka_home", "joint", math.radians(10)),
        ],
        "note": "从 JAKA Mini robot_points.json 导入；首尾回到 home，试管上下点位仅沿 Z 直线移动。",
        "created_at": _now(),
    }
    flows.append(flow)
    save_flows(flows)
    return {"flow": flow, "created": True, "message": "JAKA Mini 流程已导入"}


@app.post("/api/flows")
def create_flow(req: FlowReq):
    points = {p["id"] for p in load_points()}
    for seg in req.segments:
        if seg.point_id not in points:
            raise HTTPException(400, f"点位不存在: {seg.point_id}")
        if seg.move_type not in MOVE_TYPES:
            raise HTTPException(400, f"非法运动方式: {seg.move_type}")
    flows = load_flows()
    flow = {
        "id": "f_" + uuid.uuid4().hex[:8],
        "name": req.name, "segments": [s.model_dump() for s in req.segments],
        "note": req.note, "created_at": _now(),
    }
    flows.append(flow)
    save_flows(flows)
    return flow


@app.put("/api/flows/{fid}")
def update_flow(fid: str, req: FlowReq):
    flows = load_flows()
    for f in flows:
        if f["id"] == fid:
            f["name"] = req.name
            f["segments"] = [s.model_dump() for s in req.segments]
            f["note"] = req.note
            save_flows(flows)
            return f
    raise HTTPException(404, "流程不存在")


@app.delete("/api/flows/{fid}")
def delete_flow(fid: str):
    flows = load_flows()
    new = [f for f in flows if f["id"] != fid]
    if len(new) == len(flows):
        raise HTTPException(404, "流程不存在")
    save_flows(new)
    return {"ok": True}


@app.post("/api/flows/{fid}/run")
def run_flow(fid: str):
    flows = load_flows()
    flow = next((f for f in flows if f["id"] == fid), None)
    if not flow:
        raise HTTPException(404, "流程不存在")
    runner.run(flow)
    return runner.state()


@app.post("/api/flows/run/control")
def control_flow(req: FlowControlReq):
    return runner.control(req.action)


@app.get("/api/flows/run/state")
def flow_state():
    return runner.state()


# ---- A5 + JAKA Mini + ZERG 串行协同流程 ----
@app.get("/api/coordination/state")
def coordination_state():
    return coordinator.state()


@app.post("/api/coordination/run")
def coordination_run():
    return coordinator.start()


@app.post("/api/coordination/control")
def coordination_control(req: CoordinationControlReq):
    return coordinator.control(req.action)


@app.get("/api/transfer-subflow/state")
def transfer_subflow_state():
    return transfer_subflow.state()


@app.post("/api/transfer-subflow/run")
def transfer_subflow_run():
    return transfer_subflow.start()


@app.post("/api/transfer-subflow/control")
def transfer_subflow_control(req: CoordinationControlReq):
    return transfer_subflow.control(req.action)


def _workflow_points(point_ids):
    by_id = {point["id"]: point for point in load_points()}
    return [by_id[point_id] for point_id in sorted(point_ids, key=lambda item: by_id.get(item, {}).get("name", item)) if point_id in by_id]


@app.get("/api/transfer-subflow/points")
def transfer_subflow_points():
    return _workflow_points(transfer_subflow.used_point_ids())


@app.get("/api/orange-capping/state")
def orange_capping_state():
    return orange_capping_subflow.state()


@app.post("/api/orange-capping/run")
def orange_capping_run():
    return orange_capping_subflow.start()


@app.post("/api/orange-capping/control")
def orange_capping_control(req: CoordinationControlReq):
    return orange_capping_subflow.control(req.action)


@app.get("/api/orange-capping/points")
def orange_capping_points():
    return _workflow_points(orange_capping_subflow.used_point_ids())


@app.get("/api/combined-subflow/state")
def combined_subflow_state():
    return combined_subflow.state()


@app.post("/api/combined-subflow/run")
def combined_subflow_run():
    return combined_subflow.start()


@app.post("/api/combined-subflow/control")
def combined_subflow_control(req: CoordinationControlReq):
    return combined_subflow.control(req.action)


@app.get("/api/combined-subflow/points")
def combined_subflow_points():
    return _workflow_points(transfer_subflow.used_point_ids() | orange_capping_subflow.used_point_ids())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
