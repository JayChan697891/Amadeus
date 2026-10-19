# Progress and recovery

Date: 2026-10-19 (America/Tijuana). Version: 0.1.0a2, local Alpha checkpoint.
Current execution scope: **M0-M2**. M3-M9 have not been started.

| Work | Evidence / status |
|---|---|
| M0-01 | Windows Python 3.14 source install; Python 3.12 clean wheel install |
| M0-02 | CONTRACT.md, ARCHITECTURE.md; state/identity/version/lease rules in Core |
| M0-03 | Local Git repo, MIT, exact direct pins and runtime/dev snapshots; no remote push |
| M0-04 | 92 tests on each interpreter; Ruff clean; mypy clean (15 source files); CI configured |
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
| M2-05 | **Connection gate complete**: registered native config/tools verified; user confirmed current desktop UI shows agentsync connected; Claude Code CLI also connected |

Native same-task Codex agents implemented core and integrations and independently reviewed security.
The lead inspected actual source, ran full checks, repaired review provenance, numeric bounds and
startup concurrency, rebuilt the package and retested the installed wheel.

Current source Python 3.14.6: `python -m pytest -q --junitxml=docs/pytest-m2-followup.xml`:
**92 passed in 7.40s**. Clean installed a2 wheel Python 3.12.14:
`python -I -m pytest -q --junitxml=docs/pytest-m2-followup-python312.xml`: **92 passed in 7.55s**.
Ruff: all checks passed. Mypy: 15 files, no issues. Build: wheel and source distribution built.
Pip check: no broken requirements. Details and limits: TEST-REPORT.md, COMPATIBILITY.md.

M2-05 was closed in this continuation: the public CLI installed the actual shared MCP entry,
native probes loaded that entry without overrides, and the user directly confirmed the desktop
UI displayed agentsync connected. UI observation is user-reported, not automated clicking or
screenshot evidence. A complete model-driven two-desktop development session remains a later
end-to-end scenario; it is not needed to claim that this M2 connection gate is complete.
See M2-CONTINUATION.zh-CN.md and the distinct probe/confirmation JSON records.

Linux/macOS/3.11 and remote CI have not run here. Independent verification of submitted review
evidence is M5. Project-enrolled identities are not external OAuth identities. No paid calls,
public pushes, published packages or public Releases were made.

## Resume steps

1. Read AGENTS.md, WORKFLOW.md, PLAN.md, this file, CONTRACT.md and TEST-REPORT.md; inspect Git status.
2. Preserve verified coordination rules and the existing failure regressions.
3. M2-05 connection gate is closed; preserve distinction between user UI confirmation and native probes.
4. Next authorized batch: M3-01..04 context/FTS/version/source and structured handoff.
5. Then M4 path boundaries, cooperative locks, isolated Git worktrees and conflict detection.
6. Continue M5-M9 from PLAN.md; record evidence and checkpoints at each stage.
