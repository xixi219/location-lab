import unittest
from location_lab.core import Coordinate, MemoryBackend, Session, State
from location_lab.planner import command_plan


class FaultBackend(MemoryBackend):
    fail_set = False
    fail_clear = False
    clears = 0

    def set_location(self, point):
        super().set_location(point)
        if self.fail_set:
            raise OSError("connection lost after write")

    def clear_location(self):
        self.clears += 1
        if self.fail_clear:
            raise OSError("disconnected")
        super().clear_location()


class CoreTests(unittest.TestCase):
    def test_coordinate_boundaries(self):
        for lat, lon in ((90, 180), (-90, -180), (0, 0)):
            self.assertEqual(Coordinate(lat, lon).latitude, lat)

    def test_reject_invalid_coordinates(self):
        for lat, lon in ((91, 0), (-91, 0), (0, 181), (0, -181),
                         (float("nan"), 0), (0, float("inf")),
                         (True, 0), ("35", 0), (None, 0)):
            with self.subTest(lat=lat, lon=lon), self.assertRaises(ValueError):
                Coordinate(lat, lon)

    def test_set_clear_lifecycle(self):
        backend = MemoryBackend()
        session = Session(backend)
        point = Coordinate(35, 139)
        session.set_location(point)
        self.assertEqual(session.state, State.ACTIVE)
        self.assertEqual(backend.point, point)
        session.clear_location()
        self.assertEqual(session.state, State.CLEARED)
        self.assertIsNone(backend.point)
        self.assertIsNone(session.point)

    def test_partial_set_failure_requires_clear(self):
        backend = FaultBackend()
        backend.fail_set = True
        session = Session(backend)
        with self.assertRaises(OSError):
            session.set_location(Coordinate(1, 2))
        self.assertEqual(session.state, State.UNKNOWN)
        self.assertIsNotNone(backend.point)
        with self.assertRaises(RuntimeError):
            session.set_location(Coordinate(3, 4))
        session.clear_location()
        backend.fail_set = False
        session.set_location(Coordinate(3, 4))
        self.assertEqual(session.state, State.ACTIVE)

    def test_failed_clear_can_retry(self):
        backend = FaultBackend()
        session = Session(backend)
        session.set_location(Coordinate(1, 2))
        backend.fail_clear = True
        with self.assertRaises(OSError):
            session.clear_location()
        self.assertEqual(session.state, State.UNKNOWN)
        self.assertIsNotNone(backend.point)
        backend.fail_clear = False
        session.clear_location()
        self.assertEqual(session.state, State.CLEARED)

    def test_idle_and_repeated_clear_reaches_backend(self):
        backend = FaultBackend()
        session = Session(backend)
        session.clear_location()
        session.clear_location()
        self.assertEqual(backend.clears, 2)

    def test_negative_coordinate_plan_ends_options(self):
        plan = command_plan("set", Coordinate(-33.8, -70.6))
        self.assertEqual(plan["argv"][-3:], ["--", "-33.8", "-70.6"])
        self.assertFalse(plan["executed"])
        self.assertFalse(plan["hardware_verified"])

    def test_clear_plan(self):
        self.assertEqual(command_plan("clear")["argv"][-1], "clear")

    def test_invalid_plan(self):
        for action, point in (("delete", None), ("set", None), ("clear", Coordinate(0, 0))):
            with self.subTest(action=action), self.assertRaises(ValueError):
                command_plan(action, point)
