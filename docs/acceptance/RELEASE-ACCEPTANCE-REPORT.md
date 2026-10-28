# Release Acceptance Report

## Alpha19 Cursor contextual launch entry point — selected local validation

Frozen product `cd2e8d75555e954b41c421f1dfeb3308032ba440` (0.3.0a19/schema12)
adds the explicit Cursor contextual-factory argument; shared engine/context,
parsers, invocation plans and Core are unchanged. A trusted host can use the
existing prelaunch stop/deadline checks; the entry point grants no authorization
and supplies no built-in Cursor plan. Default startup remains unsupported.

Sol's focused selection: **87 passed,0 skipped**. Root independently inspected
the diff and ran Windows Python3.14/3.11 selections: **455 passed,0 skipped each**.
All451 prior case IDs retained with4 added. Fresh offline Windows wheel/sdist
environments: **122 passed,0 skipped each**; actual imports of all59 runtime
modules match the frozen source; installed case sets match and are a source
subset. Ruff/format/mypy59/diff checks passed. The single manifest-checked archive
contains raw logs, JUnit, build artifacts and reproduction drivers; see
`evidence/alpha19-local-summary.json` for hashes and paths.

The subsequent dedicated local Linux VM installed the same frozen wheel/sdist
offline into separate fresh environments: **122 passed,0 skipped each**, all59
actual module hashes and direct archive hashes matched. All4 Windows/Linux
installed case sets are identical. Dependency checks and installed Mock workflow
CLI passed. Initial SSH upload failed during startup before tests; its NOT RUN
record/log remain in the29KB Linux supplement, separate from the successful fresh
guest run. Owned VM10624 was identity-checked and gracefully stopped; disk retained.

Alpha19 macOS, full source/installed suites, actual clients and autonomous relay
are **NOT RUN**. Earlier full Linux evidence remains bound to its earlier SHA.
This component checkpoint does not complete M6-05, M5 or formal acceptance:
all42 formal requirements remain not_run and Release remains **BLOCKED**.
No Actions, paid calls, client upgrade or retry of the closed Codex preflight.

## Authorized actual Codex factory test — preflight BLOCKED

On2026-10-28, the new single-use readonly subscription test stopped before model
execution: the native executable selected by the PATH/npm installation reported
`codex-cli 0.162.0`, while the factory profile requires `0.164.0-alpha.11.1`.
Model attempts and factory invocations: **0**. Login status, subscription route,
actual response and fixture execution are **NOT RUN / NOT CHECKED**. No retry,
client upgrade, version-gate relaxation or account-configuration change was made.
This observation does not establish the versions of other installed clients.
The preflight is closed; no automatic subsequent attempt is authorized. A
specifically identified compatible CLI and verified route/safety conditions are
required before a separately authorized bounded attempt. Evidence:
`evidence/codex-factory-preflight-20261028.json`. Release remains BLOCKED.

## Alpha18 opt-in Claude launch plumbing — selected validation

Frozen `c1a53ccf62263681da17d529b9c9abe362aea4a7` adds `ClaudeProcessFactory` and
Claude contextual-factory argument using the existing launch contract. Shared
engine/context, Codex, invocation flags/parsers and Core stay unchanged. Root
Windows3.14/3.11 source selections each **451 passed,0 skipped**; old446 IDs
retained plus5 new Claude cases. Ruff/format/mypy59 pass. Four fresh offline
Windows/Linux wheel/sdist environments each **118 passed,0 skipped**, with
matching IDs and59 actual installed module hashes; Linux archive metadata matches
the built artifacts. Astra independently reviewed source and saved XML/case IDs,
installed origins and archive bindings, approving this scoped checkpoint.

Full current Linux source/OS/Python package matrix is **NOT RUN**; prior Alpha17
full results remain tied to their frozen commit. All56 other prior runtime modules
retain their bytes; differences are version metadata, the additive
Claude argument and new factory. No actual client was called. Managed hooks
remain possible, managed MCP may reject flags and HOME/config may supply
credentials/providers. Authentication, billing, sandbox and client compatibility
are unverified. Every actual model run needs fresh authorization; factory
attachment grants none. All42 formal statuses remain `not_run`; M5/Release
BLOCKED. Evidence: `evidence/alpha18-local-summary.json`.

## Alpha17 pinned Codex launch plumbing — scoped local checkpoint

Product `33b5ec26318d10783352c9c39e2364af0e8a1e53`; fixture-only successor/package
freeze `d42a07c386f7183b44a3718c2c285fd73ec82861` has identical runtime bytes.
The opt-in library factory freshly prepares fixed Codex parameters and explicit
filtered environment, then enters capture through an adapter-issued task/run/loop
observation checking stop/original deadline and consuming one local attempt.
Defaults stay unsupported; no Core operation or CLI autoexecution enables it.

Root Windows3.14/3.11 selected source suites each **446 passed,0 skipped**;
Ruff/format/mypy58 pass. Full Linux source **with required actual Docker tier**:
**1818 passed,3 Windows-specific skips,0 failures/errors**,1821 cases. All1811
previous IDs remain plus10 new context cases. Four fresh offline Windows/Linux
wheel/sdist environments each **113 passed,0 skipped**, matching case sets and
58 actual imported module hashes. Linux PEP610 archive hashes match the originals.
This is a selected installed scope, not the complete OS/Python package matrix.

Astra independently reviewed critical source and actual saved XML/case identities,
installed origins and artifact bindings, approving this scoped checkpoint. Root
executed the tests. The initial Windows UTF8 helper
failure and old Python3.11 stdlib exception mismatch remain retained, corrected
without changing product safety semantics. Preparation threads can outlive stop;
no hard I/O/spawn/descendant/server cleanup guarantee exists. Fresh authorization
is required for **every actual model run**; attaching this factory grants none.
No real client/model call occurred and neither fixture wiring nor protocol success
proves client compatibility, billing, sandboxing or Core acceptance. All42 formal
statuses remain `not_run`; M5/Release BLOCKED. Evidence:
`evidence/alpha17-local-summary.json`.

## Alpha16 actual local Docker supplement

