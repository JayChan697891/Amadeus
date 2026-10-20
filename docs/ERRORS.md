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

## M5A security migration and evidence

Legacy members intentionally migrate to viewer; fixture writes require explicit
owner grants instead of relaxing policy. Unknown extra-field names can themselves
contain secrets, so validation errors report a fixed extra_field label. Audit-store
failure regressions prove transaction rollback and revoked cache refusal.

## PR14 Linux Git fixture maintenance race

Run39395631073 at d8bc57107a1c5f0737316deeb80ac1c089c17ed4 passed8/9 jobs.
Ubuntu Python3.14 source pytest failed the strict original-repository fingerprint
assertion: an empty .git/objects/maintenance.lock existed at the initial snapshot
and disappeared before the final snapshot. The remaining27 file hashes matched.
That job's independent wheel and sdist suites passed; this does not erase the
source failure. Failed artifact SHA256:
db2e0efade433415b6500424b56a627625f4e07fde6ce4d60630638eb05891a8.

Fixture Git commits allowed asynchronous automatic maintenance. Production Git
operations already set gc.auto=0 and maintenance.auto=false. Test setup now uses
the same per-command maintenance overrides, including when local repository
configuration requests maintenance. Full fingerprint assertions still include
every .git file; no lock path is ignored and no retry hides a mutation. Newhead
local checks and all9 CI jobs must be verified independently after this repair.

Independent runner review found inherited PYTEST_ADDOPTS could silently filter
all three suites to nonempty subsets, and wheel lacked the sdist post-run archive
stability check. Remove external pytest selection/plugin environment settings and
fail if the originally installed wheel disappears or changes. Keep regressions
for each suite's actual child environment and both wheel mutation modes.

## M5B1 create-response loss and independent evidence

Independent review found cleanup was marked confirmed until Docker create returned
a usable ID. A daemon could create the container while its CLI reply timed out,
leaving an orphan with falsely confirmed cleanup. Mark cleanup unconfirmed BEFORE
create. Recover only by the exact random per-run name, validate its full ID/name/
owner label, then remove only that ID. Missing or mismatched recovery evidence is
an infrastructure error, never confirmed cleanup. Ten policy regressions cover
lost/invalid responses and recovery refusal. Durable process-crash reconciliation
remains future orchestration scope.

Docker CLI exit0 is also insufficient: inspect actual exited/nonrunning state and
candidate exit code, require every external typed JSON comparison, reject OOM,
fake JUnit, missing/extra output and enforce limits. Record policy simulations
separately from the required real Linux container acceptance job.

The first actual Docker run39437105068 (head227512a) failed14/14 cases at the
effective isolation check: isolation_mismatch, execution_started=false, cleanup
confirmed. Docker28.0.4/cgroup2 and the preloaded image were present, so this is
not missing Docker. Never mark this gate passed or skip it. Safe fixed control
booleans and bounded normalized metadata are added to identify the mismatch
without dumping raw configuration/environment. See the failure evidence index.
