# Progress and recovery

Date: 2026-10-19 (America/Tijuana). Version: 0.1.0a1, local Alpha implementation.
Current execution scope: **M0-M2**. M3-M9 have not been started.

| Work | Evidence / status |
|---|---|
| M0-01 | Windows Python 3.14 source install; Python 3.12 clean wheel install |
| M0-02 | CONTRACT.md, ARCHITECTURE.md; state/identity/version/lease rules in Core |
| M0-03 | Local Git repo, MIT, exact direct pins and runtime/dev snapshots; no remote push |
| M0-04 | 64 tests on each interpreter; Ruff clean; mypy clean (15 source files); CI configured |
| M0-05 | Plan, specification, progress, decisions, error log, compatibility and test report saved |
| M1-01 | Agent IDs, sessions, heartbeat, expiry and derived online state |
| M1-02 | Project-scoped access, tasks, immutable dependencies, priorities |
| M1-03 | SQLite atomic claims, expected versions, scoped idempotency; claim races tested |
| M1-04 | Renewable ownership leases, explicit expiration reclamation; stale owners rejected |
| M1-05 | WAL, transactional v1/v2 migrations, persistence, bounded startup contention handling |
| M2-01 | Official MCP SDK 2.3.0 stdio, 11 explicit typed tools |
| M2-02 | Two independent MCP server processes share the same absolute database; one claim winner |
| M2-03 | Python AgentSyncClient uses Core, consistent envelopes |
| M2-04 | Authenticated loopback HTTP, real TCP and ASGI tests, shared state with SDK |
| M2-05 | **Partially validated**: Codex native app-server actual tool calls; Claude Code CLI connected. Desktop UI sessions not exercised |

Native same-task Codex agents implemented core and integrations and independently reviewed security.
The lead inspected actual source, ran full checks, repaired review provenance, numeric bounds and
startup concurrency, rebuilt the package and retested the installed wheel.

Source Python 3.14.6: `python -m pytest -q --junitxml=docs/pytest-results.xml`:
**64 passed in 7.40s**. Clean installed wheel Python 3.12.14:
`python -I -m pytest -q --junitxml=docs/pytest-python312.xml`: **64 passed in 7.15s**.
Ruff: all checks passed. Mypy: 15 files, no issues. Build: wheel and source distribution built.
Pip check: no broken requirements. Details and limits: TEST-REPORT.md, COMPATIBILITY.md.

The strict desktop-session part of M2-05 remains open. Existing user client configurations were
not modified; no model inference was started. Codex native backend and Claude CLI results are
real connectivity evidence, not desktop UI tests. A complete two-desktop-agent AI development
session has not been demonstrated. This is a usable local Alpha checkpoint, not a claim that
every original M2 desktop acceptance condition is closed.

Linux/macOS/3.11 and remote CI have not run here. Independent verification of submitted review
evidence is M5. Project-enrolled identities are not external OAuth identities. No paid calls,
public pushes, published packages or public Releases were made.

## Resume steps

1. Read AGENTS.md, WORKFLOW.md, PLAN.md, this file, CONTRACT.md and TEST-REPORT.md; inspect Git status.
2. Preserve verified coordination rules and the existing failure regressions.
3. Close M2-05 with a supported desktop-host session, preferably a second host too; keep any
   model/service charging authorization separate.
4. After that gate, implement M3-01..04 context/FTS/version/source and structured handoff.
5. Then M4 path boundaries, cooperative locks, isolated Git worktrees and conflict detection.
6. Continue M5-M9 from PLAN.md; record evidence and checkpoints at each stage.