Frozen `7f658b189b62e5977dcda6b9b675bb864d61a1a3`: **26 passed,0 skipped,
0 failures/errors** in the dedicated local Linux VM. Verifier, owner execution
and reconciliation tests used the fixed preloaded image with required Docker
evidence enabled and no image pull. Root verified56 actual imported source
module hashes before/after; sources stayed unchanged. All26 IDs exactly match
Docker cases skipped in the preceding full ordinary run;3 Windows-specific skips
remain. These are separate runs, not a newly combined full-suite execution.
Negative candidate outcomes were correctly rejected; test passes do not mark
those candidates accepted. This source/dependency-venv check does not establish
new installed packages, real clients, autonomous relay or M5/Release acceptance.
All42 formal statuses remain `not_run`; Release BLOCKED. Sanitized evidence:
`evidence/alpha16-docker-local-summary.json`.

## Alpha16 offline dispatch command and local Linux regression

Product `e248a929cd08e7eb12835c3283582b3a60dc047a` adds `agentsync plan`: bounded
strict UTF-8 stdin JSON, existing dispatch advice and unverified markers. It
does not open state, authenticate or start work. Root Windows3.14/3.11 each
**44 passed,0 skipped**; lint/format/full typing pass. One fresh offline
Windows3.14 wheel passed dependencycheck, actual module/console CLI smoke
and56 installed module byte checks. No other alpha16 package matrix claim.

Current local Linux startup observation: **8/8 completed** and **10 regression
cases passed**, including all five unchanged8-process/30s migration tests.
Historical failures are retained; no root cause or universal repair claimed.
The first ordinary full suite retained **1772 passed,6 failed,29 skipped**.
Four stale traceability assertions and a journal fixture were repaired without
changing gates. The root developer wrapper also needed a multiprocessing main
guard. Corrected full source `2da1a89d222f88c801097856ed704d15b61c950a`:
**1782 passed,29 skipped,0 failures/errors**,1811 cases. All1807 original
case IDs remain,4 CLI cases were added,and all6 original failures now passed.
Retained failures and byte/case comparisons are in
`evidence/alpha16-local-summary.json`. Docker
opt-ins stayed absent; skips never count as passes. All42 formal requirements
remain `not_run`; M5/Release BLOCKED; no real-client/relay/Actions claim.

## Local startup diagnostic - Windows development evidence only

Developer tool commit `1eb17bee8a953603321f0e2ef56dff89a20ffa3b` adds fixed
owned interpreter startup observations without changing production code. Root
independently ran **4 passed,0 skipped** on each Python3.14 and3.11; Ruff,
format and focused tool typing passed. Actual **8 Windows processes** sharing
a new disposable database completed in **0.356s**, with schema12, integrity
and foreign-key checks, owned process cleanup and parent-file preservation.

Phases cover import, connect, WAL and overall initialization; BEGIN waiting
is not separately measured. The source pin covers Core service.py only.
The observation deadline does not preempt OS launch/kill/reap/cleanup.
Linux diagnostic is **NOT RUN**; historical Linux8-process startup failure
remains **OPEN**. All42 formal requirements remain `not_run`; Release BLOCKED.
Earlier installed alpha15 results remain bound to their original product SHA.
Evidence: `evidence/core-startup-local-summary.json`; raw logs/JUnits in
`D:\agentsync-debug\core-startup-root-6ndgmxne`. No remote/provider calls.

## Development alpha15 installed checkpoint - 2026-10-27 America/Tijuana

Frozen product `1d6b52605ff930787a992e8a7800caf01a8a0089`, development0.3.0a15,
schema12/dependencies unchanged. Four fresh offline Windows environments (Python
3.14/3.11 × wheel/sdist) each **782 passed,3 skipped,0 failures/errors** across
matching785 case IDs. Skips are POSIXfork and2symlink-privilege cases, not passes.
Two fresh offline Linux wheel/sdist environments each **122 passed,2 skipped,
0 failures/errors** across124 selected IDs. Their Windows-junction skips are
platform-specific; inherited-Core fork and actual two-MCP-process claim executed
and passed. Dependency checks and installed Mock CLI demos passed in all6.

Root independently verified313 Git package inputs,55 actual installed module
paths/hashes per environment, same-runtime case/skip sets, original artifact
hashes and Linux direct-archive install metadata. Pinned offline build backends
and52-wheel guest cache were used; no provider/API/hosted execution. These are
selected suites, not the full repository, OS matrix or historical8-process repair.
Astra reviewed critical source and saved results, approving this scoped development
checkpoint only; this is not independent Work human or M5/Release acceptance.

The identical32worker×8round/1000ms diagnostic now passed with sourcep95=107.837ms
and fresh installed Python3.11 p95=110.680ms, each with256 exact audit receipts
(8success/248denied,0 defects). Admission wait remains included. Historical
2303.126ms baseline failure stays preserved. This measured local improvement
does not prove generalized SLOs, fairness, audit durability or cross-process bounds.

Evidence/artifacts: `D:/agentsync-debug/alpha15-packages-vsexm9ec/`,
`D:/agentsync-debug/alpha15-python311-8x9mrsbm/`,
`D:/agentsync-debug/alpha15-linux-packages-8nxxft8u/`; persistent summary
`evidence/alpha15-local-summary.json` includes hashes and related source/perf runs.
All owned validation jobs completed. The dedicated VM was synchronized and
gracefully powered off, preserving disk and backed-up logs. An initial guard
compared an auto-parsed DateTime against a string and refused before sending
shutdown; exact UTC ticks/PID/executable/disk then matched. No forced stop occurred.

All42 formal requirements remain not_run and **Release BLOCKED**. Real clients,
full Claude flag compatibility/authentication/billing/relay, macOS and complete
platform matrix remain unverified. Old Linux startup failures remain open. No
Actions run, remote mutation, main modification, tag or public Release occurred.

## M8 process-local admission experiment - 2026-10-27 America/Tijuana

Source `b10bf99d0c8d814762849f86e76565c2c40ba394` adds weak per-database process-local
thread admission after payload validation. The original connect/transaction/auth/
replay/lease/rollback/denial-audit/close body is byte-identical; owner and migration
paths are untouched. Acquisition timeout is30s before SQL, additive to existing
SQLite/audit waits. No fairness, bounded queue, recursion, cross-process lock or
security guarantee is claimed. Strong waiter references prevent gate replacement;
unused gates reclaim and child-after-fork resets both gate registry and mutex.
Astra independently reviewed the production source and found no blocker.

