"""Deterministic, offline fault exercises using the real Session core."""
from .core import Coordinate, MemoryBackend, Session

SCENARIOS = ("normal", "set-disconnect", "clear-retry")


class ScenarioBackend(MemoryBackend):
    def __init__(self, scenario):
        super().__init__()
        self.scenario = scenario
        self.clear_attempts = 0

    def set_location(self, point):
        super().set_location(point)
        if self.scenario == "set-disconnect":
            raise ConnectionError("Simulated disconnect after backend write")

    def clear_location(self):
        self.clear_attempts += 1
        if self.scenario == "clear-retry" and self.clear_attempts == 1:
            raise ConnectionError("Simulated clear failure")
        super().clear_location()


def run_scenario(name):
    if name not in SCENARIOS:
        raise ValueError("Unknown offline scenario")
    session = Session(ScenarioBackend(name))
    events = []

    def step(action, operation):
        try:
            operation()
        except (ConnectionError, RuntimeError) as exc:
            outcome = type(exc).__name__
        else:
            outcome = "accepted"
        events.append({"action": action, "outcome": outcome, "state": session.state.value})

    point = Coordinate(35.6812, 139.7671)  # Public example, not a user's location.
    step("set", lambda: session.set_location(point))
    if name == "set-disconnect":
        step("set-while-unknown", lambda: session.set_location(point))
    step("clear", session.clear_location)
    if name == "clear-retry":
        step("set-while-unknown", lambda: session.set_location(point))
        step("retry-clear", session.clear_location)
    return {
        "mode": "mock-scenario", "scenario": name,
        "device_accessed": False, "hardware_verified": False,
        "events": events, "final_state": session.state.value,
    }
