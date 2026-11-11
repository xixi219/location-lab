# Project instructions

- Communicate with the maintainer in Traditional Chinese; keep code identifiers English.
- Read README.md and docs/system-design.md before continuing.
- Distinguish IP changes from location simulation; never claim hardware verification without evidence.
- Keep core and mock tests offline. Current release has no device execution backend.
- Do not publish or mutate remote repositories without explicit authorization.
- Do not implement game detection evasion or certificate-pinning bypass.
- Prefer a Mac companion with an isolated device adapter; do not introduce a proxy/certificate installation implicitly.
- Retain attribution and licenses if importing code; do not assume subprocess use resolves GPL obligations.
- Run PYTHONPATH=src python3 -m unittest discover -s tests -v after behavioral changes.
- Record recovery failures as unknown device state, never as restored.
- Keep pairing records, UDIDs, real coordinates, certificates, private keys and logs out of commits.
