# Amadeus a120 Windows development preview

Source: `859775bf3f1a1492153ba550d36f4ad2b146c58f`. This branch-stored preview is
not a formal Release. The original a118/a119 packages remain unchanged.

This preview fixes two CLI entry problems: `workflow start` no longer creates an
empty database when the project path is wrong, and `owner`/`workflow` return a
JSON `storage_error` instead of a traceback when the database cannot be opened.
The latter does not repair or replace a damaged database.

In the repository root, using Python3.11 or newer, create a separate environment:

```powershell
python -m venv .venv-a120
& .\.venv-a120\Scripts\python.exe -m pip install .\releases\0.3.0a120\preview-859775b\agentsync_local-0.3.0a120-py3-none-any.whl
& .\.venv-a120\Scripts\amadeus.exe demo --durable --data-dir "$PWD\local-data\amadeus-a120-01"
```

Choose a new data directory. The demo uses local simulated agents and reports
`simulation_only: true` / `verification: unverified`; it makes no model call.
For an owner-controlled project and separate CLI processes, follow
[the persisted workflow example](../../../examples/persisted_workflow.py).

The wheel and source archive have hashes in [SHA256SUMS](SHA256SUMS).
Actual local Windows3.12 validation passed19 native build/install checks and
21 focused tests in each fresh installation, with matching test identities and
97 runtime members bound to source/archive/install. These include malformed input,
missing/corrupt databases and normal owner/workflow operations. Original failures
and final results are retained in [the evidence](../../../docs/acceptance/evidence/core-preview-a120/summary.json).

Linux/macOS, the complete a120 suite/platform matrix and a120 real clients are
NOT RUN. Historical a119 live results keep their original scope. Full M6/M7 and
formal Release remain BLOCKED. No Actions, paid API, main merge or public release.
