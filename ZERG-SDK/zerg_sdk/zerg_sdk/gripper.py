import math
from typing import Iterable, Optional

from .exceptions import ValidationError
from .models import ByteOrder, DeviceState, GripPreset, RotationPreset
from .protocol import (
    ModbusRtuClient,
    float_to_registers,
    registers_to_float,
    registers_to_uint32,
)
from .registers import (
    BaudRateCode,
    CalibrationDirection,
    Register,
    SignalType,
)
from .transport import SerialTransport


class ZergGripper:
    """High-level API for a HITBOT Z-ERG-20C gripper."""

    def __init__(
        self,
        client: ModbusRtuClient,
        byte_order: ByteOrder = ByteOrder.BIG,
    ) -> None:
        self.client = client
        self.byte_order = ByteOrder(byte_order)

    @classmethod
    def open(
        cls,
        port: str,
        baudrate: int = 115200,
        slave_id: int = 1,
        timeout: float = 0.2,
        byte_order: ByteOrder = ByteOrder.BIG,
    ) -> "ZergGripper":
        transport = SerialTransport(port, baudrate=baudrate, timeout=timeout)
        return cls(ModbusRtuClient(transport, slave_id=slave_id), byte_order)

    def __enter__(self) -> "ZergGripper":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self.client.close()

    def initialize(self) -> None:
        self._write_u16(Register.INITIALIZE, 1)

    def enable_motor(self, enabled: bool = True) -> None:
        self._write_u16(Register.MOTOR_ENABLE, int(enabled))

    def set_grip_position(self, position_mm: float) -> None:
        self._require_range("position_mm", position_mm, 0.0, 20.0)
        self._write_float(Register.GRIP_POSITION, position_mm)

    def set_grip_speed(self, speed_mm_s: float) -> None:
        self._require_range("speed_mm_s", speed_mm_s, 1.0, 100.0)
        self._write_float(Register.GRIP_SPEED, speed_mm_s)

    def set_grip_current(self, current_a: float) -> None:
        self._require_range("current_a", current_a, 0.1, 0.5)
        self._write_float(Register.GRIP_CURRENT, current_a)

    def command_grip(
        self,
        position_mm: float,
        speed_mm_s: Optional[float] = None,
        current_a: Optional[float] = None,
    ) -> None:
        """Set optional motion limits first, then trigger motion by writing position."""
        if speed_mm_s is not None:
            self.set_grip_speed(speed_mm_s)
        if current_a is not None:
            self.set_grip_current(current_a)
        self.set_grip_position(position_mm)

    def set_rotation_angle(self, angle_deg: float) -> None:
        self._require_range("angle_deg", angle_deg, -3600000.0, 3600000.0)
        self._write_float(Register.ROTATION_ANGLE, angle_deg)

    def rotate_relative(self, angle_deg: float) -> None:
        self._require_range("relative angle_deg", angle_deg, -36000.0, 36000.0)
        self._write_float(Register.RELATIVE_ROTATION_ANGLE, angle_deg)

    def set_rotation_speed(self, speed_deg_s: float) -> None:
        self._require_range("speed_deg_s", speed_deg_s, 1.0, 1080.0)
        self._write_float(Register.ROTATION_SPEED, speed_deg_s)

    def set_rotation_current(self, current_a: float) -> None:
        self._require_range("current_a", current_a, 0.2, 1.0)
        self._write_float(Register.ROTATION_CURRENT, current_a)

    def command_rotation(
        self,
        angle_deg: float,
        *,
        relative: bool = False,
        speed_deg_s: Optional[float] = None,
        current_a: Optional[float] = None,
    ) -> None:
        if speed_deg_s is not None:
            self.set_rotation_speed(speed_deg_s)
        if current_a is not None:
            self.set_rotation_current(current_a)
        if relative:
            self.rotate_relative(angle_deg)
        else:
            self.set_rotation_angle(angle_deg)

    def read_state(self) -> DeviceState:
        # 0x0049 is reserved; reading one contiguous block minimizes bus traffic.
        values = self.client.read_holding_registers(Register.INITIALIZATION_STATUS, 18)
        return DeviceState(
            initialization_code=values[0],
            grip_status_code=values[1],
            grip_position_mm=self._decode_float(values[2:4]),
            grip_speed_mm_s=self._decode_float(values[4:6]),
            grip_current_a=self._decode_float(values[6:8]),
            rotation_status_code=values[8],
            rotation_angle_deg=self._decode_float(values[10:12]),
            rotation_speed_deg_s=self._decode_float(values[12:14]),
            rotation_current_a=self._decode_float(values[14:16]),
            error_flags=registers_to_uint32(values[16:18], self.byte_order),
        )

    def select_grip_preset(self, index: int) -> None:
        self._write_u16(Register.GRIP_PRESET_SELECT, self._preset_index(index))

    def select_rotation_preset(self, index: int) -> None:
        self._write_u16(Register.ROTATION_PRESET_SELECT, self._preset_index(index))

    def configure_grip_preset(self, index: int, preset: GripPreset) -> None:
        self._require_range("position_mm", preset.position_mm, 0.0, 20.0)
        self._require_range("speed_mm_s", preset.speed_mm_s, 1.0, 100.0)
        self._require_nonnegative("acceleration_mm_s2", preset.acceleration_mm_s2)
        self._require_nonnegative("deceleration_mm_s2", preset.deceleration_mm_s2)
        self._require_range("current_a", preset.current_a, 0.1, 0.5)
        address = int(Register.GRIP_PRESET_BASE) + self._preset_index(index) * 10
        self.client.write_multiple_registers(
            address,
            self._encode_floats(
                (
                    preset.position_mm,
                    preset.speed_mm_s,
                    preset.acceleration_mm_s2,
                    preset.deceleration_mm_s2,
                    preset.current_a,
                )
            ),
        )

    def configure_rotation_preset(self, index: int, preset: RotationPreset) -> None:
        self._require_range("angle_deg", preset.angle_deg, -3600000.0, 3600000.0)
        self._require_range("speed_deg_s", preset.speed_deg_s, 1.0, 1080.0)
        self._require_nonnegative("acceleration_deg_s2", preset.acceleration_deg_s2)
        self._require_nonnegative("deceleration_deg_s2", preset.deceleration_deg_s2)
        self._require_range("current_a", preset.current_a, 0.2, 1.0)
        address = int(Register.ROTATION_PRESET_BASE) + self._preset_index(index) * 10
        self.client.write_multiple_registers(
            address,
            self._encode_floats(
                (
                    preset.angle_deg,
                    preset.speed_deg_s,
                    preset.acceleration_deg_s2,
                    preset.deceleration_deg_s2,
                    preset.current_a,
                )
            ),
        )

    def set_device_id(self, device_id: int) -> None:
        if not 1 <= device_id <= 247:
            raise ValidationError("device_id must be in [1, 247]")
        self._write_u16(Register.DEVICE_ID, device_id)

    def set_baudrate(self, baudrate: int) -> None:
        try:
            code = BaudRateCode.from_baudrate(baudrate)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        self._write_u16(Register.BAUD_RATE, int(code))

    def set_calibration_direction(self, direction: CalibrationDirection) -> None:
        self._write_u16(Register.CALIBRATION_DIRECTION, int(CalibrationDirection(direction)))

    def set_auto_initialize(self, enabled: bool) -> None:
        # The manual uses 0 for automatic initialization and 1 for manual mode.
        self._write_u16(Register.AUTO_INITIALIZE, 0 if enabled else 1)

    def set_device_byte_order(self, byte_order: ByteOrder) -> None:
        order = ByteOrder(byte_order)
        self._write_u16(Register.BYTE_ORDER, 0 if order == ByteOrder.BIG else 1)

    def set_io_mode(self, enabled: bool) -> None:
        self._write_u16(Register.IO_MODE, int(enabled))

    def set_rotation_stall_stop(self, enabled: bool, sensitivity: int = 10) -> None:
        if not 0 <= sensitivity <= 100:
            raise ValidationError("sensitivity must be in [0, 100]")
        self._write_u16(Register.ROTATION_STALL_SENSITIVITY, sensitivity)
        self._write_u16(Register.ROTATION_STALL_STOP_ENABLE, int(enabled))

    def set_io_signal_types(self, input_type: SignalType, output_type: SignalType) -> None:
        self._write_u16(Register.INPUT_SIGNAL_TYPE, int(SignalType(input_type)))
        self._write_u16(Register.OUTPUT_SIGNAL_TYPE, int(SignalType(output_type)))

    def reset_multi_turn_angle(self) -> None:
        self._write_u16(Register.RESET_MULTI_TURN, 1)

    def save_parameters(self) -> None:
        """Persist configuration. The manual warns not to call this during motion."""
        self._write_u16(Register.SAVE_PARAMETERS, 1)

    def restore_defaults(self) -> None:
        self._write_u16(Register.RESTORE_DEFAULTS, 1)

    def _write_u16(self, address: Register, value: int) -> None:
        self.client.write_single_register(int(address), value)

    def _write_float(self, address: Register, value: float) -> None:
        self.client.write_multiple_registers(
            int(address), float_to_registers(value, self.byte_order)
        )

    def _decode_float(self, values: Iterable[int]) -> float:
        return registers_to_float(values, self.byte_order)

    def _encode_floats(self, values: Iterable[float]) -> list:
        result = []
        for value in values:
            result.extend(float_to_registers(value, self.byte_order))
        return result

    @staticmethod
    def _preset_index(index: int) -> int:
        if not 1 <= index <= 8:
            raise ValidationError("preset index must be in [1, 8]")
        return index - 1

    @staticmethod
    def _require_range(name: str, value: float, minimum: float, maximum: float) -> None:
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValidationError(f"{name} must be in [{minimum}, {maximum}], got {value}")

    @staticmethod
    def _require_nonnegative(name: str, value: float) -> None:
        if not math.isfinite(value) or value < 0:
            raise ValidationError(f"{name} must be finite and nonnegative, got {value}")
