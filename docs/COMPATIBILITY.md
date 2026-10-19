# Compatibility matrix

Actual Windows checks, 2026-10-19. See TEST-REPORT.md for commands and serialized evidence.

| Environment/client | Actual result | Boundary |
|---|---|---|
| Windows / CPython 3.14.6 source | 92 tests pass; Ruff/mypy pass | a2 source environment |
| Windows / CPython 3.12.14 clean wheel | 92 tests pass; a2 installed | No editable/source fallback |
| Python 3.11 | Dependency metadata checked | Not executed locally |
| Linux / macOS | CI matrix configured | Not executed; no remote CI result claimed |
| Official MCP SDK 2.3.0 stdio client | Discovery/calls/two-process race pass | Protocol client, not desktop GUI |
| Installed Codex native app-server | Connected; 11 tools; create/register/create-task/list calls pass | Public API, ephemeral thread, zero model turns; desktop UI not tested |
| Native two-session collaboration | Create/claim/run/review/accept/restart reads pass | Real isolated host; no model or desktop UI automation |
| Actual registered Codex configuration | Connected; exact 11 tools; expected unauthorized call verified | No temporary CLI/thread config override |
| Current Codex desktop MCP UI | User confirmed agentsync appeared and connected | Direct user report, not automated screenshot/clicks |
| Installed Claude Code CLI | Native mcp list health Connected | Isolated config; no model prompt or tool workflow |
| Claude Desktop chat / Cursor desktop | Config examples supplied | Not connected in this task |
| Existing open desktop conversations | Not exercised | No control/modification claimed |
| Agent control adapters | M6 | Not implemented |

M2-05 connection acceptance is complete: actual registered native calls plus user-confirmed desktop
connection and a second native CLI attempt. A full model-driven two-desktop development session
is still not claimed. Original a1 results remain historical in TEST-REPORT.md.
MCP cooperation does not grant control over arbitrary existing desktop conversations.