Root independently ran Windows Python3.14 broad Core/security/concurrency/recovery/
transport scope432pass3skip, zero failures/errors; Python3.11 scope37pass1skip.
Windows skips: POSIXfork and2symlink-privilege-dependent cases. Linux selected
Core/fork/security/real two-MCP-process scope122pass2Windows-junctionskips, zero
failures/errors. The inherited-Core fork test actually passed while parent gate
and registry mutex were held. Root matched165 Git source inputs and55 source
imports; sources stayed unchanged. A first root review incorrectly assumed zero
Linux skips; it was corrected from raw XML without rerunning or promoting skips.
Ruff/format/mypy55modules passed.

Identical32worker×8round timing includes all admission waiting and uses the same
1000ms p95 threshold. Observed p95=107.837ms,256 claim attempts,8 success/248 denial
audits exactly matched,0 audit defects, all checks passed. Earlier strict baseline
p95=2303.126ms and its failure remain preserved. This is an observed one-host
workload improvement, not proof of global fairness, all-load performance or a
universal SLO. Cross-process SQLite authority and earlier8-process startup failure
are not declared repaired.

Evidence: `D:/agentsync-debug/core-admission-root-e9ou5xav/`,
`D:/agentsync-debug/core-admission-perf-qqof4ky8/`, and
`D:/agentsync-debug/core-admission-linux-isvv1r9f/`. This is M8 performance work,
not a new M5 phase or acceptance. All42formalnot_run and Release BLOCKED.

## Linux selected-source supplement - 2026-10-27 America/Tijuana

Exact source `7c641e90bf0909c3f8ee68335817d817b34e5eaf` passed49 selected retry,
Claude preparation, usage, strict diagnostic, crash-recovery and collector tests
in the owned local Alpine VM, Python3.14.7/SQLite3.53.4: zero failures/errors/skips.
Root independently matched163 Git archive inputs,54 actual source-import paths/
hashes and raw JUnit. The source manifest remained unchanged; a bounded per-phase
journal and raw logs survive independently. A fresh nonce guest directory and
explicit empty home/config were used; no model/provider call, candidate execution
or user project was selected. Host source staysF:, all VM/debug files stayD:.

Evidence: `D:/agentsync-debug/alpha14-linux-components-gktwi5mr/`, sanitized
`evidence/alpha14-linux-components.json`. Prior VM logs/process metadata were
backed up before starting only the dedicated configured VM. This is an existing
dependency-venv source check, not fresh package installation or a full OS matrix.
The previous eight-process startup failures and installation limitations remain
open. All42formalnot_run; real relay and Release BLOCKED.

## Strict diagnostic audit coverage - 2026-10-27 America/Tijuana

The local diagnostic now compares final claim audit rows against exact expected
agent/request-digest identities and success/denial outcomes, after all timed calls.
Counts alone cannot hide a missing receipt plus a duplicate. Missing, duplicate,
unexpected or mismatched rows set claim_audit_complete=false and overall failure.
Only aggregate counts leave the owned fixture. Core and audit semantics are unchanged.

Root independent Windows Python3.14 diagnostic/existing audit-security/collector
scope11pass; Python3.11 diagnostic7pass; Ruff/format/mypy54 pass. Controlled missing
denial and equal-total identity/outcome corruption tests fail the diagnostic as
expected. Actual32workers×8rounds observed256 expected audit events,8success and
248denied, with0missing/duplicate/unexpected/mismatch. All functional checks passed;
p95=2303.126ms still FAILED the unchanged1000ms budget, exit1. This one workload
does not prove generalized audit durability. Evidence:
`D:/agentsync-debug/m8-audit-strict-root-cfi2btv7/` (JUnit/logs/strict32.json).

This source diagnostic improvement is later than the2982539 alpha14 package build;
earlier package evidence/artifacts are unchanged, not relabelled as testing this
tool revision. Linux source component validation follows separately. No real client,
M5 completion, full matrix or Release promotion; all42formalnot_run/releaseBLOCKED.

## Independent checkpoint and audit-count supplement - 2026-10-27 America/Tijuana

Astra High independently inspected the benchmark source, actual workload reports,
Core transaction paths and all four370-case JUnit files. No blocking measurement
finding: nearest-rank percentiles and attempt-throughput scope are consistent;
the32worker1000ms budget failure remains false/FAIL in both raw and summary data.
This review is not Release or Work human acceptance.

The original benchmark does not count denial audit rows. Source shows denial
logging uses another transaction with1000ms busy timeout and suppresses SQLite
errors; the performance impact and potential retention loss were not established
by that benchmark. A separate owned32worker×8round run added only a final read-only
audit query, after timed claims and before private-child cleanup. Observed8
success/ok and248denied/version_conflict events exactly match expected counts.
This run p95 was2285.607ms and still FAILED the unchanged1000ms budget. One complete
run does not guarantee audit retention under other contention/failure conditions.
No product code or audit semantics were changed and the earlier timing failure
was not replaced. Evidence: `D:/agentsync-debug/alpha14-audit-count-bg164krq/`.

Lock waiting, claim transaction cost and denial-audit cost remain unprofiled
hypotheses for future diagnostic work. Current Linux validation was not started;
a read-only process inventory found no running configured QEMU process. Earlier
Linux failures remain open. All42formalnot_run and Release BLOCKED remain unchanged.

## Development alpha14 package checkpoint - 2026-10-27 America/Tijuana

Frozen product `2982539e9b304f6e8da8fbcd57a040ec9ab158c3`, development0.3.0a14,
unchanged schema12/dependencies. Fresh independent offline Windows Python3.14
wheel and sdist environments each **370 passed /0 skipped/failed/error**. Fresh
Python3.11.15 wheel and sdist environments each matched the same **370 /0 /0**.
All4 dependency checks and installed CLI Mock workflow runs passed. A direct
Python3.11 sdist diagnostic-tool command also passed in a private scratch project.

Root independently compared309 frozen Git package inputs, actual54 module paths/
hashes per installed environment and all four370-case ID sets. Previous known
unraisable/transport warnings were absent. Ruff/format and mypy54modules passed.
Source developer helpers, including the new benchmark, are included in the sdist.
Python3.11 source installation used pinned offline build backend packages and
existing cached dependencies, without provider/API/network execution.

