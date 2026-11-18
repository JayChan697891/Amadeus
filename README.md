> Published archive: versions and checksummed files are in [releases/](releases/). See [RECOVERY.md](RECOVERY.md) and [PUBLICATION-MANIFEST.json](PUBLICATION-MANIFEST.json). Earlier no-publication statements in historical development reports describe the pre-publication checkpoint.

# Amadeus

Free, MIT-licensed local coordination for multiple agents. Python SDK, MCP stdio and HTTP API
share one SQLite task system. No paid model, API key, cloud server or GUI is needed.

Status: **0.1.0a2 local Alpha checkpoint**. See [progress](docs/PROGRESS.md),
[test evidence](docs/TEST-REPORT.md) and [compatibility](docs/COMPATIBILITY.md).
Protocol tests do not establish Codex/Claude/Cursor desktop compatibility.
The current desktop MCP connection was confirmed by the user; real native tool/collaboration
probes passed independently. See [M2 continuation](docs/M2-CONTINUATION.zh-CN.md).

## Windows quick start

From this repository directory, with Python 3.11+ installed:

```powershell
py -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev-lock.txt
& .\.venv\Scripts\python.exe -m pip install -e . --no-deps
& .\.venv\Scripts\python.exe -m agentsync --data-dir "$PWD\local-data\demo" demo
& .\.venv\Scripts\python.exe -m pytest
```

No activation or PowerShell execution-policy changes are needed. Demo uses two simulated agents,
rejects the second claim, submits a result, records separate review and checks persistence.
Use a dedicated empty data directory for repeatable demo runs.
For runtime-only installation use requirements-lock.txt instead of the development snapshot.
Both files are exact Windows-tested snapshots, not universal cross-platform resolver locks.

## Interfaces

- Python: `from agentsync.sdk.client import AgentSyncClient`; use `.call(operation, **payload)`.
- MCP: `python -m agentsync --data-dir ABSOLUTE_PATH mcp`.
- HTTP: set a private `AGENTSYNC_HTTP_TOKEN`, then `python -m agentsync serve`.
  Default bind is 127.0.0.1:8765. POST `/v1/{operation}` with bearer authorization and JSON.
- See `examples/`, [operation contract](docs/CONTRACT.md), and [Chinese guide](README.zh-CN.md).

Every MCP process must use the same absolute data directory. Defaults are independent of cwd.
Never put the live WAL database on a network share. Keep project admin/session tokens private.
Stdio MCP hosts have local process access; Alpha is not a hostile-agent sandbox.

## Quality checks

```powershell
& .\.venv\Scripts\python.exe -m ruff check .
& .\.venv\Scripts\python.exe -m mypy
& .\.venv\Scripts\python.exe -m build
```

Review evidence is stored text, not verified execution. Task submitters cannot accept their own
work, but Alpha does not independently run or validate tests submitted by other agents.
Context sharing, locks, Git worktrees, control adapters, scheduling, BYOK models and usage
are M3-M9, recorded in [the plan](docs/PLAN.md). Model fees, if later enabled, are the user's.
The owner authorized this public source archive on 2026-10-19; no model services were called for publication.
