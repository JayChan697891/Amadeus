# Error and limitation log

- Initial host Python did not include pip. Resolved by creating an isolated venv with ensurepip;
  no global Python changes required.
- Earlier conversation retrieval returned content references instead of the plan body.
  Resolved using the user's supplied full specification.
- Real desktop-client connectivity is a separate acceptance gate; never replace it with mock results.
- a2: agent-browser snapshots selected an empty detached page; stopped this route. Computer Use
  guidance forbids ChatGPT desktop UI automation, so no fallback UI action was performed. User
  manually confirmed the desktop server connected. Public native probes remained usable.
- a2: default documented app-server control socket was not available for the running desktop;
  no private IPC or renderer bridge was used to bypass that boundary.
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

## Published archive scripts failed full-repository Ruff

The nine-job run 39245887274 passed tests but failed lint because archive utilities
were newly included. Safe fixes plus formatting and an equivalent def replacement
resolved all violations; no rule suppression. See Issue #2 and RUFF-CI-REPAIR.md.

## M3 accepted handoff could strand pending work

Lead review found identity reservations lacked a deadline. Added a maximum 300-second
reservation capped at a valid session expiry, with recovery/replay regressions.
Old leases stay revoked. See M3-REPORT.md.

## M4A filesystem portability

Windows inode values require TEXT storage; lstat/fstat ctime semantics differ across
Python versions. Root pinning stores full identities and file inspection compares
ctime only within the same API. macOS conflict keys normalize NFC before casefolding.
Local Windows symlink tests skip when privilege 1314 is unavailable; junction and
hardlink tests execute. Platform-specific skips are never treated as passed cases.

## M4B lead-review repairs

Source clean/process filters and config includes could execute commands during Git
status; reject these source-local configurations before status/pack. Durable sidecar
receipts outlive SQLite rollback, so inputs must remain bound across crash retries;
real RED/GREEN regressions now prevent wrong snapshot/task/ordered-pair reuse.
Reject overlapping source and managed storage before mkdir. See M4B-REPORT.md.
