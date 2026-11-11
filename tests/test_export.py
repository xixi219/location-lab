import importlib.util
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("export_project", ROOT / "scripts" / "export_project.py")
EXPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)


class ExportTests(unittest.TestCase):
    def make_project(self, root):
        for name in EXPORTER.FILES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture: " + name + "\n")

    def test_export_includes_recovery_source_but_not_local_data(self):
        self.assertIn("src/location_lab/places.py", EXPORTER.FILES)
        self.assertIn("tests/test_places.py", EXPORTER.FILES)
        self.assertIn("experiments/device-controller/dvt_location_session.py", EXPORTER.FILES)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root)
            private = root / "private"
            private.mkdir()
            (private / "local-data.txt").write_text("excluded test fixture")
            (root / ".env").write_text("excluded test fixture")
            with ZipFile(EXPORTER.export(root)) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()),
                                 {"location-lab/" + name for name in EXPORTER.FILES}
                                 | {"location-lab/MANIFEST.sha256"})

    def test_export_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root)
            first = EXPORTER.export(root).read_bytes()
            self.assertEqual(first, EXPORTER.export(root).read_bytes())

    def test_export_rejects_symlinked_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root)
            source = root / "README.md"
            source.unlink()
            source.symlink_to(root / "AGENTS.md")
            with self.assertRaises(ValueError):
                EXPORTER.export(root)
