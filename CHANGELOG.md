# Changelog

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
