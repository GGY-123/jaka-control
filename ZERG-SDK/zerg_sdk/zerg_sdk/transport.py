import threading
from typing import Optional, Protocol

from .exceptions import TransportError


class Transport(Protocol):
    def exchange(self, request: bytes) -> bytes:
        """Send one Modbus RTU request and return exactly one response frame."""

    def close(self) -> None:
        """Release transport resources."""


class SerialTransport:
    """Half-duplex Modbus RTU transport backed by pyserial."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.2,
        write_timeout: Optional[float] = None,
    ) -> None:
        try:
            import serial
        except ImportError as exc:
            raise TransportError(
                "pyserial is required for a real serial connection; install python3-serial"
            ) from exc

        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout,
                write_timeout=write_timeout if write_timeout is not None else timeout,
            )
        except serial.SerialException as exc:
            raise TransportError(f"failed to open serial port {port}: {exc}") from exc
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        return bool(self._serial.is_open)

    def _read_exact(self, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            chunk = self._serial.read(size - len(data))
            if not chunk:
                raise TransportError(
                    f"serial response timed out after {len(data)}/{size} bytes"
                )
            data.extend(chunk)
        return bytes(data)

    def exchange(self, request: bytes) -> bytes:
        with self._lock:
            try:
                self._serial.reset_input_buffer()
                written = self._serial.write(request)
                self._serial.flush()
                if written != len(request):
                    raise TransportError(
                        f"serial write incomplete: {written}/{len(request)} bytes"
                    )

                header = self._read_exact(2)
                function = header[1]
                if function & 0x80:
                    return header + self._read_exact(3)
                if function == 0x03:
                    byte_count = self._read_exact(1)
                    return header + byte_count + self._read_exact(byte_count[0] + 2)
                if function in (0x06, 0x10):
                    return header + self._read_exact(6)
                raise TransportError(
                    f"unsupported function in response: 0x{function:02X}"
                )
            except TransportError:
                raise
            except Exception as exc:
                raise TransportError(f"serial exchange failed: {exc}") from exc

    def close(self) -> None:
        with self._lock:
            if self._serial.is_open:
                self._serial.close()

