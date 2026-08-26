from enum import IntEnum


class Register(IntEnum):
    INITIALIZE = 0x0000
    GRIP_POSITION = 0x0002
    GRIP_SPEED = 0x0004
    GRIP_CURRENT = 0x0006
    ROTATION_ANGLE = 0x000A
    ROTATION_SPEED = 0x000E
    ROTATION_CURRENT = 0x0010
    RELATIVE_ROTATION_ANGLE = 0x0014
    MOTOR_ENABLE = 0x0016
    GRIP_PRESET_SELECT = 0x0017
    ROTATION_PRESET_SELECT = 0x0018

    INITIALIZATION_STATUS = 0x0040
    GRIP_STATUS = 0x0041
    GRIP_POSITION_FEEDBACK = 0x0042
    GRIP_SPEED_FEEDBACK = 0x0044
    GRIP_CURRENT_FEEDBACK = 0x0046
    ROTATION_STATUS = 0x0048
    ROTATION_ANGLE_FEEDBACK = 0x004A
    ROTATION_SPEED_FEEDBACK = 0x004C
    ROTATION_CURRENT_FEEDBACK = 0x004E
    ERROR_FLAGS = 0x0050

    DEVICE_ID = 0x0080
    BAUD_RATE = 0x0081
    CALIBRATION_DIRECTION = 0x0082
    AUTO_INITIALIZE = 0x0083
    SAVE_PARAMETERS = 0x0084
    RESTORE_DEFAULTS = 0x0085
    BYTE_ORDER = 0x0089
    RESET_MULTI_TURN = 0x008F
    IO_MODE = 0x0090
    ROTATION_STALL_STOP_ENABLE = 0x009E
    ROTATION_STALL_SENSITIVITY = 0x009F
    INPUT_SIGNAL_TYPE = 0x00A0
    OUTPUT_SIGNAL_TYPE = 0x00A1

    GRIP_PRESET_BASE = 0x0100
    ROTATION_PRESET_BASE = 0x0180


class BaudRateCode(IntEnum):
    BAUD_9600 = 0
    BAUD_19200 = 1
    BAUD_38400 = 2
    BAUD_57600 = 3
    BAUD_115200 = 4
    BAUD_153600 = 5
    BAUD_256000 = 6

    @property
    def baudrate(self) -> int:
        return (9600, 19200, 38400, 57600, 115200, 153600, 256000)[self.value]

    @classmethod
    def from_baudrate(cls, baudrate: int) -> "BaudRateCode":
        for item in cls:
            if item.baudrate == baudrate:
                return item
        raise ValueError(f"unsupported baud rate: {baudrate}")


class GripStatus(IntEnum):
    REACHED = 0
    MOVING = 1
    GRIPPING = 2
    DROPPED = 3


class RotationStatus(IntEnum):
    REACHED = 0
    MOVING = 1
    BLOCKED = 2
    DROPPED = 3
    STALL_STOPPED = 4


class CalibrationDirection(IntEnum):
    OPEN = 0
    CLOSE = 1


class SignalType(IntEnum):
    NPN = 0
    PNP = 1

