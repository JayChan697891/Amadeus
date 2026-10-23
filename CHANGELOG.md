# Changelog

## 0.3.0a9 — M5B3B1 durable candidate verification queue

Add a separate owner-only candidate queue with immutable checked input bindings,
historical idempotent receipts and version-fenced cancellation. Add schema10
tables without changing old snapshot verification semantics. No candidate
worker, lease, execution, task verification, approval consumption or apply.
Frozen local validation and independent Work acceptance remain required.

## 0.3.0a8 — M5B3B0 transaction-bound metadata capture

Extract a private owner-authenticated capture seam that reads the caller-owned
SQLite transaction without managing its lifetime. Preserve public capture and
existing export behavior. No candidate queue, schema change or execution gate.
Final validation and independent Work review remain required.

## 0.3.0a7 — M5B3A2 existing candidate input export

- Owner-only checked export of actual managed merge-candidate object content.
- Open existing storage without reconstruction; strict receipts/intents and pre/post Git identity checks.
- Reject bare and worktree Git redirects before Git, and verify applicable parent graph.
- Preserve bounded source/object rules; no jobs, execution, task completion, schema or apply changes.

## 0.3.0a6 — M5B3A1 candidate metadata binding

- Owner-only read-only capture of project-consistent candidate/worktree/snapshot/task records.
- Frozen metadata and canonical receipt fingerprints; strict stored JSON validation.
- No filesystem/Git validation, code execution, task gate, schema change or source apply.

## 0.3.0a5 — M5B2C explicit cleanup receipt

- Owner-only internal one-shot reconciliation for expired, acknowledged full-ID executions.
- Additive schema9 intent/receipt and fencing before any Docker side effect.
- Exact identity/image matching, removal acknowledgement and same-daemon absence observation.
- Cleanup observations never restore passed results or allow job reuse.
- No automatic recovery/retry, task acceptance, safe apply or real client relay; release blocked.

## 0.3.0a1 — M5A under development

- Default read-only membership and explicit project-owner role grants.
- Separate owner control plane and bounded, resource-pinned expiring approvals.
- Structured secret-free audit fields and authorization before cached responses.
- Security migration requires explicit write/review regrant for existing agents.
- No approved apply or arbitrary execution endpoint; final release remains blocked.


## 0.2.0a3 — M4B development checkpoint

- Independent managed Git object store and per-task worktrees; source checkout read-only.
- Real third-tree merge conflict detection, pinned commits and NUL-safe path reports.
- Immutable merge candidates await human approval; no user-branch apply endpoint.
- Schema v5, 29 shared-Core operations, source-config command-execution guards and
  interrupted side-effect replay bindings. Formal release remains blocked.


## 0.2.0a2 — M4-01/02 under verification

- Project-confined resource metadata and SHA-256 file version checks.
- Cooperative exclusive file/directory leases with versioned renewal/release and replay checks.
- Global physical-path conflicts prevent duplicate project registrations bypassing a lease.
- Schema v4 root identity and lock history; worktrees/Git conflict reports remain the next checkpoint.

## 0.2.0a1 — M3 under verification

- Project-scoped context revisions, source/summary metadata and literal substring search.
- Structured, version-pinned handoffs with explicit recipient decisions and sender withdrawal.
- Immediate lease invalidation on submission; identity-reserved next claims after resolution.
- SQLite schema v3 preserves M0-M2 data and review history. All transports use the same Core.
- This checkpoint covers M3; M4 file/worktree conflict protection remains planned.

## 0.1.0a2 — unreleased

- Added complete inference-free two-native-session collaboration and host restart probes.
- Added a safe native Codex MCP installer: no-overwrite checks, dry run, isolated Python
  prerequisite validation and registration readback. No GUI automation or paid model calls.
- Data-path inspection can avoid creating directories; existing Core behavior is unchanged.
- Desktop UI acceptance remains pending; a native host probe does not close it.

## 0.1.0a1 — unreleased

M0-M2 Alpha implementation under verification: local project/agent registration, transactional
task coordination, leases, versions, idempotency, separate review, persistence, MCP stdio,
Python SDK and authenticated loopback HTTP. Real desktop-client validation remains a distinct gate.