Artifacts/evidence: `D:/agentsync-debug/alpha14-packages-69ssdg9x/` and
`D:/agentsync-debug/alpha14-python311-9c8mvex7/`. Sanitized persistent summary:
`evidence/alpha14-local-summary.json`. Wheel SHA256
`2a4ad247402e516a37432b2f6ac0e67e44ecfe30f15d821d35dd67cc1c4872da`;
sdist SHA256 `845cd9ad7572e082c31b286afce2c238ad5e14a3e1d1c43c1c16f249188296d2`.

These are scoped installed-component suites, not the full repository or OS matrix.
The measured32worker p95 diagnostic-budget failure remains **FAILED**, and prior
Linux startup/installation limitations remain unresolved. Real clients, complete
Claude flag compatibility/authentication/billing/tool effects and autonomous relay
remain NOT RUN/unverified. All42 formal requirements stay not_run and **Release
BLOCKED**. No tag, Release, Actions execution, main change or remote mutation.

## M6 Claude bounded invocation preparation - 2026-10-27 America/Tijuana

New explicit-profile preparation checks namespace/version/environment before bounded
file reads, pins executable SHA256 and checks file/root identities, then returns
fixed restricted/tool-deny/empty-MCP/ordinary-hook-disabling argv, cwd and stdin.
No subprocess, account discovery or execution path is added; default ClaudeAdapter
factory remains unsupported. Managed hooks/policy and configuration credentials
remain outside this preparation boundary. Version/model are host assertions and
all execution/auth/billing/client/sandbox/tool restriction flags remain false.
No --bare, weaker fallback or instruction-to-command conversion is present.

Astra High independently inspected final module SHA256
`dba25746da96924f2b094059d2553d79065e7abaec3959250b79f8cdd0122cef` with no blocking
source finding; this is not runtime/Release acceptance. Root independently ran
Windows Python3.14 Claude/Codex plan/Claude adapter/collector scope190pass, and
Python3.11 plan6pass; zero failures/errors/skips. Ruff/format/mypy54modules passed.
Evidence: `D:/agentsync-debug/m6-claude-plan-root-zwkx1ith/`.

Separate help/version-only native CLI observations in an empty D-drive home/config
reported2.1.295, no created config files and no model prompt. Most prepared flags
appear in help; --max-turns does not, despite current official documentation.
The full combination is NOT RUN, not verified. Binary SHA256
`a30012741c3d0b55e2a6c252dab3781134b75be95896ae89d40a93e10f83bcd6`; an independent
prepare-only check hashed this installed binary and left the fixture unchanged,
without launching it. Help evidence: `D:/agentsync-debug/claude-help-only-pqo5glrq/`;
preparation receipt: `installed-binary-preparation.json` in the root evidence folder.

Sources/limits are linked in M6-ADAPTERS.md. Real CLI turn, flag-combination effects,
permissions, authentication/billing, cancellation and relay remain NOT RUN. M6-04
partial with11 selectors; all42formalnot_run; release BLOCKED.

## M8 declared local contention diagnostic - 2026-10-27 America/Tijuana

A local-only tool creates its own temporary project/database, explicitly grants
workers, synchronizes claim attempts, verifies exactly one persisted winner per
round, cancels owned leases, and checks final versions/SQLite integrity/foreign
keys before closing handles and removing only its private child. Reports omit
credentials, actor/task IDs, raw exception messages and scratch paths. Claim-
attempt throughput includes expected conflicts; startup, barrier, verification
and cleanup are outside measured claim latency. CLI failures use nonzero exits.

Root independently ran Windows Python3.14 focused11pass and Python3.11 tool4pass,
zero failures/errors/skips; Ruff/format and mypy53modules passed. Actual Windows
Python3.14 workloads used1/8/16/32workers,8rounds each:456 attempts,32 winners,424
expected version conflicts, no unexpected errors. All functional/persistence/
integrity checks passed. Nearest-rank p95ms were3.400/133.483/660.562/2395.555.
The declared diagnostic threshold stayed1000ms for every workload:32workers
**FAILED its latency budget**, exit1. Other three workload budgets passed. This
is an observed local scaling limit, not a universal SLO or a security failure.
Performance follow-up remains open; no audit rule or gate was weakened.

Evidence: `D:/agentsync-debug/m8-contention-root-mqb8e39b/` (`result.json`, raw
JUnit/logs and `workloads.json` with individual reports/hashes). Initial Sol tests
exposed a Windows SQLite context retaining an open handle during temporary cleanup;
explicit closing repaired it. Only final Sol JUnit was retained at the provided
path; original pre-fix raw JUnit is NOT RETAINED, so no reconstructed failure log
is presented. Root tests and workload reports are independently saved. Current
Linux/macOS, startup contention, real client performance and the full acceptance
scenario remain NOT RUN/unverified. M8-02 partial, all42formalnot_run, release BLOCKED.

## M7 deterministic retry planning - 2026-10-27 America/Tijuana

A pure RetryPolicy/plan_retry component provides bounded deterministic exponential
backoff, a numeric caller-declared Retry-After floor (never capped downward), and
per-task/global/deadline stops. Unknown/unconfirmed outcomes never recommend a
retry. Positive delays that cannot advance the supplied clock stop explicitly.
This is unverified snapshot advice; confirmation is not authorization or proof
that an external side effect is safe to repeat. It never sleeps, dispatches,
reserves a budget or changes Core. Real HTTP/provider behavior was not tested.

Root read actual source/tests and raw JUnit: Windows Python3.14 scoped54pass,
Python3.11 retry18pass, zero failures/errors/skips. Ruff/format and mypy53modules
passed. One isolated Mock composition explicitly waits1ms and starts a distinct
second attempt; this is not real-client or autonomous relay evidence.
Evidence: `D:/agentsync-debug/m7-retry-root-09rucwxf/`. Source SHA256
`05a40fb13e2f4b8c35de1805d378c63f3ed582e719bb39b36b7be5f55ea53291`.
M7-04 remains partial; all42 formal execution statuses remain not_run and Release
BLOCKED. No new package build, provider calls, Actions or main changes.

