# Amadeus current direction: finish M7/M8 and remaining release gates

Current debugging checkpoint: c56cbe2 / a115 has 197 unique affected Windows
source passes (34 new, 163 existing), with unchanged source and retained initial
harness failure. Linux Python 3.14 also passed all 197 identical cases; all 228
source hashes match frozen Git bytes. The full Windows source/wheel/sdist collector
remains active, not passed. See PROGRESS.md for the exact
original handles and acceptance/evidence/m115-source-checks/summary.json for the
completed evidence. Continue the original matrix and real-client release gates.

Owner execution order updated on 2026-11-13: finish the original plan's remaining
product code before starting further debugging. The original Windows 3.12 a114
collector may finish naturally; retain its evidence. Do not start the prepared
Windows/Linux continuation queues until the implementation audit is complete.

The code audit identified three original-scope connections, now authored:
M3/M1 owner recovery of a pending handoff after both participants lose all valid
sessions; M7 continuation of saved unfinished work after a positively terminated
failed attempt, with fresh recipient authority and unknown executions fenced;
and M8 project-persistent usage for the application's explicit model advice calls.
These are product changes, not additional M5 phases. The code-first pass is now
complete: implementation and independent source review cover these connections.
Start debugging the previously unrun a115 source and affected existing paths next;
do not interpret this inventory as runtime acceptance. Existing evidence
continues to describe its original frozen SHA, never these later changes.

The code-first inventory below covers the original 42 tasks. "Present" means
implementation was located and read; it does not mean a requirement passed its
acceptance tests. The release requirements register retains its independent gates.

| Original scope | Product implementation | Code-first remaining work |
| --- | --- | --- |
| M0-01–05 | Packaging, dependency locks, architecture, workflow and local tooling | Present; hosted Actions remain prohibited |
| M1-01–05 | Core projects/sessions/tasks, transactional leases and SQLite migrations | Present; new abandoned-handoff recovery authored |
| M2-01–05 | Shared Core through MCP stdio, HTTP and Python SDK; client examples | Present; actual-client evidence stays separate |
| M3-01–04 | Versioned context/search, structured handoff and owner recovery | Present; new recovery regression source NOT RUN |
| M4-01–05 | Paths/locks, snapshots/worktrees, conflicts and approved target integration | Present at a114; no original-checkout overwrite required |
| M5-01–05 | Permissions, approvals, audit, independent verification and security regressions | Present; retain the single frozen M5 exit checklist |
| M6-01–05 | Common lifecycle, Mock and Codex/Claude/Cursor factories, capture and manager | Present; unsupported capabilities explicit, real clients not inferred |
| M7-01–04 | DAG/capacity scheduling, queue, providers/advice, durable Mock budgets/retries and confirmed-failure continuation | Present; new continuation regression source NOT RUN |
| M8-01–02 | Usage, durable recovery and benchmark tools; new project provider accounting | Present; new provider accounting regression source NOT RUN |
| M9-01–02 | Existing collectors, matrix/manifest/review, package/license tooling and examples | Present; current-code execution and publication remain gated |

Frozen ddd4b42 (0.3.0a114) implements original M4-05 owner-approved integration into an
ordinary target repository's new branch and independent new worktree. The exact
verified candidate is imported locally; the original checkout is preserved.
Approval, task/proof/source bindings and permanent destination reservations are
checked before effects. Interrupted effects remain partial/unknown, without retry.
Windows affected source evidence reconciles 120 unique cases: 119 pass and one
Linux Docker skip. The original 120-case run and repaired 24-case subset remain
separate; this is not a new full-suite run. No real user workspace was touched.

