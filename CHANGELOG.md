# Changelog

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