## M8 explicit usage checkpoint recovery - 2026-10-27 America/Tijuana

`UsageLedger.to_json()` and `UsageLedger.from_json(expected_project_id, text)`
export/restore normalized caller observations without file/database/network I/O.
Schema1 exact fields,32MiB UTF-8 bound, shallow preflight, duplicate-member/run
rejection, strict types/counters/timestamps and namespace checks apply. Restoration
uses existing admission validation into a private new ledger and recomputes sums
and elapsed metrics; no saved summary is trusted. Raw output/client metadata are
omitted, but caller-controlled identifiers remain in the checkpoint. Fixed
unverified markers and unknown costs confer no authenticity or billing proof.

Astra High approved the minimal consistency design and independently inspected
final usage.py SHA256 `f3318eadbba16b235fe648ea966708ecd0c7a50f601d1f82046386810cc2cba2`,
finding no blocking source issue. This was source-only review, not test execution
or Release acceptance. Root inspected actual source/tests/JUnit and ran Windows
Python3.14 usage/Cursor boundary/collector scope **19 passed**, Python3.11 usage
**15 passed**, zero failures/errors/skips. Ruff/format and mypy52modules passed.
Two fresh interpreters independently restored one caller-written private fixture
file, preserved unknown-vs-zero, Mock separation, replay deduplication and full
capacity. The API does not write that file or restore running Agents/tasks.

Evidence: `D:/agentsync-debug/m8-usage-recovery-root-nas39osp/` (`result.json`,
raw command logs/JUnit, `restart-smoke.json` and sanitized fixture). Sol raw
evidence: `D:/agentsync-debug/usage-checkpoint-sol-20261027/`; one intermediate
assertion identified mixed validation-error messages, which were normalized and
retested. M8-01/M8-02 mappings remain partial. All42 formal statuses remain
`not_run`; no new package/platform matrix, automatic crash-safe file storage or
real-client relay is claimed. Prior package evidence stays bound to77426fa.
This is Unreleased source at the existing development version. Release BLOCKED.

## M7 elapsed admission budget supplement - 2026-10-27 America/Tijuana

`run_mock_workflow_demo(..., max_elapsed_seconds=None)` optionally accepts a strict
finite positive number up to60 seconds, validated before filesystem access. The
private monotonic deadline includes setup, gates fresh/retry claims and starts,
and checks returned results. Once expiry is detected, active Mock runs are
cancelled before the zero-active summary; remaining owned Core tasks fail and
unstarted dependents remain pending. No budget argument preserves previous output.
This controls admission, not preemption: a synchronous call or hanging await can
outlast the deadline, and cleanup completes afterward. No real-client authority,
provider call, billing, durable retry or independent acceptance is introduced.

Root read actual source/tests and raw evidence. Windows Python3.14 affected suite
**52 passed**; Python3.11 workflow **14 passed**, all zero failures/errors/skips.
After adding three elapsed selectors to M7-04, the updated collector gate regression
passed separately **1/1** and keeps all42 formal requirements `not_run`. Ruff/format
and mypy52modules passed. Deterministic deadline fixtures cover setup, claim, start,
retry and pre-I/O validation; they do not measure real performance. A separate
actual monotonic-clock smoke with a1microsecond admission budget stopped before
any claim/start, returned four pending tasks and removed its private child. Its
whole call took0.0497s, demonstrating why this is not a hard timeout.

Evidence: `D:/agentsync-debug/m7-time-budget-root-ewvjv1i0/` (`result.json`, raw
logs/JUnit and `final-supplement.json`). Initial attempt to edit the manifest
asserted before writing due to an indentation mismatch; corrected association
was then policy-tested. Runtime hashes from the52/14 suites remain unchanged.
This source component has no new package/platform/real-client run. The preceding
a13 package evidence belongs only to77426fa. Hard watchdogs, token/cost budgets,
AI decomposition, persistent retries and real relay remain unverified. Release BLOCKED.

## M8 Core crash and expired-lease recovery supplement - 2026-10-27 America/Tijuana

One new isolated three-process regression uses actual abrupt exit73 and the persisted
one-second lease deadline, without clock patches or database timestamp edits. The
restarted Core retains the running task, rejects expired claim replay, reclaims it
once, rejects the old lease/replay before and after successor ownership, and lets
the successor proceed to review. A distinct reviewer completes the root; its
dependent becomes claimable. A third process verifies exact persisted public state,
one review, SQLite integrity and foreign keys. Review remains a peer assertion,
not independent code verification or real Agent execution.

Root inspected the source and raw JUnit/logs: Windows Python3.14 recovery plus
existing claim/migration concurrency and collector policy checks **157 passed**,
zero failures/errors/skips; Python3.11 recovery **2 passed**, zero failures/errors/
skips. Focused Ruff lint/format and diff checks passed. No runtime/package version
change or redundant rebuild. Evidence: `D:/agentsync-debug/m8-recovery-root-nd076l_6/`
(`result.json`, `py314.xml`, `py311.xml` and command logs). Exact source hashes are
recorded there. Existing M8-02 selectors are reused and supplemented; coverage is
partial, with all42 formal execution statuses still `not_run`. Current Linux/macOS,
MCP/HTTP/scheduler/adapter process recovery, performance stress and real autonomous
relay remain NOT RUN/unverified; old Linux failures are not cleared. Release BLOCKED.

## Final development alpha13 package supplement — 2026-10-27 America/Tijuana

Frozen product/package source `77426fa4a02125417f10b6582ad87dccf50683f5`, version
`0.3.0a13`. Fresh offline Windows Python3.14 wheel and sdist environments each
passed **318 tests /0 skipped /0 failed/error**. A fresh Windows Python3.11.15
wheel environment also passed **318 /0 /0**, using the existing local dependency
cache offline. All3 dependency checks and installed CLI Mock workflow runs passed.
Root independently matched raw318-case ID sets,52 imported module paths/hashes
per environment and frozen Git package inputs. Ruff/format/mypy52modules/diff passed.
The earlier unraisable/closed-pipe warnings were absent in all3 final test logs.

