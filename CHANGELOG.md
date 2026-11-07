# Changelog

## 0.3.0a30 - implementation checkpoint

- Add a pinned Cursor CLI plan and opt-in process factory for terminal JSON.
- Run configurable Mock task graphs and worker rosters through a local stdin command.
- Let opted-in Mock tasks pass a pinned context revision and a new lease to another worker.
- Save and restore explicitly selected private usage checkpoints.
- Keep raw historical evidence copies in Git and omit them from source packages.
- Validation deferred to the end of the implementation phase.

## 0.3.0a29 - current desktop CLI declaration

- Admit the exact reviewed desktop declaration `0.167.0-alpha.3.2` alongside
  previously reviewed declarations; retain the original default and launch guards.
- Local version/help/feature inspection remains separate from real model tasks,
  which require fresh authorization and existing safety/cost conditions.

## 0.3.0a28 - explicit desktop Codex preparation version

- Allow the exact reviewed desktop CLI declaration `0.166.0-alpha.6` during
  Codex plan preparation, retaining the original version and default profile.
- Keep unknown versions denied and preserve fixed arguments, environment filtering
  and all unverified authorization/client/cost markers. No live model test implied.

## 0.3.0a27 - configurable owned Mock workflow

- Execute a validated bounded task DAG using the existing temporary-project Mock
  workflow, dependency/capability dispatch, attempt budgets and separate peer reviews.
- Retain the fixed demo and its behavior. Inputs grant no external execution;
  every result remains a simulation and unverified.

## 0.3.0a26 - manager lifecycle error boundary

- Normalize adapter callback failures into fixed public manager errors across
  lifecycle operations; retain legitimate error codes without private messages.
- Preserve caller cancellation, original dispatch ownership and successful private
  result data. This does not establish complete output auditing or real-client safety.

## 0.3.0a25 - nonblocking dispatch receipt

- Add `RunManager.dispatch_task(adapter_id, task)` to obtain an admitted handle
  without waiting for a possibly stalled adapter start. Compose with the bounded
  `wait_dispatch` observer; returned receipts still do not imply execution success.
- Share the existing admission path with `start_task`, preserving namespace,
  idempotency, capacity, cancellation and sanitized failure behavior.

## 0.3.0a24 - bounded dispatch observation

- Add `RunManager.wait_dispatch(handle, timeout_seconds=...)` to wait up to 300
  seconds for an existing adapter start receipt. Zero seconds polls immediately.
- Observation timeout or caller cancellation preserves the original dispatched
  work and history slot. It never retries, cancels execution or implies run success.
- Real clients, automatic relay, M5 and Release acceptance remain unverified/blocked.

## 0.3.0a23 - internal independent task completion

- Add an owner-mediated completion gate with independent reviewer authentication,
  exact candidate/task versions, fixed policy and passed isolated execution evidence.
- Atomically persist completion, review, verification proof, idempotent receipt and
  audit; classify legacy text reviews and historical responses as unverified.
- Add schema14 without a public execution/completion transport, source application,
  automatic dispatch or real-client acceptance. M5 and Release remain blocked.

## 0.3.0a22 - owner candidate execution prototype

- Connect an owner-only internal candidate executor to the fixed Docker verifier,
  binding fresh candidate bytes, reservation, intent, profile and result evidence.
- Persist a permanent one-attempt fence before container creation; retain unknown
  outcomes and allow one exact-identity cleanup after lease expiry.
- Keep cleanup observations stable when an expired executor returns concurrently;
  preserve historical reservation receipts and keep task acceptance unverified.
- Add schema13 without exposing execution through Core, MCP or HTTP. Actual
  client relay, verified task completion, automatic retries and apply remain gated.

## 0.3.0a21 - portable planning JSON output

- Fix valid Unicode project IDs crashing `agentsync plan` when redirected stdout
  uses ASCII encoding; JSON escapes preserve the decoded planning result.

## 0.3.0a20 - offline reported-usage command

- Print the existing usage ledger summary from a bounded stdin checkpoint with
  `agentsync usage --project-id ID`, without opening Core state or calling clients.
- Keep caller-reported provenance, unknown costs and incomplete metrics explicit;
  invalid inputs receive a fixed error without echoing private checkpoint data.

## 0.3.0a19 - Cursor contextual launch entry point

- Allow a trusted Cursor host factory to use the existing task-bound launch
  context for prelaunch cancellation and original-deadline checks.
