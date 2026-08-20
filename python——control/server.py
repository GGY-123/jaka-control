# -*- coding: utf-8 -*-
import os
import json
import time
import math
import threading
import datetime
import uuid
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from jaka_arm import JakaArm
from gripper import (
    PGIGripper, FORCE_MIN, FORCE_MAX, SPEED_MIN, SPEED_MAX,
    POSITION_MIN, POSITION_MAX, DEFAULT_SLAVE, DEFAULT_BAUD,
)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
POINTS_FILE = os.path.join(DATA_DIR, "points.json")
FLOWS_FILE = os.path.join(DATA_DIR, "flows.json")
SIM = os.environ.get("JAKA_SIM", "0") == "1"
DEFAULT_IP = os.environ.get("JAKA_IP", "10.5.5.100")
# 夹爪：默认真实模式；若 GRIPPER_SIM=1 则强制仿真
GRIPPER_SIM = os.environ.get("GRIPPER_SIM", "0") == "1"
GRIPPER_PORT = os.environ.get("GRIPPER_PORT", "")
GRIPPER_SLAVE = int(os.environ.get("GRIPPER_SLAVE", "1"))
GRIPPER_BAUD = int(os.environ.get("GRIPPER_BAUD", "115200"))

MOVE_TYPES = {"joint", "linear", "circular"}
COORD_BASE, COORD_JOINT, COORD_TOOL = 0, 1, 2
ABS, INCR = 0, 1


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
            self.arm.joint_move(target, move_mode, is_block, speed)
        elif move_type == "linear":
            if acc is not None and tol is not None:
                self.arm.linear_move_extend(target, move_mode, is_block, speed, acc, tol)
            else:
                self.arm.linear_move(target, move_mode, is_block, speed)
        else:  # circular
            if mid_pos is None:
                raise HTTPException(400, "圆弧运动需要中间点 mid_pos")
            a = acc if acc is not None else 50
            t = tol if tol is not None else 0.1
            self.arm.circular_move(target, mid_pos, move_mode, is_block, speed, a, t)
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

    def state(self):
        return {"status": self.status, "index": self.index,
                "flow_id": self.flow["id"] if self.flow else None,
                "segments": len(self.flow["segments"]) if self.flow else 0}

    def run(self, flow):
        if self.status == "running":
            raise HTTPException(400, "已有流程在执行")
        self.flow = flow
        self.index = -1
        self.stop_flag = False
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
            self.status = "stopped"
            self.flow = None
            raise
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


robot = Robot()
gripper = PGIGripper(sim=GRIPPER_SIM)
runner = FlowRunner(robot, gripper)

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
