import contextlib
import io
import json
import unittest
from location_lab.cli import main
from location_lab.scenarios import run_scenario


class ScenarioTests(unittest.TestCase):
    def test_normal(self):
        result = run_scenario("normal")
        self.assertEqual([e["state"] for e in result["events"]], ["active", "cleared"])
        self.assertFalse(result["device_accessed"])
        self.assertFalse(result["hardware_verified"])

    def test_partial_set_blocks_further_set_until_recovery(self):
        events = run_scenario("set-disconnect")["events"]
        self.assertEqual(events, [
            {"action": "set", "outcome": "ConnectionError", "state": "unknown"},
            {"action": "set-while-unknown", "outcome": "RuntimeError", "state": "unknown"},
            {"action": "clear", "outcome": "accepted", "state": "cleared"},
        ])

    def test_clear_failure_does_not_claim_recovery(self):
        events = run_scenario("clear-retry")["events"]
        self.assertEqual([e["state"] for e in events], ["active", "unknown", "unknown", "cleared"])
        self.assertEqual(events[1]["outcome"], "ConnectionError")
        self.assertEqual(events[2]["outcome"], "RuntimeError")
        self.assertEqual(events[-1]["action"], "retry-clear")

    def test_unknown_scenario_rejected(self):
        with self.assertRaises(ValueError):
            run_scenario("real-device")

    def test_cli_scenario_and_repeatability(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["scenario", "clear-retry"]), 0)
        self.assertEqual(json.loads(out.getvalue()), run_scenario("clear-retry"))

    def test_cli_unknown_scenario(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            main(["scenario", "real-device"])
        self.assertEqual(exc.exception.code, 2)