M9's existing complete source, wheel and sdist collector finished on Windows 3.12
at 2026-11-13 12:46:46 UTC, exit 0: each suite 2371 pass / 56 skip with no failures
or errors. Preserve this frozen a114 evidence. The code-first continuation above
supersedes the prepared later-row launch: do not run old candidate packages as
validation of the new product code. After implementation finishes, freeze a new
candidate and resume the incomplete debugging scope and required matrix. Actual
Linux Docker integration and full matrix are not complete for a114. Source evidence is in
acceptance/evidence/m4-owner-integration/summary.json. macOS, unsupported real
vendors and external Release approval remain explicit gaps. No new M5 phase.

Product 95244e2 (0.3.0a113) connects bound controlled-relay receipts to the
existing owner project usage store without combining caller and receipt totals.
Windows wheel 510 passed / 1 Docker skip and Linux sdist 511 passed / 0 skips
cover the same 511 IDs; exact packages, source/runtime identity and actual local
Docker-to-owned-review usage sync pass. Evidence:
acceptance/evidence/m8-receipt-usage/summary.json. Independent Astra technical review
accepted this limited scope; no external Work or formal Release approval is claimed. This is not actual billing or
real-vendor acceptance. Next implement original M4-05's owner-approved target
new-branch/worktree integration, preserving the original checkout. Private-ref
delivery alone remains insufficient. Then freeze and run M9's current full local
matrix. No new M5 phase or real user-workspace application is authorized here.

Product 7fa4597 (0.3.0a112) implements original M7-04/M8-02 durable owner-only
Mock retries, budget reservations, driver generations, cancellation, handoff and
independent review in Core schema16. Windows wheel 630 passed / 1 skip and Linux sdist 631 passed / 0 skips;
631 matching case IDs and actual Linux Docker delivery pass. Preserve source
325pass/6skip evidence and supplements for unchanged slow verifier modules.
Evidence: acceptance/evidence/m7-durable-workflow/summary.json.
Independent Astra technical review accepted this limited scope; external Work
approval and formal Release are not claimed. This limited scope
does not prove real-client recovery/billing or formal Release. Subsequent a113
closes the receipt-to-project-usage connection; M5 stays at its original five items.

Product1014307 (0.3.0a111) adds strict dependent review using prepared Codex/Claude/
Cursor profiles, pinned verified source and review.md-only unverified output.
Legacy Codex handoff remains compatible. Windows wheel360pass/11Docker skips and
Linux sdist371pass/0skips cover the same371case IDs. Actual Linux Docker3/3 then an
owned Cursor protocol emitter and reopen pass; real Claude/Cursor remain NOT RUN.
Evidence: acceptance/evidence/m7-dependent-review/summary.json. Independent technical
review accepted this limited scope. The original M7-04/M8-02 durable Mock execution path is implemented
and separately checked at7fa4597 above.
Unknown dispatch cannot be retried, budgets do not replace authority, and estimated
costs must not be represented as real bills. Keep existing temporary Mock mode.

Product529df3b (0.3.0a110) now exposes the existing approved private-ref delivery
through explicit owner SDK/CLI calls. Fresh Windows wheel/Linux sdist affected
checks each pass496cases/1platform skip; the actual Linux Docker-to-verified-task,
SDK approval, separate CLI delivery and reopened status pass with original source
unchanged and no remaining containers. Evidence:
acceptance/evidence/m4-owner-delivery/summary.json. This is limited M4-05 progress;
source-workspace apply remains deferred and formal Release blocked. Independent
technical evidence review accepted the limited scope. Next fill the original M6/M7 cross-client dependent-review gap,
then evaluate durable confirmed-failure retries and budget admission against the
original requirements. Keep unknown executions fenced and live vendors NOT RUN.

M8's existing benchmark tool has now run one declared local contention load on
both installed platforms:4threads/20rounds and2spawned workers with mixed Core/HTTP/
20rounds. All four commands pass, audit totals exactly match120claims per platform,
one winner per round and no leftovers. Evidence:
acceptance/evidence/m8-bounded-load/summary.json. This is not exhaustive stress or
a production SLO. Next inspect M4-05's actual remaining integration capability
against the original requirement before deciding whether new product code is needed;
do not reimplement existing private-ref delivery or create another M5 phase.

