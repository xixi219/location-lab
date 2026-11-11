#!/usr/bin/env python3
"""Unreleased, local-only controller for one explicitly selected iPhone.

This wrapper does not import pymobiledevice3. It invokes the version installed
in this workspace's ignored .device-venv and deliberately keeps device IDs,
coordinates, pairing records, and upstream stderr out of its output.
"""
from __future__ import annotations

import argparse
import json
import math
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOOL = ROOT / ".device-venv" / "bin" / "pymobiledevice3"
CLEAR_HELPER = ROOT / "private" / "dvt_clear_grace.py"
SESSION_SUPERVISOR = ROOT / "private" / "dvt_location_session.py"


class DeviceToolError(RuntimeError):
    """An intentionally redacted failure from the local device tool."""


def emit(**values: object) -> None:
    values.setdefault("hardware_verified", False)
    print(json.dumps(values, ensure_ascii=False))


def tool_path(value: str | None) -> Path:
    path = Path(value) if value else DEFAULT_TOOL
    if not path.is_file() or not path.stat().st_mode & 0o111:
        raise DeviceToolError("device-tool-unavailable")
    return path


def run(tool: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [str(tool), *args], text=True, capture_output=True, check=False, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeviceToolError("device-tool-unavailable") from exc


def selected_usb_device(tool: Path, udid: str) -> str:
    if not udid.strip():
        raise DeviceToolError("explicit-device-id-required")
    result = run(tool, "usbmux", "list")
    if result.returncode:
        raise DeviceToolError("device-discovery-failed")
    try:
        devices = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise DeviceToolError("device-discovery-invalid") from exc
    matches = [
        item for item in devices
        if item.get("ConnectionType") == "USB" and item.get("Identifier") == udid
    ]
    if len(matches) != 1:
        raise DeviceToolError("requested-device-not-a-single-usb-match")
    return udid


def device_options(udid: str) -> tuple[str, ...]:
    return ("--userspace", "--udid", udid)


def developer_mode_enabled(tool: Path, udid: str) -> bool:
    result = run(tool, "amfi", "developer-mode-status", *device_options(udid))
    if result.returncode:
        raise DeviceToolError("developer-mode-status-unavailable")
    if result.stdout.strip() not in ("true", "false"):
        raise DeviceToolError("developer-mode-status-invalid")
    return result.stdout.strip() == "true"


def dvt_read_preflight(tool: Path, udid: str) -> None:
    result = run(
        tool, "developer", "dvt", "sysmon", "process", "single", *device_options(udid),
        "--filter", "name=SpringBoard", "--key", "name",
    )
    if result.returncode:
        raise DeviceToolError("dvt-service-unavailable")


def supervisor_request(
    tool: Path, action: str, latitude: float | None = None, longitude: float | None = None
) -> bool:
    python = tool.with_name("python")
    if not python.is_file() or not SESSION_SUPERVISOR.is_file():
        return False
    command = [str(python), str(SESSION_SUPERVISOR), "request", action]
    if action == "set" and latitude is not None and longitude is not None:
        command.extend(("--latitude", str(latitude), "--longitude", str(longitude)))
    try:
        result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=15)
        response = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return False
    return result.returncode == 0 and response.get("ok") is True