- Preserve the legacy factory, unsupported default and parent-only cleanup;
  no built-in Cursor invocation plan or actual client verification is added.

## 0.3.0a18 - opt-in pinned Claude launch plumbing

- Add a Claude process factory using the existing restricted plan and shared
  task-bound launch observations; defaults remain unsupported.
- Keep managed-hook, credential/provider, billing and sandbox limitations explicit;
  no actual client execution or acceptance is implied.

## 0.3.0a17 - opt-in pinned Codex launch plumbing

- Add a task/run/loop-bound launch observation with an original-deadline check
  and one consumed local process-start attempt.
- Add an opt-in Codex process factory with fresh pin checks and explicit filtered
  environment; preserve unsupported defaults and legacy factory behavior.
- Keep actual-client authorization, billing, isolation and acceptance unverified.

## 0.3.0a16 - offline dispatch advice command

- Expose existing dispatch planning through bounded stdin JSON with `agentsync plan`.
- Preserve unverified planning markers without opening Core state or starting work.
- Reject duplicate fields, nonfinite numbers, unknown options and oversized input.
- Keep alpha15 installed and Linux regression evidence bound to their frozen source.

## 0.3.0a15 - development admission and diagnostic checks

- Add bounded process-local Core thread admission while preserving transaction behavior.
- Reset inherited gate state after fork and reclaim unused per-path gates.
- Require exact claim-audit identity/outcome coverage in local contention diagnostics.
- Keep earlier alpha14 package evidence bound to its original source commit.

## 0.3.0a14 - development recovery and adapter preparation

- Add an actual Core crash/lease-expiry regression with successor and dependency recovery.
- Add optional elapsed admission limits to the isolated Mock workflow.
- Add pure bounded retry advice with confirmed outcomes and Retry-After floors.
- Add strictly bounded JSON checkpoints for normalized caller-reported usage.
- Add isolated local claim-contention diagnostics with explicit latency budgets.
- Add non-executing pinned Claude CLI preparation with fixed restrictions.

This development checkpoint changes no schema/dependencies. Build/install validation
is recorded separately; real-client execution, automatic durable recovery and
formal release acceptance remain unverified or blocked.

## 0.3.0a13 — development compatibility repair

Replace timestamp-based capture freshness with a private process-local creation
fence and explicit event-loop association. Fresh captures can share a timestamp
with their adapter run on coarse Windows clocks; preexisting or foreign-loop
captures remain rejected without taking ownership or stopping them. Public
timestamps, markers and cancellation limits remain unchanged. This development
alpha grants no authentication, real-client verification or release acceptance.

## 0.3.0a12 — development checkpoint

- Add a bounded standalone Cursor JSON parser and typed host-factory adapter.
- Add heterogeneous RunManager routing with bounded history and shared dispatch receipts.
- Add optional read-only capability advice using explicit requirements and self-reported declarations.
- Add an isolated Mock diamond workflow demo with bounded retries and attempt budgets.
- Add an unknown-aware UsageLedger separating protocol observations from simulations.
- Include developer acceptance/debug helpers in source distributions so packaged tests can find them.

This development alpha changes no schema or dependencies and is not a release,
tag or approval. Real clients, autonomous relay and formal acceptance remain
unverified or blocked; component checks do not satisfy those gates.

Add opt-in bounded private per-phase pytest evidence that survives a later test
termination, and owned migration-test child cleanup without changing test limits.

Bound cancellation of an accidentally never-started capture as unknown; preserve
uncertain adapter capacity and pending-start cleanup without claiming parent exit.

Add bounded Codex/Claude protocol projection and sanitized local inspectors, a
pure pinned readonly Codex plan, and shared typed host-factory lifecycle handling.
Default startup stays unsupported; unknown runs retain instance slots and parent
cancellation does not assert server cancellation or process-tree cleanup. Preserve
Codex public records and keep Claude session/result fields private. No credentials,
SDK/client launch, Core authorization or automatic apply was added. These local
checkpoints are not a release or M5/real-client acceptance; see the acceptance report.

## 0.3.0a11 — M5B3B2B candidate execution intent guard

Add owner-only prepare/get/abandon of a single non-executing candidate intent.
Fence ledger recovery while a prepared intent exists; require explicit terminal
abandonment before owner reservation interruption. Preserve prior proofs/history
and add schema12 tables only. No execution capability, token, worker, Docker,
renewal, task gate or apply. Frozen validation/Work review remain required;
formal Release BLOCKED.