M7-03 tests2af7ccc now cover the existing five provider serializers/parsers and
actual owned-loopback transport (success,429,redirect refusal,limits,cancellation).
Windows/Linux installed-runtime regressions each269pass; no product change or paid
calls. The requirement mapping ispartial rather thanmissing; no real provider
compatibility is claimed. Evidence: acceptance/evidence/m7-provider-offline/summary.json.
Next execute the existing bounded M8 concurrency diagnostic with a declared load,
then address remaining original-plan product gaps. M5 closure is not reopened by
test-only coverage additions; all full Release gates remain in force.

Runtime09425da has completed current Windows/Linux installed-sdist regression with
an affected-test repair at9fb36a1. Original c262 full runs retain4failures each;
two repaired test files pass246cases on each platform, with all2334final case IDs
and unchanged inputs reconciled. Combined Windows2279pass/55skip and Linux2328pass/
6skip; no product change or new M5 stage. Evidence:
acceptance/evidence/m9-sdist-regression/summary.json. Independent technical review
accepts B6 and closes the original five M5 requirements for the fixed open scope;
apply remains deferred and Release blocked. No external Work/PR approval is claimed.
Next improve existing M7-03 BYOK offline coverage, not reimplement its provider layer.

Tests07aba94 now cover actual coordinator subprocess exit after verified source,
both recoverable preparation and uncertain dispatch intent. Installed unchanged
runtime09425da passes all10flow cases with7actual Docker executions and zero models;
independent review accepts only this limited recovery scope. Evidence:
acceptance/evidence/m8-process-recovery/summary.json. Next complete current frozen
installation/full local regression, retaining unsupported vendors and release gates.

Installed09425da now has one continuous actual two-Codex flow through explicit host
decisions, Docker8/8, independent verified producer completion and an automatically
prepared receiver. Full358byte model review accepted as a document only/unverified;
fresh reopen creates no model calls/tasks/attempts. See
acceptance/evidence/m7-continuous-live/summary.json. This closes the previously
unrun same-version continuous composition example, not cross-vendor compatibility,
unattended approvals, crash recovery or complete M7/Release. Next verify actual
host-process interruption at recoverable and uncertain dispatch boundaries; reuse
existing local integration fixtures without another model call. No new M5 phase.

Current product09425da composes the producer, explicit exact staging/execution/
completion decisions, actual independent Docker proof and receiver handoff in
VerifiedProposalFlow. A verified-source checkpoint can resume the receiver without
rerunning producer or verifier. Unknown execution remains fenced. The local fresh
Linux wheel passes8affected checks with5actual Docker executions and no real models.
Earlier17e0ab4 retains its24check regression; counts remain separate by SHA.
Evidence: acceptance/evidence/m7-verified-handoff/summary.json; limited source/package review
accepted. No new M5 substage, permission strategy, queue protocol or apply operation.
Next exercise this combined flow with actual clients and then recoverable host
interruption. Unsupported client features stay explicitly unsupported under the
original specification, rather than becoming new unconditional exit conditions.

Latest actual milestone: installedb455d9b coordinator derives the saved real6017005
producer reference, automatically prepares one dependent task/worktree, checkpoints
for exact-plan review and resumes one real Codex receiver.21.635seconds/exit0;
the372byte review was independently accepted as a document only, completed/unverified.
Fresh reopen returns the same result with zero authority calls or new attempts.
No candidate/application behavior or release gate changed. Evidence:
acceptance/evidence/m7-host-handoff-live/summary.json (limited evidence independently accepted).
Next close continuous producer-to-independent-verification-to-receiver composition
and real interrupted-agent recovery; the staged continuation does not prove those.
No new M5 substage or duplicate implementation is authorized by this milestone.