Evidence/artifacts: `D:/agentsync-debug/alpha13-packages-wsy5uci3/` and
`D:/agentsync-debug/alpha13-python311-1_06_4p9/`; consolidated receipt
`D:/agentsync-debug/AGENTSYNC-CHECKPOINT-20261027.json`.
Wheel SHA256 `728af5aef18e521017d9264372baeb3eaae81b82f4aec55dcec0a577011103fa`;
sdist SHA256 `423744438154687878880565f159eab52128a1f6a73dc7fca18685fd0210f13d`.

Private Python3.11 runtime/bootstrap/cache live on D:. User Python registration/
PATH fingerprints remained unchanged. Initial setup's locator confused the managed
alias with its real directory; a separate canonical-path probe recovered without
reinstalling. Setup evidence: `D:/agentsync-debug/python311-setup-2qknq1_r/`.
The alpha12 **301pass/10fail** result and transport warnings remain preserved;
the interrupted broader Windows attempt is still NOT COMPLETED. No Windows full
suite or current Linux/macOS matrix, Python3.11 sdist, real clients or autonomous
relay is claimed by these scoped results. All42 formal requirements remain
`not_run`; formal release remains **BLOCKED**. No Release/tag/main change occurred.

## Coarse-clock capture freshness repair — 2026-10-27 America/Tijuana

Actual isolated Python3.11.15 alpha12 wheel tests executed **301 passed /10 failed**,
not NOT RUN: fresh captures could share the run's public loop-clock timestamp and
were falsely classified `capture_stale`. Transport warnings were also observed.
Raw failure evidence and the correction to the driver's stale NOT RUN label are
in `D:/agentsync-debug/alpha12-python311-3wv_qoj1/`.

Developmenta13 replaces timestamp comparison with private process-local creation
ordering and explicit same-loop association. Capture-ID reuse rejection remains
first; stale/foreign captures stay unowned/uncancelled. Public dataclasses,
timestamps, timers, unknown slots and late-parent cleanup are unchanged. This
mechanism is not authorization, client provenance or cross-restart identity.

Synthetic RED preserved3fresh equal-timestamp failures and3stale rejections;
GREEN7cases include all3adapters fresh/stale and foreign-loop rejection. Sol's
Python3.14 affected suite108pass; root's actual Python3.11 source suite111pass.
Evidence: `D:/agentsync-debug/creation-fence-{red,green,regression,root311}.xml`.
Astra reviewed the actual diff without a blocking finding (source-only review).
Fixed installed-package tests remain pending at this checkpoint; no claim of
full Python3.11 support, actual clients, relay or formal release is made. BLOCKED.

## Development alpha12 installation checkpoint — 2026-10-27 America/Tijuana

Product/package source commit: `9ebb13e2799cb2d58e36ab429845b0eede9a3c0d`,
version `0.3.0a12`, unchanged schema12/dependencies. This is a development alpha,
not a published Release/tag or formal acceptance. The previous a11 source archive
omitted `tools/release_acceptance.py` and `tools/pytest_case_journal.py` even though
packaged tests reference them. MANIFEST now includes developer helper source.

Built wheel/sdist from302 Git-verified package inputs on D:. Fresh independent
offline Windows Python3.14 environments each executed **311 passed /0 skipped /
0 failed/error** from the extracted source-package tests. Both pip checks and
actual installed `agentsync.exe demo --workflow` passed. Root independently read
the raw JUnit (identical311-case sets),52 actual imported module paths/hashes,
isolated venv configuration and54 installed distributions per environment.
Both archives contain the matching runtime; source helpers match frozen Git bytes.

Evidence/artifacts: `D:/agentsync-debug/alpha12-packages-5bk73scl/`.
Wheel SHA256 `1e8b3df1b9c8d4fdacafbbe9526b607dc975bb8ef3f2a4a1b52d999621461f78`;
sdist SHA256 `dd8798e8859a662b4c1ed3a292db963d3b57aaa5db3fecda31db718c8cb9f259`.
The earlier interrupted full Windows run remains NOT COMPLETED; these are scoped
installation/component results. Linux/current full platform matrix and actual
clients/relay were not executed here. All42 formal requirements remain `not_run`;
M5 blockers and formal release remain **BLOCKED**.

## Caller-reported usage component — 2026-10-27 America/Tijuana

Added a bounded project-local UsageLedger for exact typed adapter results. It
retains scalar identities/status/timing/counters only, separates Mock from protocol
totals, deduplicates identical observations and rejects conflicts/overflow without
partial admission. Missing values differ from reported zero; incomplete totals
remain unknown. Logical adapter intervals are not provider/API duration. Failure
ratios require complete reported terminal outcomes. Costs stay unknown; billing
and real-client verification remain false. No raw output/client correlation IDs,
credentials, actual API accounting, paid call or restart recovery was introduced.

Root inspected code and ran **163 passed /0 skipped /0 failed/error** across the
ledger, actual known-Python Cursor/Core composition and release collector. Ruff,
format, mypy52modules and diff passed. Evidence with JUnit/commands/tested hashes:
`D:/agentsync-debug/m8-usage-review-_adka4an/`. M8-01 now has four partial component
selectors. All42 formal requirements remain `not_run`; current real clients,
autonomous relay, full platform matrix and formal release remain unverified/BLOCKED.

## Isolated automatic Mock workflow — 2026-10-26 America/Tijuana

`demo --workflow` composes the existing planner, Core and MockRunManager in a fresh
temporary child of an explicit scratch parent. Two fixed workers execute a diamond
of four fixture tasks with one failed attempt/retry, overlapping Mock records,
authenticated claims/updates, distinct peer simulated reviews and persistence
checking. Per-task/global attempt bounds stop further starts and leave descendants
pending. Existing projects, adapters, credentials and arbitrary tasks cannot be
supplied. The private child is removed, including on unexpected errors. Output is
explicitly simulation-only/unverified; actual-client/formal acceptance is false.

Astra High performed a source-only architecture/component review with no blocking
finding, then Sol completed implementation. Root inspected code and independently
ran **164 passed /0 skipped /0 failed/error** across workflow integration, existing
demo, owner CLI input and release-collector tests. Ruff/format, mypy51modules and
diff passed. Evidence: `D:/agentsync-debug/m7-workflow-focused-ow0tpz7w/`.

