# Security and privacy

Status: offline prototype. No device backend, network listener, pairing-store access or remote control is implemented.
Do not treat this as a production location service.

## Current boundary

The CLI validates coordinates and runs in-memory simulations or prints command plans.
Coordinates supplied to plan appear in its local stdout. Do not upload output containing private coordinates.
Test coordinates are public examples. No upstream source, certificates or pairing records are bundled.

## Required before device integration

- Explicitly select one owned, trusted device; never silently choose the first device.
- Keep pairing material in OS-protected storage; never accept it through public issues.
- Serialize writes per device. Mark timeouts/partial writes unknown; retry clear, not set.
- Persist minimal recovery state atomically; corrupted state must not imply successful recovery.
- Redact UDIDs, coordinates, certificates and tokens from exported diagnostics.
- Keep all privilege requests explicit and scoped; do not install certificates, reset devices or alter trust rules automatically.
- Pin and review dependencies before adding the device backend.
- If local HTTP control is added: loopback only initially, authenticated sessions, Origin/Host validation,
  CSRF protection, input limits, and no permissive CORS. LAN access requires a separate design.

No vulnerability reporting endpoint exists until the repository is created.
Do not put secrets or exploitable private-device information in public issues.
After repository creation, configure a private reporting channel before announcing security support.
