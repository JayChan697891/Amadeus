# Release Acceptance Report

## Complete Linux baseline failure classified: 2026-10-25 America/Tijuana

The previously running44-module baseline248d0be suite has now finished **FAIL**:
1442pass /3 platform skips /26 fixture-setup errors /0 test-body failures.
Root independently parsed all1471 XML cases and checked source/log/JUnit hashes.
The D-only test driver accidentally replaced IMAGE inside the environment key
`AGENTSYNC_DOCKER_TEST_IMAGE`. Mandatory-image guards correctly rejected all26
Docker/reconciliation/owner fixtures; those real container cases were NOT RUN.
This is an actual failed attempt, not a passing Linux gate or a product fix.
Original logs/XML remain immutable. A corrected driver will run only the affected
subset separately; no fixture, timeout or isolation rule is relaxed.
See [failed-driver evidence](evidence/linux-driver-failure-20261025.json).
Formal release remains **BLOCKED**. Earlier RUNNING statements below record their
observation time and are superseded by this result.

## Current offline Claude projection checkpoint: 2026-10-25 America/Tijuana

Execution: Codex. Formal release **BLOCKED**; M5 five-item scope/exit checklist and
all42 formal requirements/16 scenarios remain NOT RUN. No real Claude client was
started. `parse_claude_jsonl` and the repository inspector are bounded offline
components, with fixed unverified/client-not-executed/billing-not-verified flags.
M6-04 now has4 exact component selectors and partial coverage, never acceptance.

| Latest45-module snapshot scope | Actual result |
|---|---|
| Source all unit + selected Core integration |977pass /2skip /0fail/error|
| Fresh offline wheel / isolated sdist components |603pass /1skip each /0fail/error|
| Root D parser/CLI independent run |97pass /1 Windows FIFO skip|
| Static checks |Ruff, format, mypy and diff passed|

Root independently parsed the actual XML and verified310 frozen source files,
all45 source/archive/installed module bytes, artifact hashes and noneditable
origins. Source skips are the existing unavailable Windows directory-symlink
fixture and the new POSIX FIFO fixture; package components skip only that FIFO.
The complete Windows1441pass/30skip below is the prior44-module product248d0be,
not a full suite of this newer snapshot. Linux complete248d0be is separate and
still needs its own final evidence; no new45-module Linux run is claimed.

Independent review reproduced an optimistic-success defect in the original
D-only draft when the final assistant was truncated/refused/tool-awaiting. Root
recorded6 failed cases, fixed last-assistant stop tracking, and verified77 parser
tests; a peer repeated77 plus13 independent cases. Failed/unknown/incomplete
results expose no final text. Later complete assistant output can recover earlier
truncation. Draft failures, test-fixture mistakes and final logs/XML remain in D.
The new CLI reveals only result byte sizes/hashes, not raw IDs/messages/tool data.

Supported input is a limited main-session stream-json subset, not full SDK
compatibility. Legal hook/user/partial/trailing-system streams outside that subset
are unsupported. Real Claude startup, permissions, cancellation, timeout, usage
authentication, autonomous relay and M9 remain NOT RUN/UNVERIFIED. No provider/API,
Actions, remote mutation, main modification or approval consumption was added.

Evidence: [Claude local checkpoint](evidence/claude-protocol-local-20261025.json)
and D:/agentsync-debug/CLAUDE-PROTOCOL-CHECKPOINT-20261025.json.

## Prior explicit invocation and limited actual-client checkpoint: 2026-10-25 America/Tijuana

Formal release **BLOCKED**; M5 five-item scope and B1–B6/D1–D5 remain unchanged.

Complete existing Windows `tests/` additionally executed against product commit
`248d0be9685fd3cb474b633c177f29947f6f3f21`: **1441pass /30skip /0fail/error**
(1471 actual XML cases), source305 files/44 runtime modules unchanged. Root checked
actual XML and hashes independently. Skips:26 Linux Docker/reconciliation/owner,
1 POSIX FIFO and3 Windows symlink privileges. See
[complete Windows evidence](evidence/full-windows-248d0be-20261025.json).
Two old Unicode report paragraphs were subsequently repaired from the original
UTF-8 Git baseline; no product bytes changed. Linux full-suite first VM-off attempt
is NOT RUN, retained at D:/agentsync-debug/full-linux-248d0be-yqhy0u4g; a separate
attempt after restoring the dedicated VM is still RUNNING, not counted as passed.
The new pure `CodexHostProfile` / `prepare_invocation` pins the executable SHA,
namespace, asserted CLI version and fixed readonly arguments. It does not launch,
discover credentials or authorize a task. Optional explicit child environments
are copied and bounded; excluded keys are not forwarded. This is not a sandbox
or proof that credentials cannot be read. Default adapter startup stays unsupported.

