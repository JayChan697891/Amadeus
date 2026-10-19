# Verification report — current a2 and historical a1

## 0.1.0a2 continuation — 2026-10-19

- Source Python 3.14.6: `python -m pytest -q --junitxml=docs/pytest-m2-followup.xml`:
  **92 passed in 7.40s**.
- Installed a2 wheel Python 3.12.14: `python -I -m pytest -q --junitxml=docs/pytest-m2-followup-python312.xml`:
  **92 passed in 7.55s**. Ruff and mypy passed (15 source files).
- `python tests/manual/probe_codex_collaboration.py`: actual two native sessions and host restart
  preserve the exact task state/result/reviewer. No inference turns.
- `python examples/mcp_clients/install_codex.py`: actual shared entry installed; a second call
  returned already_configured. Independent TOML comparison found only equivalent removal of
  another server's empty args list by the native CLI; other settings are semantically preserved.
- `python tests/manual/probe_registered_codex.py`: actual shared config with no overrides,
  connected, 11 tools, expected AgentSync unauthorized envelope from a real call.
- User directly confirmed desktop MCP state: "已出现并显示已连接". This is user-observed UI evidence,
  kept separate from native probe results in desktop-connection-confirmation.json.

M2-05 connection gate is now closed. No automated desktop UI interaction, no model-driven
two-desktop development session, and no paid calls are claimed. See M2-CONTINUATION.zh-CN.md.
The 28 added automated cases validate installer mutation safety, pure data-path inspection,
and evidence structure/redaction. They are not represented as 28 new real-client calls.

## 0.1.0a1 historical checkpoint

Date: 2026-10-19, America/Tijuana. All results below were actually executed.

| Check | Command (project directory) | Actual result |
|---|---|---|
| Source suite, CPython 3.14.6 | `.venv/Scripts/python.exe -m pytest -q --junitxml=docs/pytest-results.xml` | **64 passed, 7.40s** |
| Clean wheel, CPython 3.12.14 | `work/clean312/Scripts/python.exe -I -m pytest -q --junitxml=docs/pytest-python312.xml` | **64 passed, 7.15s** |
| Static/style | `.venv/Scripts/python.exe -m ruff check .` | All checks passed |
| Types | `.venv/Scripts/python.exe -m mypy` | No issues in 15 source files |
| Build | `.venv/Scripts/python.exe -m build` | Wheel + source distribution built |
| Dependencies | `python -m pip check` in source and clean runtime envs | No broken requirements |
| Fresh wheel import | clean Python `-I`; assert site-packages import | 3.12.14, 0.1.0a1 |
| CLI | `python -I -m agentsync --data-dir ABSOLUTE_DEMO_DIRECTORY demo` | 2 agents, duplicate rejected, completed, persistence true |
| Codex native host | `python tests/manual/probe_codex_host.py` | Connected, 11 tools, 4 actual calls, zero model turns |
| Claude Code native host | `python tests/manual/probe_claude_host.py` | MCP health Connected; isolated config, no model prompt |

Raw results: pytest-results.xml and pytest-python312.xml. Host evidence:
codex-host-probe.json and claude-host-probe.json. Hostnames are removed from exported JUnit;
test names, counts, timings and outcomes are preserved.

## Behaviors checked

- 12 concurrent Core clients: one claim winner. Two interpreter subprocesses and two independent
  MCP subprocess connections also race one task with one winner. Five rounds of eight fresh
  processes initialize new databases (40 actual child initializers).
- Expired leases cannot renew/write/replay; reclaimed tasks reject former owners. Stale versions,
  forged/cross-project credentials and expired session heartbeat resurrection fail.
- Idempotent repeats preserve results; conflicting payloads and superseded lease requests fail.
- Dependency gates block early claims; self-review denied; reject/rework/resubmit/accept persists.
- v1 populated DB migration preserves data; new review author/time/evidence/version survives reopen.
- State/list and raw DB do not expose issued credentials. No submitted commands execute.
- Extreme integers, extra fields, malformed strings, NUL paths and invalid credentials fail safely.
- HTTP bearer, client IP, Host, malformed JSON, CORS boundaries; real loopback TCP requests.
- Server process exits; fresh SDK interpreter reads its persisted task.
- SDK -> HTTP claim/run/review -> SDK acceptance -> reopen state remains consistent.
- No model API key, model service, GPU or cloud account is needed for this core/demo.

## Actual defects found and repaired

1. MCP v2 property naming mismatch in integration test; fixed against installed API.
2. Missing review attribution; added transactional schema v2 history and readback.
3. SQLite integer overflow escaped envelopes; bounded input schemas and added regressions.
4. CLI accepted an HTTP-unsupported loopback alias; aligned supported hosts.
5. **Clean Python 3.12 wheel initially had 57 pass / 1 fail**: concurrent first startup hit
   `PRAGMA journal_mode=WAL: database is locked`. Added bounded retry only for SQLite transient
   lock codes outside migration transactions; tested propagation/deadline bounds; rebuilt,
   reinstalled, and obtained final 64/64 passing results above.

No failing tests were removed. Tests were extended for defects found during review.

## Acceptance limits

These results prove local coordination and tested transports/native host backends. They do not
prove desktop UI interaction or a complete two-desktop-AI-agent development session; M2-05 was partial
at a1, then closed for connection acceptance by the distinct a2 native and user-observed evidence above.
Review evidence is an attributed assertion, not automatically executed/verified by AgentSync;
that is M5. Locks/worktrees/control adapters/BYOK and v1.0 are not claimed. Linux/macOS/3.11
and remote GitHub Actions have not run.

## Ruff CI repair verification

Independent F-drive source verification: 92 passed in 7.51s, Ruff check and format
passed, mypy 15 source files passed, wheel/sdist built. See RUFF-CI-REPAIR.md and
the linked PR for the final nine-job GitHub Actions result.
