#!/usr/bin/env python3
"""Send DVT clear and keep its userspace connection alive briefly to flush it.

This is an experimental companion to device_control.py for pymobiledevice3
11.52.1. The upstream clear selector deliberately has no reply, so process
return alone cannot prove that a device received it.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from pymobiledevice3.remote.rsd_tunnel import PreferredRsdTunnel
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation


async def clear(udid: str) -> None:
    async with PreferredRsdTunnel(serial=udid, autopair=False) as rsd:
        if rsd.udid != udid:
            raise RuntimeError("device mismatch")
        async with DvtProvider(rsd) as provider, LocationSimulation(provider) as location:
            await location.clear()
            await asyncio.sleep(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--udid", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(clear(args.udid))
    except Exception:
        # Do not print upstream exceptions: they can include identifiers.
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
