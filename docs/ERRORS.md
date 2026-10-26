2026-10-26: independently reproduced bare CapturedProcess factory hang (both adapter
deadlines/cancel and interpreter shutdown). Minimal cancel fix preserves unknown
slots; actual RED and same-reproducer GREEN retained. First root broad run failed35
CLI checks because its D wrapper omitted child source-path propagation; corrected
wrapper passed1019/2skip without product/test-rule changes. Old full Windows driver
failed cache-inclusive manifest despite1582/31skip and321 original files unchanged;
new driver disabled parent bytecode writes but child processes still added21
cache files, so original FAIL remains. Current fullWindows1587/31skip and all322
originalfiles unchanged are independently checked, no tests removed. Linux fresh install timed out600s,
outer transport1200s; recovered same-guest source98pass and NOT RUN package tests.
No install retry or timeout relaxation. Current Linux fullattempt exited2 after
one controlled SIGINT:1completedpass/4Coreinitialization30s timeout failures and
1anonymousunfinishedXMLrecord (neverpass); remaining/DockerNOTRUN. Source322
unchanged, no owned leftoverPython processes. Concurrency fixture lacks guaranteed
per-iteration child cleanup on exceptions; test-only repair now verified (10 independent Windows cases), without changing
8/5/30 limits or resolving the original Linux timeouts. Private per-phase journal
now preserves early failure evidence even if a later owned pytest fixture is
terminated; capped/incomplete evidence never grants acceptance.

D-only Linux driver correction verified: explicit JSON/env dictionary preserves AGENTSYNC_DOCKER_TEST_IMAGE and REQUIRE=1, asserted by a real child before pytest.26 previously unexecuted fixtures then passed with26 hashed actual JSON artifacts. Old complete-suite FAIL and VM-off NOT RUN remain preserved; no test/product safety relaxation or combined full-pass claim.

Complete Linux baseline driver error: a broad IMAGE placeholder replacement modified the required image environment-variable name. Actual26 fixture setup errors are preserved;1442 other tests passed,3 platform skips. Product source stayed unchanged. Fix the D-only driver and verify env names before a separate targeted run; never suppress mandatory Docker guards.

Claude D-draft classification defect: last assistant.message.stop_reason was ignored despite optimistic terminal flags. Root6failed regressions and independent repro retained; repaired last-assistant classification,77 parser/13 independent/97 combined checks passed. Real Claude was never launched. Root first-party Ruff import ordering and verifier skip-name assumptions were corrected separately; no test or check rule disabled.

Report-only encoding correction: two older Unicode paragraphs had been decoded using the host locale. Restored their original UTF-8 Git content and reapplied the latest additions. Product bytes and complete-suite evidence were unchanged.

## 2026-10-25 invocation/live checkpoint

The authorized integrated response succeeded once; original stderr retains a helper PATH-alias warning and model-list refresh timeout. No retry. Offline first attempts retain a test-helper UTF-8 decoding issue and a Windows lstat/fstat ctime comparison false rejection; final checks passed after targeted corrections. No full M6/M5 acceptance inferred.

# Error and limitation log

- M5B3A2 audit reproduced that a new regular .git redirect inside an otherwise
  unchanged captured bare repository could affect the first Git lookup. Export
  now rejects any such entry before the object boundary invokes Git, with separate
  implementer and independent adversarial regressions. All reproduction data was
  disposable. Service filesystem ABA races remain explicitly outside the atomicity
  guarantee; this library creates no passed task/execution state.

- M5B2C tracer: a real created-container process hard exit exposed the missing
  owner reconciliation operation. The new one-shot receipt is tested separately
  from automatic recovery. Unknown ACKs, initial absence and identity mismatches
  remain unresolved; interrupted cleanup intents cannot be retried in this stage.
  Local VM was restarted on D: for this continuation; no user service/data was
  used as a destructive fixture and no GitHub execution was requested.

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

## Local Linux reproduction: Docker environment removal markers

D-drive QEMU/Alpine reproduced14/14 failures with Docker29.8.2/cgroupv2. Only the
environment check was false; all other controls matched and no candidate executed.
A trusted fixed probe showed Config.Env contains bare GPG_KEY/PYTHON_VERSION/
PYTHON_SHA256 removal markers, but process os.environ excludes those names. Permit
only unique expected bare markers from the already-validated image configuration;
all valued entries still match the four fixed settings exactly. A fixed bootstrap
checks actual os.environ before reading candidate bytes. Added24 policy regressions;
114 policy cases pass. Unknown/duplicate markers or additional values still fail.

The remaining local canary case failed because Python3.12 Path.exists under/root
raises PermissionError for UID65534. Use an exclusively created host file under
traversable/tmp so a namespace leak would expose its existence, rather than mask
the probe with directory permission. Real local14case run then passed. Preserve
first-failure results and final frozen-tree results as distinct evidence.

## M5B3B1 development audit findings

An independent real Git/SQLite audit reproduced that changing a single valid
profile SHA or image ID column was accepted by get/cancel because the new queue
metadata initially did not include profile fields. The implementation now pins
kind/SHA/image inside verification_profile in the full metadata envelope and
cross-checks all three on every read. Three independent public-API regressions
verify rejection by get/list/cancel/enqueue replay after a one-column mutation.
The original two passing audit assertions demonstrate the defect reproduction;
they are not passing security acceptance cases.

A second trusted-profile fault injection used an enormous timeout integer and
revealed a raw OverflowError during profile validation. Validation must safely
map this to invalid_profile. Both findings require frozen full-suite regression
and separate independent repair confirmation before final stage acceptance.