Latest product milestone: installed host coordinator atb455d9b automatically derives
source pins, waits for independent completion and prepares/dispatches one dependent
receiver through existing Core/queue APIs. Same-session preparation is recoverable;
uncertain dispatch is never retried.15source and101fresh-wheel checks on each local
Windows/Linux platform pass. No new Core/queue protocol, M5 stage or acceptance
policy was added. Evidence: acceptance/evidence/m7-host-handoff/summary.json.
Next validate this coordinator with an actual authorized client, retaining current
launch/fee/source/independent-review gates. That real run has NOT started; local
protocol fixtures and historical two-run evidence do not satisfy full M7/Release.

Checkpoint8a4ba72: deterministic invalid pinned proposal input is now rejected
before wave admission. Post-admission revalidation/failure fences remain intact.
23source tests and86fresh-wheel tests on each local Windows/Linux platform pass.
Evidence: acceptance/evidence/m7-pinned-admission/summary.json. The owner resumed
work after the requested pause. The current next task is to compose
existing public APIs for host-side automatic pin derivation/next-task preparation;
retain independent completion, exact launch consent and inert output gates. No
new queue API or model attempt has started for that next item.

Latest milestone: a distinct real Codex reviewer on2ac4557 received and reviewed
the saved6017005 producer artifact. Exact context pin, separate identities and
full407byte document were independently checked. New review task completed as
unverified; original verified producer unchanged. This is a host-prepared,
cross-upgrade two-run handoff, not unattended or cross-vendor M7 acceptance.
Next repair queue admission ordering so deterministic invalid pinned input is
rejected before reserving a wave; preserve all post-admission failure fences.
Evidence: acceptance/evidence/m7-model-review-live/summary.json. Release stays blocked.

