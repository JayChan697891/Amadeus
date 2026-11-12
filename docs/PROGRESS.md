# Amadeus current progress

## Queue liveness diagnosis and source-distribution installation

The bounded queued pilot on6017005 stopped before login-status/model dispatch at
2026-11-12T12:43:02UTC. Its producer heartbeat was277.944664seconds old, beyond the
120second online window, although the authentication session remained valid.
The queue correctly returned no_ready_tasks; exact launch plan, argv, environment
and workspaces were unchanged. Task remains pending/v1/unverified, both attempts
not_dispatched and no pending wave. The temporary authentication copy was removed
and its RAM filesystem unmounted; original authentication is unchanged. No retry.
Real queued-client acceptance remains NOT RUN, not a model failure or success.
[Failed preflight evidence](acceptance/evidence/m7-queue-preflight/summary.json).

Test-only74e1527 adds the actual liveness regression without changing product
rules: stale heartbeat refuses launch; legal authenticated heartbeat restores
the original selection and exact plan. Existing expired-session and online tests
were reused.13Windows checks pass, with independent diff/XML review.
[Regression](acceptance/evidence/m7-heartbeat-regression/summary.json).
The frozen6017005 sdist now installs offline on fresh Windows3.12.16 and Linux3.14.7
environments; one existing queue integration smoke case passes per platform.
All88 runtime members/87Python modules match before/after; dependencies are valid.
[Installation evidence](acceptance/evidence/m7-sdist-install/summary.json).

A complete local regression uses those installed sdist runtimes with frozen
test/source74e1527. Linux is complete:2290passed/6skipped, zero failures/errors;
14actual Docker and2same-Core Docker proposal cases passed. The six skips are
five Windows-only cases and one non-Linux unsupported-backend case. Independent
review checked the complete command/XML/log and source/runtime identity.
Windows is complete:2251passed/45skipped, zero failures/errors. Both environments
have the same2296case IDs; each skipped case passed on the other platform.
This does not provide missing Windows symlink privileges or Linux container
capabilities on Windows. Independent review accepts this complete local matrix
for the exact installed runtime/test-source pair; no additional full rerun needed.
[Full regression evidence](acceptance/evidence/m7-full-regression/summary.json).
Recovery: D:/agentsync-debug/m7-full-74e1527;
Linux guest /root/amadeus-full-74e1527. Both result.json records are terminal;
driver.py has a guarded main for multiprocessing.1222source files and88 installed
package members remained unchanged; sanitized logs/JUnit and version pins saved.
The dedicated Docker daemon has zero containers and the owned VM is stopped.
No new live client attempt is scheduled.
Next prepare a separate bounded live-queue fixture only under the existing
authorization/fee gates, maintaining its own valid Core heartbeat before current
selection and exact-plan checks. Do not retry the consumed preflight controller.
Keep unknown cancellation/timeout and missing second-client access explicitly
unverified; this local matrix does not replace those actual-client requirements.
Claude/Cursor real runs remain unavailable: owner has neither subscription.
M5/M6/M7 and formal Release remain BLOCKED.

## M7 prepared proposal scheduling

Frozen product6017005 adds CodexProposalQueueItem to the existing bounded queue.
Prepared single-producer proposals share dependency/priority/capability/load and
disjoint participant/worktree selection with existing two-client fixed-reply
items. Explicit submit_for_review and exact per-launch consent remain mandatory;
the wave is bound into the proposal contract. Only complete same-wave capture,
immutable publication and review receipts count as ready_for_review/unverified.
Unknown, cancellation, missing receipts and budget exhaustion keep the fence.
There is no automatic candidate staging, execution, completion or source apply.

Authenticated restart reconciliation can recognize historical submission after
the producer expires. A review finding corrected the current-state observer:
re-read the task after context/receipt validation so a concurrent legal independent
review cannot leave a stale submitted_for_review answer. The new race regression
passes. Old pair previews/pins/journal and standalone proposal contracts remain
compatible. No new M5 subdivision or release-gate change was made.

Before the observer correction,71 source cases passed; afterward the two affected
suites33passed. Those are separate scopes. Final frozen fresh Windows3.12.16 and
Linux3.14.7 wheel installations each pass72cases, zero skips/failures. All88 runtime
package members (87Python modules) match before/after, with no source shadowing and
valid dependencies. Ruff/format330/mypy87 pass. Independent review accepted the
code and packages;642 tracked sdist members match the frozen commit. Sdist install,
new full matrix and actual queued model execution remain NOT RUN.
[Evidence](acceptance/evidence/m7-proposal-queue/summary.json).

Debug: D:/agentsync-debug/m7-package-proposal-queue; artifacts under
releases/0.3.0a109/m7-queue-6017005. The dedicated Docker daemon has no containers and
the owned VM is stopped. No model calls or credentials were used for this feature.
The actual a2634ec client evidence below is historical, not a new-SHA model pass.
Next assess one bounded real queued proposal under an exact approved launch plan;
no such run has started or been scheduled. Cross-client remains unavailable and
full M5/M6/M7/Release remain BLOCKED.

## Consolidated a2634ec regression and test-only repair

Complete existing suites against the earlier installed a2634ec wheel finished:
Windows2206passed/34failed/45skipped; Linux2245passed/34failed/6skipped, including
actual local Docker. Both have the same34 failed cases: the exact MCP tool list
missed publish_task_proposal (1), acceptance test counts/selector fixtures lagged
implemented Codex/Cursor components (32), and the local test driver lacked a main
guard so multiprocessing reentered pytest (1). Source and87 runtime module bytes
are unchanged. Platform skips and original failures remain in the saved XML/logs.

Test-only6e2975e updates the exact tool/selector expectations without deleting tests
or weakening unverified/Release-blocked assertions. A guarded driver uses the normal
pytest module entry point. The two affected suites and unchanged process/thread
competition case pass163checks on each existing Windows/Linux installation.
Independent review accepts the repair and driver diagnosis. Initial Linux preparation
failed before collection because the prior limited fixture bundle lacked the runner;
a fresh complete Git archive supplied the missing files. That failure is retained.
[All original results and scoped repairs](acceptance/evidence/m6-full-regression/summary.json).

This is a full baseline plus targeted repair, not a claimed full rerun or a6017005
full-matrix pass. No new model calls, source application or GitHub Actions occurred.
Debug: D:/agentsync-debug/m6-full-a2634ec, m6-linux-live-20261112 and
m6-regression-repair-6e2975e. Formal M5/M6/M7/Release gates remain unchanged.

## Actual Linux proposal to same-Core verified completion

Runtime a2634ec now has one actual subscription-route Codex pipeline on the local
Linux Core/Docker host. The pinned CLI returned the requested153-byte solution in
27.416seconds, exit0; the adapter stored immutable context and submitted the same
task for review. After inspecting the actual source and exact staging digest,
the owner-mediated staging service created a genuine isolated candidate. Existing
Docker verification passed8/8 inputs and19 isolation checks. A distinct Core
reviewer completed the same task; reopening confirms completed/version6/verified.
Candidate bytes match the reviewed proposal through execution and completion.
Independent development review accepted this limited evidence without a rerun.

Temporary ChatGPT authentication used a0700 tmpfs home; current mount/source/type/
options were checked before copying. The0600 copy was removed and the mount released
before candidate execution. Original authentication, source and producer worktree
are unchanged.87 installed runtime modules match the existing wheel before/after.
The fixed local Docker socket independently reports the recorded container absent.
Raw capture remains private; its476-byte stderr has not been classified. Billing
was not independently verified; owner-confirmed credits0/autorechargeoff and actual
CLI ChatGPT login status were the fee/route gates. No API key or paid API was used.

[Evidence](acceptance/evidence/m6-linux-live/summary.json) includes a report-derived
JUnit aggregate, exact plans/helpers, actual receipts and hashes. It is not a new
pytest/full-matrix run. The prior Linux readiness, fixture and Windows records
below remain historical. This attempt is consumed; never rerun its controller.
Debug: D:/agentsync-debug/m6-linux-live-20261112. Private guest state is not uploaded.

This closes the limited same-Core real-proposal pipeline gap, not M6 as a whole.
Review is host-mediated, not a second model. Cross-client remains NOT RUN because
the owner has neither Claude nor Cursor subscription. Active-generation timeout,
server/descendant cancellation, unattended relay/application and the unique M5
exit checklist remain open. Full M5/M6/M7/Release remain BLOCKED. Next inspect those
existing requirements and implement the next authorized product gap; do not create
another M5 subdivision or repeat this successful single-client experiment.

## Linux single-task host readiness

Runtime a2634ec adds explicit `linux_readonly=True` for the pinned0.167.0-alpha.3.2
CLI, with strict boolean/platform/version checks and mutual exclusion with MXC.
Default/legacy/MXC plans retain their parameters. Linux selects a named minimal/
project read-only profile, network denied, exact pinned executable read permission
for portable re-exec, restricted feature settings and no collaboration registration.
The45-argument plan remains below the unchanged64-argument limit.

Actual official musl CLI package digest matched before execution. Native no-model
checks accept strict configuration and render the limited tool surface.18 requested
features are effectively false; unified_exec remains true, explicitly retained in
the evidence. Advertised tools are exec/wait/questions/sleep with apply_patch,
resource reads and clock nested headings. This does not mean all tools are absent.
Known local commands read the project, cannot write it, cannot read the outside
synthetic canary, and cannot connect to an owned loopback listener; the unsandboxed
control connects. No external target, credential copy or model call occurred.

Frozen source48pass; fresh Windows wheel48pass; fresh Linux wheel47pass/1Windows
MXC-only skip.87 runtime modules match before/after on both platforms. Ruff,
format329 and mypy87 pass. Independent review accepts this scoped implementation,
native evidence and packages. Earlier failed command forms, portable path probe
and network-test helper correction remain recorded, not counted as passes.
[Evidence](acceptance/evidence/m6-linux-readonly/summary.json).

The D-drive VM now uses a32GiB overlay with the original complete16GiB image retained
as its backing/rollback layer. Guest cloud-init grew the filesystem at boot; about
15GiB was available afterward. All earlier work remains. The owned VM is stopped.
CLI: /root/amadeus-codex-linux-0167/bin/codex in this VM; no default-home/PATH changes.
Debug: D:/agentsync-debug/m6-linux-codex-preflight and m6-package-linux-readonly-portable.

Next prepare one bounded real Codex proposal capture/review on the same Linux
Core/Docker host, with authentication/fee gates, exact launch consent and temporary
credential cleanup before isolated candidate verification. No real Linux run is
started or scheduled yet. Earlier consumed runs stay untouched. Cross-client remains
NOT RUN (no Claude/Cursor subscription); full M5/M6/M7/Release remain BLOCKED.

## Same-Core proposal pipeline with actual local Docker

Runtime d4c7cf9 is unchanged. Test c181f99 exercises fixed local Python protocol
output through controlled capture, review submission, explicit owner/stager pins,
genuine managed Git candidate, actual Linux Docker and a distinct Core reviewer.
Two scenarios pass: correct output completes with durable verified status; wrong
output stays review/unverified. The producer is refused self-review even with the
reviewer role. Repeat model/execution starts are rejected. Original source/producer
trees remain unchanged and reopened task states match the persisted outcomes.

The initial ba941c2 test used unsupported get_task only at its final reopen check;
both failures are preserved. c181f99 uses authenticated list_tasks and passes both
scenarios in fresh isolated projects. Windows traceability92pass and Docker2skip
belong to ba941c2; Linux executes those two Docker cases. No product fix was needed.
Review found the independent absence check could consult a different Docker context.
7fe0c28 pins it to the verifier's trusted CLI/local socket and an empty config/minimal
environment. The new helper subsequently confirmed both c181f99 container IDs absent
on that socket. No repeated Docker scenario was needed for this observation-only fix.

Evidence: [m6-proposal-pipeline/summary.json](acceptance/evidence/m6-proposal-pipeline/summary.json).
87 runtime module hashes match before/after; exact d4c7cf9 installed wheel reused.
Ruff/format329 pass. Source/test/package SHAs are separately recorded, not collapsed
into a full new-SHA acceptance claim. The dedicated owned VM is stopped.
Debug: D:/agentsync-debug/m6-proposal-pipeline and m6-proposal-pipeline-recheck.
No model calls or credential copies. Core reviewer identities are host-mediated;
the protocol fixture is not a real Agent. Full M5/M6/M7/Release remain BLOCKED.

Next recovery entry: assess a supported real Codex CLI on the same isolated Linux
Core/Docker host, then a separately authorized real run of this existing path.
The older Windows capture is historical and must not be retroactively submitted or
retried. No Claude/Cursor subscription is available; cross-client remains NOT RUN.
No new real-client run has been launched or scheduled by this checkpoint.

## Controlled proposal submission and staging bridge

