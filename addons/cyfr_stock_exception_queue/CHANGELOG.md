# Change log

## 19.0.1.0.0 — 2026-11-05

- First release candidate: bounded company/warehouse scans of nonconsigned internal stock and active orderpoints.
- Read-only exception queue with negative, below-minimum, persistent-zero and stale states. Persistent zero remains visible as a separate flag when a below-minimum condition takes priority.
- Five-minute fair rotation with one scope batch per invocation, a 50-location scope cap, bilingual guidance, Polish UI catalog, demo data and model/security tests.
