import time

from zerg_sdk import GripStatus, RotationStatus, ZergGripper


with ZergGripper.open("/dev/ttyUSB0") as gripper:
    gripper.initialize()
    while not gripper.read_state().initialized:
        time.sleep(0.1)

    gripper.command_grip(position_mm=10.0, speed_mm_s=30.0, current_a=0.3)
    while gripper.read_state().grip_status == GripStatus.MOVING:
        time.sleep(0.05)

    gripper.command_rotation(
        90.0, relative=True, speed_deg_s=360.0, current_a=0.8
    )
    while gripper.read_state().rotation_status == RotationStatus.MOVING:
        time.sleep(0.05)