Frozen d4c7cf9 binds optional submit_for_review to the approved launch contract.
After immutable publication, the original live lease and exact task revision are
required for review submission. Missing completion receipts remain incomplete.
Default capture behavior and old launch digests are preserved. The new owner-only
bridge requires a separate staging worker and the exact caller-reviewed plan hash;
queue creation, isolated execution and independent completion remain explicit.

Frozen source:151passed; fresh Windows wheel:45passed; fresh Linux wheel:23passed.
Both installations match87 runtime module hashes before/after with no source
shadowing and valid dependencies. Ruff/format328/mypy87 pass. The first Linux
preparation failed before tests because its archive was absent; the preserved
empty directory was checked, upload repaired and the tests executed once.
Independent frozen-source review found no blocker. The original actual bf54d44
capture remains proposal_stored, running/v4/unverified with review not requested
and unchanged source/worktree, observed read-only under the new code.

Evidence: [m6-proposal-review/summary.json](acceptance/evidence/m6-proposal-review/summary.json).
Debug: D:/agentsync-debug/m6-proposal-review and m6-package-proposal-review.
No new model call, credentials, candidate execution or source apply. Full matrix,
current real-model pipeline and cross-client checks are NOT RUN. Claude/Cursor
subscriptions are unavailable. M5/M6/M7/Release gates remain BLOCKED.
Next: exercise the same-Core capture-to-review-to-staging-to-Docker-to-independent
completion path using a known local protocol fixture; distinguish this integration
check from actual client/model acceptance. The owned VM remains available for it.

## Product owner-reviewed proposal staging

Implementation193d9b2 adds OwnerProposalStaging.preview/stage_once/status. Owner
and active staging-worker authority bind an exact reviewed digest to authenticated
publication/context, current review-state task, original worktree/head and file
hashes. New worktree/candidate records use genuine Git operations and the staging
identity; original producer/source workspaces remain untouched. A permanent
task-wide intent precedes effects. Any interrupted attempt stays incomplete and
cannot be retried. No automatic queue, code execution, task completion or apply.
Tracked Git attributes/modules, foreign metadata indirection and path aliases are
explicitly unsupported/rejected. The unique M5 safety/Release gates are unchanged.

Frozen source run:179passed,1Windows POSIX-FIFO skip,1traceability-count failure.
0712899 fixes only that test count (12 to14); affected92 traceability cases pass.
Fresh193d9b2 Windows/Linux wheel installations each pass32 staging tests, with87
runtime modules matching before/after and pip check passing. The0712899 rebuilt
package passes92 affected traceability cases in a fresh Windows installation;
all88 runtime package members and staging tests are byte-identical to the tested
193d9b2 artifact. Staging tests were not unnecessarily rerun after the count-only
fix; the final artifact's Linux installation and full new-SHA matrix are NOT RUN.
Ruff/format327 and mypy87 pass. Development failures and the corrected audit-target/
Git-receipt parsing assumptions remain recorded. Independent review accepted the
implementation and the193d9b2 Windows/Linux package checks; final evidence review
is tracked in [the hash-bound summary](acceptance/evidence/m6-proposal-staging/summary.json).

Recovery: source0712899, debug D:/agentsync-debug/m6-proposal-staging,
D:/agentsync-debug/m6-package-proposal-staging and m6-package-staging-final.
The owned VM has stopped. No new model call, candidate execution or credentials.
Next connect controlled proposal submission-to-review with this owner staging
service and existing candidate verification flow. Preserve producer lease/attempt
fences and a distinct completion reviewer; do not recover unknown model runs by
inventing success. Claude/Cursor have no subscription, so cross-client stays NOT RUN.
Full M5/M6/M7/Release remain BLOCKED.

## Actual proposal artifact: isolated owner-mediated verification

Runtimebf54d44 and pilot8520691 now bridge the captured actual Codex add.py into
a new dedicated local Linux project, with genuine managed Git candidate records.
The exact63-byte proposal is preserved; a separately hashed owner-authored JSON-lines
driver adapts it to the existing fixed verifier. No generated code runs on the host.
One actual Docker pipeline checked8 inputs:8passed,19 isolation predicates true,
exit0, cleanup confirmed and independently observed container absent. A distinct
Core reviewer completed only the new fixture task atversion5/verified. Reopening
the original Windows producer still shows running/version4/unverified; its context,
source/worktree and runtime are unchanged. No new model call or authentication copy.

Fresh offline Linux wheel installation uses the existing9e4b64bf artifact;
all85 runtime modules and migrations match its bytes before/after, pip check passes.
The new pilot passes Ruff/format. JUnit records one aggregate actual pipeline case
with8 checked inputs, explicitly report-derived rather than a pytest invocation.
See [artifact evidence](acceptance/evidence/m6-proposal-artifact/manifest.json).

Owner now confirms neither Claude nor Cursor subscription. Cross-client calls and
acceptance remain NOT RUN; do not request the same account facts or start paid APIs.
This is owner-mediated import and reviewer operation, not automated import,
cross-Core authenticated provenance, a second model reviewer or full M6/Release.
The local safe evidence is D:/agentsync-debug/m6-proposal-artifact-20261112;
private guest Core state remains solely in the dedicated VM, never uploaded.

Next: implement the product owner-only proposal-to-managed-candidate staging seam,
with reviewed immutable content/task/worktree/head pins and no source-workspace apply.
Reuse the existing candidate exporter, queue, executor and independent completion
gate; retain original unknown/failure fences and the unique M5 exit checklist.
The pilot is complete and must not be rerun as a model task. Full release matrix,
cross-client execution and unattended artifact relay remain unverified.

## Current product: actual Codex proposal capture

Productbf54d44 integrates exact approved proposal contracts with the existing
one-attempt Codex lifecycle and atomic Core publication. Capture and immutable
context are linked by canonical file and envelope hashes plus producer/task/
worktree/head/launch pins. Proposal storage never satisfies ordinary relay review,
changes task state or imports/executes code. Unknown/crash states remain fenced.

Windows187passed including92 traceability cases; fresh offline wheel36passed,
85 runtime module hashes matched before/after. Pip check/Ruff/format/mypy85 pass.
Initial test-only version assertion failures are retained without weakening gates.
Linux/macOS and the full new-SHA matrix are NOT RUN.

One real Codex call at2026-11-12 09:49:48UTC exited0 in22.014s. It generated a63-byte
add.py proposal; Core reopened proposal_stored/contextversion1/taskversion4, while
the task stays running/unverified and legacy relay observation stays incomplete.
Astra independently accepted actual capture-to-Core only. Syntax-only inspection
found one add function/no imports/top-level actions; semantic correctness and code
execution remain UNVERIFIED/NOT RUN. Raw695stdout/119unclassifiedstderr bytes stay
restricted locally. Temporary auth removed; original, fixtures and runtime unchanged.
See [source/package and real capture evidence](acceptance/evidence/m6-proposal-capture/summary.json).

Resume from bf54d44: independently validate the generated artifact through existing
isolated verification, with an explicitly reviewed owner import that creates real
managed candidate provenance. No fabricated CandidateInput/receipts, workspace apply
or host execution of model code. The consumed pilot is not retried. Its private
local directory is D:/agentsync-debug/m6-codex-proposal-live-20261112; raw output,
credentials and Core state must not be uploaded. Existing M5/Release gates remain.
Claude/Cursor account/no-extra-fee facts remain pending; no additional call is started.

## Current product: inert task-bound source proposals

Product80754db adds publish_task_proposal across Core/SDK/HTTP/MCP. Authenticated
worker+running task version+live lease+owned clean Git head bind a new immutable
context revision atomically with idempotency/audit. Code remains inert data; task,
worktrees, candidate queues and verification remain unchanged. Historical replay
returns the same context without renewing authority. Source/path labels are not
proof of a model run or permission to import code.

Windows source241passed; requirement mapping92passed; fresh offline wheel55passed,
85 runtime module hashes matched before/after and pip check passed. Ruff/format/
mypy85 pass. Initial fixture/setup failures are preserved. Astra accepted this scoped source/package evidence. Linux/macOS and full matrix for this new delta NOT RUN.
See [frozen proposal storage evidence](acceptance/evidence/m6-task-proposal/summary.json).

The following was the prior checkpoint: integrate successful complete adapter output
with a host-pinned proposal contract and this atomic receiver (implemented above). Preserve unknown/timeout/cancel fences, hash-only
receipts and unchanged task state. A later owner importer must produce a genuine
managed merge candidate before existing isolated verification/completion gates;
never fabricate CandidateInput or trust a context source label. This remains M6
work under the existing M5 checklist, not a new M5 substage. Cross-client account
facts remain pending and historical real tests below keep their original SHA scope.

## M6 single Codex pilot

The once-authorized real Codex task ran at product `6a8ff41`. The CLI recognized
ChatGPT authentication and exited 0 after about 31 seconds, but the adapter
rejected its output as `protocol_invalid`. The result is UNKNOWN and the Core
attempt remains incomplete/running/unverified, including after reopening; no
review submission or real-client acceptance occurred. The source and actual
worktree were unchanged. The authorized temporary auth.json copy was removed,
and the original authentication file's bytes were unchanged. Both single-use
permissions are consumed. No retry was performed or authorized.

The exact parser cause remains unknown because the ephemeral session and host
runner retained no raw stdout. Do not infer an encoding or event-schema defect.
Product `080722e` now preserves only a whitelisted parser reason, byte counts,
SHA256 and truncation flags through the adapter and stopped attempt receipt.
Unknown state, held slots, result suppression and no-retry semantics remain.
Astra reviewed this diagnostic change; it is not a fix or reclassification of
the earlier real attempt. Windows Python 3.12 passed 86 shared-adapter/pipeline
cases and 4 owner-status/journal/budget cases; Ruff/format and mypy (84 modules)
passed. The initial five failing diagnostic regressions are retained.
See [actual attempt and diagnostic evidence](acceptance/evidence/m6-native-mxc/live-and-diagnostics-summary.json).

The same `080722e` wheel, rebuilt from the frozen sdist, now passes all 7 new
selected diagnostic cases in fresh offline Windows3.12 and Linux3.14 installs.
Both runs matched all84 runtime-module hashes before/after and passed pip check;
44 unrelated cases per invocation were deselected, not counted as passes. The
owned Linux VM stopped after evidence retrieval. See
[installed diagnostic evidence](acceptance/evidence/m6-native-mxc/diagnostic-package-summary.json).
This adds no model call and does not resolve the real protocol failure.


For the preceding `6a8ff41` product, Windows source preflight passed 39 cases,
and a fresh offline wheel rebuilt from sdist passed 51 selected cases with all
84 installed module hashes matched. Linux Python 3.14 source now passed 50 cases
with one Windows-only MXC skip and all 84 runtime modules matched. Its owned
D-drive virtual machine stopped normally after evidence retrieval. These results
do not cover `080722e` installed packages/Linux/macOS or any formal Release gate.

Resume from repaired product `ee456900fad6bb4cfc09cad0eecdc9ce1371ab74`.
The separately authorized diagnostic ran once at the preceding `080722e` runtime
on 2026-11-12 at 07:17:31 UTC. After normal Core session refresh, its actual plan
was `806d85f2da3ca833394a468410cb342dccd9cc3e19d78e348b2fe910696846b0`.
The CLI exited0 but the old parser rejected a completed startup error item before
turn.started (`invalid_event_sequence`). The 606-byte private stream then contains
the exact fixed reply and turn completion. The grant is consumed, temp auth is
removed and the original unchanged. The Core attempt remains incomplete and was
not rewritten. Raw output remains restricted locally and is not uploaded.

The parser now accepts only completed error items with a string message after
thread.started and before turn.started. Fatal errors, duplicate IDs, turn ordering
and input bounds remain enforced; warning text is never projected. Official
upstream warning emission corroborates this shape, without proving installed
binary equivalence. Offline replay of the exact saved bytes now parses the fixed
reply; this is not a new live execution or Core acceptance. Windows source:101
passed; the same wheel rebuilt from sdist passes17 tests in each fresh offline
Windows3.12 and Linux3.14 installation (46 deselected each), with84 module hashes
matched before/after and pip check passing. The owned Linux VM stopped normally.
Ruff/format and mypy84 pass. Astra scoped review found no blocker. macOS and the
full release matrix for this delta are NOT RUN.
See [repair and actual diagnostic evidence](acceptance/evidence/m6-native-mxc/startup-warning-summary.json).

The separately authorized new validation actually ran on 2026-11-12 at
08:15:51 UTC (00:15:51 America/Tijuana), using the same prepared plan
`ce6032da2c3624ef3aee259da404c2f15e82a1ef2d60681e730148f3976499b3`.
It recognized ChatGPT login, exited0 after55.953s, matched the exact reply and
reopened in Core review/unverified. Independent Astra/root review accepted this
limited submission path; a distinct Core reviewer then completed the task, still
unverified for code artifacts. No tool items were observed. Original auth and
fixtures/runtime stayed unchanged; temp auth was removed. The606-byte failed
stream belongs to the previous diagnostic; this successful run retained602 stdout
and476 unclassified stderr bytes locally only. The one-shot grant is consumed.
See [actual repaired run](acceptance/evidence/m6-native-mxc/live-repaired-summary.json).

