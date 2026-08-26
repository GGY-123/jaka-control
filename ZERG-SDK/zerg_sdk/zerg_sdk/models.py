from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .registers import GripStatus, RotationStatus


class ByteOrder(str, Enum):
    BIG = "big"
    LITTLE = "little"


@dataclass(frozen=True)
class DeviceState:
    initialization_code: int
    grip_status_code: int
    grip_position_mm: float
    grip_speed_mm_s: float
    grip_current_a: float
    rotation_status_code: int
    rotation_angle_deg: float
    rotation_speed_deg_s: float
    rotation_current_a: float
    error_flags: int

    @property
    def initialized(self) -> bool:
        return self.initialization_code == 5

    @property
    def initializing(self) -> bool:
        return self.initialization_code not in (0, 5)

    @property
    def grip_status(self) -> Optional[GripStatus]:
        try:
            return GripStatus(self.grip_status_code)
        except ValueError:
            return None

    @property
    def rotation_status(self) -> Optional[RotationStatus]:
        try:
            return RotationStatus(self.rotation_status_code)
        except ValueError:
            return None


@dataclass(frozen=True)
class GripPreset:
    position_mm: float
    speed_mm_s: float
    acceleration_mm_s2: float
    deceleration_mm_s2: float
    current_a: float


@dataclass(frozen=True)
class RotationPreset:
    angle_deg: float
    speed_deg_s: float
    acceleration_deg_s2: float
    deceleration_deg_s2: float
    current_a: float