| Executed scope | Actual result |
|---|---|
| Source unit + selected Core integration |873pass /1 existing Windows symlink skip /0fail/error|
| Fresh offline wheel / isolated sdist components |499pass each /0skip/fail/error|
| Local Linux invocation/process/protocol/Mock components |421pass /0skip/fail/error|
| Ruff / format / mypy / diff |pass;225 formatted files;47 typed source files|
| One separately authorized installed-wheel actual CodexAdapter run |starting → running → succeeded; exit0; exact synthetic reply;4 authentic events|

Root verified302 frozen files,44 runtime modules, actual XML, artifact hashes,
installed bytes and command journals. The live run used that same installed wheel,
one factory invocation, fixed plan and explicit environment, with ChatGPT login,
no API-key environment and no extra credits available at preflight. Nineteen
temporary Git/project file hashes and Core tasks before/after/reopen are identical;
the task remains pending. Billing ledger was not verified. One helper-PATH warning
and model-list refresh timeout remain in original stderr; no retry was performed.

Evidence: [offline summary](evidence/codex-invocation-local-20261025.json),
[limited actual integration](evidence/codex-adapter-integrated-smoke-20261025.json),
its authentic JSONL and D:/agentsync-debug/codex-adapter-live-in0z00f4/.
Offline evidence remains distinct from the separately authorized live run.
All42 formal requirements remain NOT RUN. M6-03 is partial/unverified; this does
not validate permissions, server cancellation, real timeout, restart idempotency,
Claude/Cursor, dual-agent autonomous relay or M9. Product verification flags remain
unverified. No Actions, main modification or remote mutation was performed.
Initial test-helper encoding failure and Windows metadata-comparison false
rejection are retained in D-drive evidence, with their eventual passing checks.

## Prior host-factory lifecycle checkpoint: 2026-10-25 America/Tijuana

Formal release **BLOCKED**. M5 remains exactly the five original requirements;
its B1–B6/D1–D5 and unique final exit conditions are unchanged.

The six-method CodexAdapter prototype now composes typed host-factory process
capture and JSONL observation. No built-in live launcher or Core endpoint exists;
default start is unsupported. Unknowns hold instance slots; local cancellation
never acknowledges server cancellation. Shared/preexisting capture routing was
reproduced with2 actual failed tests and fixed without killing the first owner.
Old source SHA71934cb8 is retained as nonexecuting text for reproduction.

| Scope | Actual result |
|---|---|
| Source all unit + selected Core integration |851pass/1 existing Windows symlink skip/0fail/error|
| Fresh offline wheel / isolated sdist components |477pass each, zero skips/failures/errors|
| Local Linux adapter/process/protocol/Mock components |399pass, zero skips/failures/errors|
| Root targeted adapter/Mock/start-cancel/Core regression |116pass|
| Ruff / format / mypy / diff |pass;221 files formatted;46 typed source files|

Root independently parsed all XML and verified296 frozen source files,43 runtime
modules, built artifact hashes, noneditable installation origins, installed bytes
and command/log journals. Source JUnit alias `junit.xml` is byte-identical to the
original `source-unit.xml`, not synthetic data. Requirement criteria/scenarios and
all42 formal not_run statuses are unchanged. M6-03 has8 exact component selectors
but remains partial/unverified. Synthetic guard tests do not count as real clients.

Three public Core/SQLite cases preserve full task/project state and reopen state;
the protocol result does not complete a Core task or grant permissions. One public
event-loop factory-delay test covers start-caller cancellation and late-parent
termination; this controlled test does not verify strict actual OS launch timing.

This continuation made zero actual CLI/model/API calls. The earlier single real
CLI smoke remains separate; its authorization is consumed. Real live adapter,
server cancellation, strict OS launch bounds, process-tree cleanup, cross-instance
or restart idempotency, Claude/Cursor/real relay and M9 remain unverified/not_run.
Never-returning factory work can remain pending after a logical unknown deadline.
The host must keep the event loop alive for late cleanup. See [M6-ADAPTERS.md](../M6-ADAPTERS.md).

Evidence: [codex-adapter-local-20261025.json](evidence/codex-adapter-local-20261025.json),
D:/agentsync-debug/CODEX-ADAPTER-LOCAL-CHECKPOINT-20261025.json and the referenced
logs/JUnit/builds. The initial local Linux VM-off NOT RUN and the three initial
Core fixture setup errors are retained, not counted as passes. No Actions,
remote mutations, main modifications or paid provider calls were used.

## Prior local checkpoint: 2026-10-25 America/Tijuana