Use [M5-FINAL-ACCEPTANCE.md](M5-FINAL-ACCEPTANCE.md) as the only M5 exit checklist.
M5 remains the original five requirements; no new stages for documentation,
duplicate evidence or noncritical enhancements. Existing stage records below are
historical. Current M6 has typed host-factory Codex/Claude/Cursor protocol adapters,
bounded offline parsers/inspectors and explicit pinned invocation plans.
The 2026-11-11 continuation rule authorizes local implementation, testing,
repair and retesting in one task. Start from the exact source and outstanding
checks in PROGRESS.md, and continue after each component checkpoint.
See [current progress](PROGRESS.md) for source changes and unrun checks.
Frozen2ac4557 adds an authenticated exact producer-proposal reference for the next
actor. Direct capture/publication/submission proof and different Core author are
required; content is untrusted bounded input, not execution authority. The
nonrecursive A-to-B-to-C path and old no-pin digests are covered.85source checks
and85fresh-wheel checks on each Windows/Linux platform pass, with independent
source/package review. Next validate a distinct real reviewer against the saved
actual producer artifact; no second model has started. New full matrix remains
NOT RUN and historical6017005 evidence is not upgraded to this new commit.
The6017005 queued proposal path now has one actual Codex execution, followed by
explicit host-approved staging,8/8actual Docker inputs and distinct Core reviewer
completion of the same task. Reopened state is completed/v6/verified; temporary
authentication is cleaned and original source/auth unchanged. This limited scope
has independent review; it is not a second-model or multi-task artifact relay.
Next reuse existing immutable context, launch consent and queue machinery for a
pinned producer-proposal input to a distinct actor's independent task. Keep review
output inert/unverified and preserve all candidate/verification gates.
The earlier queued live preflight stopped without model dispatch because the
producer heartbeat aged beyond120seconds during review. This is an observed
eligibility refusal, not a completed real queue run. Test-only74e1527 covers
authenticated heartbeat recovery while preserving exact consent and expiry
gates. The6017005 sdist has fresh offline Windows/Linux install smoke evidence.
One full local matrix using74e1527 tests is complete and independently reviewed:
Windows2251pass/45skip and Linux2290pass/6skip, zero failures/errors. Both contain
2296identicalcase IDs; skipped cases pass on the other platform, without claiming
missing platform capabilities. Keep the failed live preflight consumed, with no
retry. The next real-queue fixture still requires current authenticated heartbeat
and exact launch consent; offline passes do not replace actual-client acceptance.
M7-01/02 now connect prepared Codex code proposals to the existing bounded queue
at6017005. Dependency/load/capability selection and durable wave reconciliation
stop at submitted review; exact launch approval and separate candidate execution
remain required. Final fresh Windows/Linux wheels each pass72 scoped cases.
Independent code/package review accepted the limited implementation. Actual
queued-model evidence is now recorded above; cross-client and full Release remain unverified.
The actual same-Core Linux proposal pipeline at a2634ec now passes a bounded
real Codex task: immutable capture/review, explicitly approved genuine candidate,
8/8 actual local Docker inputs and a distinct host-mediated Core review. Reopened
task is completed/v6/verified; original workspaces and authentication are unchanged.
This supersedes the next-run preparation notes below. It is not a second model,
unattended relay, cross-client or full M6/Release acceptance. Continue from the
existing remaining safety/lifecycle/relay requirements, without repeating the run.
The real Linux host prerequisite is now available at a2634ec: explicit single-task
read-only profile, pinned official0.167 CLI, native configuration/tool projection
and actual bounded file/loopback checks.48 source/48 Windows installed/47 Linux
installed checks pass, with1Windows-only Linux skip. Default/legacy/MXC plans remain
compatible. Next prepare a fee-gated, one-shot real Codex proposal task on this same
Linux Core/Docker host; do not infer real-client execution from these no-model checks.
The same-Core fixture pipeline now passes actual Linux Docker integration at
c181f99 against unchanged runtime d4c7cf9: correct output completes through a
distinct Core reviewer; wrong output and self-review are rejected.7fe0c28 fixes
only the independent local-daemon absence observation, then checks both recorded
containers read-only. This is deterministic integration, not a real model run.
Next assess compatible real Codex hosting on that same isolated Core/Docker host;
do not repeat the historical Windows attempt or infer cross-host authentication.
Controlled proposal review submission and the owner staging bridge are implemented
at d4c7cf9:151 affected source checks,45 Windows installed checks and23 Linux
installed checks pass. Explicit launch consent, live lease/revision and independent
owner/stager pins remain required. Next integrate the same-Core path with actual
local Docker and independent completion using a clearly labeled protocol fixture;
then separately assess the real-client prerequisites. This is not full M6 acceptance.
Owner-reviewed proposal staging is implemented at193d9b2 (0712899 only corrects
a traceability test count). It creates genuine isolated managed candidates from
authenticated publications while preserving source/producer worktrees and task
state. Scoped Windows/Linux installed-package checks pass; full Release remains
unaccepted. Next connect controlled producer submission-to-review and this staging
service with existing candidate verification; do not add new M5 subdivisions.
The actual captured add.py now passed8 inputs through genuine managed candidate
creation and the existing local Linux Docker verifier (runtimebf54d44/pilot8520691).
Only the new isolated fixture task is verified; import and reviewer operation were
owner-mediated. Next product work is owner-only proposal staging with exact reviewed
pins, without source-workspace application. General automated import and unattended
artifact relay remain unverified. Owner confirms no Claude/Cursor subscriptions;
cross-client calls remain NOT RUN and paid APIs remain prohibited.
M6's first authenticated attempt at `6a8ff41` remains unknown. A separately
authorized diagnostic at `080722e` captured the startup-warning ordering failure;
`ee45690` narrowly repairs it and passes offline replay plus affected local source
and installed-package tests. The actual failed Core receipt remains unchanged.
The separately authorized repaired run now has scoped acceptance: real fixed-text
Codex to adapter to Core review, followed by a distinct host-mediated reviewer.
Two actual isolated Codex sessions now completed automatic structured handoff and
shared-context confirmation, followed by a third Core reviewer. Cursor native
Node-bundle preparation is implemented at f74f29f with local Windows/Linux evidence.
Actual local Codex cancellation at f74f29f now preserves a durable unknown result
after the owned parent ends; server cancellation and descendants remain unverified.
The actual15-second Codex deadline also preserved an unknown result despite a
captured completed turn; active-generation timeout remains unverified.
Product80754db now provides atomic task-bound inert proposal publication, with
local source and fresh Windows wheel evidence. Productbf54d44 now captures actual
Codex code proposals into Core under the pinned contract; the real task remains
running/unverified. Next: separately reviewed owner import creating genuine managed
candidate provenance, then existing isolated artifact verification. No host execution
or direct workspace application of generated code. Establish
Claude/Cursor account availability, no-extra-fee state and actual execution
boundaries before live cross-client validation. Same-client relay cannot replace cross-client acceptance. Do not retry consumed tasks or create
a new M5 subdivision.
Owner-only candidate execution and independent completion have limited local evidence.
M6's instance-local manager can return a nonblocking dispatch handle and observe
its startup receipt with a bounded wait; this does not enable automatic scheduling.
Default live startup is unsupported; Agent-facing execution/completion,
credential use, server cancellation and apply remain gated. Latest actual checks
and limitations are in acceptance/RELEASE-ACCEPTANCE-REPORT.md; component passes
do not establish the real clients, dual-agent relay or formal release. BLOCKED.

