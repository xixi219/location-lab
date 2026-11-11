# Contributing

This is an offline research prototype. Read docs/system-design.md and docs/compatibility.md first.
The public license is not selected yet; do not import third-party code without recording its license and provenance.

Run from the project root with Python 3.11+:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 run.py scenario clear-retry
```

Describe behavioral changes, tests and unverified hardware assumptions.
Keep device-dependent tests separate and opt-in. Do not claim a successful mock exercise is a hardware result.
Never include pairing records, personal coordinates, full UDIDs or credentials in commits or issues.
Update scripts/export_project.py FILES when adding deliverable files.
