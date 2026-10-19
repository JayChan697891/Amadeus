# Compatibility matrix

Actual Windows checks, 2026-10-19. See TEST-REPORT.md for commands and serialized evidence.

| Environment/client | Actual result | Boundary |
|---|---|---|
| Windows / CPython 3.14.6 source | 64 tests pass; Ruff/mypy pass | Local source environment |
| Windows / CPython 3.12.14 clean wheel | 64 tests pass; isolated import/demo pass | No editable/source fallback |
| Python 3.11 | Dependency metadata checked | Not executed locally |
| Linux / macOS | CI matrix configured | Not executed; no remote CI result claimed |
| Official MCP SDK 2.3.0 stdio client | Discovery/calls/two-process race pass | Protocol client, not desktop GUI |
| Installed Codex native app-server | Connected; 11 tools; create/register/create-task/list calls pass | Public API, ephemeral thread, zero model turns; desktop UI not tested |
| Installed Claude Code CLI | Native mcp list health Connected | Isolated config; no model prompt or tool workflow |
| Claude Desktop chat / Cursor desktop | Config examples supplied | Not connected in this task |
| Existing open desktop conversations | Not exercised | No control/modification claimed |
| Agent control adapters | M6 | Not implemented |

M2-05 is partial under the strict original desktop-session wording. Native host connectivity
is established; a full user-facing desktop AI collaboration session remains pending.
MCP cooperation does not grant control over arbitrary existing desktop conversations.
