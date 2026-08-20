# -*- coding: utf-8 -*-
import os
import sys

# 定位SDK目录并加入DLL搜索路径与模块搜索路径
_SDK_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "SDK V2.2.7", "SDK V2.2.7", "Windows", "python3", "x64"))
os.add_dll_directory(_SDK_DIR)
sys.path.insert(0, _SDK_DIR)

import jkrc

# 坐标系
COORD_BASE = 0
COORD_JOINT = 1
COORD_TOOL = 2

# 运动模式
ABS = 0
INCR = 1

# IO类型
IO_CABINET = 0
IO_TOOL = 1
IO_EXTEND = 2


class JakaArm:
    def __init__(self, ip):
        self.robot = jkrc.RC(ip)

    # ---------- 连接与电源 ----------
    def login(self):
        return self.robot.login()

    def logout(self):
        return self.robot.logout()

    def power_on(self):
        return self.robot.power_on()

    def power_off(self):
        return self.robot.power_off()

    def enable(self):
        return self.robot.enable_robot()

    def disable(self):
        return self.robot.disable_robot()

    def shut_down(self):
        return self.robot.shut_down()

    def clear_error(self):
        return self.robot.clear_error()

    def get_sdk_version(self):
        return self.robot.get_sdk_version()

    def get_controller_ip(self):
        return self.robot.get_controller_ip()

    # ---------- 运动控制 ----------
    def set_motion_planner(self, planner_type=0):
        return self.robot.set_motion_planner(planner_type)

    def set_rapidrate(self, rate=1.0):
        """设置全局运动速率倍率，范围 [0,1]，1.0=100%全速。"""
        return self.robot.set_rapidrate(rate)

    def jog(self, aj_num, move_mode, coord_type, jog_vel, pos_cmd=0):
        return self.robot.jog(aj_num, move_mode, coord_type, jog_vel, pos_cmd)

    def jog_stop(self, joint_num=-1):
        return self.robot.jog_stop(joint_num)

    def joint_move(self, joint_pos, move_mode=ABS, is_block=True, speed=0.2):
        return self.robot.joint_move(joint_pos, move_mode, is_block, speed)

    def joint_move_extend(self, joint_pos, move_mode=ABS, is_block=True, speed=0.2, acc=3.5, tol=0.1):
        return self.robot.joint_move_extend(joint_pos, move_mode, is_block, speed, acc, tol)

    def linear_move(self, end_pos, move_mode=ABS, is_block=True, speed=50):
        return self.robot.linear_move(end_pos, move_mode, is_block, speed)

    def linear_move_extend(self, end_pos, move_mode=ABS, is_block=True, speed=50, acc=100, tol=0.1):
        return self.robot.linear_move_extend(end_pos, move_mode, is_block, speed, acc, tol)

    def circular_move(self, end_pos, mid_pos, move_mode=ABS, is_block=True, speed=50, acc=50, tol=0.1):
        return self.robot.circular_move(end_pos, mid_pos, move_mode, is_block, speed, acc, tol)

    def motion_abort(self):
        return self.robot.motion_abort()

    # ---------- 状态查询 ----------
    def get_joint_position(self):
        return self.robot.get_joint_position()

    def get_actual_joint_position(self):
        return self.robot.get_actual_joint_position()

    def get_tcp_position(self):
        return self.robot.get_tcp_position()

    def get_actual_tcp_position(self):
        return self.robot.get_actual_tcp_position()

    def get_robot_status(self):
        return self.robot.get_robot_status()

    def get_robot_status_simple(self):
        return self.robot.get_robot_status_simple()

    def is_in_pos(self):
        return self.robot.is_in_pos()

    def is_in_drag_mode(self):
        return self.robot.is_in_drag_mode()

    def drag_mode_enable(self, enable):
        return self.robot.drag_mode_enable(enable)

    # ---------- IO ----------
    def set_digital_output(self, io_type, index, value):
        return self.robot.set_digital_output(io_type, index, value)

    def set_analog_output(self, io_type, index, value):
        return self.robot.set_analog_output(io_type, index, value)

    def get_digital_input(self, io_type, index):
        return self.robot.get_digital_input(io_type, index)

    def get_digital_output(self, io_type, index):
        return self.robot.get_digital_output(io_type, index)

    def get_analog_input(self, io_type, index):
        return self.robot.get_analog_input(io_type, index)

    def get_analog_output(self, io_type, index):
        return self.robot.get_analog_output(io_type, index)