The next bounded same-client relay actually completed on2026-11-12 08:29:04UTC.
Two distinct Codex workers, protocol sessions, private homes and managed worktrees
ran once each (38.108s and56.125s, both exit0). Core created/claimed the task,
compared worktrees, transferred a structured handoff and pinned context, then
submitted the second reply for independent review. The second response matched
the shared context. Astra/root accepted this limited automatic sequential relay;
a third Core identity used review_once and completed the task, still unverified
for code artifacts. Both temporary auth copies were removed, original and all
fixtures/runtime unchanged. Raw output remains local only. No source changes or
redundant tests were needed. See
[real two-session evidence](acceptance/evidence/m7-real-codex-relay/summary.json).

Cursor native-bundle support is now implemented at
`f74f29f73148d0e0e9a69ebb486eaffe6061d936`. The official Windows package uses
node.exe plus index.js; preparation pins the complete bounded package inventory,
rechecks queued directories and binds the bundle digest to exact launch consent.
Legacy hashes remain unchanged. Explicit home/config paths support private D-drive
environments. Node external resolution and filesystem atomicity remain unverified;
this is not a sandbox assertion. Windows source47passed/2symlink skips; fresh
Windows wheel16passed/2same skips; the same wheel on Linux18passed/0skips, including
actual file/directory symlinks. Both installs matched84 runtime modules; pip check,
Ruff/format/mypy84 pass. Astra found no remaining source blocker after the traversal
fix. M6-05 coverage maps the new tests;92 traceability tests pass without upgrading
formal execution_status. See [Cursor bundle evidence](acceptance/evidence/m6-cursor-node-bundle/summary.json).

Actual local cancellation is now scoped accepted at runtime f74f29f/head7d573a0.
On2026-11-12 08:58:19UTC, one actual Codex turn was observed started with the parent
still running and no terminal event. Caller cancellation propagated; the owned
parent ended with exit1. Reopened Core remains running/unverified and controller
incomplete, preserving unknown/local_cancel_requested. The5.546s value is total
adapter elapsed time, not cancellation latency. Temporary auth was removed,
original/fixtures/runtime unchanged, no retry. Astra independently reviewed the
safe records. Server cancellation, descendant cleanup and billing remain unverified.
See [actual cancellation evidence](acceptance/evidence/m6-native-mxc/cancel-live-summary.json).

A new real15-second Codex deadline at runtime f74f29f/head d73e044 recorded
adapter_timeout/timed_out=true and parent exit1 after15.014s. Reopened state stays
incomplete/running/unverified. The600-byte private stream also contains the exact
reply and turn.completed: active-generation timeout and event/deadline ordering
are NOT VERIFIED. The completed text did not override the unknown stop receipt.
Astra accepted only the real local deadline and durable fail-closed outcome.
Temp auth removed, original/fixtures/runtime unchanged; no retry. See
[actual deadline evidence](acceptance/evidence/m6-native-mxc/timeout-live-summary.json).

Next: cross-client account and isolation readiness. The official Cursor CLI was
installed only under D: and passed version/help/plan preparation, with no model
call, account/PATH or desktop-install changes. Claude2.1.295 version matches, but
default login credentials are absent. The owner was asked which existing Claude
or Cursor subscription/login is available and whether extra billing is disabled;
that factual answer remains pending. First-choice approval does not supply missing
credentials or establish fee state. Do not switch to paid API fallback. Same-client
real relay evidence remains scoped to ee45690, not full M6/M7/Release. No new M5
subdivision or duplicate baseline tests.

The isolated branch `feat/m6-single-codex-pilot` adds host-only
`ControlledRelay.preview_codex` and `run_codex_once` at `3685555`.
The pilot reuses exact launch consent, the task/worktree ownership check,
the durable one-attempt fence and the existing lifecycle adapter. A matching
reply submits the task for independent Core review with verification still
unverified. A denied or mismatched result leaves an incomplete attempt.

Cancellation repair `2016554` preserves the actual adapter stop observation
before propagating caller cancellation. Reopening can distinguish a recorded
unknown result with a confirmed ended parent from a missing observation. This
does not confirm descendant cleanup, authorize retries or verify task completion.
The new disposable-process cancellation regression failed before repair; after
repair, 14 pipeline/budget and 2 owner-status/journal tests passed on local
Windows Python 3.12. Timeout and exit-code-3 cases preserve incomplete tasks and
the no-retry fence. Ruff, formatting and mypy (84 modules) passed. See
[saved failure and retest](acceptance/evidence/m6-single-stop/summary.json).
New installed-package, Linux/macOS and live-client execution tests are NOT RUN
for this delta; earlier full suites remain scoped to their frozen product.

Windows local evidence comprises 11 relay integration cases and 77 lifecycle
cases. The installed Codex CLI `0.167.0-alpha.3.2` produced a verified
read-only launch preview against a disposable Core task and managed Git worktree.
See [M6 preview evidence](acceptance/evidence/m6-single-codex-preview.json).
The later real attempt above ended unknown. The second
client's relay remains NOT RUN. The [M5 final checklist](M5-FINAL-ACCEPTANCE.md)
governs the independent review and the M5 exit.

## Continuous local validation for 0.3.0a109

Frozen product and package tests: `de44e7bdbc2b1209fb40045cb2cb576886e696aa`.
The Windows source runner fix at `4f08dc80d245e2ce807b12031434b4dd92b4c63a`
changes release tooling and its regression fixture. Development branch
`feat/implementation-first-20261107`.

- Repaired managed delivery status after reopening the database, Windows Git ref
  locks beyond MAX_PATH, source imports in a clean release environment, and
  historical SQLite migration fixtures. No approval or verification checks were
  removed.
- Windows Ruff check, format check and mypy pass on the frozen source. During
  development, 19 focused path, delivery and migration cases and 151 release
  runner cases passed. Windows Python 3.11 source and Python 3.12 offline
  wheel each passed 154 frozen focused cases. Windows 3.11 and 3.12 then each
  passed all 26 local checks, including full source, wheel and sdist. Every
  suite had 2,044 passes and 41 skips, matching the corrected 3.14 source IDs. See
  [Windows minor-version evidence](acceptance/evidence/a109-windows-minors.json).
- The initial Windows full source run had 46 failures, 1,998 passes and 41
  skips. Its test subprocesses could import the old installed version. With
  the fixed import path all 46 failed cases and all 151 runner tests passed
  separately. The corrected full source run and the frozen offline Windows
  wheel and rebuilt sdist suites each had 2,044 passes and 41 skips.
  See [Windows evidence](acceptance/evidence/a109-windows-local.json).
- The frozen Linux source suite completed with 2,080 passed and 5 platform
  skips. All 84 imported runtime modules matched the frozen bytes before and
  after the suite. The post-check found none of the 32 recorded fixture
  containers. See [Linux source evidence](acceptance/evidence/a109-linux-source.json).
  Fresh Linux wheel and rebuilt sdist each also passed 2,080 with 5 platform
  skips. All three suites had the same ordered test IDs, and the final
  post-check found none of the 96 recorded fixture containers. See
  [Linux package evidence](acceptance/evidence/a109-linux-packages.json).
- Linux 3.11.18 and 3.12.16 were built from checksum-verified CPython sources in
  the D-drive guest. An initial Linux candidate preflight rejected the same
  804 manifest entries because the Windows snapshot used CRLF. Collector fix
  `0be709a` makes new snapshots LF and accepts an exact historical CRLF
  encoding. All 161 targeted release tests and a real Linux staging probe passed.
  Linux 3.11 and 3.12 each passed all 26 local checks, including full source,
  wheel and sdist with the exact Windows 3.12 archive hashes. Each Linux suite
  had 2,080 passes and 5 skips. All 192 recorded fixture containers were
  absent after cleanup. See
  [Linux minor-version evidence](acceptance/evidence/a109-linux-minors.json).
- The local Windows M8 diagnostic passed 256 claim attempts with 256 matching
  audit outcomes and 117.46 ms p95 under its 1,000 ms budget. The host also
  ran other local validation workloads, so this is a diagnostic observation.
  A second local test with four processes split between Core and loopback HTTP
  passed 32 attempts with 32 matching audit outcomes and 110.64 ms p95.
- The previous turn policy allowed a Git checkpoint to end the turn. AGENTS and
  WORKFLOW now require checking and continuing the next authorized task.
  Continuation in this Codex chat is active. A separate Work return callback
  followed by automatic dispatch has no observed execution. The existing Work
  review on PR #33 applies to its historical frozen Linux evidence.

Completed local logs are under `D:/agentsync-debug/continuation-cc30ed21`.
Windows reports are under `windows-py311-full/`, `windows-py312-full/`,
`windows/` and `fixed-windows/`. Linux minor-version evidence is under
`linux-minor-runtime/`. The owned guest stopped normally after verification,
with both disks preserved. Resume from the
[M5–M6 execution adjustment](M5-M6-EXECUTION-ADJUSTMENT.md) and the isolated
`feat/m6-single-codex-pilot` branch. Reuse this baseline and rerun affected
checks only for changes in code or tests.

Current macOS, live client relay, final M5 evidence review and formal Release
remain open. No GitHub Actions test was dispatched.

0.3.0a38 development source adds the Amadeus project name and `amadeus` command.
Validation is NOT RUN for this checkpoint. M5 and Release remain BLOCKED.

## Alpha31 source checkpoint

M6 and M7 add an isolated two-client relay for exact approved
plans, live lease rechecks, durable one-attempt fences, managed worktree conflict
checks, pinned context handoff and an explicit third-identity review. The optional
model library implements text-only GPT, Claude, Gemini, DeepSeek and local Ollama
providers with the same advisory API as Mock. M8 adds local call timing, failure
counts and optional caller-rate estimates. Interrupted relay receipts remain
incomplete, while Core retains its existing expired-lease recovery path.

Validation is NOT RUN for alpha30 and alpha31. The first pending checks remain
the earlier real-client connection and safety gates, followed by new source and
installed-package paths in milestone order. D1 automatic application and D2
automatic verified completion remain deferred under the existing M5 decisions.
The code supports a fixed host-controlled pilot. General unattended real relay,
live provider compatibility, release evidence and formal acceptance remain open.

2026-11-07, alpha30 source checkpoint. The owner requested implementation before
testing or debugging. M6 adds explicit pinned Cursor ask/terminal-JSON preparation
and a contextual process factory. M7 exposes configurable Mock workflows on stdin
with a bounded worker roster and parallel budget. Optional simulated handoff pins
a context revision, transfers ownership through Core, schedules a recipient
attempt under the same budgets and selects a third participant for review.
M8 adds explicit local save and restore for private usage checkpoints. M9 keeps
raw evidence in Git, omits those copies from future source packages and keeps
Ruff focused on maintained files. The acceptance matrix tool summarizes saved
local reports only when their frozen source identities match.

Validation for alpha30 is NOT RUN, including static checks, product execution,
package builds, all real clients and Release Acceptance. Earlier a29 and a28
evidence belongs to its own frozen commits. M5 and Release remain BLOCKED. Continue
with the remaining implementation, including optional provider integration and
the controlled relay path, within existing authorization gates.

2026-11-06 alpha29 frozen `05a811a244d7cbf2c1c36f8f180baa4468dba7e3`:
add only exact desktop declaration0.167.0-alpha.3.2, preserving old declarations,
legacy default, argv/environment guards and unverified markers. Root independently
ran six affected modules on Windows Python3.14/3.11 source and fresh offline
wheel/rebuilt sdist: each184passed,0skip/failure/error;178retained+6new,0removed.
Root checked713Git inputs,542Git-matched sdist files+8generated metadata,
63runtime origins each, package/directURL/log/JUnit hashes and identical case sets.
Ruff/format src/tests/tools and mypy63 pass; broad repository Ruff includes
historical raw evidence-driver failures, preserved and not claimed passed.
Evidence: acceptance/evidence/alpha29-local-summary.json and its49raw readable
members; release packages stored once, no duplicate checkpoint archive.

Fresh user permission allows one subscription-only fixed-text readonly test;
metadata-only login status confirms ChatGPT, with no raw account output retained.
Model attempts0, authorization unconsumed: cost/paid-credit exclusion and actual
tool/isolation gates remain unknown. Astra preflight BLOCKED_BEFORE_MODEL_REQUEST;
no failed/unknown model task retried. Full current suites/real clients/relay/formal42
NOT RUN; Work review pending, M5/Release BLOCKED. No Actions/main/account changes.

