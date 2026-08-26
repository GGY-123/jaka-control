import unittest

from zerg_sdk import GripPreset, ValidationError, ZergGripper
from zerg_sdk.protocol import float_to_registers
from zerg_sdk.registers import Register


class RecordingClient:
    def __init__(self) -> None:
        self.calls = []
        self.read_values = []
        self.closed = False

    def write_single_register(self, address, value) -> None:
        self.calls.append(("single", address, value))

    def write_multiple_registers(self, address, values) -> None:
        self.calls.append(("multiple", address, list(values)))

    def read_holding_registers(self, address, count):
        self.calls.append(("read", address, count))
        return list(self.read_values)

    def close(self) -> None:
        self.closed = True


class GripperTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = RecordingClient()
        self.gripper = ZergGripper(self.client)

    def test_grip_parameters_are_written_before_motion_trigger(self) -> None:
        self.gripper.command_grip(10.0, speed_mm_s=20.0, current_a=0.4)
        self.assertEqual(
            [call[1] for call in self.client.calls],
            [Register.GRIP_SPEED, Register.GRIP_CURRENT, Register.GRIP_POSITION],
        )
        self.assertEqual(self.client.calls[-1][2], float_to_registers(10.0))

    def test_out_of_range_value_is_rejected_before_io(self) -> None:
        with self.assertRaises(ValidationError):
            self.gripper.set_grip_position(20.1)
        self.assertEqual(self.client.calls, [])

    def test_read_state_decodes_contiguous_feedback(self) -> None:
        values = [5, 2]
        values += float_to_registers(9.5)
        values += float_to_registers(0.0)
        values += float_to_registers(0.35)
        values += [0, 0]
        values += float_to_registers(90.0)
        values += float_to_registers(0.0)
        values += float_to_registers(0.8)
        values += [0x0000, 0x0004]
        self.client.read_values = values

        state = self.gripper.read_state()

        self.assertTrue(state.initialized)
        self.assertAlmostEqual(state.grip_position_mm, 9.5)
        self.assertAlmostEqual(state.rotation_angle_deg, 90.0)
        self.assertEqual(state.error_flags, 4)
        self.assertEqual(self.client.calls[0], ("read", Register.INITIALIZATION_STATUS, 18))

    def test_grip_preset_is_one_based_for_users(self) -> None:
        preset = GripPreset(10.0, 20.0, 1000.0, 1000.0, 0.45)
        self.gripper.configure_grip_preset(1, preset)
        call = self.client.calls[0]
        self.assertEqual(call[1], Register.GRIP_PRESET_BASE)
        self.assertEqual(len(call[2]), 10)

    def test_close_delegates_to_client(self) -> None:
        self.gripper.close()
        self.assertTrue(self.client.closed)


if __name__ == "__main__":
    unittest.main()

