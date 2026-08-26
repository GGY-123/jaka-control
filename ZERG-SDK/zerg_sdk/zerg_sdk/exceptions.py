class ZergError(Exception):
    """Base exception for this SDK."""


class TransportError(ZergError):
    """Serial transport failed or returned an incomplete frame."""


class ProtocolError(ZergError):
    """A Modbus response was malformed or did not match its request."""


class CrcError(ProtocolError):
    """A Modbus response failed CRC validation."""


class DeviceError(ProtocolError):
    """The device returned a Modbus exception response."""

    EXCEPTION_NAMES = {
        1: "illegal function",
        2: "illegal data address",
        3: "illegal data value",
        4: "server device failure",
    }

    def __init__(self, code: int) -> None:
        self.code = code
        name = self.EXCEPTION_NAMES.get(code, "unknown exception")
        super().__init__(f"Modbus device exception 0x{code:02X}: {name}")


class ValidationError(ZergError, ValueError):
    """A command value is outside the range documented by the device."""