Live GitHub feedback now accepts PR33 head8671c2d's Linux supplement in its limited
scope (comment6675346744), including136text members and403source SHA-256 values;
14historical binary archive hashes could not be recomputed by Work. This does not
accept alpha29, real clients, B3, M5 or Release. Issues7/11 remain open.

2026-11-06 full Linux supplement, frozen `50bcbf50095f7df1ca6a420e5d68c3892991f9d1`:
complete source, fresh offline wheel and rebuilt sdist each2039passed/4explained
skips/0failure,error,2043uniqueIDs; all1899prior cases retained+144new. Required
actual Docker enabled. Root and Astra data audits matched417Git inputs,63runtime
modules/origins,357sdist Git members+8generated metadata files, artifact/directURL
hashes and identical case/skip sets.96recorded container IDs independently absent;
owned postcheckVM5552 gracefully stopped. OldVM11692 was absent on resume; shutdown
was not observed and is not claimed graceful. Astra38data checks passed, no findings.
Full evidence138-member archive and directly readable logs/JUnit/origins/records:
acceptance/evidence/full-linux-50bcbf5-summary.json. Limited supplement Work accepted
at8671c2d (403text input hashes independently recomputed;14old archives unavailable);
PR33 prior limited component accepted at08a3e93. Full current Windows/macOS,
real clients/model tasks, relay and formal42 NOT RUN; M5/Release BLOCKED.

Alpha28 M6 exact desktop CLI declaration at `fdb316b736825f0ac7b3e6a79ddee1046ff23668`
admits0.166.0-alpha.6 alongside the unchanged0.164.0-alpha.11.1 default; unlisted
versions including installed npm0.162 remain denied. Existing opt-in factory uses
the same gate, without granting new execution authorization. Root probed actual
CLI version/help/read-only features in disposable homes and prepared a plan against
the real pinned desktop binary; no model task/login/account change. Official basis:
https://learn.chatgpt.com/docs/non-interactive-mode . Actual auth/billing/sandbox,
full flag-combination execution and live client behavior remain unverified.
Root Windows3.14/3.11 source and fresh offline Windows wheel/sdist six affected
modules each151pass/0skip, same143retained+8newIDs. Root matched407Git inputs,
351sdist Git members,63runtime origins each, raw artifacts/logs/JUnit/55archive
members; Ruff/format/mypy63 pass. Astra limited static review no open blockers.
InitialRED1 retained. First collector assumed review findings were objects instead
of strings; corrected to check explicit open_blockers and exact hashes before archive.
No product test rerun or result change. Evidence: acceptance/evidence/alpha28-local-summary.json.
Whole current repository/Linux/macOS/live model tasks/relay/formal42 NOT RUN;
Work pending, M5/Release BLOCKED. No Actions/main merge/paid API/VM startup.

Alpha27 M7 configurable owned Mock workflows at `b9533352abc4c8c94a2676792f00b616b63032ee`
adds typed copied task graphs (1..16), strict pre-I/O validation and deterministic
topological creation. Non-demo chains/fan-in/parallel tasks reuse dependency/capability
dispatch, attempt/time budgets, explicit simulated failure/retry and opposite-worker
reviews. Original four-task demo retained; no caller Core/adapters/credentials or
external execution. Root Windows3.14/3.11 source and fresh offline Windows wheel/sdist
eight affected modules each175pass/0skip, same144retained+31newIDs. Root checked405Git
inputs,350matching sdist members,63runtime origins each and raw artifact/log/JUnit hashes.
Ruff/format/mypy63 pass; Astra limited static review has no open blockers. InitialRED31
and initial mypy annotation error retained. Evidence: acceptance/evidence/alpha27-local-summary.json
(45-member archive). Work pending; whole current repository/Linux/macOS/real clients/relay
and42formal requirements NOT RUN. All results simulation/unverified; M5/Release BLOCKED.

Alpha26 M6 callback error boundary at `5eaaf152c447d6a6cf79fd9fbf1cfc734fda62a9`
fixes reproduced private exception leaks from manager lifecycle callbacks and
malformed receipt/error properties. Fixed public codes/messages/statuses replace
private details without exception chaining; validated routing IDs are captured
once and reused. Cancellation, successful private results and dispatch ownership
remain intact. Root Windows3.14/3.11 source and fresh offline Windows wheel/sdist
seven affected modules each152pass/0skip, same99retained+53newIDs. Root checked
403Git inputs,349sdist matching members,63runtime origins per environment and
all artifact/JUnit/log/archive hashes. Ruff/format/mypy63 pass. Astra static review
found three related issues, all fixed; initialRED26/reviewRED7 retained. Evidence:
acceptance/evidence/alpha26-local-summary.json (58-member archive). Work pending;
full current repository/Linux/macOS/real clients/formal42 NOT RUN. This is not full
B3 lifecycle auditing; M5/Release remain BLOCKED. No Actions/paid calls/main merge.

2026-11-04: owner cancelled the Claude package/handoff and resumed Codex work.
Live PR30 feedback retains productd9b1abc's limited component acceptance but blocks
handoff documents for a missing repo DELIVERY.json and conflicting Work statuses.
Current documentation retires that entry, removes the external-file dependency
and reconciles status; this correction awaits Work review. No runtime/test changes.

Alpha25 M6 nonblocking receipt at `d9b1abc22a6748575bf9935cb9c651172d250ba2`
adds `RunManager.dispatch_task`, sharing unchanged admission with `start_task`.
Callers obtain a handle before adapter startup returns, then use the bounded
observer; mixed calls retain one start/history slot, namespace/capacity checks,
original receipt replay and fixed failure codes. Windows3.14/3.11 source and
fresh offline Windows wheel/sdist seven affected modules each99pass/0skip,
identical74retained+25newIDs. Root verified399Git inputs,347sdist matching
members and63actual module origins per environment; Ruff/format176/mypy63 pass.
Astra independent source/result review found no blocker in this limited scope.
Evidence: acceptance/evidence/alpha25-local-summary.json and43-member archive.
Full alpha25 repository/Linux/macOS, real clients and formal42 NOT RUN;
M5/Release BLOCKED and Work acceptance pending. No Actions/main changes.

Alpha24 bounded M6 dispatch observation at `03185807230beea0c276654c7dbb9a6702c56b64`
adds `RunManager.wait_dispatch` without starting/retrying/cancelling adapter work.
Strict0..300s observation timeout returns the existing sanitized receipt state;
caller cancellation preserves the original dispatch and history slot. Returned is
not run success. Windows3.14/3.11 source and fresh offline Windows wheel/sdist
affected seven-module groups each94pass/0skip, identical74retained+20newIDs.
Root verified397Git files,346sdist matching members and63actual module origins
per environment; Ruff/format176/mypy63 pass. Evidence archive and package hashes:
acceptance/evidence/alpha24-local-summary.json. No Linux/macOS or complete alpha24
suite, real clients or formal42 execution this round; M5/Release stay BLOCKED and
Work acceptance pending. No Actions, VM startup, main or account changes.

Alpha23 internal independent task completion at `e0b1d7c6e0333a3485169253d2d9500d7762c2b7`
adds schema14 and `OwnerVerifiedTaskCompletion.complete_once`. Owner and independent
reviewer auth precede lookup/replay; both task versions, fresh physical candidate,
trusted profile and passed isolated evidence must match. Completion, immutable proof,
review, receipt and audit commit together; ordinary text reviews remain unverified.
Linux full source1895pass/4platformskip,1899IDs; fresh Linux wheel/sdist affected
modules each63pass/1platformskip,64IDs. Windows3.11 selected6pass; frozen Ruff,
format/mypy63 pass.395Gitinputs/180sdistinputs/63actual modules independently matched.
Three actual Docker-to-independent-completion records verified;44fullcontainerIDs
independently absent and ownedVM10636 gracefully off. Astra accepts LIMITED internal
B4 scope only. Formal42statuses remainnot_run; Agent-facing automation, realclients,
apply and overallM5/Release remain BLOCKED. Installed fullsuites and complete new
Windows/macOS matrix NOT RUN. Initial import-origin collection error and read-only
collector ambiguity preserved, corrected without hiding failures. Evidence:
acceptance/evidence/alpha23-local-summary.json. No Actions/main changes.

Alpha22 lifecycle supplement at `bda27722ace70eec4f2ea59696c3301763828fd6` changes
only tests. Source and fresh Linux wheel/sdist each36pass/1platformskip, same37IDs
(33retained+4new),389Gitinputs/178sdistinputs/62actualmodules independently matched.
15final actual observations cover success, mismatch, timeout, Running-before-cancel
and process exit after created commit with Core reopen and exact-ID cleanup.
Lease expiry uses an explicit controlled service clock; cancellation is cooperative.
20IDs including earlierfocus independently absent; ownedVM22544 gracefully off.
Astra accepts B5 LIMITED internalowner single-attempt lifecycle scope only. No
runtime changes from437d306 fullsuite; fullrepository atbda2772 NOT RUN. B4,
realclients and overallM5/Release remain BLOCKED; Agentdispatch/recovery unopened.
See acceptance/evidence/alpha22-lifecycle-summary.json. No Actions/main changes.

B4 design-only Core/Git pilot confirms exact review-version flow and stale paired
binding after one textual completion. Backend MOCK only; no B4 implementation or
acceptance. See acceptance/evidence/b4-flow-feasibility.json; sole M5 checklist
retains the complete implementation boundary. This is not product progress.

Alpha22 owner candidate execution product `437d306643b6529e600aa93c64e9ac0b9cf81d28`
adds schema13, a permanent one-attempt fence and exact-ID cleanup. A reproduced
late-executor/cleanup race is fixed; real post-commit acknowledgement-loss tests
retain the fence. Linux full1864pass/4skip, prior1835cases (3future-schema renames)+33new; Windows3.11 eight
critical passes and fresh Windows wheel/sdist six passes each.62actual modules,
387Git inputs and sdist source/test/tool inputs independently checked. One actual
candidate Docker success;54fullcontainer IDs from both Linux attempts independently
absent. Initial full1856pass/8fail/4skip retained; all eight fixed. Task status
remains unverified. Actual candidate timeout/cancel/crash cleanup not fully run;
component evidence does not resolve B5/B6. Earlier interrupted Windows group and
RED retained. See acceptance/evidence/alpha22-local-summary.json. ReleaseBLOCKED.

Alpha21 Windowsfull source066b8dd completed1800pass/35skips/0fail,error in1082.8s.
377Gitinputs/60actualmodules/1835caseIDs independently matched. Bootstrap main
guard added before spawn, original+intervention preserved; spawn case passed.
One anyio rewrite warning retained. Source/product unchanged, not alpha22 proof.
See acceptance/evidence/alpha21-windows-full-summary.json. M5/ReleaseBLOCKED.

Alpha21 installed supplement: fresh offline localLinux wheel and rebuilt sdist
each1832pass/3Windows-specificskips/0fail,error, same1835IDs as full source.
60actualinstalledmodules,175Git source/test/tool inputs and both artifact hashes
independently matched;52rawDocker records/fullIDs all independently absent.
No new product change; source productcb71f0e. Windowsfull066b8dd stillRUNNING.
See acceptance/evidence/alpha21-installed-full-summary.json. M5/ReleaseBLOCKED.

Alpha21 full-source supplement at `f162ee13e5e70303486a3ab1ca79bec3e18503a3`:
Linux WITH required realDocker1832pass/3Windows-specificskips/0fail,error;
1835uniqueIDs retain1821old+14new.375Gitinputs and60runtimebytes match;26raw
Docker records/26fullIDs independently confirmed absent. Astra saved-evidence
review no blocker; ownedVM26724 gracefully off. WindowsFULL600s TIMEDOUT,
noJUnit/no fullpass;2likelypending cases eachpassed (~7.7/7.9s), cumulative setup
cost inferred, Gitstartup not separately measured. No blindfullrerun. Existing
selectedsource/package50passes stay separate. All42not_run/ReleaseBLOCKED.
See acceptance/evidence/alpha21-full-source-summary.json (164KB raw archive).

Alpha21 (`cb71f0e232253561a6da4ae5f346b312f94ce91b`) fixes a reproduced
Unicode project-ID crash in offline planning with ASCII stdout. JSON escaping
preserves parsed results and unverified markers. Root Windows3.14/3.11 source
and fresh Windows wheel/sdist each50pass0skip, identical IDs (old49+1new),60
modulehashes matched; lint/format/mypy pass. Red/green logs, JUnit and builds in
one archive. That selected checkpoint did not run Linux/macOS/full suites;
subsequent source evidence is above. Actualclients NOT RUN; ReleaseBLOCKED and
all42formalnot_run. See acceptance/evidence/alpha21-local-summary.json.

