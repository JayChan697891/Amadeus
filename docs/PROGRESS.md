# Progress and recovery

Date: 2026-10-19 (America/Tijuana). Version: 0.2.0a1 under development.
Current execution scope: **M3-01..04**, Issue #4. M4-M9 remain planned.
M3 local verification: 142 tests passed, full-repository Ruff lint/format and mypy
(16 source files) passed; wheel/sdist built. Clean-wheel and remote CI acceptance
are recorded in M3-REPORT.md and the associated PR before Work signs off.
The table below records the historical M0-M2 checkpoint. Its Ruff repair PR #3 was
independently accepted by Work at 3c429ea, with all 9 CI jobs and their artifacts
verified. PR #3 remains unmerged. M3 development is based on that accepted branch.

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

Historical limitation updated: Windows/Linux/macOS x Python 3.11/3.12/3.14 passed
remote CI for PR #3. Independent verification of submitted in-product review evidence
remains M5. Project-enrolled identities are not external OAuth identities. GitHub
publication and owner-only Codex Cloud setup were subsequently user-authorized.
No paid provider API calls or public package Releases were made.

## Resume steps

1. Read AGENTS.md, WORKFLOW.md, PLAN.md, this file, CONTRACT.md and TEST-REPORT.md; inspect Git status.
2. Preserve verified coordination rules and the existing failure regressions.
3. M2-05 connection gate is closed; preserve distinction between user UI confirmation and native probes.
4. M3-01..04 is implemented; finish its independent wheel/remote/Work acceptance gate.
5. Continue M4 path boundaries, cooperative locks, isolated Git worktrees and conflict detection.
6. Continue M5-M9 from PLAN.md; record evidence and checkpoints at each stage.

## Ruff CI follow-up

Issue #2: Codex repaired full-repository Ruff violations without runtime changes.
Local 92 tests, lint, format, types and build passed. PR-head remote matrix is the
acceptance gate; see RUFF-CI-REPAIR.md. main remains unchanged.
