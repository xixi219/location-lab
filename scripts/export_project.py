"""Create a deterministic source ZIP from an explicit allowlist."""
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "SECURITY.md", "CONTRIBUTING.md", "docs/system-design.md",
    "docs/compatibility.md", 
    ".gitignore", "AGENTS.md", "README.md", "THIRD_PARTY_NOTICES.md",
    "pyproject.toml", "run.py", "scripts/export_project.py",
    "docs/architecture.md", "docs/diagrams.md", 
    "docs/research.md", "docs/roadmap.md", "docs/testing.md",
    "docs/transfer.md", "docs/validation.md",
    "src/location_lab/__init__.py", "src/location_lab/__main__.py",
    "src/location_lab/cli.py", "src/location_lab/core.py",
    "src/location_lab/planner.py", "src/location_lab/scenarios.py", "src/location_lab/places.py",
    "tests/test_core.py", "tests/test_cli.py", "tests/test_scenarios.py", "tests/test_places.py",
    "src/location_lab/local_control.py", "tests/test_local_control.py", "docs/mac-usb-control.md",
    "src/location_lab/usb_transport.py", "src/location_lab/usb_worker.py", "tests/test_usb_transport.py", "tests/test_usb_controller.py",
    "src/location_lab/progress_journal.py", "src/location_lab/device_boundary.py",
    "tests/test_progress_journal.py", "tests/test_device_boundary.py",
    "src/location_lab/next_stop.py", "src/location_lab/next_stop_web.py",
    "tests/test_next_stop.py", "tests/next_stop_ui_test.js", "docs/next-stop.md",
    "tests/test_export.py", "experiments/README.md",
    "experiments/device-controller/README.original.md",
    "experiments/device-controller/device_control.py",
    "experiments/device-controller/iphone_location.py",
    "experiments/device-controller/dvt_clear_grace.py",
    "experiments/device-controller/dvt_location_session.py",
    "experiments/device-controller/plus_code.py",
    "experiments/device-controller/DEPENDENCY_VERSIONS.txt",
    "experiments/device-controller/MANIFEST.sha256",
)


def export(root=ROOT):
    entries = {}
    for name in sorted(FILES):
        path = root / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Expected regular project file: {name}")
        entries[name] = path.read_bytes()
    entries["MANIFEST.sha256"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in entries.items()
    ).encode()
    output = root / "dist" / "location-lab-source.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            info = ZipInfo("location-lab/" + name, date_time=(2026, 11, 7, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n")
    return output


if __name__ == "__main__":
    print(export())