Execution: Codex. Formal release acceptance: **BLOCKED**. M5 is frozen to its
original five requirements; its only exit checklist is
[M5-FINAL-ACCEPTANCE.md](../M5-FINAL-ACCEPTANCE.md). No new M5 substage is opened.

After validation, the36 changed project files were frozen locally on
`feature/m6-local-prototype-20261025`, product commit
`b70cd1b9671de3910979b66f8c711b0f0f1f51af` / tree
`624e231fc050f3c9035390520d3f6a2fe6786734`. All42 Git module blobs match the
tested source, built archives and installed modules. This receipt-only report
update does not rerun product tests or grant M5 acceptance. The branch was not
pushed; main and PR25 remain unchanged. See
[local freeze receipt](evidence/m6-local-freeze-20261025.json).

Base HEAD aac28a0f688962eca640b930e92eeaa608ff824f, version0.3.0a11/schema12.
The tested product is an uncommitted290-file snapshot, not a newly accepted Git
commit. Root independently checked source/package/installed42-module bytes,
actual JUnit counts and saved log/attempt hashes. Subsequent changes to this
report/progress/evidence summary are documentation only, not another test run.

| Executed local scope | Actual result | Evidence |
|---|---|---|
| Source all unit + selected Core integration |811pass/1 explicit Windows symlink skip/0fail/error|D:/agentsync-debug/local-process-capture-7hiuiaq7/source-unit.xml|
| Fresh offline wheel installation, component suite |437pass/0skip/fail/error|same root/wheel-junit.xml; wheel-origins.json|
| Fresh isolated sdist installation, component suite |437pass/0skip/fail/error|same root/sdist-junit.xml; sdist-origins.json|
| Existing local Linux VM process/protocol/trace components |287pass/0skip/fail/error|D:/agentsync-debug/process-capture-linux-gqcwjy9z/junit.xml|
| Ruff / format / mypy / diff |pass;217 files formatted;45 typed source files|root local checks and native saved logs|
| Prior complete Windows suite, before new protocol/process code |1303pass/30skip/0fail/error|D:/agentsync-debug/CURRENT-LOCAL-FULL-CHECKPOINT-20261024.json; not a complete run of this later snapshot|
| One authorized actual Codex CLI no-tools inline-fixture smoke |exit0;4 events;reply hash matched;19 fixture files unchanged|evidence/codex-readonly-cli-smoke-20261025.json and .jsonl|

New functionality: bounded single-turn Codex event parsing; repository CLI emits
only message size/hash summaries; trusted-host parent-process capture supports
bounded stdout/stderr, automatic execution deadline observation, cancellation and
stable terminal records.24 tests use known local Python helpers, not Codex.
`exited` means a process exit, not task success. Parent-only termination, inherited
environment and unverified descendant cleanup are explicit. Startup handshake
before a transport exists is not guaranteed to finish within the execution
deadline; cancellation during that handshake remains NOT RUN. No real client is
connected to this mechanical layer, and it is not an OS sandbox.

All42 formal requirement scenarios retain not_run; real adapter evidence retains
unverified. M6-03 partial coverage comes from protocol components, not the manual
CLI smoke being relabelled as adapter acceptance. Real CodexAdapter integration,
real cancellation/timeout, Claude, Cursor, automatic relay, independent verified
completion, approval consumption/safe apply and full M9 remain NOT RUN/UNVERIFIED.
M5-01/03 have historical limited VERIFIED evidence; current whole M5 is not VERIFIED.
B1–B6 and D1–D5 remain exactly in the unique M5 checklist.

The user separately authorized one subscription-only read-only model task. Actual
CLI0.164.0-alpha.11.1 used ChatGPT login and no API-key environment; no credit
purchase or account configuration change occurred. Original model-preflight
configuration failure is preserved separately: stdout empty, no model turn; its
reserved provider overrides were removed before the sole actual model task.
Usage is captured data, not independent billing verification. That authorization
is consumed; no additional actual model run was made.

Preserved non-passing attempts: two source-driver CLI import failures, one Linux
VM-off NOT RUN, native RED/fixture failures and nine GitHub detail transport
failures. The source driver was corrected to give source-only subprocesses the
same import path while fresh package tests keep isolated imports. Existing D-drive
VM was restarted after preserving old logs. No failure was deleted or counted as
pass.17 open PR descriptions and full Issues7/11 were read; nine full PR detail
reads remain LIMITED. No Actions, remote mutations, main edits or merge.

Evidence summary: [m6-local-prototype-20261025.json](evidence/m6-local-prototype-20261025.json).
Full root checkpoint: D:/agentsync-debug/M6-LOCAL-PROTOTYPE-CHECKPOINT-20261025.json.
This is a local development checkpoint, not product release approval.

