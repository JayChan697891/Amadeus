# Error and limitation log

- Initial host Python did not include pip. Resolved by creating an isolated venv with ensurepip;
  no global Python changes required.
- Earlier conversation retrieval returned content references instead of the plan body.
  Resolved using the user's supplied full specification.
- Real desktop-client connectivity is a separate acceptance gate; never replace it with mock results.
- MCP v2 test initially used v1-style `inputSchema`; corrected to installed API `input_schema`.
- SQLite priority overflow escaped the error envelope; fixed with signed 64-bit schema bounds
  and independent regressions. Expected task versions are bounded before increment.
- CLI accepted 127.0.0.2 while HTTP rejected that Host; CLI now accepts the exact supported addresses.
- Reviews originally lacked persisted reviewer attribution; v2 history migration fixes provenance.
- Claude CLI root --mcp-config is not honored by mcp list. Used official MCP registration commands
  under an isolated configuration directory; health connected without a prompt or credentials.
- One-off Claude probe console could not print a Unicode check mark under cp1252; rerun UTF-8.
  This was a probe output issue, not a service failure.
- Clean-wheel Python 3.12 regression exposed PRAGMA journal_mode=WAL startup contention with
  eight fresh processes. Added bounded retry only for SQLITE_BUSY/LOCKED outside the migration
  transaction; unrelated failures still propagate. Retained race regression and expanded it to
  five fresh rounds (40 child initializers). Rebuild/reinstall verification recorded in TEST-REPORT.md.
