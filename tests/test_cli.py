import contextlib
import io
import json
import unittest
from location_lab.cli import main


class CliTests(unittest.TestCase):
    def run_cli(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(argv)
        self.assertEqual(code, 0)
        return json.loads(out.getvalue())

    def test_demo_is_explicit_mock(self):
        result = self.run_cli(["demo", "--latitude", "35", "--longitude", "139"])
        self.assertEqual(result["mode"], "mock")
        self.assertEqual(result["states"], ["active", "cleared"])
        self.assertFalse(result["hardware_verified"])

    def test_plan_is_not_execution(self):
        result = self.run_cli(["plan", "set", "--latitude", "0", "--longitude", "-74"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["argv"][-1], "-74.0")

    def test_clear_without_coordinate(self):
        self.assertEqual(self.run_cli(["plan", "clear"])["mode"], "plan-only")

    def test_invalid_cli_returns_usage_error(self):
        for argv in (["demo"], ["plan", "set", "--latitude", "1"],
                     ["demo", "--latitude", "nan", "--longitude", "0"],
                     ["plan", "clear", "--longitude", "1"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exc:
                    main(argv)
                self.assertEqual(exc.exception.code, 2)
