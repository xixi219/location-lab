import tempfile
import unittest
from pathlib import Path

from location_lab.core import Coordinate
from location_lab.places import Place, PlaceStore, google_maps_url, route_plan


class PlaceTests(unittest.TestCase):
    def test_save_is_private_and_upserts_case_insensitively(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PlaceStore(Path(directory) / "places.json")
            store.save(Place("Tokyo", Coordinate(35.6812, 139.7671)))
            store.save(Place("tokyo", Coordinate(35.0, 139.0)))
            self.assertEqual([place.name for place in store.list()], ["tokyo"])
            self.assertEqual(store.list()[0].coordinate, Coordinate(35.0, 139.0))

    def test_route_is_plan_only_and_keeps_requested_order(self):
        route = route_plan([Place("B", Coordinate(1, 2)), Place("A", Coordinate(3, 4))])
        self.assertFalse(route["executed"])
        self.assertFalse(route["hardware_verified"])
        self.assertEqual([step["name"] for step in route["steps"]], ["B", "A"])
        self.assertIn("query=1%2C2", route["steps"][0]["google_maps_url"])
        self.assertIn("sustained observation", route["next_step_requirement"])

    def test_google_url_requires_no_key(self):
        self.assertEqual(google_maps_url(Coordinate(-33.8, -70.6)),
                         "https://www.google.com/maps/search/?api=1&query=-33.8%2C-70.6")
