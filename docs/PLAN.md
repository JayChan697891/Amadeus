# AgentSync implementation plan

Baseline: user-approved specification v1.0, 2026-10-19 (see SPECIFICATION.md).
Current execution: **M0 -> M1 -> M2 only**. No paid provider calls or public publication.
Version 0.1.0a1 is an Alpha implementation; release gates are independently recorded.

| Stage | Work packages | Acceptance / continuation |
|---|---|---|
| M0 | M0-01 environment/install; M0-02 architecture/state machine; M0-03 Git/MIT/deps; M0-04 pytest/Ruff/types/CI; M0-05 recovery docs | Installable package, passing quality checks, local checkpoint |
| M1 | M1-01 identity/heartbeat; M1-02 projects/tasks/dependencies; M1-03 atomic claim/version/idempotency; M1-04 leases/reclaim; M1-05 SQLite/migrations/concurrency | Single claim winner; stale owners rejected; persistence |
| M2 | M2-01 official MCP stdio; M2-02 shared absolute DB; M2-03 Python SDK; M2-04 authenticated local HTTP; M2-05 real client configurations/connectivity | All transports share Core; protocol and desktop results reported separately |
| M3 | M3-01 context store; M3-02 FTS/source/version search; M3-03 structured handoff; M3-04 accept/reject/reassign | Agent B continues A's actual work from authorized handoff |
| M4 | M4-01 canonical path boundaries; M4-02 lock leases; M4-03 Git worktrees; M4-04 version/diff/conflict detection; M4-05 confirmed safe merge | Isolated parallel edits; manufactured conflicts detected |
| M5 | M5-01 permissions; M5-02 risk approvals; M5-03 redacted audit; M5-04 independent evidence checks; M5-05 security regression | Neither model assertions nor arbitrary submitted commands authorize acceptance |
| M6 | M6-01 adapter contract; M6-02 Mock; M6-03 Codex; M6-04 Claude; M6-05 Cursor/manager | Official supported interfaces, capability matrix, paid execution approval |
| M7 | M7-01 dependency scheduler; M7-02 capabilities/load; M7-03 optional BYOK; M7-04 decomposition/retries/budgets | Mock-only deterministic end-to-end before optional paid execution |
| M8 | M8-01 usage/source/unknown costs; M8-02 recovery/stress/performance | Do not invent third-party subscription usage or bills |
| M9 | M9-01 platform compatibility; M9-02 docs/license/build/release | Separately approved public push/release only |

Use one Core for every integration. Locks in M4 will be cooperative. Local SQLite WAL
must not be shared across machines/network filesystems. Native control adapters are M6,
not part of this batch. Review in Alpha records a separate reviewer's evidence assertion;
automatic verification of those claims is explicitly M5.

At every checkpoint update PROGRESS.md, TEST-REPORT.md, ERRORS.md and DECISIONS.md.
Never mark M2-05 complete merely because the official SDK client can call the server.