# Historical M5B3B2B candidate execution intent guard in development

Implement owner-only prepare/get/abandon and transactionally fence reservation
recovery while a prepared intent exists. See M5B3B2B-CONTRACT.md. Version0.3.0a11 /
schema12 additive tables; old job/claim states/proofs/history unchanged. This is
non-executing admission only, no Docker/credential/worker/renew/taskgate/apply.
Prior B2A accepted PR24. Full frozen validation and Work review pending; Release
BLOCKED. D:debug/F:source; no Actions/paid/main changes.

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

# M5B2C bounded cleanup-receipt implementation

Advance recovery component coverage with a trusted owner-only one-shot cleanup
receipt for expired, acknowledged full-ID executions. See M5B2C-CONTRACT.md and
M5B2C-GUIDE.md. No cleanup result grants candidate success, job reuse, task
acceptance, source apply or automatic retry. Full M5/M9 release remains BLOCKED.
Final acceptance requires frozen source/wheel/sdist tests, Windows regression,
real hard-exit/identity cases, independent evidence inspection and Work review.

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

Current validation policy: GitHub upload/storage only; no Actions execution or
benchmarks. D:/agentsync-debug hosts local Windows and Linux Docker validation.
M5B1 code cfb5304 completed18localchecks, source/wheel/sdist each754pass3skip,
42real Docker observations. Work acceptance is separate. Durable jobs/leases
are the next bounded design, followed by supervised execution/recovery and safe
approval/application. Full M5 and formal release remain incomplete.

# AgentSync implementation plan