Alpha20 (`b2e855947a30d4ee57b0d947ec9420816c84eeb0`) adds offline
`agentsync usage --project-id ID`: strict1MiB stdin checkpoint, existing summary,
no Core/files/client calls; unknown costs and caller-reported markers preserved.
Root Windows3.14/3.11 source and fresh Windows wheel/sdist each49pass0skip;
60actualmodulehashes and identical case sets verified; lint/format/mypy pass.
Initial test-assertion failure and missing-httpx collection error retained in one
archive. Linux/macOS/fullsuite/realclients NOT RUN. All42not_run/ReleaseBLOCKED.
See acceptance/evidence/alpha20-local-summary.json. Alpha19 Astra review approved
its limited component/source/evidence scope; it is not Work/M5 acceptance.

Alpha19 (`cd2e8d75555e954b41c421f1dfeb3308032ba440`) exposes Cursor's opt-in
contextual factory through the unchanged shared launch guard. No built-in Cursor
plan or default startup. Root Windows3.14/3.11 each455pass0skip (451old IDs+4new);
fresh Windows/Linux wheel/sdist each122pass0skip,59actualmodulehashes matched;
all4installed case sets identical, lint/format/mypy pass. One1MB main archive plus
29KB Linux supplement retain logs/JUnit/builds/drivers/manifests. Initial SSH upload
failed before tests and is preserved; fresh guest run passed. OwnedVM safely off.
macOS/full suite/actualclients NOT RUN; all42formalnot_run/ReleaseBLOCKED.
See acceptance/evidence/alpha19-local-summary.json. No real-client retry or Actions.

One newly authorized Codex factory subscription test stopped at preflight:
PATH/npm native CLI reports0.162.0; the pinned profile requires0.164.0-alpha.11.1.
BLOCKED;0model attempts/0factory calls. Login/actual response NOT RUN. No retry,
upgrade or loosened gate. See acceptance/evidence/codex-factory-preflight-20261028.json.

Alpha18 adds opt-in pinned ClaudeProcessFactory on the existing launch context.
Flags/shared engine/context/Codex/parsers/Core unchanged; defaultsunsupported.
Root Windows3.14/3.11 each451pass0skip (prior446retained+5new). Fresh Windows/
Linuxwheel+sdist each118pass0skip,59actualmodulehashes/caseIDs matched. This is
selected validation; fullAlpha17Linux evidence is not promoted toAlpha18.
Managedhooks/configcredentials/billing/isolation/actualClaude remain unverified.
Astra source/results review no blocker. All42formalnot_run/ReleaseBLOCKED.
See acceptance/evidence/alpha18-local-summary.json.

Alpha17 adds opt-in pinned CodexProcessFactory + task/run/loop-bound launch
observation: stop/original-deadline check and one consumed local attempt before
capture. Defaultsunsupported; legacy behavior preserved; no liveclientcall.
Root Windows3.14/3.11 each446pass0skip; fullLinux WITHrequiredDocker1818pass3
Windows-skips/0fail/error,1821IDs (prior1811retained+10new). Fresh Windows/Linux
wheel/sdist each113pass0skip,58actualmodulehashes matched; two original fixture/
portability failures preserved. Astra source/results review no blocker. All42not_run,
ReleaseBLOCKED. See acceptance/evidence/alpha17-local-summary.json.

Alpha16 actual localLinux Docker supplement at7f658b1:26passed0skip/fail/error,
fixed preloaded image/no pull;56 actual source module bytes verified before/after.
All26 match Docker case IDs skipped in the prior ordinary full run;3platformskips
remain. Separate observations, no combined single-suite claim. All42formalnot_run,
ReleaseBLOCKED. See acceptance/evidence/alpha16-docker-local-summary.json.

Development0.3.0a16 adds offline stdin-only `agentsync plan` dispatch advice.
Root Windows3.14/3.11 each44pass; lint/format/mypy56 pass. Fresh Windows3.14
wheel installed offline: CLI module/entrypoint smoke, dependencycheck and56
actual module hashes pass; no Core state opened. Linux startup10pass plus
8-process diagnostic pass; original cause unknown. Corrected fullLinux at2da1a89:
1782pass/29skip/0fail,error; all1807oldIDs retained+4newCLIcases;6oldfailures pass.
See acceptance/evidence/alpha16-local-summary.json.
Original failed attempt preserved. All42formalnot_run; ReleaseBLOCKED.

Local developer startup diagnostic at1eb17be: fixed owned interpreter children,
service-module hash pin, import/connect/WAL/init phases, private new shared DB,
integrity/FK/schema checks and bounded parent observation with kill/reap cleanup.
Root Windows Python3.14/3.11 each4pass0skip; Ruff/format/focused mypy pass.
Actual8processes completed in~0.356s; parent file preserved. No production edits.
Linux diagnostic NOT RUN, historical8process timeout stillOPEN; BEGIN not split.
See acceptance/evidence/core-startup-local-summary.json. No gate promotion.

Development0.3.0a15 product1d6b526 frozen.4freshWindows(Python3.14/3.11 ×wheel/sdist)
environments each782pass3platformskips;2freshLinux wheel/sdist each122pass2Windows-
junctionskips withreal fork/MCPprocessclaim pass. Root verified55modulebytes each,
785matchingWindows/124Linux IDs,313Gitinputs andartifact/directarchivehashes.
IndependentAstra source+result review approves scopeddevelopment only. Same32×8
budget nowpassed:sourcep95~107.837ms/installed3.11~110.680ms vs2303.126baselineFAIL;
256audits complete. All42formalnot_run/ReleaseBLOCKED; oldLinux8process issueopen.
OwnedVM gracefully stopped aftersync; disk/logs/evidence preserved,3GiB RAM released.
See acceptance/evidence/alpha15-local-summary.json.

M8 bounded process-local Core admission implemented; existing SQL/auth/replay/lease/
audit/close body byte-identical, owner/migration paths unchanged. Astra source
review no blocker. Independent Windows3.14 broad432pass3skip; Python3.11 scoped
37pass1forkskip; Linux122pass2Windows-junctionskips withreal inherited-Corefork
andtwo-MCPprocessclaim passed. Same32×8/1000ms workload p95 observed107.837ms
versus2303.126ms baseline, exact256audits; queue wait remains inside timing.
Evidence D:core-admission-root-e9ou5xav, core-admission-perf-qqof4ky8,
core-admission-linux-isvv1r9f. No generalSLO/fullmatrix/Release claim.

Actual local Linux source supplement at7c641e9:49pass/0skip/fail/error,54 actual
source imports and163 Git inputs independently matched; sources unchanged. Guest
Python3.14.7/SQLite3.53.4. D:alpha14-linux-components-gktwi5mr. Existing dependency
venv only, not fresh Linux packages/fullmatrix; old startup failures NOT CLEARED.
Formal42not_run/releaseBLOCKED.

M8 benchmark now validates exact audit actor/request/outcome coverage after timing.
Missing/duplicate/unexpected/mismatched receipts fail; only aggregatecounts exported.
Root Windows3.14 scoped11pass, Python3.11 tool7pass, static54module checks pass.
Actual32×8 strict run matched256events(8success/248denied), audit errors0; p95
2303.126ms still FAILED1000ms. Core/M5 semantics unchanged; current source
diagnostic extends the earlier2982539 packaged checkpoint.
D:m8-audit-strict-root-cfi2btv7. All42formalnot_run/releaseBLOCKED.

Astra final scoped evidence review found no blocking measurement issue. Separate
32worker audit-count probe matched8success/248denied events; p95~2285.607ms still
FAILED1000ms. This does not prove generalized audit durability. No product/audit
code change. D:alpha14-audit-count-bg164krq. Linux QEMU currently not running;
no new Linux job started, old failures remain open. Release stays BLOCKED.

Development0.3.0a14 product2982539 frozen. Fresh offline Windows Python3.14 and
Python3.11 wheel/sdist each370pass/0skip/fail/error; root matched all370-case sets,
54 actual imported modules per environment and309 Git package inputs. Dependency
checks and installed CLI demo all4 passed; Python3.11 sdist standalone diagnostic
passed. Ruff/format/mypy54 pass. No current Linux/macOS/fullsuite/real relay claim.
32worker p95>1000ms diagnostic failure remains open; all42formalnot_run/releaseBLOCKED.
See acceptance/evidence/alpha14-local-summary.json and Release Acceptance Report.

M6 Claude pinned restricted CLI preparation implemented without launching. Explicit
model/version/binary hash, fixedargv/stdin, filteredenv and bounded file checks;
all auth/billing/tool/sandbox/actualclient markers false. Root scoped Windows3.14
190pass, Python3.11 plan6pass; Ruff/format/mypy54 pass. Astra final source review
no blocker. Separate nativeCLI help/version-only2.1.295 and installed hash-only
preparation observed; completeflags/auth/realturn NOT RUN.
Evidence D:m6-claude-plan-root-zwkx1ith; formal42not_run/release BLOCKED.

M8 isolated local contention diagnostic implemented. Root Windows3.14 focused
11pass; Python3.11 tool4pass; Ruff/format/mypy53 pass. Actual1/8/16/32worker ×8round
workloads measured456 claim attempts: all functional checks passed, no unexpected
errors. p95ms3.400/133.483/660.562/2395.555 under declared1000ms threshold:32worker
budget FAILED(exit1), retained without weakening. Source startup/barrier/cleanup
excluded; no Release SLO/platform claim. D:m8-contention-root-mqb8e39b.
M8-02 partial; old Linux failures open; all42formalnot_run; release BLOCKED.

M7 pure retry advice implemented: deterministic capped exponential backoff, numeric
Retry-After minimum, explicit confirmed-outcome requirement, attempt/global/time
budgets and precision-safe stops. Root Windows3.14 retry/Mock/collector54pass;
Python3.11 retry18pass; Ruff/format/mypy53 pass. Only the caller-controlled Mock
composition waits/starts; planner performs no execution. Evidence D:m7-retry-root-09rucwxf.
All42 formal not_run; real retry and release remain BLOCKED.

M8 normalized usage checkpoint export/restore implemented without I/O. Strict
namespace/format/bounds/duplicate checks rebuild a new ledger and recompute totals;
unknown costs, replay identity, capacity and Mock separation survive restoration.
Sol implemented; Astra High reviewed final usage.py SHA f3318ead... with no blocker
(source review only). Root independent Windows3.14 scoped19pass, Python3.11 usage
15pass; two fresh-interpreter restores passed. Ruff/format/mypy52 pass.
D:m8-usage-recovery-root-nas39osp. Explicit caller storage, no automatic durable
files/Agent recovery. Unreleased source; all42 formal not_run; release BLOCKED.

M7 Mock workflow now accepts optional finite elapsed admission budget (0,60]s,
including owned setup. Expiry stops claims/starts, cancels active simulations,
fails owned Core tasks and leaves descendants pending. Default output preserved.
Root Windows3.14 affected52pass; Windows3.11 workflow14pass; updated collector
policy1pass; real monotonic setup-expiry smoke passed. Ruff/format/mypy52 pass.
This is no hard watchdog; source component only, new packages NOT RUN. Evidence:
D:m7-time-budget-root-ewvjv1i0. All42 formal not_run; release BLOCKED.

M8 actual crash/lease recovery component added: abrupt process exit73, real lease
expiry, one-time reclamation, stale owner/replay rejection, successor review and
dependency continuation survive another fresh process. Root independent Windows
Python3.14 recovery/concurrency/collector group157pass; Python3.11 recovery2pass.
No runtime changes; old Linux contention failures remain unresolved. M8-02 partial,
all42 formal not_run and release BLOCKED. Raw D:m8-recovery-root-nd076l_6.

Final developmenta13 package source77426fa: fresh offline Windows Python3.14
wheel/sdist and Python3.11.15 wheel each318pass/0skip. Root verified matching318-case
sets,52 actual imported module hashes and no prior unraisable/closed-pipe warnings.
Dependency checks and installed CLI Mock workflow passed in all3 environments.
Ruff/format/mypy52modules passed. Rawalpha12 301pass/10fail and interrupted fullsuite
remain preserved; current full OS/Python matrix/real relay/release remain BLOCKED.

Actual Python3.11 alpha12 package run exposed301pass/10fail from equal-clock fresh
captures falsely rejected as stale; warnings preserved. Developmenta13 uses private
creation order plus loop identity, without weakening stale/reuse checks. Root3.11
source111pass; Sol3.14affected108pass; synthetic RED3freshfail/GREEN7pass. Astra
source review found no blocker; subsequent installed-package checks are recorded above.

Development alpha0.3.0a12 frozen at9ebb13e: fresh offline Windows Python3.14
wheel/sdist each311pass/0skip, pipcheck and actual installed CLI Mock demo pass.
Root matched52 imported module hashes,54 distributions per environment,302 Git
package inputs and both311-case ID sets. Source package now includes missing tools.
This is component package validation; current Linux/full matrix/real relay blocked.

