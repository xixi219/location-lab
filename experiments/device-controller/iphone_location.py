#!/usr/bin/env python3
"""Local convenience entry point for the ignored experimental controller.

It resolves exactly one USB iPhone without printing its identifier, then replaces
itself with device_control.py. Device writes still require --allow-device-write.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / ".device-venv" / "bin" / "pymobiledevice3"
CONTROLLER = ROOT / "private" / "device_control.py"


def fail(category: str) -> int:
    print(json.dumps({"ok": False, "category": category, "hardware_verified": False}))
    return 2


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return fail("action-required")
    if any(item == "--udid" or item.startswith("--udid=") for item in args):
        return fail("device-id-is-selected-automatically")
    if any(item == "--tool" or item.startswith("--tool=") for item in args):
        return fail("tool-path-is-fixed")
    if "--help" in args or "-h" in args:
        os.execv(sys.executable, [sys.executable, str(CONTROLLER), *args, "--udid", "help"])
    if not TOOL.is_file() or not CONTROLLER.is_file():
        return fail("local-device-tool-unavailable")
    try:
        result = subprocess.run(
            [str(TOOL), "usbmux", "list"], text=True, capture_output=True,
            check=False, timeout=30,
        )
        devices = json.loads(result.stdout) if result.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return fail("device-discovery-failed")
    matches = [item.get("Identifier") for item in devices if item.get("ConnectionType") == "USB"]
    if len(matches) != 1 or not isinstance(matches[0], str):
        return fail("expected-exactly-one-usb-iphone")
    os.execv(
        sys.executable,
        [sys.executable, str(CONTROLLER), *args, "--udid", matches[0]],
    )
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