## 0.3.0a10 — M5B3B2A one-shot owner reservation

Add owner-only candidate reservation, explicit terminal interruption and strict
claim/proof/recovery relations. Schema11 preserves original queued/cancelled
records and historical receipts. Reservation never starts a worker or execution;
no token, renewal, task gate, approval consumption or apply. Formal Release stays
BLOCKED; frozen local validation and independent Work acceptance are required.

## 0.3.0a9 — M5B3B1 durable candidate verification queue

Add a separate owner-only candidate queue with immutable checked input bindings,
historical idempotent receipts and version-fenced cancellation. Add schema10
tables without changing old snapshot verification semantics. No candidate
worker, lease, execution, task verification, approval consumption or apply.
Frozen local validation and independent Work acceptance remain required.

## 0.3.0a8 — M5B3B0 transaction-bound metadata capture

Extract a private owner-authenticated capture seam that reads the caller-owned
SQLite transaction without managing its lifetime. Preserve public capture and
existing export behavior. No candidate queue, schema change or execution gate.
Final validation and independent Work review remain required.

## 0.3.0a7 — M5B3A2 existing candidate input export

- Owner-only checked export of actual managed merge-candidate object content.
- Open existing storage without reconstruction; strict receipts/intents and pre/post Git identity checks.
- Reject bare and worktree Git redirects before Git, and verify applicable parent graph.
- Preserve bounded source/object rules; no jobs, execution, task completion, schema or apply changes.

## 0.3.0a6 — M5B3A1 candidate metadata binding

- Owner-only read-only capture of project-consistent candidate/worktree/snapshot/task records.
- Frozen metadata and canonical receipt fingerprints; strict stored JSON validation.
- No filesystem/Git validation, code execution, task gate, schema change or source apply.

## 0.3.0a5 — M5B2C explicit cleanup receipt

- Owner-only internal one-shot reconciliation for expired, acknowledged full-ID executions.
- Additive schema9 intent/receipt and fencing before any Docker side effect.
- Exact identity/image matching, removal acknowledgement and same-daemon absence observation.
- Cleanup observations never restore passed results or allow job reuse.
- No automatic recovery/retry, task acceptance, safe apply or real client relay; release blocked.

## 0.3.0a1 — M5A under development

- Default read-only membership and explicit project-owner role grants.
- Separate owner control plane and bounded, resource-pinned expiring approvals.
- Structured secret-free audit fields and authorization before cached responses.
- Security migration requires explicit write/review regrant for existing agents.
- No approved apply or arbitrary execution endpoint; final release remains blocked.


## 0.2.0a3 — M4B development checkpoint

- Independent managed Git object store and per-task worktrees; source checkout read-only.
- Real third-tree merge conflict detection, pinned commits and NUL-safe path reports.
- Immutable merge candidates await human approval; no user-branch apply endpoint.
- Schema v5, 29 shared-Core operations, source-config command-execution guards and
  interrupted side-effect replay bindings. Formal release remains blocked.


## 0.2.0a2 — M4-01/02 under verification

- Project-confined resource metadata and SHA-256 file version checks.
- Cooperative exclusive file/directory leases with versioned renewal/release and replay checks.
- Global physical-path conflicts prevent duplicate project registrations bypassing a lease.
- Schema v4 root identity and lock history; worktrees/Git conflict reports remain the next checkpoint.

## 0.2.0a1 — M3 under verification

- Project-scoped context revisions, source/summary metadata and literal substring search.
- Structured, version-pinned handoffs with explicit recipient decisions and sender withdrawal.
- Immediate lease invalidation on submission; identity-reserved next claims after resolution.
- SQLite schema v3 preserves M0-M2 data and review history. All transports use the same Core.
- This checkpoint covers M3; M4 file/worktree conflict protection remains planned.

## 0.1.0a2 — unreleased

- Added complete inference-free two-native-session collaboration and host restart probes.
- Added a safe native Codex MCP installer: no-overwrite checks, dry run, isolated Python
  prerequisite validation and registration readback. No GUI automation or paid model calls.
- Data-path inspection can avoid creating directories; existing Core behavior is unchanged.
- Desktop UI acceptance remains pending; a native host probe does not close it.

## 0.1.0a1 — unreleased

M0-M2 Alpha implementation under verification: local project/agent registration, transactional
task coordination, leases, versions, idempotency, separate review, persistence, MCP stdio,
Python SDK and authenticated loopback HTTP. Real desktop-client validation remains a distinct gate.