M8 caller-reported usage ledger implemented: typed normalized records, replay
deduplication, strict bounds/overflow, Mock separation and unknown-aware totals.
Root scoped suite163pass/0skip; Ruff/format/mypy52modules pass. Actual Cursor helper
results compose with the ledger without Core mutation or invented token/billing data.
No provider billing, subscription estimate, transport accounting or recovery claim.

Isolated Mock workflow demo implemented: fresh disposable child Core, four-task
diamond, overlapping Mock starts, bounded retry/attempt budget and distinct peer
simulated reviews. Independent targeted suite164pass/0skip; lint/format/types pass.
Astra's source-only component review found no blocker; real release stays BLOCKED.
Broader Windows attempt was supervisor-interrupted to avoid unrelated repeated
database checks; NOT COMPLETED, no full-suite pass count. Raw evidence retained.

M7 optional capability-aware task/dispatch advice implemented: explicit complete
task requirements match self-reported worker declarations before truncation;
dependency validation, priorities and load limits preserved. Independent affected
Windows suite267pass/0skip, Ruff/format/mypy pass. Actual Core viewer claim still
denied despite matching capability. No auto-claim/execute or verified capability.

Cursor standalone terminal-JSON parser and host-factory adapter implemented;
independent affected Windows suite280pass/0skip, Ruff/format/mypy50modules pass.
M6-05 has eight component selectors; formal requirements remain not_run. Known
local Python fixtures preserve Core state; actual Cursor launch/permissions/relay
remain NOT RUN. Shared lifecycle code was unchanged. Existing Linux blockers persist.

M6 heterogeneous RunManager implemented: scoped routing for trusted registered
adapters, cancellation-safe request deduplication, bounded history and nonblocking
dispatch inspection. Independent Windows affected regression: 137pass/0skip;
Ruff/format/mypy pass. Core remains unchanged by protocol fixture success.
See M6-ADAPTERS.md and acceptance/RELEASE-ACCEPTANCE-REPORT.md. Cursor and actual
clients/relay remain NOT RUN; M5 blockers and earlier Linux failures remain open.

Final local source test-infrastructure: 1041pass/5skip, Ruff/format/mypy/diff pass.
Owned child cleanup and opt-in bounded private per-phase journal verified.
Linux concurrency failures/package timeout remain unresolved; release BLOCKED.

Never-started capture cancellation repaired in product7d01aed: actual supervised
Codex/Claude reproduction now terminates unknown and keeps its slot. Windows source
1019pass/2skip; fresh offline wheel/sdist98pass each; Linux focused source98pass.
Linux package attempt failed at600s install/1200s transport bounds; wheel postinstall
and sdist checks NOT RUN, same-guest evidence recovered without retry. Current Windows actual fullsuite1587pass/31skip,
322 originalfiles unchanged, driverFAIL from21 generatedbytecodecache additions.
Linux full INTERRUPTED:1completedpass/4fail plus1anonymousunfinishedrecord;
concurrentCore30s deadlines failed, remaining/DockerNOTRUN. Python3.11 actual NOT RUN;
formal release/real clients/relay remain BLOCKED. See acceptance/RELEASE-ACCEPTANCE-REPORT.md.

Fresh Linux wheel/sdist each641pass/0skip/fail/error, normal offline installs; root verified47 imported/post-test module hashes and52 distributions within each isolated venv,10 stage exits, actual XML and source317 unchanged. This completes the component installation supplement only; formal release/real-client/full matrix gates remain blocked.

Linux follow-up:641 components passed/0skip/fail/error,317 frozen files unchanged; root tied code/tests/tools/requirement Git blobs to da61adf. Fresh package installs remain the separate Windows640pass/1skip each; no full current platform matrix or real-client acceptance.

Latest shared lifecycle / ClaudeAdapter prototype:47 modules/317 frozen files; source1014pass/2skip; installed wheel/sdist640pass/1skip each. Root independently checked actual XML/artifact/module bytes and Codex public-record compatibility. Default startup unsupported; zero actual clients/credentials/Core wiring. M6-04 eight component selectors, all42/16 formal not_run, release BLOCKED; current Linux component evidence pending separately.

Latest Claude OFFLINE projection:45 modules/310 frozen files; source977pass/2skip; fresh wheel/sdist603pass/1skip each; Ruff/format/mypy pass. Root verified actual XML/package bytes. M6-04 partial component mapping only; all42/16 formal not_run; zero real Claude calls, release BLOCKED. See acceptance/RELEASE-ACCEPTANCE-REPORT.md.

Complete frozen Windows product248d0be:1441pass/30skip/0fail/error;1471 actual cases,305 files/44 modules unchanged. Root independently checked XML/hashes. See acceptance/evidence/full-windows-248d0be-20261025.json. Claude draft not included; Linux complete suite still running.

2026-10-25 latest: pure fixed readonly invocation plan and optional explicit child
environment implemented. Root verified302 files/44 runtime modules: source873pass/
1skip; fresh wheel/sdist499pass each; local Linux421pass; Ruff/format/mypy pass.
One NEW separately authorized actual installed-wheel CodexAdapter+plan+environment
run completed once with exit0 and exact reply. All19 fixture hashes and pending
Core task before/after/reopen stayed unchanged. Warning/model-list refresh timeout
preserved; no retry, API key, Actions or remote mutation. This is a limited response
smoke; permissions/cancel/timeout/relay/M9 remain unverified and release BLOCKED.
See acceptance/RELEASE-ACCEPTANCE-REPORT.md and latest evidence summaries.

2026-10-25 continuation: host-factory CodexAdapter now implements the six-method
generic lifecycle with default unsupported startup, bounded instance history,
request/task deduplication and fail-closed unknown slots. Shared/preexisting
capture misrouting was reproduced (2 real failed regressions) and repaired
without cancelling another run's handle. Protocol completion does not mutate
authoritative Core state (3 actual temporary Core/SQLite tests).
Root independently verified296-file/43-module snapshot: source851pass/1skip;
fresh wheel/sdist477pass each; local Linux399pass. Ruff/format/mypy pass.
Controlled public-factory-delay start cancellation is now tested; strict OS
startup bound, live launcher, server cancellation and real adapter acceptance
remain unverified. No additional real model call, Actions or remote change.
See M6-ADAPTERS.md and D:/agentsync-debug/CODEX-ADAPTER-LOCAL-CHECKPOINT-20261025.json.
Earlier checkpoints below retain their original results and limitations.

2026-10-25 America/Tijuana: read original specification, current code, all stored
M5 archive evidence, live open PRs and Issues7/11. Single exit checklist and exact
BLOCKER/DEFERRED/limited VERIFIED scope: [M5-FINAL-ACCEPTANCE.md](M5-FINAL-ACCEPTANCE.md).
Current frozen local snapshot Windows:1303pass/30skip/0fail/error; root independently
verified source/package/log hashes and Ruff/format/mypy/diff. This is not a clean
Git commit or formal M5/Release acceptance. No GitHub Actions or remote writes.
M6 offline protocol parser and repository inspection CLI now implemented: source
components787pass/1skip; fresh wheel/sdist components413pass each; local Linux263pass.
Root verified286-file snapshot/41 modules and installed/archive bytes. See
D:/agentsync-debug/CODEX-PROTOCOL-CHECKPOINT-20261025.json. No complete new OS matrix.
One separately authorized actual Codex CLI no-tools inline-fixture smoke exited0,
four events/reply hash and19 unchanged files independently checked; see acceptance/
evidence/codex-readonly-cli-smoke-20261025.json. This is not adapter/cancel/timeout/
filesystem/relay acceptance; the single model-task authorization is consumed.
The material below records historical stages rather than a new M5 task queue.

Additional local-only parent-process capture completed:24 known Python-helper
tests, no real client. Latest290-file/42-module snapshot: source811pass/1skip;
fresh wheel/sdist components437pass each; local Linux process/protocol/trace287pass.
Root independently recomputed XML/log/archive/install hashes. See
D:/agentsync-debug/M6-LOCAL-PROTOTYPE-CHECKPOINT-20261025.json and the current
acceptance/RELEASE-ACCEPTANCE-REPORT.md. Mechanical capture is parent-only, inherits
host environment and is not a sandbox. Pre-transport startup deadline and start
cancellation remain unverified; no actual client is wired to this layer.

# Historical M5B3B2B candidate execution intent guard in development

Implement owner-only prepare/get/abandon and transactionally fence reservation
recovery while a prepared intent exists. See M5B3B2B-CONTRACT.md. Version0.3.0a11 /
schema12 additive tables; old job/claim states/proofs/history unchanged. This is
non-executing admission only, no Docker/credential/worker/renew/taskgate/apply.
Prior B2A accepted PR24. Full frozen validation and Work review pending; Release
BLOCKED. D:debug/F:source; no Actions/paid/main changes.

---

# Cloud-only continuation configuration saved, trigger unverified

See CLOUD-CONTINUATION.md. Single plan6adb59ed26cc8191a935d85e639458bf
for2026-10-23 10:50 America/Tijuana is enabled, but next_run_time=null
and no explicit environment field was exposed. Do not claim verified automatic
cloud execution after shutdown. Latest GitHub state must guide any actual run.

---

# M5B3B2A independent Work acceptance recorded

PR24 comment6365449101 accepts the bounded owner reservation/ledger interruption,
reviewing product0fd2041 and evidencehead74abf24. Issues11/7 comments6365454598 /
6365456556 remain open. Work read actual repository/archive bytes and independently
verified154 manifest files,18checks/26artifacts,4JUnit,33module package identity,
253-file source snapshots and6new claim/proof/recovery observations plus old
regression evidence. Work did not rerun tests or access the original daemon.
Receipt: acceptance/evidence/m5b3b2a-work-receipt.md. Documentation descendants
are not re-executed product commits. Formal Release BLOCKED. Before candidate
execution: separate execution-aware authority/recovery guard and cleanup contract.

---

# Verified M5B3B2A local checkpoint

Product 0fd2041c8efd1c4fa348117e013c0c5b1f30e470, tree 9a76e8c5280c34d38087f42fc35b702808d15c59;0.3.0a10/schema11.
18checks pass; Linux three suites each 1058pass/3skip;
Windows 1031pass/30skip. 38 new cases;
six actual reservation/recovery observations.33modules and253-file
source/package identity verified;78 old Docker regression IDs independently absent.
Owner reservation only; no execution/task gate/apply. Independent Work review
pending, formal Release BLOCKED. See M5B3B2A-REPORT.md and evidence index.
D:debug/F:source; no Actions, paid calls or main changes.

---

# M5B3B2A candidate owner reservation in development

Implement the bounded owner-only one-shot reservation and explicit ledger
interruption from M5B3B2A-CONTRACT.md. Version0.3.0a10/schema11; no worker
credential, callback, renewal, execution or task gate. Prior B1 independently
accepted in PR23. Migration/old ledger focused group:125 passed; full frozen
source/package/Windows validation and independent Work review remain pending.
Formal Release BLOCKED. D:debug/F:source; GitHub storage only, no Actions.

---

# M5B3B1 independent Work acceptance recorded

PR23 comment6356443059 accepts the bounded candidate queue, reviewing product
f65e134 and evidenceheada2f7efa. Issues11/7 records6360133299 /6360134616 stay open.
Work independently inspected actual code/repository bytes,143-file archive,
4JUnit,32module package identity and6queue/6metadata/6input/78Docker saved records;
it did not rerun tests or access the original daemon. Receipt:
acceptance/evidence/m5b3b1-work-receipt.md. Docs descendants are not re-executed
product commits. Full Release BLOCKED. Next: bounded candidate claim prerequisite.

---

# Verified M5B3B1 local checkpoint

Product f65e134d672d4c4333701b982759cc86567a97a6, tree 64c402b142ab10246e2dfa76e31cf0167c71acba; 0.3.0a9/schema10.
18 checks pass; Linux three suites each 1020 pass / 3 skip; Windows 993 pass / 30 skip.
50 new cases; six actual queue records with raw metadata/request rows; 32 modules
and 244-file source identity verified. Old 6 metadata + 6 input +
78 Docker regression observations are separate. Profile-binding and timeout audit
findings repaired. See M5B3B1-REPORT.md and acceptance evidence index.
Queue only; no worker/lease/execution/task gate/apply. Work review separate;
formal Release BLOCKED. D:debug/F:source; no Actions, paid calls or main changes.

---

# M5B3B1 candidate queue in development

Implement the independent owner candidate queue from M5B3B1-CONTRACT.md:
enqueue/get/list/cancel, schema10 additive tables, immutable checked content
metadata, historical request receipts and transactional owner/version binding.
No candidate worker/claim/lease, execution, task gate or apply. Version0.3.0a9.
B0 private same-connection capture is independently accepted in PR22. Existing
snapshot jobs/executor remain distinct. Final frozen tests and Work acceptance
are still required; formal Release BLOCKED. D:debug/F:source; no Actions.

