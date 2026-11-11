"""Produce argv for review only. No imports of or calls into pymobiledevice3."""
from .core import Coordinate

PREFIX = ("pymobiledevice3", "developer", "dvt", "simulate-location")


def command_plan(action: str, point: Coordinate | None = None) -> dict:
    if action not in ("set", "clear"):
        raise ValueError("action must be set or clear")
    if action == "set" and not isinstance(point, Coordinate):
        raise ValueError("set requires a Coordinate")
    if action == "clear" and point is not None:
        raise ValueError("clear does not accept coordinates")
    argv = [*PREFIX, action]
    if point is not None:
        # End option parsing so southern/western coordinates remain positional.
        argv.extend(["--", str(point.latitude), str(point.longitude)])
    return {
        "mode": "plan-only",
        "executed": False,
        "hardware_verified": False,
        "argv": argv,
        "requirements": [
            "Compatible locally installed pymobiledevice3 (for userspace hold tests, use >=11.50.1); verify its --help",
            "One explicitly identified trusted iPhone; iOS/build recorded",
            "Developer services, image and transport prerequisites verified",
            "For set, keep the session alive and independently observe it persists; separately clear and verify recovery",
        ],
    }
