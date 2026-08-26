#!/usr/bin/env python3
"""Move JAKA A5 to one Cartesian TCP pose supplied on the command line."""

import argparse
import math
import os
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SDK_DIR = Path(os.environ.get("JAKA_SDK_DIR", PROJECT_DIR / ".." / ".." / "JAKA_Mini2_Python_Test" / "sdk")).resolve()


def require_ok(name, result):
    if not isinstance(result, (tuple, list)) or not result or result[0] != 0:
        raise RuntimeError(f"{name} failed: {result!r}")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Move JAKA A5 linearly to x y z rx ry rz (mm, rad)."
    )
    parser.add_argument("x", type=float, help="TCP X in mm")
    parser.add_argument("y", type=float, help="TCP Y in mm")
    parser.add_argument("z", type=float, help="TCP Z in mm")
    parser.add_argument("rx", type=float, help="TCP Rx in rad")
    parser.add_argument("ry", type=float, help="TCP Ry in rad")
    parser.add_argument("rz", type=float, help="TCP Rz in rad")
    parser.add_argument("--ip", default=os.environ.get("JAKA_IP", "10.5.5.100"))
    parser.add_argument("--speed", type=float, default=30.0, help="Linear speed in mm/s (default: 30)")
    parser.add_argument("--acc", type=float, default=100.0, help="Linear acceleration in mm/s^2 (default: 100)")
    parser.add_argument("--tol", type=float, default=0.1, help="Position tolerance in mm (default: 0.1)")
    parser.add_argument("--execute", action="store_true", help="Actually send the motion command")
    parser.add_argument("--keep-enabled", action="store_true", help="Leave the robot enabled after motion")
    args = parser.parse_args()

    target = [args.x, args.y, args.z, args.rx, args.ry, args.rz]
    if not all(math.isfinite(value) for value in target):
        parser.error("all pose values must be finite")
    if not 1.0 <= args.speed <= 500.0:
        parser.error("--speed must be in [1, 500] mm/s")
    if not 1.0 <= args.acc <= 5000.0:
        parser.error("--acc must be in [1, 5000] mm/s^2")

    print(f"Robot IP: {args.ip}")
    print("Target TCP (mm, rad):", target)
    print(f"Linear motion: speed={args.speed} mm/s, acc={args.acc} mm/s^2, tol={args.tol} mm")
    if not args.execute:
        print("Check complete. No connection or motion command was sent.")
        print("Add --execute only after confirming the path is clear.")
        return

    if not (SDK_DIR / "jkrc.so").is_file():
        raise RuntimeError(f"JAKA SDK not found: {SDK_DIR / 'jkrc.so'}")
    os.environ["JAKA_SDK_DIR"] = str(SDK_DIR)
    os.environ["LD_LIBRARY_PATH"] = str(SDK_DIR) + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")
    sys.path.insert(0, str(PROJECT_DIR))
    from jaka_arm import ABS, JakaArm

    arm = JakaArm(args.ip)
    logged_in = powered = enabled = False
    try:
        require_ok("login", arm.login())
        logged_in = True
        require_ok("power_on", arm.power_on())
        powered = True
        require_ok("enable_robot", arm.enable())
        enabled = True
        print("Login, power, and enable: OK")
        require_ok("linear_move_extend", arm.linear_move_extend(target, ABS, True, args.speed, args.acc, args.tol))
        print("Motion complete.")
    finally:
        if enabled and not args.keep_enabled:
            print("disable_robot:", arm.disable())
        if logged_in:
            print("logout:", arm.logout())


if __name__ == "__main__":
    main()
