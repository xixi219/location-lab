# Reference and dependency ledger

No upstream source, binaries, artwork, certificates or private keys are included in this prototype.

| Reference | Observed license | Use in this prototype |
| --- | --- | --- |
| OpenHRTT/wloc | MIT, project-owned code only | Architecture research; no copied implementation |
| doronz88/pymobiledevice3 | GPL-3.0-or-later (pyproject declaration; verified 2026-11-11) | Optional external SDK adapter, API pinned to 11.52.1; original glue only, SDK not installed or bundled |

WLoc copyright: (c) 2026 WLoc8.com contributors.
If WLoc code or substantial portions are reused, retain its copyright and MIT permission notice.
Its NOTICE points to THIRD_PARTY_NOTICES.md, but that file was absent from the observed main tree and returned 404 on 2026-11-07.
Audit dependencies individually before copying or distributing any WLoc component.

pymobiledevice3 integration/distribution needs a specific licensing decision before packaging.
Do not assume invoking a separate process automatically removes GPL obligations.
The current workspace has no public project license selected; this is not an MIT fork.

Sources:
- https://github.com/OpenHRTT/wloc/blob/54bd7378853d12c2e69aa7d7da33bc21c617d2c6/LICENSE
- https://github.com/OpenHRTT/wloc/blob/54bd7378853d12c2e69aa7d7da33bc21c617d2c6/NOTICE
- https://github.com/doronz88/pymobiledevice3/blob/776d601cec83b894c3ad0eeee8ab4db375a46e4a/LICENSE


The opt-in USB worker references official v11.52.1 interfaces without copying upstream bodies:
- https://github.com/doronz88/pymobiledevice3/blob/v11.52.1/pymobiledevice3/remote/userspace_tunnel.py
- https://github.com/doronz88/pymobiledevice3/blob/v11.52.1/pymobiledevice3/lockdown.py
- https://github.com/doronz88/pymobiledevice3/blob/v11.52.1/pymobiledevice3/services/dvt/instruments/location_simulation.py

Only original adapter scaffolding and doubles tests are included. No SDK install, hardware run,
or combined product distribution has been performed. Subprocess isolation is a lifecycle/security
boundary, not a resolution of licensing obligations; release licensing review is still required.
