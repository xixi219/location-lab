#!/usr/bin/env python3
"""Local-only persistent DVT location session for the ignored experiment.

One process owns the DVT LocationSimulation connection. Local clients can send
another ``set`` request through its Unix-domain socket, which updates the
location on the same connection instead of clearing it between waypoints.
Neither the socket protocol nor its output contains a device identifier.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import signal
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pymobiledevice3.remote.rsd_tunnel import PreferredRsdTunnel
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation


ROOT = Path(__file__).resolve().parents[1]
SOCKET = Path(tempfile.gettempdir()) / (
    "location-lab-dvt-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:16] + ".sock"
)
MAX_REQUEST_BYTES = 1024


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False), flush=True)


def valid_coordinate(latitude: object, longitude: object) -> tuple[float, float]:
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        raise ValueError("coordinates-invalid")
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("coordinates-invalid") from exc
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError("coordinates-invalid")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("coordinates-out-of-range")
    return lat, lon


@dataclass
class SessionState:
    location: LocationSimulation
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    cleared: bool = False


async def send(writer: asyncio.StreamWriter, value: dict[str, Any]) -> None:
    writer.write(json.dumps(value, ensure_ascii=False).encode() + b"\n")
    await writer.drain()


async def handle_client(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, state: SessionState
) -> None:
    try:
        payload = await asyncio.wait_for(reader.readline(), timeout=5)
        if not payload or len(payload) > MAX_REQUEST_BYTES:
            raise ValueError("request-invalid")
        request = json.loads(payload)
        if not isinstance(request, dict):
            raise ValueError("request-invalid")
        action = request.get("action")
        async with state.lock:
            if action == "status":
                await send(writer, {"ok": True, "state": "session-running-unverified"})
            elif action == "set":
                latitude, longitude = valid_coordinate(request.get("latitude"), request.get("longitude"))
                await state.location.set(latitude, longitude)
                state.cleared = False
                await send(writer, {"ok": True, "state": "session-running-unverified"})
            elif action == "clear":
                await state.location.clear()
                await asyncio.sleep(2)
                state.cleared = True
                await send(writer, {"ok": True, "state": "clear-command-returned-unverified"})
                state.stop.set()
            else:
                raise ValueError("action-invalid")
    except (ValueError, json.JSONDecodeError, asyncio.TimeoutError):
        await send(writer, {"ok": False, "category": "request-invalid"})
    except Exception:
        # Upstream exceptions may contain device identifiers; never expose them.
        await send(writer, {"ok": False, "category": "dvt-request-failed"})
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def serve(udid: str) -> int:
    if SOCKET.exists():
        # Never replace an extant endpoint: it may still belong to a live
        # session. A stale endpoint needs deliberate local recovery instead
        # of risking a second controller for the same device.
        return 2
    try:
        async with PreferredRsdTunnel(serial=udid, autopair=False) as rsd:
            if rsd.udid != udid:
                return 2
            async with DvtProvider(rsd) as provider, LocationSimulation(provider) as location:
                state = SessionState(location)
                server = await asyncio.start_unix_server(
                    lambda reader, writer: handle_client(reader, writer, state), path=str(SOCKET)
                )
                os.chmod(SOCKET, 0o600)
                loop = asyncio.get_running_loop()
                for signum in (signal.SIGINT, signal.SIGTERM):
                    try:
                        loop.add_signal_handler(signum, state.stop.set)
                    except NotImplementedError:
                        pass
                try:
                    await state.stop.wait()
                finally:
                    server.close()
                    await server.wait_closed()
                    if not state.cleared:
                        try:
                            await location.clear()
                            await asyncio.sleep(2)
                        except Exception:
                            # A signal-path recovery failure must remain unknown to callers.
                            pass
    except Exception:
        return 2
    finally:
        try:
            SOCKET.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            # Do not override a prior session result from cleanup code.
            pass
    return 0


async def request(value: dict[str, Any]) -> int:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(str(SOCKET)), timeout=2)
        await send(writer, value)
        line = await asyncio.wait_for(reader.readline(), timeout=10)
        writer.close()
        await writer.wait_closed()
        response = json.loads(line)
        if not isinstance(response, dict):
            raise ValueError
    except Exception:
        emit({"ok": False, "category": "session-supervisor-unavailable"})
        return 2
    emit(response)
    return 0 if response.get("ok") is True else 2


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="mode", required=True)
    server = subparsers.add_parser("serve")
    server.add_argument("--udid", required=True)
    client = subparsers.add_parser("request")
    client.add_argument("action", choices=("status", "set", "clear"))
    client.add_argument("--latitude", type=float)
    client.add_argument("--longitude", type=float)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.mode == "serve":
        return asyncio.run(serve(args.udid))
    request_value: dict[str, Any] = {"action": args.action}
    if args.action == "set":
        try:
            latitude, longitude = valid_coordinate(args.latitude, args.longitude)
        except ValueError as exc:
            emit({"ok": False, "category": str(exc)})
            return 2
        request_value.update(latitude=latitude, longitude=longitude)
    elif args.latitude is not None or args.longitude is not None:
        emit({"ok": False, "category": "coordinates-not-allowed"})
        return 2
    return asyncio.run(request(request_value))


if __name__ == "__main__":
    raise SystemExit(main())
