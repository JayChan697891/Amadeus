# Release acceptance design

This document designs final v1.0 acceptance against the **42 formal requirements**
in SPECIFICATION.md and the milestone sequence in PLAN.md. It does not declare
those requirements passed. The machine-readable traceability register is
[requirements.json](requirements.json): every M0–M9 ID has an acceptance case ID,
execution method, expected outcome, existing selectors, missing work, and target
evidence location. The original T01–T16 scenarios remain mapped separately.

## Current frozen acceptance queue — a122

Product source is fixed at `5232e9e8bd33a949f7ffdc68410cd614a297af66`.
Use the original [a122 archives](../../releases/0.3.0a122/preview-5232e9e/manifest.json):
wheel SHA256 `8fd24c89b8b21a0b9e1aa5564fe130846af7a9516bb2c7cd2faf114ccc2c08ab`,
sdist SHA256 `c2607dfdf0bca5d6da324fd5550fddc734d97fddf4d6dee3d671333125397f5f`.
The four Windows/Linux installations already passed the same 97 affected cases.
Their completed commands are not a queue to repeat or a complete release matrix.
Historical a116/a120 full results retain their own source bindings.

This queue consolidates existing missing evidence; it adds no product requirement,
M5 phase or release exception. Each row needs its own exact driver/fixture hashes,
readiness review and observed exit before its status changes. Execution order is
the table order among ready rows; an unavailable row does not block unrelated work.

| Original requirements | Remaining bounded evidence | Readiness and stop conditions |
| --- | --- | --- |
| M2-05, M3-03/04 | **SCOPED PASS**, one actual a122 run: both actors, pinned context, old-lease/recipient/lock denials, owner audit and normal host reopen. See [exact plan and result](evidence/core-preview-a122/native-handoff/summary.json). | Five install bindings were reviewed before one new-fixture execution. Zero model calls, no account credentials or candidate execution. Root matched18 persisted audit records; both hosts ended by EOF and all10 recorded PIDs were absent. Task stays review/unverified, with no independent candidate acceptance. Do not repeat; original a121 exit1 remains BLOCKED. |
| M6-03, T13/T14 | **SCOPED PASS** for a122 real Codex launch, version/command/run/session bindings, result collection and independent artifact verification. One current direct `cancel_task` probe now has scoped Root/Astra acceptance; natural timeout remains **NOT RUN**, full M6 unaccepted. | [Actual cancel result](evidence/core-preview-a122/lifecycle-controls/cancel-result/summary.json): after `turn.started`, direct cancellation ended the owned parent; original `unknown/local_cancel_requested` status retained. This is distinct from parent interruption and does not establish server cancellation, descendant cleanup or Core completion. Older evidence retains its SHA; unsupported resume/server-cancel declarations remain explicit. Do not add service-internal generation/cancellation proof as a gate. |
| M7-02, M8-02 | **SCOPED PASS** for two real Codex calls, recovery of the persisted receiver proposal after actual controller exit73, and independent completion of the same receiver v6/verified. | Root/Astra accepted [the final observed boundary](evidence/core-preview-a122/composed-recovery/verification/summary.json). One owner-authorized Docker run passed2 cases/19 isolation checks, fresh owner-enrolled identities handled expiry, and no additional model calls occurred. Source remains failed and dependent unchanged. Both candidate grants are consumed. Do not repeat or extend this to full M7/M8 or cross-vendor acceptance. |
| M9-01/02 | First full current a122 Windows3.12 wheel suite **PASS:2539/57skip**; first Linux3.14 wheel suite **PASS:2589/7skip**,36 Docker observations, Root/Astra reviewed. Both first installed-sdist full suites now match their respective wheel case identities/outcomes, with Root/Astra scoped acceptance. Other complete current-candidate source/platform and release gates remain **BLOCKED / NOT RUN** as recorded. | Original archive/source/install hashes and all2587 old cases plus9 new cases checked. Do not repeat this suite or the completed97-case install checks. Preserve unavailable macOS and real Claude/Cursor cases, original static FAIL, pending license decision and manual credential cleanup. No all-in-one collector repeat or public release without separate approval. |

