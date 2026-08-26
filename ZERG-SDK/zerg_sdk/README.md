# zerg-sdk

`zerg-sdk` is a ROS-independent Python SDK for the HITBOT Z-ERG-20C rotating
electric gripper. It implements the documented Modbus RTU functions `0x03`,
`0x06`, and `0x10` without depending on a Modbus framework.

## Install

```bash
python3 -m pip install -e .
```

The only runtime dependency is `pyserial`. Importing and testing the protocol
layer does not open a serial port.

## Basic usage

```python
from zerg_sdk import ZergGripper

with ZergGripper.open("/dev/ttyUSB0", baudrate=115200, slave_id=1) as gripper:
    gripper.initialize()
    gripper.command_grip(10.0, speed_mm_s=30.0, current_a=0.3)
    gripper.command_rotation(
        90.0, relative=True, speed_deg_s=360.0, current_a=0.8
    )
    print(gripper.read_state())
```

Values use the units in the device manual: millimetres, degrees, seconds, and
amperes. The SDK validates every range documented by the manufacturer.

The default data byte order is big-endian, matching the manual's exact example
`90.0 -> 42 B4 00 00`. Use `ByteOrder.LITTLE` only after configuring register
`0x0089` accordingly. Standard IEEE-754 encoding is used; the manual's `0.2`
and `0.8` examples show a one-bit rounding discrepancy in their last byte.

Configuration methods such as `set_device_id()`, `set_baudrate()`, and
`set_device_byte_order()` do not automatically call `save_parameters()` or
restart the device. This prevents an ordinary motion command from writing
flash memory unexpectedly.

## Test

From the repository root:

```bash
PYTHONPATH=zerg_sdk python3 -m unittest discover -s zerg_sdk/test -v
```

The tests use the raw request and response examples from the product manual and
do not require a connected device.