def start_supervisor(tool: Path, udid: str) -> None:
    python = tool.with_name("python")
    if not python.is_file() or not SESSION_SUPERVISOR.is_file():
        raise DeviceToolError("session-supervisor-unavailable")
    try:
        subprocess.Popen(
            [str(python), str(SESSION_SUPERVISOR), "serve", "--udid", udid],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise DeviceToolError("session-supervisor-unavailable") from exc
    for _ in range(30):
        if supervisor_request(tool, "status"):
            return
        time.sleep(0.2)
    raise DeviceToolError("session-supervisor-unavailable")


def clear(tool: Path, udid: str) -> None:
    if supervisor_request(tool, "clear"):
        return
    python = tool.with_name("python")
    if not python.is_file() or not CLEAR_HELPER.is_file():
        raise DeviceToolError("clear-helper-unavailable")
    try:
        result = subprocess.run(
            [str(python), str(CLEAR_HELPER), "--udid", udid],
            text=True, capture_output=True, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeviceToolError("clear-command-failed") from exc
    if result.returncode:
        raise DeviceToolError("clear-command-failed")


def coordinate(
    latitude: float | None, longitude: float | None, place_name: str | None
) -> tuple[float, float]:
    if place_name is not None:
        if latitude is not None or longitude is not None:
            raise DeviceToolError("place-cannot-combine-with-coordinates")
        if not place_name.strip():
            raise DeviceToolError("place-name-required")
        source = str(ROOT / "src")
        if source not in sys.path:
            sys.path.insert(0, source)
        try:
            from location_lab.places import PlaceStore, default_store

            choices = {place.name.casefold(): place for place in PlaceStore(default_store()).list()}
            place = choices.get(place_name.casefold())
        except (ImportError, OSError, ValueError) as exc:
            raise DeviceToolError("saved-place-unavailable") from exc
        if place is None:
            raise DeviceToolError("saved-place-not-found")
        return place.coordinate.latitude, place.coordinate.longitude
    if latitude is None or longitude is None:
        raise DeviceToolError("both-coordinates-required")
    if not all(math.isfinite(value) for value in (latitude, longitude)):
        raise DeviceToolError("coordinates-must-be-finite")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise DeviceToolError("coordinates-out-of-range")
    return latitude, longitude


def run_cli_fallback(tool: Path, udid: str, latitude: float, longitude: float) -> None:
    command = [
        str(tool), "developer", "dvt", "simulate-location", "set", *device_options(udid),
        str(latitude), str(longitude),
    ]
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise DeviceToolError("cli-fallback-unavailable") from exc
    time.sleep(1)
    if process.poll() is not None:
        raise DeviceToolError("cli-fallback-session-ended-during-startup")


def run_set(
    tool: Path,
    udid: str,
    latitude: float,
    longitude: float,
    hold: float | None,
    cli_fallback: bool,
) -> None:
    if cli_fallback:
        clear(tool, udid)
        run_cli_fallback(tool, udid, latitude, longitude)
        emit(action="set", state="session-running-unverified", observation="required", backend="cli-fallback")
        return
    if not supervisor_request(tool, "status"):
        start_supervisor(tool, udid)
    if not supervisor_request(tool, "set", latitude, longitude):
        raise DeviceToolError("set-command-failed")
    emit(action="set", state="session-running-unverified", observation="required")
    if hold is None:
        return
    try:
        time.sleep(hold)
    except KeyboardInterrupt:
        clear(tool, udid)
        emit(
            action="clear",
            state="clear-command-returned-unverified",
            observation="confirm-real-location-independently",
        )
        emit(action="set", state="interrupted-and-clear-requested", observation="required")
        return
    clear(tool, udid)
    emit(
        action="clear",
        state="clear-command-returned-unverified",
        observation="confirm-real-location-independently",
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("action", choices=("inspect", "set", "clear"))
    result.add_argument("--udid", required=True, help="Local only; never printed by this program")
    result.add_argument("--tool", help="Path to pymobiledevice3; default is this workspace's .device-venv")
    result.add_argument("--latitude", type=float)
    result.add_argument("--longitude", type=float)
    result.add_argument("--place", help="Exact local saved-place name; never printed by this program")
    result.add_argument("--hold", type=float, help="Bounded seconds before clear; omit to wait for Ctrl+C")
    result.add_argument("--fallback-cli", action="store_true", help=argparse.SUPPRESS)
    result.add_argument("--allow-device-write", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        tool = tool_path(args.tool)
        udid = selected_usb_device(tool, args.udid)
        enabled = developer_mode_enabled(tool, udid)
        if not enabled:
            raise DeviceToolError("developer-mode-disabled")
        dvt_read_preflight(tool, udid)
        if args.action == "inspect":
            if (args.latitude is not None or args.longitude is not None or args.place is not None
                    or args.hold is not None or args.fallback_cli):
                raise DeviceToolError("inspect-does-not-take-location-options")
            emit(action="inspect", developer_mode=True, dvt_service="opened")
            return 0
        if not args.allow_device_write:
            raise DeviceToolError("allow-device-write-required")
        if args.action == "clear":
            if (args.latitude is not None or args.longitude is not None or args.place is not None
                    or args.hold is not None or args.fallback_cli):
                raise DeviceToolError("clear-does-not-take-location-options")
            clear(tool, udid)
            emit(action="clear", state="clear-command-returned-unverified")
            return 0
        latitude, longitude = coordinate(args.latitude, args.longitude, args.place)
        if args.hold is not None and (not math.isfinite(args.hold) or not 0 <= args.hold <= 300):
            raise DeviceToolError("hold-must-be-between-zero-and-300")
        run_set(tool, udid, latitude, longitude, args.hold, args.fallback_cli)
        return 0
    except DeviceToolError as exc:
        emit(action=args.action, ok=False, category=str(exc))
        return 2
    except KeyboardInterrupt:
        emit(action=args.action, ok=False, category="interrupted-recovery-uncertain")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
