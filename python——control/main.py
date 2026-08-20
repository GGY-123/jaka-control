# -*- coding: utf-8 -*-
import time
from jaka_arm import JakaArm, INCR

ROBOT_IP = "10.5.5.100"


def main():
    arm = JakaArm(ROBOT_IP)

    print("登录:", arm.login()[0])
    time.sleep(1)

    print("上电:", arm.power_on()[0])
    time.sleep(8)

    print("使能:", arm.enable()[0])
    time.sleep(1)

    print("SDK版本:", arm.get_sdk_version())
    print("当前关节角(rad):", arm.get_joint_position())
    print("当前TCP位姿(mm/rad):", arm.get_tcp_position())

    # 末端沿基坐标系Z向上升20mm，再返回（增量、阻塞、低速）
    print("沿Z+移动20mm:", arm.linear_move([0, 0, 20, 0, 0, 0], INCR, True, 20)[0])
    print("沿Z-移动20mm:", arm.linear_move([0, 0, -20, 0, 0, 0], INCR, True, 20)[0])

    print("下使能:", arm.disable()[0])
    print("关电源:", arm.power_off()[0])
    print("注销:", arm.logout()[0])


if __name__ == "__main__":
    main()
