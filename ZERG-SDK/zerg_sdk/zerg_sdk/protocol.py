import struct
import threading
from typing import Iterable, List

from .exceptions import CrcError, DeviceError, ProtocolError, ValidationError
from .models import ByteOrder
from .transport import Transport


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def append_crc(frame: bytes) -> bytes:
    return frame + struct.pack("<H", crc16_modbus(frame))


def bytes_to_registers(data: bytes) -> List[int]:
    if len(data) % 2:
        raise ValueError("register data must contain an even number of bytes")
    return [struct.unpack(">H", data[i : i + 2])[0] for i in range(0, len(data), 2)]


def registers_to_bytes(registers: Iterable[int]) -> bytes:
    values = list(registers)
    for value in values:
        if not 0 <= value <= 0xFFFF:
            raise ValueError(f"invalid 16-bit register value: {value}")
    return b"".join(struct.pack(">H", value) for value in values)


def float_to_registers(value: float, byte_order: ByteOrder = ByteOrder.BIG) -> List[int]:
    fmt = ">f" if byte_order == ByteOrder.BIG else "<f"
    return bytes_to_registers(struct.pack(fmt, float(value)))


def registers_to_float(
    registers: Iterable[int], byte_order: ByteOrder = ByteOrder.BIG
) -> float:
    data = registers_to_bytes(registers)
    if len(data) != 4:
        raise ValueError("a float requires exactly two registers")
    fmt = ">f" if byte_order == ByteOrder.BIG else "<f"
    return struct.unpack(fmt, data)[0]


def registers_to_uint32(
    registers: Iterable[int], byte_order: ByteOrder = ByteOrder.BIG
) -> int:
    data = registers_to_bytes(registers)
    if len(data) != 4:
        raise ValueError("an int32 requires exactly two registers")
    fmt = ">I" if byte_order == ByteOrder.BIG else "<I"
    return struct.unpack(fmt, data)[0]


class ModbusRtuClient:
    """Minimal Modbus RTU master for the three functions supported by Z-ERG-20C."""

    def __init__(self, transport: Transport, slave_id: int = 1) -> None:
        if not 1 <= slave_id <= 247:
            raise ValidationError("slave_id must be in [1, 247]")
        self.transport = transport
        self.slave_id = slave_id
        self._lock = threading.RLock()

    def _exchange(self, function: int, payload: bytes) -> bytes:
        request_pdu = bytes((self.slave_id, function)) + payload
        request = append_crc(request_pdu)
        with self._lock:
            response = self.transport.exchange(request)

        if len(response) < 5:
            raise ProtocolError(f"response is too short: {len(response)} bytes")
        expected_crc = crc16_modbus(response[:-2])
        received_crc = struct.unpack("<H", response[-2:])[0]
        if received_crc != expected_crc:
            raise CrcError(
                f"CRC mismatch: received 0x{received_crc:04X}, expected 0x{expected_crc:04X}"
            )
        if response[0] != self.slave_id:
            raise ProtocolError(
                f"unexpected slave id {response[0]}, expected {self.slave_id}"
            )
        if response[1] == (function | 0x80):
            if len(response) != 5:
                raise ProtocolError("malformed Modbus exception frame")
            raise DeviceError(response[2])
        if response[1] != function:
            raise ProtocolError(
                f"unexpected function 0x{response[1]:02X}, expected 0x{function:02X}"
            )
        return response[2:-2]

    def read_holding_registers(self, address: int, count: int) -> List[int]:
        self._validate_address(address)
        if not 1 <= count <= 125:
            raise ValidationError("read register count must be in [1, 125]")
        data = self._exchange(0x03, struct.pack(">HH", address, count))
        if not data or data[0] != count * 2 or len(data) != 1 + count * 2:
            raise ProtocolError(
                f"unexpected read byte count: expected {count * 2}, got {data[0] if data else 0}"
            )
        return bytes_to_registers(data[1:])

    def write_single_register(self, address: int, value: int) -> None:
        self._validate_address(address)
        if not 0 <= value <= 0xFFFF:
            raise ValidationError("register value must be in [0, 65535]")
        payload = struct.pack(">HH", address, value)
        response = self._exchange(0x06, payload)
        if response != payload:
            raise ProtocolError("write-single response does not echo the request")

    def write_multiple_registers(self, address: int, registers: Iterable[int]) -> None:
        self._validate_address(address)
        values = list(registers)
        if not 1 <= len(values) <= 123:
            raise ValidationError("write register count must be in [1, 123]")
        encoded = registers_to_bytes(values)
        payload = struct.pack(">HHB", address, len(values), len(encoded)) + encoded
        response = self._exchange(0x10, payload)
        expected = struct.pack(">HH", address, len(values))
        if response != expected:
            raise ProtocolError("write-multiple response does not match address/count")

    def close(self) -> None:
        self.transport.close()

    @staticmethod
    def _validate_address(address: int) -> None:
        if not 0 <= address <= 0xFFFF:
            raise ValidationError("register address must be in [0, 65535]")

