"""Private local place storage and route planning; never contacts an iPhone."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from .core import Coordinate


@dataclass(frozen=True)
class Place:
    name: str
    coordinate: Coordinate

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("place name must not be empty")

    def to_dict(self) -> dict:
        return {"name": self.name, "latitude": self.coordinate.latitude,
                "longitude": self.coordinate.longitude}


def default_store() -> Path:
    """Return a user-private path without creating it."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Location Lab" / "places.json"
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "location-lab" / "places.json"
    return Path.home() / ".local" / "state" / "location-lab" / "places.json"


class PlaceStore:
    """A small, atomic JSON store. Coordinates are never written to project files."""
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def list(self) -> list[Place]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("place store is unreadable; it was not modified") from exc
        if not isinstance(data, list):
            raise ValueError("place store must contain a list")
        places = []
        for row in data:
            if not isinstance(row, dict):
                raise ValueError("place store contains an invalid entry")
            places.append(Place(str(row.get("name", "")), Coordinate(
                row.get("latitude"), row.get("longitude"))))
        return sorted(places, key=lambda place: place.name.casefold())

    def save(self, place: Place) -> None:
        places = {item.name.casefold(): item for item in self.list()}
        places[place.name.casefold()] = place
        self._write(sorted(places.values(), key=lambda item: item.name.casefold()))

    def delete(self, name: str) -> bool:
        original = self.list()
        kept = [item for item in original if item.name.casefold() != name.casefold()]
        if len(kept) == len(original):
            return False
        self._write(kept)
        return True

    def _write(self, places: list[Place]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps([item.to_dict() for item in places], ensure_ascii=False,
                                        indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


def google_maps_url(point: Coordinate) -> str:
    """A free, no-key Google Maps search URL; opening it is left to the user."""
    return "https://www.google.com/maps/search/?" + urlencode(
        {"api": "1", "query": f"{point.latitude},{point.longitude}"})


def route_plan(places: list[Place]) -> dict:
    if not places:
        raise ValueError("route requires at least one saved place")
    return {
        "mode": "route-plan-only",
        "executed": False,
        "hardware_verified": False,
        "steps": [{"index": index + 1, "name": place.name,
                   "latitude": place.coordinate.latitude,
                   "longitude": place.coordinate.longitude,
                   "google_maps_url": google_maps_url(place.coordinate)}
                  for index, place in enumerate(places)],
        "next_step_requirement": (
            "Connect one explicitly selected trusted iPhone; verify set, sustained observation, "
            "and clear recovery before device execution."
        ),
    }