---

# M5B3B0 independent Work acceptance recorded

PR22 comment6329149589 now accepts the bounded private transaction-capture stage,
reviewing product37b17a3 and evidencehead37720ee. Issues11/7 records6356135968 /
6356136874 remain open. Work independently inspected code/archive/JUnit/package
and supplemental real SQL-error evidence; it did not rerun tests or inspect the
original daemon. See acceptance/evidence/m5b3b0-work-receipt.md.
Receipt-only documentation descendants are not re-executed product commits.
Formal Release remains BLOCKED. Next: separately implement M5B3B1 candidate queue.

---

# Verified M5B3B0 local checkpoint

Product 37b17a3d0c27b0a34ca93e03c4944f02a7a63071, tree 4036fc4a1b19abb57fd6559f34e14e731412c170; 0.3.0a8/schema9.
18 checks pass; Linux source/wheel/sdist each 970 pass / 3 skip;
Windows 943 pass / 30 skip. Seven new real transaction cases pass in all suites.
Root verified 31 Python modules, 233-file source identity, all logs/artifacts/JUnit,
6 metadata + 6 input + 78 old container regression observations and exact ID absence.
Private helper prerequisite only; no queue or task acceptance. See M5B3B0-REPORT.md.
Work acceptance separate; formal Release BLOCKED. D:debug/F:source; no Actions.

---

# M5B3B0 transaction prerequisite in development

Implement the private owner-authenticated metadata capture seam on an existing
caller-owned transaction before any candidate queue. Original public capture and
existing object export retain their semantics. Version0.3.0a8/schema9; no queue,
execution/lease, task gate or apply. See M5B3B0-CONTRACT.md. Final frozen-source
local checks and independent Work review remain pending. Formal Release BLOCKED.

---

# Next queue design checkpoint

M5B3B1-DESIGN.md records an independently peer-reviewed proposal for a separate
candidate queue with enqueue/get/list/cancel only. No implementation/schema10,
claim/lease, execution or task gate was added; product remains0.3.0a7/schema9.
The final authenticated binding comparison must use the insertion connection;
Git stays outside write transactions. History replay/current state and denial
versus mutation audit distinctions are explicit. Finalize strict serialized
field/response bounds in the implementation contract before coding.
Do not claim this design checkpoint as a new product or formal Release pass.

---

# M5B3A2 independent Work acceptance recorded

Work accepted the bounded candidate-object export stage on PR21 comment6320283524,
reviewing product2ed3607 and evidenceheadcb176f0. Issues11/7 comments6320512727 /
6320513992 retain open status. See acceptance/evidence/m5b3a2-work-receipt.md.
The reviewer independently read repository bytes and recomputed saved evidence;
it did not rerun tests or access the local Docker daemon. Later receipt changes
are docs only. Formal Release remains BLOCKED. Next: separately design the
candidate-aware durable job/executor binding before any verified task gate.

---

# Verified M5B3A2 local checkpoint

Product2ed3607de761f731ce8f80385af86260e126a4f4, tree59af2cb1af025394c722d46fd3e25f3cdc503f98;0.3.0a7/schema9.
18checks pass; source/wheel/sdist each963pass3skip; Windows936pass30skip.
41newchecks and6actual candidate input records; no new execution/task acceptance.
Root verified31Python modules against Git/wheel/sdist, all logs/artifacts/JUnit,
225-file source identity, metadata/input fingerprints and78old container absences.
Bare.git redirect finding repaired and independently regressed. See
M5B3A2-REPORT.md and acceptance/evidence/m5b3a2-local-inspection.json.
Work review separate; full Release BLOCKED. D:debug/F:source, GitHub storage only.

---

# M5B3A2 development checkpoint

Version0.3.0a7/schema9, owner-only checked existing candidate content export.
No reconstruction, jobs, execution, task gate or apply. Root independently tested
actual candidate bytes and four adversarial cases using disposable Git projects.
An independent audit reproduced a bare-repository .git redirect before the first
Git command; the new guard and two independently run regressions close that issue.
These are development observations; frozen source/package/Windows validation and
Work review follow. Full M5 and formal Release remain BLOCKED; GitHub storage only.

---

# Work-accepted M5B3A1 checkpoint

Actual independent review accepted evidence head0dd96e9942e96ee12cd86ead26350413bee65868;
see acceptance/evidence/m5b3a1-work-receipt.md. Next bounded task is M5B3A2:
validate existing disk/Git identities and export actual managed candidate content,
with final owner/DB recapture. No task gate, execution or apply is implied.
Full Release remains BLOCKED.

---

# Verified M5B3A1 local checkpoint

Product65e97a3185a68b350aead0d364e69ced73df98f4, treee008b5cfec9a9066f14f7a44c5530a08730eb66a,0.3.0a6/schema9.
DB-only candidate metadata capture: no Git/filesystem/execution/task acceptance.
18checks pass; Linux three suites each922pass3skip; Windows896pass29skip.
6metadata observations and78existing container regressions, all78IDs independently
absent. Root verified hashes/JUnit/origins/7package modules and source identity.
See M5B3A1-REPORT.md and acceptance/evidence/m5b3a1-local-inspection.json.
Work review separate; no new scope starts. Full Release BLOCKED. D:debug/F:source,
GitHub storage only; no Actions/paid calls/main changes.

---

# M5B3A1 bounded development

Version0.3.0a6/schema9: DB-only owner candidate metadata binding. M5B3A full input
bridge remains incomplete: no disk/Git/object validation or task gate. Root's
two actual Git-generated-record integration cases passed during development;
they show metadata capture and explicitly do not attest a dirty checkout. These
are not frozen-SHA acceptance results. Final local source/package checks and
independent Work review follow code freeze. GitHub storage only, D:debug/F:source.
Formal Release remains BLOCKED.

---

# Work-accepted M5B2C checkpoint

Work accepted the limited stage at evidence head53797c5c. Actual review and
tested identities: acceptance/evidence/m5b2c-work-receipt.md. No further
implementation starts at this quota boundary. Next bounded task is the managed
merge-candidate input bridge in M5B3A-DESIGN.md: design only, not a completed
product feature or task gate. Full Release remains BLOCKED.

---

# Verified M5B2C local checkpoint

Code c1f2e83a61af5c267e3374dd46398b2a57b6abf1, treede68cde10628e48122fad14409983ccbab570802; version0.3.0a5/schema9.
18/18localchecks; source/wheel/sdist each895pass3skip; Windows869pass29skip.
78real container observations and independent exact-ID absence checks. Each
new five-case environment yields2removed receipts,2unresolved,1ineligible; all
original executions remain unverified. Root checked saved hashes, all JUnit,
origins, module/package bindings and the complete file manifest. See M5B2C-REPORT.md
and acceptance/evidence/m5b2c-local-inspection.json. Work review remains separate.
Explicit one-shot cleanup only; no retry/resume, task gate, apply or real relay.
Full M5/release BLOCKED. D:debug, F:source, GitHub storage only; main unchanged.

---

# Current M5B2C development checkpoint

Version0.3.0a5/schema9 adds an owner-only exact full-ID cleanup receipt. The job
remains cleanup_pending/unverified and cannot be reused. Root incrementally ran
5actual local Linux cases: created process hard exit, running process SIGKILL,
initial absence, renamed protected object and lost create ACK. All5expectations
passed on development overlays. They are not final-SHA acceptance evidence.
Frozen source/wheel/sdist and Windows regression, independent file/hash review
and Work acceptance follow code freeze. GitHub storage only; debug on D:.
Full M5, real adapters/relay, safe apply/task gate and formal release stay BLOCKED.

---

# Work-accepted M5B2B checkpoint

Independent Work review accepted the limited scope at evidence head
74fda3dc92018fc46664dc3fe3a09a97360d59ed. See
acceptance/evidence/m5b2b-work-receipt.md for the actual review link and tested
identities. Formal Release remains BLOCKED; Issues 11/7 remain open. This receipt
checkpoint changes documentation only and does not claim another test run.

---

# Verified M5B2B local checkpoint

Code b5504e09bf1cb1c390d56cac11e68a8176d2091d,
tree4b0fdcba6ed826870ec19c8382ccbf7064108550, version0.3.0a4/schema8.
D-localcollector18/18pass; source/wheel/sdist each847pass3Windows-onlyskip;
Windows source826pass24explicit skip. 63real Docker/owner observations, all63exact
container IDs independently absent. Owner cases preserve cancellation and expired
authority even after passing candidate output. Root checked saved hashes, JUnit,
origins, module/package bindings and per-file manifest. See M5B2B-REPORT.md and
acceptance/evidence/m5b2b-local-inspection.json. Work review remains separate.
No automatic reconciliation/retry, task acceptance, approval consumption, safe
apply or real model relay. Full M5/release BLOCKED; GitHub storage only; main unchanged.

---

# Current M5B2B owner executor checkpoint

Version0.3.0a4/schema8, owner single snapshot execution; no scheduler/retry/apply
or task acceptance. Prior M5B1/PR16 and M5B2A/PR17 received independent Work review.
Root independently inspected source and incrementally executed7actual local Linux
owner cases: fixed snapshot despite dirty checkout,3false candidate reports,
timeout, cancel-after-create/no-start and real backend pass followed by lease
expiry→pending/unverified. These development runs used unfrozen overlays, not a
final-SHA certification. Final source/wheel/sdist collection follows code freeze.
Strategy/ledger/migration developer subset259pass, Docker policy139pass.
GitHub storage only; debugging on D:. Full M5 and formal release remain BLOCKED.

---

# Verified M5B2A local checkpoint

Version0.3.0a3/schema7, tested613c95dab054f013c6a6029949e2678ad2056e37,
tree0eb394df1d83c13888bf1068b2625f60adc6a250. Complete D-localcollector18/18pass;
three independent environment suites each780pass3Windows-onlyskip. Checkout suite
used fresh noneditable install, with all27Python modules compared to the checkout.
42existing-backend observations and42independent exact-container absence checks.
New ledger remains non-executing/unverified. Lead checked files, installed origins,
all saved hashes/JUnit and new module hashes across Git/wheel/sdist.
See M5B2A-REPORT.md and acceptance/evidence/m5b2a-local-inspection.json.
M5B1 Work acceptance passed (PR16 comment6292907383); Issue15 closed.
M5B2A Work acceptance pending; fullM5/Issue11, Release/Issue7 remain BLOCKED.
GitHub only stores files; no Actions. Main unchanged.

---

# Current M5B2A development checkpoint

Version0.3.0a3/schema7: internal owner-authorized durable verification job/attempt
ledger, no executable worker or successful verification outcome. Contract and
guide: M5B2A-CONTRACT.md / M5B2A-GUIDE.md. Separate branch from M5B1.
Developer preflight on the working tree:26new policy cases,28focused cases pass;
Windows full source766pass17explicit skips. Lead independently inspects code and
will run final frozen-source/wheel/sdist validation locally on D:. These preliminary
counts do not certify a later commit. No GitHub Actions is used; main is unchanged.
Full M5, real client relay and formal release remain BLOCKED.

---

# Verified local M5B1 checkpoint

Code cfb5304c3979fc1677c73618120c0d33f928018a, tree5e8580769ead8be5a6b4a21ee269aa0a0da01be6.
D:/agentsync-debug Linux collector18/18pass; source/wheel/sdist each754pass3Windows-onlyskip.
All14 real Docker tests executed in each interpreter;42 safe result records and42
independent exact-container absence checks. Windows same-product source740pass17skip.
Lead verified saved hashes, JUnit, installed origins and Git/wheel/sdist/verifier
module consistency. Evidence: acceptance/evidence/m5b1-local-inspection.json and
acceptance/RELEASE-ACCEPTANCE-REPORT.md. Work acceptance remains separate.
GitHub storage only; no new Actions execution. Private debug runtime stays D:.
Full M5, actual adapters/relay and formal release remain BLOCKED.

The observations below are historical checkpoints, including preserved RED evidence.

---

# Current M5B1 verifier foundation (Issue15)

Current local debug environment is D:/agentsync-debug (see LOCAL-DEBUG.md).
A verified QEMU/Alpine VM now runs Docker29.8.2, cgroupv2 and builtin seccomp.
Actual local reproduction isolated the environment predicate as the only mismatch:
Docker's bare expected ENV deletion markers were mistaken for extra process vars.
Recognize only markers derived from validated image metadata and guard the actual
container environment before reading candidate source. Move the canary to traversable
host /tmp. All14 real Docker cases then passed in9.80s. Final exact-commit source/
wheel/sdist collection is the next gate; this preliminary run does not certify a
later tree. No GitHub execution was used. Full M5 and formal release remain BLOCKED.

The observations below describe earlier checkpoints and are preserved as history.