The broader Windows attempt in `D:/agentsync-debug/m7-workflow-review-qqo1n24z/`
was deliberately **INTERRUPTED/NOT COMPLETED** after scope review found that its
unrelated database inventory was excessive. Only the identified owned pytest
process was stopped after checking no direct children; raw partial stdout,
nonzero exit and supervisor record remain. No JUnit was produced and no passed
case count is inferred from progress dots. This is not a complete Windows result.

M7-04 has partial retry/attempt-budget simulation coverage only. AI decomposition,
provider backoff, time/token/cost budgets, durable recovery, real handoff and
autonomous real-client relay remain unimplemented/unverified. All42 formal
requirements remain `not_run`; M5 blockers and earlier Linux failures persist.
Formal release remains **BLOCKED**.

## Capability-aware planning component — 2026-10-26 America/Tijuana

Existing read-only task/dispatch planners now optionally match explicit complete
task requirements against caller/self-reported agent capabilities. Input tokens,
maps and totals are bounded; filtering precedes truncation and preserves the
full dependency graph. Omitting requirements retains existing behavior. Mode
labels do not assert verified capability, current authorization or execution.

Root inspected code and independently ran **267 passed /0 skipped /0 failed/error**
covering affected planners/managers, acceptance collector and actual temporary
Core state. A matching viewer was recommended but still forbidden to claim; Core
and reopened state remained unchanged. Ruff/format, mypy50modules and diff passed.
Evidence: `D:/agentsync-debug/m7-capability-review-57fybcbk/` (commands/logs/JUnit/
tested-file hashes). M7-02 has eight component selectors. All42 formal requirements
remain `not_run`; real autonomous relay, current Linux/new package validation and
formal release remain NOT RUN/BLOCKED. Existing Linux failures are unresolved.

## Cursor protocol component — 2026-10-26 America/Tijuana

Added a bounded standalone terminal-JSON parser and typed CursorAdapter using the
existing shared host lifecycle. Explicit supported schema plus observed exit0 is
required for result text. Stream JSON, malformed input and unsupported schemas
cannot become success. Caller-reported timings and correlation IDs remain
unverified. No built-in launcher, credentials, Core transition or authorization
was added; shared lifecycle code was unchanged.

Root independently inspected files and ran **280 passed /0 skipped /0 failed/error**
across new parsing/process/Core fixtures, adjacent adapters/manager and acceptance
collector tests. Ruff/format, mypy50modules and diff passed. Raw logs, commands,
JUnit and tested-file hashes: `D:/agentsync-debug/m6-cursor-review-ithzwbp8/`.
M6-05 now maps eight component selectors. All42 formal requirements remain
`not_run`, and real Cursor/real client relay remain NOT RUN. No Linux, new package
installation or full platform matrix was run here; earlier Linux failures remain.
Formal release remains **BLOCKED**.

## Local heterogeneous run manager — 2026-10-26 America/Tijuana

Implemented scoped registration/routing, duplicate-request dispatch ownership,
opaque handles, bounded non-evicting history, identity checks and nonblocking
pending/returned/error inspection. A caller cancelling its wait cannot trigger
a second dispatch. Fixed error codes replace private start exceptions; raw
protocol results retain their original unverified markers. This adds no Core
transition, client permission, scheduling, recovery or candidate application.

Independent affected Windows tests: **137 passed, 0 skipped, 0 failed/errors**;
Ruff, formatting, mypy (48 modules) and diff checks passed. Evidence including
commands, JUnit and tested-file hashes: `D:/agentsync-debug/m6-manager-review-8movlm76/`.
The independently rerun acceptance collector suite also passed **148 tests**
(`acceptance-junit.xml` there), including positive/negative exact selector matching
and refusal to promote local manager results to real-client acceptance.
Earlier `m6-manager-review-y2crn24c` retains the first format-check failure, since
fixed; its 135 test passes are not added to the final count. Known local Python
fixtures exercised Codex/Claude protocol results alongside Mock and confirmed
that actual Core state, including after reopen, stayed unchanged.

M6-05 has component coverage only. Real Cursor, real current-engine clients,
autonomous relay, Linux/current package checks and Python 3.11 execution were
**NOT RUN** here. Previous Linux failures remain unresolved. All 42 formal
requirements remain `not_run`; formal release remains **BLOCKED**.

## Never-started capture cancellation repair — 2026-10-26 America/Tijuana

Final local test-infrastructure checkpoint: **1041pass /5skip /0fail/error**
from the root's actual source unit/concurrency/selected Core suite; Ruff, format,
mypy and diff passed. Test-only cleanup preserves8children/5iterations/30seconds
and original errors; independent migration+cleanup check10pass. New opt-in private
pytest journal persists each phase before a later owned test is terminated, with
strict capacity/path/write-error guards. Three Windows journal path/FIFO guards
remain NOT RUN. All47 runtime module bytes still match7d01aed. This supplement
does not resolve or erase the four Linux concurrency failures, retry Linux package
installation, or establish a full new OS/Python/real-client release matrix.

Product `7d01aed3b2fb41bb2ab6dee8d0c2e1f94374842f` repairs a reproduced hang:
a trusted factory returning `CapturedProcess()` without `start()` left both client
adapters running after deadline, with cancellation and interpreter shutdown stuck.
The same independently supervised reproduction now exits0: both retain unknown
slots, with no parent exit/client/Core verification claim. Pending-start cleanup
is unchanged. Five new public-interface regressions cover the bare capture and
both adapters' cancellation/deadline behavior; no existing tests were removed.

Current completed checks: Windows source **1019pass /2skip**, Ruff/format/mypy/diff
pass; fresh offline Windows wheel and sdist **98pass /0skip each**, with47 actual
imported modules and54 installed distributions inside each isolated environment.
Linux source focused checks **98pass /0skip**; root matched exact testcase IDs and
verified322 original files unchanged after the failed installation attempt.

Linux package validation is **LIMITED/FAILED**: normal offline wheel dependency
installation exceeded600 seconds, outer transport exceeded1200 seconds; wheel
post-install tests and sdist installation/tests are **NOT RUN**. Same-guest final
evidence was recovered without executing again. The preceding Windows full-suite
driver retained **FAIL** because generated bytecode entered its all-files manifest;
actual1613 cases were1582pass/31skip, with all321 original files unchanged. Current Windows full actual1618 cases are **1587pass /31skip /0fail/error**;
all322 original files match Git7d01aed, no prior testcase disappeared, five were
added. The second driver still reports **FAIL** because21 child-generated bytecode
cache files entered its all-files manifest; that raw failure is preserved.

