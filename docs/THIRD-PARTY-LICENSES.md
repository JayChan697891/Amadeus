# Third-party runtime dependencies

Inventory from installed package metadata and bundled license files. Generated 2026-10-19;
version labels checked against installed 0.3.0a112 on 2026-11-13 UTC. All 31 runtime
dependency versions, declarations and recorded license-file hashes match the retained
[Windows inventory](acceptance/evidence/m9-sdist-regression/repair-windows-sdist-license-inventory.json).
This metadata check does not change the pending final license/release review.
This covers the runtime transitive dependency closure, including Windows-only pywin32.
Project code is MIT; dependencies retain their own licenses. See THIRD-PARTY-NOTICES.txt.

The table records upstream metadata, not a complete classification of every bundled
component. In particular, pywin32's `PSF` label does not replace its component
licenses: its installed files include adodbapi under LGPL 2.1, Mark Hammond/Greg
Stein terms, Scintilla and Python historical terms, and MAPI MIT text and NOTICE.
Those texts are retained in THIRD-PARTY-NOTICES.txt. Cryptography's declared
`Apache-2.0 OR BSD-3-Clause` is an alternative-license expression; both license
texts are retained. The current Amadeus wheel/sdist do not bundle third-party
wheels, binaries or site-packages. Redistributing a dependency bundle would need
its own scope review. The complete multi-platform license/release review remains
pending; this clarification does not alter the frozen a114 artifacts under test.

| Package | Version | Declared license |
|---|---|---|
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| attrs | 26.1.0 | MIT |
| cffi | 2.1.1 | MIT-0 |
| click | 8.5.0 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| fastapi | 0.147.0 | MIT |
| h11 | 0.16.0 | MIT |
| httpcore2 | 2.15.1 | BSD-3-Clause |
| httpx2 | 2.15.1 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| mcp | 2.3.0 | MIT |
| mcp-types | 2.3.0 | MIT |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| pycparser | 3.11 | BSD-3-Clause |
| pydantic | 2.14.1 | MIT |
| pydantic_core | 2.50.1 | MIT |
| PyJWT | 2.15.1 | MIT |
| python-multipart | 0.0.32 | Apache-2.0 |
| pywin32 | 312 | PSF |
| referencing | 0.37.0 | MIT |
| rpds-py | 2026.9.1 | MIT |
| sse-starlette | 3.5.0 | BSD-3-Clause |
| starlette | 1.9.0 | BSD-3-Clause |
| truststore | 0.10.5 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
