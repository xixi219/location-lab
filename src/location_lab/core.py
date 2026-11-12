"""Backend-neutral coordinates and explicit session state."""
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Protocol


@dataclass(frozen=True)
class Coordinate:
    latitude: float
    longitude: float

    def __post_init__(self):
        for name, limit in (("latitude", 90), ("longitude", 180)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite number")
            if not isfinite(value) or not -limit <= value <= limit:
                raise ValueError(f"{name} must be between {-limit} and {limit}")


class Backend(Protocol):
    def set_location(self, point: Coordinate) -> None: ...
    def clear_location(self) -> None: ...


class State(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    CLEARED = "cleared"
    UNKNOWN = "unknown"


class Session:
    """Backend-call returned state, never independent GPS verification or device ACK.

    Backend operations may partially succeed before raising. In that case, keep
    UNKNOWN until a subsequent explicit clear succeeds. Do not allow another set.
    This synchronous MVP does not support concurrent callers.
    """
    def __init__(self, backend: Backend):
        self.backend = backend
        self.state = State.IDLE
        self.point: Coordinate | None = None

    def set_location(self, point: Coordinate) -> None:
        if not isinstance(point, Coordinate):
            raise ValueError("point must be a Coordinate")
        if self.state == State.UNKNOWN:
            raise RuntimeError("Clear the uncertain session before setting another location")
        try:
            self.backend.set_location(point)
        except Exception:
            self.state = State.UNKNOWN
            self.point = None
            raise
        self.point = point
        self.state = State.ACTIVE

    def clear_location(self) -> None:
        # Always contact the backend, including idle: a past process may have set it.
        try:
            self.backend.clear_location()
        except Exception:
            self.state = State.UNKNOWN
            self.point = None
            raise
        self.point = None
        self.state = State.CLEARED


class MemoryBackend:
    """No device I/O, no persistence, no GPS effects."""
    def __init__(self):
        self.point: Coordinate | None = None

    def set_location(self, point: Coordinate) -> None:
        self.point = point

    def clear_location(self) -> None:
        self.point = None