## Historical frozen report: 0.3.0a10

Version: 0.3.0a10
Commit: 0fd2041c8efd1c4fa348117e013c0c5b1f30e470
Platform: Linux-6.18.54-0-virt-x86_64-with-musl1

Formal release acceptance: **BLOCKED**

| Check | Status | Evidence |
| --- | --- | --- |
| pytest | pass | logs/pytest.log |
| ruff | pass | logs/ruff.log |
| format | pass | logs/format.log |
| mypy | pass | logs/mypy.log |
| build | pass | logs/build.log |
| pip_check | pass | logs/pip_check.log |
| wheel_venv | pass | logs/wheel_venv.log |
| wheel_install | pass | logs/wheel_install.log |
| wheel_pip_check | pass | logs/wheel_pip_check.log |
| wheel_cli | pass | logs/wheel_cli.log |
| wheel_origin_sdk | pass | logs/wheel_origin_sdk.log |
| wheel_pytest | pass | logs/wheel_pytest.log |
| sdist_venv | pass | logs/sdist_venv.log |
| sdist_install | pass | logs/sdist_install.log |
| sdist_pip_check | pass | logs/sdist_pip_check.log |
| sdist_cli | pass | logs/sdist_cli.log |
| sdist_origin_sdk | pass | logs/sdist_origin_sdk.log |
| sdist_pytest | pass | logs/sdist_pytest.log |

## Distribution installations

| Format | Install status | Exact artifact | SHA-256 |
| --- | --- | --- | --- |
| wheel | pass | artifacts/agentsync_local-0.3.0a10-py3-none-any.whl | 7c5d7d61bd60f8fe2e1973530b163608b9b5c7ff468e1f6351ec6b944849e4ac |
| sdist | pass | artifacts/agentsync_local-0.3.0a10.tar.gz | 580912f3ad616f2cdeaf630642e7ddac96fef526ea220f619747c19cd2cf51ff |

## Per-requirement acceptance

Component test observations do not satisfy complete requirement acceptance. Planned evidence paths are targets, not existing files.