The independent Linux full attempt is **INTERRUPTED / NOT COMPLETED**, exit2 after
one controlled SIGINT. Actual completed results: **1pass /4fail**. Four concurrent
Core-initialization cases exceeded their unchanged30-second subprocess deadline.
A sixth anonymous XML element is unfinished and must **not** be counted as a pass.
Remaining tests, including Docker cases, are **NOT RUN**. All322 source files remain
unchanged and no owned test Python processes remain. This is a failed/limited
current Linux attempt, not a Linux release pass.

Python3.11 runtime remains **NOT RUN**; static grammar/API/dependency review does
not replace an installed-runtime test. Real clients on this engine, autonomous
relay and the complete M9 matrix remain unverified. All42/16 formal statuses and
the unique M5 exit checklist are unchanged. Release remains **BLOCKED**.
See [repair evidence](evidence/unstarted-capture-local-20261026.json).

## Latest fresh Linux package installation supplement

Two new independent Linux venvs normally installed the actual Windows-built
wheel and sdist offline from52 compatible cached dependencies. The sdist used
normal PEP517 isolation. No no-deps/shared-site/PYTHONPATH fallback was used.
Wheel: **641pass /0skip/fail/error**. Sdist: **641pass /0skip/fail/error**.
Root independently parsed both actual XMLs, matched testcase identities to the
frozen Linux source run, verified all10 stage exits/log hashes, direct_url archive
hashes,47 imported module locations and post-test byte hashes, actual pyvenv.cfg
and52 distributions inside each environment. Source317 files stayed unchanged.

These are component installation checks on this Linux/Python runtime. They do not
establish a complete current suite, all supported platforms/Python versions, real
client behavior or formal release acceptance. Release remains **BLOCKED**.
See [fresh Linux installation evidence](evidence/linux-fresh-packages-20261026.json).

## Latest Linux components and Git binding

The current47-module frozen source components finished **641pass /0skip/fail/error**
on the existing local Linux VM. Root independently parsed actual JUnit, checked
logs/hashes and317-file before/after manifests, and bound all source/test/tool plus
requirement bytes to product commit `da61adf2c90196814c96a7827756b346bcd02f51`.
The original precommit base/provenance remains intact; closeout documentation was
added after tests. This is the same23 component selectors used by the two fresh
Windows package environments, not a complete new Linux suite or Linux installation.
No Docker cases or real clients were repeated in this component run.
See [Linux component evidence](evidence/claude-adapter-linux-20261026.json).
Formal release remains **BLOCKED**; earlier pending statements below are historical.

## Current shared lifecycle / ClaudeAdapter checkpoint: 2026-10-26 America/Tijuana

Execution: Codex. Formal release **BLOCKED**. M5 scope/exit conditions unchanged.
`ClaudeAdapter` implements the six lifecycle methods through a private typed
shared host-process engine. Codex public classes stay in codex.py with identical
record fields, values, privacy representations and invalid-configuration errors;
root checked that differential in source and both fresh installed packages.
Default startup is unsupported. A factory is trusted host code, not authorization.
No launcher, SDK, credentials/config reader, Core endpoint or automatic apply was
added. Claude and Codex parse their own formats into private observations; no
Claude events are converted into pretend Codex captures.

| Latest47-module snapshot | Actual result |
|---|---|
| Source all unit + selected Core integration |1014pass /2 platform skips /0fail/error|
| Fresh offline wheel / isolated sdist components |640pass /1 FIFO skip each /0fail/error|
| Root independent related regression |529pass /1 FIFO skip|
| Ruff / format / mypy / diff |passed;233 formatted files;47 typed source files|

Root verified317 frozen files, all47 source/archive/installed module bytes,
noneditable origins, actual JUnit counts, command journals and artifact hashes.
The final8-selector snapshot reran source/build/wheel/sdist checks after a trace
patch line-ending mismatch; the earlier4-selector pilot and failed patch check
remain recorded separately. Original D CRLF bytes are retained; runtime files were
normalized to Git LF before the final tests and package builds.

Claude22 unit cases and3 temporary Core/SQLite cases exercise known Python
helpers only. Pending/running Core tasks and reopened state stay unchanged after
protocol completion. Late factory cleanup, request concurrency, capture reuse,
stale handles, history and unknown slots are covered. Local cancel/timeout can
only observe owned-parent termination; server cancellation, process-tree cleanup,
strict OS launch timing and cross-instance/restart identity remain unverified.

M6-04 has8 exact component selectors, partial/unverified. All42 formal requirements
and16 scenarios remain NOT RUN. Historical one-turn actual Codex evidence belongs
to the earlier implementation; no actual Codex or Claude call was made through
this refactored engine. Real client permissions, real relay and M9 remain gates.
Local Linux components for this exact frozen source are a separate pending run;
earlier real Docker26 target passes remain a separate supplement, not a full run.

Evidence: [shared lifecycle checkpoint](evidence/claude-adapter-local-20261026.json)
and D:/agentsync-debug/CLAUDE-ADAPTER-CHECKPOINT-20261026.json.

## Targeted real Docker supplement: 2026-10-25 America/Tijuana

After repairing only the D-only driver, the previously unexecuted26 fixtures
ran against frozen product6b16f20 and all passed:14 Docker +7 owner execution
+5 reconciliation;0 skips/failures/errors, exit0,119.63s. Root independently
verified actual child environment names/values, pinned-image inspect, actual
JUnit,26 JSON artifacts/hashes and unchanged312-file/45-module archive binding.
The testcase identities exactly match the earlier26 fixture setup errors.
No fixture, timeout, rule, safety limit or product code was changed. No image pull,
provider call or real Agent execution occurred. The intermediate VM-off attempt
remains NOT RUN; old failures remain immutable.

This is a targeted supplement, **not one complete passing Linux run**. Formal
release remains **BLOCKED**. See
[actual target evidence](evidence/docker-targeted-6b16f20-20261025.json).

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

## Prior offline Claude projection checkpoint: 2026-10-25 America/Tijuana

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