Local source regression after resume:716 passed/17 skipped (14 unavailable real
Docker,3 Windows symlink privileges),162.81s. Ruff/format/mypy26files passed.
See acceptance/evidence/local-only-20261020.json and redacted JUnit/log. Real Docker
still unverified; no Actions run was requested.

2026-10-20 user override: GitHub is storage only; no more Actions debugging,
testing or benchmarks. Both workflows now have manual-only triggers and uploads
use [skip ci]; the agent must not dispatch them. Validation is local/other
authorized compute only. This host has no Docker/Podman and WSL reports it is not
installed. Real Linux isolation remains unavailable here and must not be bypassed.
Preserve historical failures; local policy/Git tests cannot certify real Docker.

Version0.3.0a2, feature/m5b-verifier based on PR14 headf1f13ded.
PR16 first head227512a ran actual Docker gate39437105068:14 cases failed with
isolation_mismatch before candidate execution; all reported cleanup confirmed.
Actual backend acceptance is FAILED, not skipped/passed. Preserve this failure;
add safe effective-control diagnostics, identify the actual mismatched control,
repair only with evidence, then rerun the complete final-head gates. Local first
head source715pass17skip does not erase the Docker failure. No next implementation
stage is accepted until this gate and Work review are complete.

PR14 exact head passed9/9 quality jobs in run39433390898. Lead downloaded all9
ZIPs and verified every saved log/artifact hash, clean/stable source and matching
tree74072e7. Source/wheel/sdist each594cases: Windows594pass, POSIX591pass3skip.
Actual local collector18checks passed, three suites each592pass2permission skips.
Evidence: acceptance/evidence/rat14-ci-inspection.json and
F:/syuc/work/rat-followup/release-20261020T134712Z-3c60ae469b61. Work independent
reacceptance requested for this exact head; do not infer its decision.

M5B1 adds only an owner-controlled fixed black-box library: immutable managed Git
objects, bounded standalone solution.py, no host execution/mounts, inspected Linux
Docker isolation, trusted external JSON assertions and exact container cleanup.
See M5B1-CONTRACT.md / M5B1-GUIDE.md. Preliminary local source regression passed
703cases with16 explicit skips before the final cleanup repair; this is not final
head evidence. Actual Docker14cases are skipped locally because no backend exists.
Dedicated LinuxCI must execute them without skip/fallback before backend acceptance.

No agent-facing verifier API, job queue, restart recovery, task auto-acceptance,
approval consumption or source apply is added. M5B integration/M5B2, M6-M9 and
real autonomous relay remain open. Formal release BLOCKED; main unchanged.

---

# Release Acceptance package-install stage (Issue13 history)

Runtime version0.3.0a1 remains unchanged from M5A head7479dfa. Separatebranch
feature/release-sdist-acceptance improves tooling only. ParentPR12 nineCIjobs passed;
lead downloaded/hash-inspected all9 reports/JUnit/builds (see evidence/m5a-ci-inspection.json).
M5A local exacthead source+freshwheel each561pass2symlinkskip; all12checkspassed.
Work independently accepted the M5A scope at7479dfa (PR12 comment6286926323).
M5 stages remain partial until verifier/apply.

Issue13 adds fresh isolated sdistinstall/fulltests with exactarchiveSHA/PEP610origin,
independent wheel/sdist failure gates, installer-destination isolation and redacteddiff.
61 runner-policy unit cases passed; these mocks are not actualartifact/client proof.
At d8bc571, actual local source/wheel/sdist each585pass2symlinkskip, all18 checks
passed with clean stable source. Remote run39395631073 completed8/9: Ubuntu3.14
source failed because fixture Git spawned asynchronous maintenance and its lock
vanished between full fingerprints. Wheel/sdist passed. Fixture repair retains
every fingerprint assertion; newhead full local and nineCI gates remain pending.
See acceptance/INSTALLATION-REPORT.md and ERRORS.md for failure evidence.
Formalrelease remainsBLOCKED; actualadapter/autonomousrelay/sandboxverifier unverified.

---

# Current M5A stage (2026-10-20 America/Tijuana)

Version0.3.0a1, Issue11, feature/m5a-permissions. Contract: M5A-CONTRACT.md.
M4B exacthead98bd361c47f94b61ef03439651e2163ba6740a1f passed stable full12localchecks
(source+cleanwheel370pass/2Windowspermission skips), then nine remote CI jobs.
All9artifacts were downloaded and SHA256/contents checked; report trees match head
4df79c6dead14a86396f3957a24e79e4fbd2f376. Each source/wheel has372cases; Windows372pass,
Linux/macOS369pass/3Windows-only skips. See acceptance/evidence/m4b-ci-inspection.json.
Work independently accepted currentM4Bhead and closedIssue9; PR10receipt6284302265.
Approvedscope is prepare-only candidates; actualapply remainsM5B.

Current work: defaultviewer membership grants, owner-only role/approval control plane,
strict authorization before cachedresponses/objectlookup/Git, bound expiring approvals
and whitelist structured audit. Intentional security migration makes oldmembersviewer;
owner must explicitly regrant write/review roles. All existing tests must retain their
original assertions with explicit owner setup, never global permission monkeypatching.

No apply-to-user-branch endpoint or independent verification executor is added.
Owner credentials are a capability boundary, not proof of a physical human against
sameOS access. Actual unsafe submitted tests require a verifiedOSsandbox; Docker,
Podman/runhcs are unavailable in this local runtime; WSL presence alone is not proof
of safe isolation. M5B verifier remains blocked until proper execution isolation.
FormalReleaseAcceptance and actualmodelautonomous relay remain unverified/BLOCKED.

Next: finish exactsource/wheel/9CI/Work gates for M5A, then bounded M5B verifier
runtime/approvalconsumption. Continue M6-M9 only with their explicit test gates.

---

# Current M4B checkpoint (supersedes historical entries below)

Version 0.2.0a3, Issue #9, independent branch feature/m4-worktrees based on PR #8.
M4A exact head fe3ac7418413f4740f158035605ac2843b9c964d passed all12 local checks
(source/wheel326pass2skip) and9CI jobs. Nine artifact archives were independently
hash-verified; tested merge tree c593af08 equals head tree. Work independently accepted M3/M4A, closed Issues #4/#6 and kept #7 open.
Receipt: PR #8 issuecomment-6284092991. No main merge.

M4B implements independent Git object store/worktrees, real third-tree conflict
checks and awaiting_human_approval candidates. No original user-repository write
or approved apply endpoint exists. Source-config filter/include execution and
post-crash request rebinding were found in lead review and repaired with regressions.
Current final full source/wheel and CI evidence must be generated after edits freeze.
M4-05 approval/application and M5-M9 remain incomplete. Formal release BLOCKED.
All42 formal requirements remain tracked; new component coverage does not automatically
pass full acceptance cases. No real model/client autonomous relay has been verified.

Next: finish exact-SHA regression/installation/remote evidence and Work review, then
M5 approvals/audit/independent evidence verifier, M6 actual adapters, M7/M8 scheduler/
recovery and M9 full release run. Preserve every prior test and failure reproducer.

---

# Current checkpoint: M4A and Release Acceptance

Date: 2026-10-19 (America/Tijuana), version 0.2.0a2.
M3 source and installed-wheel tests passed (142 each), PR #5 CI passed 9/9 at
72ab6b5. Submission to Work is recorded; it is not a Work acceptance decision.

M4-01/02 implements canonical path inspection, SHA-256 file versions, cooperative
file/directory locks, lease ownership/replay/expiry protections and schema v4.
All three transports share Core. M4-03..05 remains pending; no user-file write or
merge API exists. Baseline before acceptance infrastructure: 211 passed / 1 skipped;
final evidence is generated by the acceptance runner after all edits.

Release Acceptance (Issue #7) adds complete formal requirement traceability,
separate real-client capability evidence, isolated process-death recovery tests,
fail-closed formal release gates and reproducible reports/logs/JUnit/build identity.
Current release conclusion is BLOCKED while real autonomous relay and M4B-M9 remain
unverified. See acceptance/DESIGN.md and acceptance/CLIENT-MATRIX.md.

Resume: read the current contract and generated report; repair any failed local or
remote checks, submit this checkpoint to Work, then implement M4-03..05 in a separate
bounded branch. Continue M5-M9, adding acceptance cases at each stage. No paid API
calls, main merge or formal Release without authorization. Do not infer a passed
requirement from a test file merely existing.

---

Historical evidence follows; the current checkpoint above supersedes old stage labels.

# Progress and recovery

Date: 2026-10-19 (America/Tijuana). Version: 0.2.0a1 under development.
Current execution scope: **M3-01..04**, Issue #4. M4-M9 remain planned.
M3 local verification: 142 tests passed, full-repository Ruff lint/format and mypy
(16 source files) passed; wheel/sdist built. Clean-wheel and remote CI acceptance
are recorded in M3-REPORT.md and the associated PR before Work signs off.
The table below records the historical M0-M2 checkpoint. Its Ruff repair PR #3 was
independently accepted by Work at 3c429ea, with all 9 CI jobs and their artifacts
verified. PR #3 remains unmerged. M3 development is based on that accepted branch.

| Work | Evidence / status |
|---|---|
| M0-01 | Windows Python 3.14 source install; Python 3.12 clean wheel install |
| M0-02 | CONTRACT.md, ARCHITECTURE.md; state/identity/version/lease rules in Core |
| M0-03 | Local Git repo, MIT, exact direct pins and runtime/dev snapshots; no remote push |
| M0-04 | 92 tests on each interpreter; Ruff clean; mypy clean (15 source files); CI configured |
| M0-05 | Plan, specification, progress, decisions, error log, compatibility and test report saved |
| M1-01 | Agent IDs, sessions, heartbeat, expiry and derived online state |
| M1-02 | Project-scoped access, tasks, immutable dependencies, priorities |
| M1-03 | SQLite atomic claims, expected versions, scoped idempotency; claim races tested |
| M1-04 | Renewable ownership leases, explicit expiration reclamation; stale owners rejected |
| M1-05 | WAL, transactional v1/v2 migrations, persistence, bounded startup contention handling |
| M2-01 | Official MCP SDK 2.3.0 stdio, 11 explicit typed tools |
| M2-02 | Two independent MCP server processes share the same absolute database; one claim winner |
| M2-03 | Python AgentSyncClient uses Core, consistent envelopes |
| M2-04 | Authenticated loopback HTTP, real TCP and ASGI tests, shared state with SDK |
| M2-05 | **Connection gate complete**: registered native config/tools verified; user confirmed current desktop UI shows agentsync connected; Claude Code CLI also connected |

Native same-task Codex agents implemented core and integrations and independently reviewed security.
The lead inspected actual source, ran full checks, repaired review provenance, numeric bounds and
startup concurrency, rebuilt the package and retested the installed wheel.

Current source Python 3.14.6: `python -m pytest -q --junitxml=docs/pytest-m2-followup.xml`:
**92 passed in 7.40s**. Clean installed a2 wheel Python 3.12.14:
`python -I -m pytest -q --junitxml=docs/pytest-m2-followup-python312.xml`: **92 passed in 7.55s**.
Ruff: all checks passed. Mypy: 15 files, no issues. Build: wheel and source distribution built.
Pip check: no broken requirements. Details and limits: TEST-REPORT.md, COMPATIBILITY.md.

M2-05 was closed in this continuation: the public CLI installed the actual shared MCP entry,
native probes loaded that entry without overrides, and the user directly confirmed the desktop
UI displayed agentsync connected. UI observation is user-reported, not automated clicking or
screenshot evidence. A complete model-driven two-desktop development session remains a later
end-to-end scenario; it is not needed to claim that this M2 connection gate is complete.
See M2-CONTINUATION.zh-CN.md and the distinct probe/confirmation JSON records.

Historical limitation updated: Windows/Linux/macOS x Python 3.11/3.12/3.14 passed
remote CI for PR #3. Independent verification of submitted in-product review evidence
remains M5. Project-enrolled identities are not external OAuth identities. GitHub
publication and owner-only Codex Cloud setup were subsequently user-authorized.
No paid provider API calls or public package Releases were made.

## Resume steps

1. Read AGENTS.md, WORKFLOW.md, PLAN.md, this file, CONTRACT.md and TEST-REPORT.md; inspect Git status.
2. Preserve verified coordination rules and the existing failure regressions.
3. M2-05 connection gate is closed; preserve distinction between user UI confirmation and native probes.
4. M3-01..04 is implemented; finish its independent wheel/remote/Work acceptance gate.
5. Continue M4 path boundaries, cooperative locks, isolated Git worktrees and conflict detection.
6. Continue M5-M9 from PLAN.md; record evidence and checkpoints at each stage.

## Ruff CI follow-up

Issue #2: Codex repaired full-repository Ruff violations without runtime changes.
Local 92 tests, lint, format, types and build passed. PR-head remote matrix is the
acceptance gate; see RUFF-CI-REPAIR.md. main remains unchanged.