Scope correction after checking SPECIFICATION, RAT-M6-03 and the
[frozen M5 boundary](../M5-FINAL-ACCEPTANCE.md): the previous queue wording promoted
an unverified capability into an extra gate. The original requirements evaluate
local lifecycle behavior and declared capabilities, not service-internal token
generation. The [public CLI event contract](https://learn.chatgpt.com/docs/non-interactive-mode)
provides no timestamped guarantee of that internal state. Preserve the limitation
without adding a release condition or declaring any requirement passed. Independent
completion of the recovered real receiver proposal and the bounded M6-03 scope
assessment are now recorded above. The a122 Linux installed-wheel complete suite has now finished once; see
[actual results](evidence/core-preview-a122/full-linux314/root-review.json).
Remaining distribution coverage and the existing license decision require review;
do not repeat these suites or invent an extra gate. Guest disk capacity must be
checked before further large runs.

Store only new sanitized results under `evidence/core-preview-a122/` after actual
execution; planned paths are not existing evidence. Preserve failed attempts,
original logs and exact commands. The current working record and next executable
entry are in [PROGRESS](../PROGRESS.md); [CLIENT-MATRIX](CLIENT-MATRIX.md) distinguishes
native protocol observations from real model control. This plan does not start
jobs, extend credentials permissions or accept any of the 42 formal requirements.

Historical execution scripts may be stored as `.py.txt` evidence data. Their
original bytes and SHA-256 remain unchanged; each summary's `raw_execution_sources`
maps the archive name to the recorded execution filename(s). To reproduce, restore
those names in an isolated temporary directory, respecting any original one-shot
model/credential authorization limits. Logs and commands retain their original
names. Current active Python lint results do not claim that archived execution
scripts were reformatted, linted successfully or rerun.

## Initial audit and gaps

The code inspection found 14 requirements with existing component coverage,
14 with partial coverage, and 14 with missing coverage for the complete work
package. These are coverage classifications, not executed results. All register
execution statuses start at `not_run`; aggregate pytest success cannot turn an
unimplemented work package into a pass.

Existing tests cover task identity/state/leases, SQLite migrations, process
contention, MCP/SDK/HTTP coherence, context revisions/handoffs, and the M4A path
and cooperative-lock boundary. Reuse these tests rather than duplicating their
assertions. The following material gaps block final release:

| Area | Existing evidence boundary | Missing final acceptance |
|---|---|---|
| M0–M2 | Package, transport, persistence/security tests; historical client probes | Current artifact-level license/private-data inventory and current per-client live evidence |
| M3 | Real independent protocol client subprocess handoff | Real model-driven cross-client development continuation |
| M4 | Paths, file hashes and cooperative lease locks | Managed worktrees, actual Git conflict detection, approved safe merge |
| M5 | Credentials, error redaction, independent reviewer identity | Operation-role matrix, high-risk approvals, full audit redaction, independent evidence execution and adversarial tool-output handling |
| M6 | Host connectivity probes | Uniform adapter contract and real Codex/Claude Code/Cursor lifecycle |
| M7 | Task dependency checks | Scheduler, load/capability allocation, provider abstraction, budgets, automatic relay and bounded rate-limit retries |
| M8 | Some persistence and lease recovery tests | Scheduler/adapter crash reconciliation, provenance-aware usage, declared load/recovery budgets |
| M9 | Build configuration and platform-sensitive tests | Full current-SHA platform execution, wheel/sdist installation, distribution notices, complete gated release report |

`tests/integration/test_host_report.py` validates saved native evidence and
corruption rejection. It does not execute a live client. The M3 independent MCP
process test exercises real protocol/process behavior without model inference;
it does not prove a control adapter or autonomous relay. Historical Codex native
host calls and Claude CLI health are useful connection evidence only. A user's
desktop-connected report must retain its provenance rather than become an
automated desktop test claim.

## Test layers and evidence

| Layer | Reuse now | Add at the owning milestone |
|---|---|---|
| Unit | tests/unit | State/adapter/scheduler/budget/usage contracts |
| Integration | tests/integration | Approved workspace operations; adapters and scheduler persistence |
| Security | tests/security | Full authorization matrix, synthetic-secret audit scan, approval and prompt-injection regressions |
| Concurrency | tests/concurrency | Worktree races, scheduler duplicate triggers, concurrent callback/recovery cases |
| Fault recovery | Existing live HTTP restart, migrations and lease tests | Deterministic child-process kill/restart at each persisted transition, 429/5xx/timeout fixtures |
| Cross-platform | Existing platform-sensitive path and process tests | Windows/Linux/macOS current-SHA matrix with explicit filesystem capabilities and skips |
| Release installation | Existing import/CLI tests | Build/install wheel and sdist in fresh environments outside checkout, dependency and license inventories |
| End-to-end | Existing Core workflow and MCP handoff | Real two-client development/review/conflict workflow and adapter-driven automatic relay |

For each run save the command, exit code, start/end time, OS/Python/dependency and
client versions, package version, exact source commit SHA, dirty-tree state,
fixture identity, stdout/stderr, JUnit XML, build artifacts and hashes. Shared
runner evidence uses `<run>/report.json`, `logs/pytest.log`, `junit.xml` and
`artifacts/`. The register's requirement/scenario subdirectories describe the
target case-specific evidence layout, not files already emitted by a runner.
Reports must distinguish missing JUnit caused by launch failure from zero tests.

JUnit counts and artifact hashes substantiate the tested commands only. Each
formal requirement needs a mapped executed case and checked assertions before
its status changes to passed. Save failure seed, timeout, process transition,
reproduction command, and sanitized fixture so a fresh isolated run can reproduce
the defect. Do not archive credentials, personal repositories, global client
configuration, or unsanitized provider responses.

## Real two-Agent acceptance

Use a dedicated disposable Git repository and absolute isolated state directory.
Record every transition and content hash. Agent A and B must be distinct real
supported clients/sessions; scripted protocol clients are a separate test tier.

1. A creates the project/task, publishes requirements and a constraint revision,
   claims development work, and obtains the relevant cooperative lock.
2. B reads the same task and context; duplicate claim fails. Both clients create
   separate managed worktrees. Their deliberate conflicting fixture edits produce
   a reported Git conflict without overwriting the original worktree.
3. A produces a bounded actual code artifact and submits its changed-file hashes,
   test observations, unresolved questions and immutable context references in a
   structured handoff. New context revisions do not mutate the pinned package.
4. B accepts the handoff with a new lease, continues the artifact, then submits
   for independent review. An independent authorized reviewer reruns allowlisted
   acceptance commands against the exact immutable submitted SHA/artifact.
   Self-declared results and supplied JUnit alone cannot authorize completion.
5. Through the real control adapters, the scheduler detects completion, starts
   the eligible next task on the other client and collects its result without
   human message forwarding. Verify real continuation at least once and the
   error/retry path separately. Manual handoff is not autonomous relay.
6. Restart the service and one client, replay callbacks/triggers, expire a lease
   and inject a bounded 429 response in a local fake-provider fixture. Assert
   unique run/owner, bounded backoff, preserved evidence and stale-owner denial.

Real-provider rate-limit injection is unnecessary and must not spend money:
fake endpoints prove deterministic retry logic while reports explicitly mark
that boundary. Real adapter smoke and relay require approved, available auth and
quota. Missing auth, exhausted quota, unavailable client or unsupported platform
is `blocked`/`unverified`, never mock success.

## Client acceptance matrix

| Client | Required real observations | Existing boundary / gate |
|---|---|---|
| Codex | Public supported SDK/CLI version, start, run/session identity, status/result and independently tested artifact; probe advertised cancel/resume | Native connection probes do not satisfy M6-03 |
| Claude Code | Public SDK/CLI, bounded tool permissions, lifecycle and artifact, explicit unsupported capabilities | CLI MCP health does not satisfy M6-04 |
| Cursor | Supported noninteractive CLI per claimed OS, lifecycle, structured output, timeout/nonzero exit | Configuration examples do not satisfy M6-05 |
| Other MCP-compatible clients | Connection, discovery, calls, state coherence per explicitly claimed client/version | Generic MCP protocol success does not imply client compatibility |
| MockAdapter | Deterministic lifecycle, failures, retries and budgets with no credentials | Required software regression tier; cannot satisfy any real-client/relay gate |

Record capability values as supported/tested, unsupported, blocked, not_run or
unverified, with evidence. No GUI simulation, unsupported internal API or saved
fixture may masquerade as a public control adapter. Add future advertised clients
to this matrix and the register before claiming support.

## Safety and execution order

All destructive tests must create an owned temporary root or dedicated test
repository, resolve its absolute path and verify every mutation remains beneath
that root. Never run cleanup/reset/merge/kill against the user workspace,
production data or an unverified PID. Test child processes are started and owned
by the fixture, bounded by timeouts, then joined/terminated and inspected. Only
fixture-owned state may be removed. No source checkout/global MCP settings are
test targets. Hostile-path tests place link targets in sibling fixture roots,
not arbitrary personal directories.

Implementation proceeds with the owning milestones:

1. Establish the register, truthful report/status model, reproducible aggregate
   runner and preserved CI/JUnit/build evidence. Add fresh artifact installation
   checks without changing the implementation to satisfy fabricated coverage.
2. Complete M4B worktree/conflict/safe-merge cases and M5 approval/audit/evidence
   verifier cases. Keep every existing security regression.
3. At M6 add one adapter contract and MockAdapter tests, then separate actual
   client smoke runs for Codex, Claude Code and Cursor. Never spend on provider
   inference without explicit cost authorization.
4. At M7/M8 add scheduler relay, duplicate event, budget, rate-limit and crash
   recovery fixtures; follow with real two-client relay in an authorized runtime.
5. At M9 freeze a candidate SHA and package set; execute every formal acceptance
   case and platform/client matrix; independently review evidence and publish a
   Release Acceptance Report before any separately authorized release.

## Final release gate

A report must list passed, failed, not_run, blocked and unverified cases, linked
requirements, limitations, exact candidate artifacts and SHA. A passing aggregate
pytest run is a development regression result, not final product acceptance.

Final acceptance is blocked if any critical case fails, any serious security
issue remains unresolved, any required formal requirement lacks case evidence,
artifacts differ from the tested candidate, or **real autonomous relay has not
been demonstrated**. Documented unsupported capabilities are allowed only where
the specification permits explicit unsupported (for example client cancellation);
they cannot waive a required ability to start and collect a real supported
client task. Missing required real client/platform evidence prevents an
unqualified final acceptance claim. A limited alpha checkpoint may be reported
with precise limitations, never relabeled v1.0 accepted. GitHub Release publication
still requires its separate authorization.


## M4B staged update

M4B adds actual isolated Git worktree, conflict, immutable candidate and crash/replay
component cases to the register. The 14/14/14 inventory above describes the initial
audit, not the updated count. Approval/application and real client autonomous relay
remain outstanding. The final requirement cases remain not_run until independently
executed against the release candidate.

## M5B1 staged update

The register now maps bounded Git snapshot, simulated Docker policy and actual Linux
Docker black-box test selectors separately. This owner library verifies only finite
cases for standalone solution.py; it does not queue jobs, change task completion,
consume approval or apply a merge. Ordinary matrix runs without Docker image record
the14 actual-container cases as skipped; the required local Linux debug gate must
execute them. GitHub is upload/storage only under the current owner instruction;
do not dispatch Actions or use hosted checks/benchmarks. Full M5-04 acceptance stays not_run until integrated permission, durable
recovery, applicable independent evidence and completion gates are actually tested.

## M5B2B staged update

The register includes owner execution, durable binding, cancellation/fencing and
schema migration components. Real integrated owner cases use isolated managed Git
and local Linux Docker; policy injection tests remain separately labelled. A
finite snapshot/profile result is not a task-completion gate or whole M5-04 pass.
Unknown crash/create state remains pending with no automatic retry/reconciliation.
M5B1 and M5B2A limited checkpoints passed Work review; full M5/M9 and real client
relay remain open. All execution stays local on D:, never GitHub Actions.
