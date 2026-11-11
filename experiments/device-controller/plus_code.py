#!/usr/bin/env python3
"""Recover and decode standard Google Plus Codes without a network request.

Local-only helper for the experimental queue. It supports ordinary short codes
with six code characters (for example ``2HV9+PH``) and their full ten-character
form. A reference point is needed only to recover the omitted leading digits.
"""
from __future__ import annotations

import argparse
import json
import math


ALPHABET = "23456789CFGHJMPQRVWX"
PAIR_RESOLUTIONS = (20.0, 1.0, 0.05, 0.0025, 0.000125)


def normalized(code: str) -> str:
    compact = code.upper().replace("+", "").replace(" ", "")
    if len(compact) not in (6, 10) or any(character not in ALPHABET for character in compact):
        raise ValueError("expected a six- or ten-character standard Plus Code")
    return compact


def encode_pair(latitude: float, longitude: float) -> str:
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("reference coordinate out of range")
    lat = min(latitude, 89.999999999) + 90
    lon = min(longitude, 179.999999999) + 180
    result: list[str] = []
    for resolution in PAIR_RESOLUTIONS:
        lat_digit, lat = divmod(lat, resolution)
        lon_digit, lon = divmod(lon, resolution)
        result.extend((ALPHABET[min(int(lat_digit), 19)], ALPHABET[min(int(lon_digit), 19)]))
    return "".join(result)


def decode_full(code: str) -> tuple[float, float]:
    digits = normalized(code)
    if len(digits) != 10:
        raise ValueError("a full Plus Code has ten code characters")
    latitude = -90.0
    longitude = -180.0
    for index, resolution in enumerate(PAIR_RESOLUTIONS):
        latitude += ALPHABET.index(digits[index * 2]) * resolution
        longitude += ALPHABET.index(digits[index * 2 + 1]) * resolution
    # A Plus Code denotes an area; use its centre for a point simulation.
    return latitude + PAIR_RESOLUTIONS[-1] / 2, longitude + PAIR_RESOLUTIONS[-1] / 2


def recover(short_code: str, reference_latitude: float, reference_longitude: float) -> str:
    short = normalized(short_code)
    if len(short) != 6:
        raise ValueError("recovery requires a six-character short Plus Code")
    reference = encode_pair(reference_latitude, reference_longitude)
    full = reference[:4] + short
    latitude, longitude = decode_full(full)
    area_resolution = PAIR_RESOLUTIONS[1]
    if latitude - reference_latitude > area_resolution / 2:
        latitude -= area_resolution
    elif reference_latitude - latitude > area_resolution / 2:
        latitude += area_resolution
    if longitude - reference_longitude > area_resolution / 2:
        longitude -= area_resolution
    elif reference_longitude - longitude > area_resolution / 2:
        longitude += area_resolution
    return encode_pair(latitude, longitude)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code")
    parser.add_argument("--reference-latitude", type=float, required=True)
    parser.add_argument("--reference-longitude", type=float, required=True)
    args = parser.parse_args(argv)
    try:
        full = recover(args.code, args.reference_latitude, args.reference_longitude)
        latitude, longitude = decode_full(full)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"full_plus_code": full[:8] + "+" + full[8:],
                      "latitude": latitude, "longitude": longitude}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