| Requirement | Title | Execution | Acceptance evidence | Coverage | Component selectors |
| --- | --- | --- | --- | --- | --- |
| M0-01 | Windows environment and local install | not_run | not_run | existing | tests/integration/test_transports.py::test_documented_sdk_import (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M0-02 | Architecture, state machine and shared interfaces | not_run | not_run | partial | tests/unit/test_core.py (junit.xml: 18 matched, 18 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 18 matched, 18 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 18 matched, 18 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_transports.py::test_sdk_http_share_one_persistent_workflow (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M0-03 | Git repository, MIT license and dependencies | not_run | not_run | partial | None implemented |
| M0-04 | Automated tests, Ruff, typing and CI | not_run | not_run | existing | None implemented |
| M0-05 | Plan, progress, errors and decisions recovery | not_run | not_run | partial | None implemented |
| M1-01 | Agent identity, session, heartbeat and online state | not_run | not_run | existing | tests/unit/test_core.py::test_heartbeat_extends_session_and_online_window (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_core_security.py::test_online_status_comes_from_heartbeat_not_registration (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_core_security.py::test_expired_session_cannot_heartbeat_or_replay_write (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M1-02 | Projects, membership, tasks and dependencies | not_run | not_run | partial | tests/unit/test_core.py::test_persistence_review_and_dependencies (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_core_security.py::test_session_and_project_credentials_are_bound (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M1-03 | Atomic task claims, versions and state transitions | not_run | not_run | existing | tests/concurrency/test_claims.py::test_only_one_concurrent_claim_wins (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_core_security.py::test_cross_process_claim_has_exactly_one_winner (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_core_security.py::test_idempotency_replay_collision_and_authentication (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_jobs.py (junit.xml: 40 matched, 40 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 40 matched, 40 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 40 matched, 40 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_candidate_queue_migration.py (junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped) |
| M1-04 | Task lease renewal, timeout and recovery | not_run | not_run | existing | tests/unit/test_core.py::test_expired_lease_replay_reclaim_and_new_owner (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_core_security.py::test_renewal_replay_does_not_extend_lease_and_expiry_still_wins (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M1-05 | SQLite persistence, transactions and migrations | not_run | not_run | partial | tests/concurrency/test_claims.py::test_concurrent_first_process_migrations (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_m3_migration.py (junit.xml: 3 matched, 3 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 3 matched, 3 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 3 matched, 3 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_m4_migration.py (junit.xml: 3 matched, 3 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 3 matched, 3 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 3 matched, 3 passed, 0 failures, 0 errors, 0 skipped) |
| M2-01 | Official MCP stdio server | not_run | not_run | existing | tests/integration/test_transports.py::test_real_mcp_stdio_tools_and_core (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_m3_transports.py::test_mcp_handoff_has_explicit_nested_typed_schema (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M2-02 | Multiple MCP processes share one state database | not_run | not_run | existing | tests/integration/test_transports.py::test_two_mcp_processes_share_atomic_claim (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M2-03 | Python SDK | not_run | not_run | existing | tests/integration/test_transports.py::test_documented_sdk_import (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_transports.py::test_sdk_http_share_one_persistent_workflow (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M2-04 | Authenticated local HTTP API | not_run | not_run | existing | tests/integration/test_live_http.py::test_real_loopback_http_and_process_restart (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_http_boundary.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped) |
| M2-05 | Real MCP client connection and configuration | not_run | unverified | partial | tests/integration/test_host_report.py (junit.xml: 9 matched, 9 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 9 matched, 9 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 9 matched, 9 passed, 0 failures, 0 errors, 0 skipped) |
| M3-01 | Authorized project context store | not_run | not_run | existing | tests/unit/test_context.py::test_context_history_idempotency_and_metadata (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_m3_security.py::test_context_and_handoff_project_isolation (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M3-02 | Context search, summaries, source and revisions | not_run | not_run | existing | tests/unit/test_context.py (junit.xml: 24 matched, 24 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 24 matched, 24 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 24 matched, 24 passed, 0 failures, 0 errors, 0 skipped); tests/concurrency/test_m3_races.py::test_context_update_concurrent_with_handoff_pins_requested_revision (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M3-03 | Structured handoff package | not_run | not_run | existing | tests/security/test_m3_security.py::test_handoff_pins_context_and_invalid_reference_is_atomic (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_m3_transports.py::test_http_m3_operations_share_sdk_core_and_fixed_snapshots (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M3-04 | Handoff acceptance, rejection, withdrawal and reassignment | not_run | not_run | partial | tests/integration/test_m3_transports.py::test_real_independent_mcp_client_process_handoff (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/concurrency/test_m3_races.py::test_resolve_withdraw_race_never_changes_completed_decision (junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_m3_security.py (junit.xml: 16 matched, 16 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 16 matched, 16 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 16 matched, 16 passed, 0 failures, 0 errors, 0 skipped) |
| M4-01 | Workspace path validation and canonical identity | not_run | not_run | existing | tests/security/test_resource_paths.py (junit.xml: 43 matched, 41 passed, 0 failures, 0 errors, 2 skipped; wheel-junit.xml: 43 matched, 41 passed, 0 failures, 0 errors, 2 skipped; sdist-junit.xml: 43 matched, 41 passed, 0 failures, 0 errors, 2 skipped) |
| M4-02 | Cooperative file/directory locks and leases | not_run | not_run | existing | tests/security/test_file_locks.py (junit.xml: 24 matched, 23 passed, 0 failures, 0 errors, 1 skipped; wheel-junit.xml: 24 matched, 23 passed, 0 failures, 0 errors, 1 skipped; sdist-junit.xml: 24 matched, 23 passed, 0 failures, 0 errors, 1 skipped); tests/concurrency/test_file_lock_races.py::test_two_independent_processes_have_exactly_one_lock_winner (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_m4_transports.py (junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped) |
| M4-03 | Independent Git worktrees | not_run | not_run | existing | tests/integration/test_m4b_workspaces.py::test_committed_only_capture_and_independent_owned_worktrees_preserve_original (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_m4b_workspaces.py::test_concurrent_create_request_has_one_owned_worktree_and_restart_replays (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M4-04 | File versions, diffs and merge conflict detection | not_run | not_run | existing | tests/security/test_resource_paths.py::test_unicode_backslashes_hash_changes_missing_and_directory (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_resource_paths.py::test_mutation_during_real_hash_read_is_explicitly_unstable (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_m4b_workspaces.py::test_actual_same_line_conflict_uses_third_tree_and_preserves_both_actors (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_m4b_workspaces.py::test_dirty_and_stale_worktree_inputs_fail_without_discarding_edits (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_m4b_workspaces.py::test_nul_parsed_unicode_and_space_filenames_survive_conflict_comparison (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_candidate_binding.py (junit.xml: 25 matched, 25 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 25 matched, 25 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 25 matched, 25 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_binding_git_records.py (junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_export.py (junit.xml: 36 matched, 36 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 36 matched, 36 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 36 matched, 36 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_export_security.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped) |
| M4-05 | Safe merge policy and human approval | not_run | not_run | partial | tests/integration/test_m4b_workspaces.py::test_nonconflicting_candidate_awaits_approval_and_replay_is_immutable (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M5-01 | Identity, project and operation authorization | not_run | not_run | existing | tests/security/test_core_security.py (junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_m3_security.py (junit.xml: 16 matched, 16 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 16 matched, 16 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 16 matched, 16 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_file_locks.py::test_only_owning_session_can_mutate_even_for_same_agent (junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_m5_permissions.py (junit.xml: 167 matched, 167 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 167 matched, 167 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 167 matched, 167 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_jobs.py (junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_executor.py (junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_owner_execution.py (junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_reconciliation.py (junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_execution_reconciliation.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_candidate_binding.py (junit.xml: 25 matched, 25 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 25 matched, 25 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 25 matched, 25 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_binding_git_records.py (junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_export.py (junit.xml: 36 matched, 36 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 36 matched, 36 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 36 matched, 36 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_export_security.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_jobs.py (junit.xml: 40 matched, 40 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 40 matched, 40 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 40 matched, 40 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_candidate_queue_migration.py (junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_queue_security.py (junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_claims.py (junit.xml: 34 matched, 34 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 34 matched, 34 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 34 matched, 34 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_claim_migration.py (junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped) |
| M5-02 | High-risk approvals and default read-only execution | not_run | not_run | partial | tests/integration/test_m5_governance.py (junit.xml: 8 matched, 8 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 8 matched, 8 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 8 matched, 8 passed, 0 failures, 0 errors, 0 skipped); tests/concurrency/test_m5_approval_races.py (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped) |
| M5-03 | Structured redacted audit logs | not_run | not_run | existing | tests/security/test_core_security.py::test_secrets_absent_from_state_list_and_database (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_core.py::test_strict_schema_and_no_secret_validation_echo (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_m5_audit_transactions.py (junit.xml: 3 matched, 3 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 3 matched, 3 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 3 matched, 3 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_m5_governance.py (junit.xml: 8 matched, 8 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 8 matched, 8 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 8 matched, 8 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_jobs.py (junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_executor.py (junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_owner_execution.py (junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_reconciliation.py (junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_execution_reconciliation.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_claims.py (junit.xml: 34 matched, 34 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 34 matched, 34 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 34 matched, 34 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_claim_migration.py (junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped) |
| M5-04 | Independent acceptance criteria and evidence verification | not_run | not_run | partial | tests/integration/test_acceptance.py::test_dependency_review_rejection_rework_and_persistence (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_core_security.py::test_owner_version_and_review_identity_are_enforced (junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 1 matched, 1 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_snapshot.py (junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_docker.py (junit.xml: 139 matched, 139 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 139 matched, 139 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 139 matched, 139 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_docker_verifier.py (junit.xml: 14 matched, 14 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 14 matched, 14 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 14 matched, 14 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_jobs.py (junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_executor.py (junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_owner_execution.py (junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_reconciliation.py (junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_execution_reconciliation.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_candidate_binding.py (junit.xml: 25 matched, 25 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 25 matched, 25 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 25 matched, 25 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_binding_git_records.py (junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_export.py (junit.xml: 36 matched, 36 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 36 matched, 36 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 36 matched, 36 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_export_security.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_jobs.py (junit.xml: 40 matched, 40 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 40 matched, 40 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 40 matched, 40 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_candidate_queue_migration.py (junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_queue_security.py (junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_claims.py (junit.xml: 34 matched, 34 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 34 matched, 34 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 34 matched, 34 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_claim_migration.py (junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped) |
| M5-05 | Security regression and untrusted tool output | not_run | not_run | partial | tests/security/test_http_boundary.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_core_security.py::test_strict_schemas_reject_unknown_and_coerced_fields (junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_m3_security.py::test_replayed_writes_and_reads_always_authenticate (junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_m5_permissions.py (junit.xml: 167 matched, 167 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 167 matched, 167 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 167 matched, 167 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_m5_migration.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped); tests/security/test_m5_owner_cli_inputs.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_snapshot.py (junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_docker.py (junit.xml: 139 matched, 139 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 139 matched, 139 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 139 matched, 139 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_docker_verifier.py (junit.xml: 14 matched, 14 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 14 matched, 14 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 14 matched, 14 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_jobs.py (junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_executor.py (junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_owner_execution.py (junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_reconciliation.py (junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_execution_reconciliation.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_candidate_binding.py (junit.xml: 25 matched, 25 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 25 matched, 25 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 25 matched, 25 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_binding_git_records.py (junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 2 matched, 2 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_export.py (junit.xml: 36 matched, 36 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 36 matched, 36 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 36 matched, 36 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_export_security.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_jobs.py (junit.xml: 40 matched, 40 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 40 matched, 40 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 40 matched, 40 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_candidate_queue_migration.py (junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_queue_security.py (junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_claims.py (junit.xml: 34 matched, 34 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 34 matched, 34 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 34 matched, 34 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_candidate_claim_migration.py (junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 4 matched, 4 passed, 0 failures, 0 errors, 0 skipped) |
| M6-01 | Uniform adapter lifecycle and capability declarations | not_run | not_run | missing | None implemented |
| M6-02 | MockAdapter for multiple simulated agents | not_run | not_run | missing | None implemented |
| M6-03 | Real Codex control adapter | not_run | unverified | missing | None implemented |
| M6-04 | Real Claude Code control adapter | not_run | unverified | missing | None implemented |
| M6-05 | Real Cursor adapter and run manager | not_run | unverified | missing | None implemented |
| M7-01 | Dependency graph and deterministic scheduling | not_run | not_run | missing | None implemented |
| M7-02 | Capability, availability and load allocation | not_run | not_run | missing | None implemented |
| M7-03 | Optional BYOK multi-model providers | not_run | not_run | missing | None implemented |
| M7-04 | AI-assisted decomposition, retries and budgets | not_run | not_run | missing | None implemented |
| M8-01 | Usage, cost, elapsed time and failure rate | not_run | not_run | missing | None implemented |
| M8-02 | Recovery, retry, performance and concurrency stress | not_run | not_run | missing | tests/unit/test_verification_jobs.py (junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 26 matched, 26 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_executor.py (junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 35 matched, 35 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_owner_execution.py (junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped); tests/unit/test_verification_reconciliation.py (junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 43 matched, 43 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_execution_reconciliation.py (junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 5 matched, 5 passed, 0 failures, 0 errors, 0 skipped) |
| M9-01 | Windows, Linux and macOS compatibility | not_run | not_run | partial | tests/security/test_resource_paths.py (junit.xml: 43 matched, 41 passed, 0 failures, 0 errors, 2 skipped; wheel-junit.xml: 43 matched, 41 passed, 0 failures, 0 errors, 2 skipped; sdist-junit.xml: 43 matched, 41 passed, 0 failures, 0 errors, 2 skipped); tests/concurrency/test_claims.py (junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 6 matched, 6 passed, 0 failures, 0 errors, 0 skipped); tests/integration/test_transports.py (junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 7 matched, 7 passed, 0 failures, 0 errors, 0 skipped) |
| M9-02 | Packaging, licenses, docs and authorized release | not_run | not_run | partial | tests/unit/test_release_acceptance.py (junit.xml: 66 matched, 66 passed, 0 failures, 0 errors, 0 skipped; wheel-junit.xml: 66 matched, 66 passed, 0 failures, 0 errors, 0 skipped; sdist-junit.xml: 66 matched, 66 passed, 0 failures, 0 errors, 0 skipped) |

## Required outstanding evidence

- remaining_milestones: M4-05 approved application and M5-M9 implementation and acceptance remain incomplete.
- real_codex_adapter: Actual Codex client adapter has not been independently verified.
- real_claude_adapter: Actual Claude Code client adapter has not been independently verified.
- real_other_adapters: Other planned clients, including Cursor, lack actual-client evidence.
- autonomous_relay: Real autonomous dual-agent relay, independent review and conflict handling are unverified.
- cross_platform: A local run does not establish the complete supported OS/Python matrix.
- m9_acceptance: Full M9 release acceptance has not been performed.

## Scope and reproduction

Commands, exit codes, JUnit counts, version, SHA, platform and artifact hashes are in report.json.
Run from the recorded source with the recorded commands. No actual-client or autonomous relay result is inferred from local tests.
Skipped tests remain skipped in JUnit; they are not passes. No destructive user-workspace tests or paid calls are performed.


# M5B3B2A local acceptance report

Product `0fd2041c8efd1c4fa348117e013c0c5b1f30e470`, tree `9a76e8c5280c34d38087f42fc35b702808d15c59`. Version0.3.0a10/schema11.
Bounded owner-only one-shot candidate reservation and explicit terminal ledger
interruption. No worker credential, callback, renewal, execution, task gate,
approval consumption or apply. Formal Release **BLOCKED**.

## Frozen local verification

All18 collector checks passed. Linux source, fresh wheel and isolated sdist
ran 1061 cases each: 1058 passed/3 Windows-only
skips/zero failures or errors. Windows: 1031 passed/30 skipped,
zero failures or errors. Its skips remain26 Linux Docker,3 unavailable Windows
link-privilege fixtures and1 POSIX FIFO; the FIFO case executes on Linux.
Every suite executes 34 new real Git/SQLite reservation cases
and4 populated-v10/fresh/failure/future migration cases. The v10 fixture uses
original historical DDL with copied disposable API records, not an old binary.

Ruff/format/mypy, all artifact/log hashes and all four full JUnit files checked.
All33 Python modules match Git/wheel/sdist bytes. New claim/migration tests are
byte-identical in the sdist; 253-file Windows/Linux source
snapshots match. Installation origin/version checks are saved in collector logs.
Development functional RED/GREEN and supplemental audit are separate from full
suite counts. The first migration selection was already green; no migration
RED claim is made. Setup missing-module errors are not behavioral RED evidence.

Tests cover owner/project/profile/version fences before Git, strict intervals,
nonfinite/overflow/precision-loss clocks, deadline boundary reads without writes,
explicit active/expired/backwards-clock recovery, one reservation forever,
historical receipt replay with unavailable Git storage, task/owner/receipt races,
dirty/missing candidate input, same-version concurrent claimers, cancellation
winning during export, audit-error rollback, process exit before commit and
stored immutable pin/recovery-response corruption. Controlled clock/race/audit/
process-exit hooks are explicit fault injection, not autonomous client evidence.

The root independently audited final code and ran two additional actual-Git
fault cases: change only the valid deadline column, or change proof version to
2.0 and recompute its unkeyed digest. Five public access paths reject both, and
no recovery is persisted. These2 supplemental cases are not added to full suite
counts. Huge integer service-clock rejection was repaired while developing:
finite checks catch OverflowError and avoid a second audit timestamp overflow;
invalid-clock failure writes no unreliable timestamp. No checks were disabled.

## Saved actual records and regression boundaries

Six new observations (two per Linux environment) preserve actual job metadata,
claim proof bytes/digest, historical claim/enqueue/recovery responses, raw recovery
rows and current views. Root recomputed canonical metadata, binding/input/source/
profile fingerprints, literal candidate blob SHA, immutable proof fields/digest,
recovery request fingerprint and response digest. Claimed2 and interrupted3
states remain distinct from original queued1 history. Recovery leaves immutable
proof bytes unchanged and explicitly records ledger interruption only.
execution_verified=false, real_clients_verified=false, worker_credential_issued=false
and cleanup_performed=false. No real candidate execution or automatic relay.

Six prior queue, six prior metadata and six prior object-input records remain
separate regressions. Existing78 Docker observations are42 backend/21 owner
executor/15 reconciliation. Root independently inspected every exact full ID
absent after all suites without issuing removal. Per environment old cleanup
product records2 removed/2 unresolved/1 ineligible; fixture cleanup is distinct.
These old snapshot executions do not prove new candidate execution.

## Integrity, limitations and release gates

Schema11 transactionally rebuilds only candidate jobs/requests to expand allowed
states, preserving original columns/rows/receipts/fingerprints and composite FKs;
new claim/recovery rows are independently validated in both directions. No old
snapshot verifier semantics change. Existing v10 cancelled history stays intact.
Owner authentication precedes Git or replay. Reads/reopen never auto-expire,
requeue, recover or start execution. Expired claims remain recorded claimed
until explicit owner interruption; backwards-clock timing is unknown.

This is owner_reservation_v1 only. Before future execution, recovery requires
an execution-aware guard and dedicated cleanup. It must never clear authority
for a possibly running process. Unkeyed hashes are integrity checks, not
signatures or authorization; trusted service Python/DB/FS and no OS ABA atomicity.
No candidate worker recovery/renewal, verified task completion, approval
consumption/safe apply, real adapter/autonomous relay, full platform/M9 acceptance.

Archive `M5B3B2A-0fd2041-local.tar.gz`: 792898 bytes; SHA256 `7e9022f64c43124b0b6cd7667ed4271feeaa5c6d2db821f3c64fd57083e3671f`.
Self-excluding manifest 154 files. Sanitized logs/JUnit/builds/source/
package identities and independent reproduction scripts retained; no VM keys,
disks/seeds or fixture databases. Index acceptance/evidence/m5b3b2a-local-inspection.json.

Formal42 complete scenarios remain not_run; component coverage remains18 existing/
13 partial/11 missing and evidence38 not_run/4 unverified. Issues11/7 stay open.
Independent Work acceptance is pending and separate; later documentation heads
are not re-executed product commits. F:source/D:debug. GitHub storage only;
no Actions, paid calls, main edits or merge.
