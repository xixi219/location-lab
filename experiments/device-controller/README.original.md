# Local experimental device controller

`device_control.py` is intentionally ignored by Git. It is a local experiment that invokes the
separately installed `pymobiledevice3` tooling. It is not bundled with, or published as, the Location Lab release.

The external CLI is GPL-3.0-or-later. Keeping this wrapper local does not make a future distribution or
licensing decision for the project. The controller requires an explicit local device identifier and never
prints it. It emits command acknowledgement state only; observe a map or a separate Core Location test app
before treating a set or clear command as real-world location evidence.

`dvt_clear_grace.py` holds the experimental DVT connection open for two seconds after clear because this
upstream selector has no reply. It is version-specific and still does not substitute for map observation.

`dvt_location_session.py` is a local-only, single-device supervisor. Once it owns a DVT location session,
each subsequent `set` changes coordinates over that same session rather than clearing to real location
between waypoints. It listens only on a user-private Unix socket and has no network listener. A failed or
interrupted recovery remains unverified; the script does not claim that the real location was restored.

`iphone_location.py` is the local entry point: it selects exactly one USB iPhone without displaying its
identifier, and still requires `--allow-device-write` for a set or clear. Typical local use is:

```sh
PYTHONPATH=src python3 -m location_lab places save --name "My place" --latitude <lat> --longitude <lon>
python3 private/iphone_location.py inspect
python3 private/iphone_location.py set --place "My place" --hold 300 --allow-device-write
python3 private/iphone_location.py clear --allow-device-write
```

The bounded `set` clears when its hold time ends. Without `--hold`, the local supervisor keeps the
single-device session alive so an operator can issue another explicit `set`; it does not perform an
unattended multi-stop route. For every set and clear, independently observe a map before treating the
result as verified.