Baseline: user-approved specification v1.0, 2026-10-19 (see SPECIFICATION.md).
Current execution: **M5B1 bounded verifier foundation plus Release Acceptance**,
Issues #15/#7/#11. M5A passed independent Work acceptance. PR14 package evidence
headf1f13ded passed9/9CI plus independent artifact inspection; Work reacceptance is
separate. M5B1 is a synchronous owner library only; queue/recovery, permission API,
approval consumption and safe apply remain further stages. See M5B1-CONTRACT.md.
M3 is preserved at 72ab6b5 (PR #5); its nine CI jobs passed. Work independently accepted M3 and M4A (PR #8 comment6284092991);
Issues #4/#6 are closed while Release Acceptance #7 remains open. M4A PR #8 at fe3ac74 passed nine CI jobs and independent artifact inspection.
M4B head98bd361 passed9CI jobs with all372 cases executed per source/wheel environment
(platform-specific skips separately recorded). Version0.3.0a1 is M5A under development;
actual approved application, independent sandbox verification and M6-M9 remain incomplete. The user authorized
continuous staged work and GitHub PR publication, no direct main writes/merges or
paid provider calls. See M4A-CONTRACT.md and acceptance/DESIGN.md.

| Stage | Work packages | Acceptance / continuation |
|---|---|---|
| M0 | M0-01 environment/install; M0-02 architecture/state machine; M0-03 Git/MIT/deps; M0-04 pytest/Ruff/types/CI; M0-05 recovery docs | Installable package, passing quality checks, local checkpoint |
| M1 | M1-01 identity/heartbeat; M1-02 projects/tasks/dependencies; M1-03 atomic claim/version/idempotency; M1-04 leases/reclaim; M1-05 SQLite/migrations/concurrency | Single claim winner; stale owners rejected; persistence |
| M2 | M2-01 official MCP stdio; M2-02 shared absolute DB; M2-03 Python SDK; M2-04 authenticated local HTTP; M2-05 real client configurations/connectivity | All transports share Core; protocol and desktop results reported separately |
| M3 | M3-01 context store; M3-02 FTS/source/version search; M3-03 structured handoff; M3-04 accept/reject/reassign | Agent B continues A's actual work from authorized handoff |
| M4 | M4-01 canonical path boundaries; M4-02 lock leases; M4-03 Git worktrees; M4-04 version/diff/conflict detection; M4-05 confirmed safe merge | Isolated parallel edits; manufactured conflicts detected |
| M5 | M5-01 permissions; M5-02 risk approvals; M5-03 redacted audit; M5-04 independent evidence checks; M5-05 security regression | Neither model assertions nor arbitrary submitted commands authorize acceptance |
| M6 | M6-01 adapter contract; M6-02 Mock; M6-03 Codex; M6-04 Claude; M6-05 Cursor/manager | One actual approved, isolated client result bound to Core; use a supported public interface and the current no-extra-cost constraint |
| M7 | M7-01 dependency scheduler; M7-02 capabilities/load; M7-03 optional BYOK; M7-04 decomposition/retries/budgets | Reproducible automatic handoff between two real clients after the M6 single-client gate; Mock covers deterministic cases |
| M8 | M8-01 usage/source/unknown costs; M8-02 recovery/stress/performance | Do not invent third-party subscription usage or bills |
| M9 | M9-01 platform compatibility; M9-02 docs/license/build/release | Separately approved public push/release only |

The [M5–M6 execution adjustment](M5-M6-EXECUTION-ADJUSTMENT.md) keeps M5 on its
single exit checklist while the isolated M6 branch proceeds. Codex launch
preview, lifecycle capture and Core review binding are available on the pilot
branch. The next M6 acceptance step requires the verified execution conditions
and a real result. M7's second live client depends on that result.
The single-client pilot now retains observed cancellation results across restart;
local process regressions cover cancellation, timeout and abnormal exit without
releasing its one-attempt fence. This is M6 lifecycle implementation, not a new
M5 stage or real-client acceptance.
The opt-in native Windows permissions plan has local boundary evidence. The
current live-launch dependency is effective extra-tool dispatch restriction and
isolated authentication, with the owner's no-extra-cost confirmation recorded.
Keep the one real-call grant unconsumed until those prerequisites are met.

Use one Core for every integration. Locks in M4 will be cooperative. Local SQLite WAL
must not be shared across machines/network filesystems. Native control adapters are M6,
not part of this batch. Review in Alpha records a separate reviewer's evidence assertion;
automatic verification of those claims is explicitly M5.

At every checkpoint update PROGRESS.md, TEST-REPORT.md, ERRORS.md and DECISIONS.md.
Never mark M2-05 complete merely because the official SDK client can call the server.

Release Acceptance traces all 42 formal requirements and T01-T16. At each checkpoint
execute the implemented subset and retain unimplemented cases as not_run. At M9 run
the full suite, platform/package gates and separately authorized real client relay.
