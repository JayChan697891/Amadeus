# Third-party runtime dependencies

Originally generated2026-10-19. The current technical material check on2026-11-18
binds frozen a122/5232e9e, its original wheel/source archive and the existing
Windows3.12/Linux3.14 inventories. All31 dependency versions and declarations in
this table match the current Windows inventory. Root rehashed43 recorded installed
license files: the project file matches LICENSE, and every dependency file has a
matching notice body after documented line-ending/outer-whitespace normalization.
[Actual comparison and bounded review](acceptance/evidence/core-preview-a122/license-material-review/summary.json).

The31 shared Linux distributions have the same versions/declarations. Of their35
recorded license files, two have different original hashes: pydantic-core and
rpds-py. Converting the Windows files from CRLF to LF reproduces both saved Linux
hashes exactly. This compares previously verified Linux evidence, not a new Linux
execution. Windows alone includes pywin32. The source archive contains the exact
current notices; the wheel contains only this project's package and metadata.
Neither archive bundles dependency wheels or native binaries.

This completes material integrity/coverage checking for those specified archives;
it does not resolve legal suitability or grant formal M9/Release acceptance.
Original inventory `license_review=pending` declarations remain unchanged. The
separate independent release decision and publication authorization are still
required; untested platforms and future dependency bundles are outside this check.
Project code is MIT; dependencies retain their own licenses. See
[THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).

The table records upstream metadata, not a complete classification of every bundled
component. In particular, pywin32's `PSF` label does not replace its component
licenses: its installed files include adodbapi under LGPL 2.1, Mark Hammond/Greg
Stein terms, Scintilla and Python historical terms, and MAPI MIT text and NOTICE.
Those texts are retained in THIRD-PARTY-NOTICES.txt. Cryptography's declared
`Apache-2.0 OR BSD-3-Clause` is an alternative-license expression; both license
texts are retained. The current Amadeus wheel/sdist do not bundle third-party
wheels, binaries or site-packages. Redistributing a dependency bundle would need
its own scope review. The complete multi-platform license/release review remains
pending; no frozen package, dependency or historical evidence was changed.

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
