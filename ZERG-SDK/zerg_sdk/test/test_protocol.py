import unittest

from zerg_sdk.exceptions import CrcError, DeviceError
from zerg_sdk.models import ByteOrder
from zerg_sdk.protocol import (
    ModbusRtuClient,
    append_crc,
    float_to_registers,
    registers_to_float,
)


class ScriptedTransport:
    def __init__(self, expected_request: bytes, response: bytes) -> None:
        self.expected_request = expected_request
        self.response = response
        self.closed = False

    def exchange(self, request: bytes) -> bytes:
        if request != self.expected_request:
            raise AssertionError(
                f"request {request.hex(' ')} != {self.expected_request.hex(' ')}"
            )
        return self.response

    def close(self) -> None:
        self.closed = True


class ProtocolTest(unittest.TestCase):
    def test_crc_matches_manual_initialize_frame(self) -> None:
        frame = append_crc(bytes.fromhex("01 06 00 00 00 01"))
        self.assertEqual(frame, bytes.fromhex("01 06 00 00 00 01 48 0A"))

    def test_write_float_frame_matches_manual_90_degrees(self) -> None:
        transport = ScriptedTransport(
            bytes.fromhex("01 10 00 0A 00 02 04 42 B4 00 00 27 8E"),
            bytes.fromhex("01 10 00 0A 00 02 61 CA"),
        )
        client = ModbusRtuClient(transport)
        client.write_multiple_registers(0x000A, float_to_registers(90.0))

    def test_read_status_frame_matches_manual(self) -> None:
        transport = ScriptedTransport(
            bytes.fromhex("01 03 00 41 00 01 D4 1E"),
            bytes.fromhex("01 03 02 00 00 B8 44"),
        )
        client = ModbusRtuClient(transport)
        self.assertEqual(client.read_holding_registers(0x0041, 1), [0])

    def test_little_endian_float_round_trip(self) -> None:
        registers = float_to_registers(90.0, ByteOrder.LITTLE)
        self.assertEqual(registers, [0x0000, 0xB442])
        self.assertEqual(registers_to_float(registers, ByteOrder.LITTLE), 90.0)

    def test_crc_error_is_rejected(self) -> None:
        transport = ScriptedTransport(
            bytes.fromhex("01 03 00 41 00 01 D4 1E"),
            bytes.fromhex("01 03 02 00 00 00 00"),
        )
        with self.assertRaises(CrcError):
            ModbusRtuClient(transport).read_holding_registers(0x0041, 1)

    def test_modbus_exception_is_raised(self) -> None:
        request = append_crc(bytes.fromhex("01 03 00 41 00 01"))
        response = append_crc(bytes.fromhex("01 83 02"))
        transport = ScriptedTransport(request, response)
        with self.assertRaises(DeviceError) as caught:
            ModbusRtuClient(transport).read_holding_registers(0x0041, 1)
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

