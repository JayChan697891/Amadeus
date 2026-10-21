# M5B2B: trusted owner single execution of a durable snapshot job

Status: implementation checkpoint awaiting final frozen-source validation and independent acceptance. The preceding M5B2A checkpoint passed independent Work review in PR17 comment6304849673. This increment connects
one queued snapshot job to real Git export and the existing M5B1 Docker verifier.
It does not introduce a scheduler, automatic retry, approval consumption, source
application, model relay, task completion or release acceptance.

## Requirements and trust boundary

This increment advances M5-04 and adds regression coverage for M5-01, M5-03 and
M5-05. A passing result means only that the pinned standalone `solution.py` passed
the fixed owner's finite black-box cases in the supported Docker environment. It
does not establish correctness of arbitrary projects or satisfy the full M5 gate.

Owner authority, the in-process executor, verifier/comparator, Docker daemon, image
and host kernel remain trusted. Candidate source, repository files, output and
self-declared reports remain untrusted. There is no host-execution fallback.

Keep the M5B2A input scope: a project-owned `repository_snapshots` record and its
captured `base_sha`. Worktree and merge-candidate receipt resolution are future
scope. The owner supplies the exact validated immutable `DockerProfile` directly;
its kind and canonical SHA256 must match the queued job. No persisted profile
registry is required for this single call, but no profile is reconstructed from
candidate content, environment, a request dictionary or an agent message.

## Internal owner library

Suggested callable surface, separate from generic operation dispatch:

```text
OwnerVerificationExecutor(core).execute_once(
    project_id, admin_token, job_id, expected_version, profile: DockerProfile
)
OwnerVerificationExecutor(core).get(project_id, admin_token, job_id)
OwnerVerificationExecutor(core).cancel(
    project_id, admin_token, job_id, expected_version, request_id
)
```

Do not register execution, cancellation or worker completion in Core's agent or
owner operation maps, HTTP, MCP, SDK passthrough or the generic owner CLI. The
library is trusted service code, not a defense against arbitrary Python running
with service authority. Nevertheless authenticate the owner before accessing
cached execution/job state and resolve every object by project as well as ID.

There is no public or owner-facing `finish(result)` method. The executor obtains
the real backend's structured result and submits it through a private capability
bound to the current attempt. Submitted JUnit, freeform dictionaries and model
assertions cannot create a successful result.

## Schema 8: preserve the ledger and add execution state

The schema 7 job/attempt CHECK constraints cannot represent normal execution
completion. Do not leave a completed executable attempt permanently `running`, or
write `interrupted`/`cancelled` to mean that an ordinary execution finished.

In one migration transaction, rebuild `verification_jobs`,
`verification_attempts` and `verification_requests` using explicit known schemas
and column lists. Preserve every existing row and field, primary/composite keys,
foreign keys and indexes, including active and terminal historical attempts,
token hashes, lease deadlines, timestamps and idempotency bindings. Extend:

- job status with neutral `finished` and `cleanup_pending`;
- attempt status with neutral `finished` and `cleanup_pending`;
- attempt reason codes with `executor_finished` and an explicitly documented
  cleanup-uncertainty code; keep all existing reason codes valid.

Retain genuine `cancelled` for a cancellation that won and whose cleanup is
confirmed. A failed test also finishes neutrally; its specific outcome belongs in
the execution overlay. Ledger-only records keep their original interpretation.

Rebuild related tables in a foreign-key-safe order, preserving IDs without
`INSERT OR REPLACE` deletion semantics. Do not use `PRAGMA writable_schema`, change
stored schema SQL text, or silently disable foreign-key validation. Deferrable
constraints or a reviewed rename/copy/drop order may be used; check the resulting
foreign keys and run `foreign_key_check` before committing `user_version=8`.
Failure at any step rolls back schema, data and version together. Reopening schema
8 is supported and future unknown versions still fail closed.

Add `verification_executions` with one execution per claimed attempt and project
consistent relationships to job and attempt. Store at least:

- execution ID, project/job/attempt IDs and attempt number;
- original claim version, execution revision and explicit cancellation revision;
- bound snapshot/commit/profile/image identifiers and hashes;
- actual exported tree/source/input-manifest hashes once established;
- phase, assessment, fixed error codes and timestamps;
- generated ownership nonce, exact container name, nullable full container ID;
- create intent, whether the create response was complete, and cleanup state;
- a bounded whitelist-only structured result and its canonical SHA256;
- verifier source/version hashes needed to identify the executed implementation.

Do not persist admin/lease tokens, raw source, case expectations, arbitrary daemon
configuration or candidate stdout/stderr. Store token hashes only in the attempt
ledger. A result digest is integrity metadata, not proof of trusted provenance by
itself. The private executor transition establishes provenance.

Suggested phases are `preparing`, `create_intent`, `created`, `executing`,
`finished`, `cleanup_pending`. Assessment is separate: `unverified`, `passed`,
`failed`, `unsupported`, `error`, `cancelled`. A cleanup-pending assessment is
never passed. Normal backend failure with confirmed cleanup can finish as failed
or error; uncertainty remains pending and blocks reuse.

## Atomic claim, Git export and input binding

The initial short transaction must authenticate the owner, validate the trusted
profile hash, resolve the snapshot/job, check queued state and expected version,
claim the job, create its attempt and insert the execution overlay atomically.
Generate the opaque worker token and container ownership identity within trusted
code. Commit before doing Git or Docker work. Do not call the existing standalone
ledger `claim` followed by a separate overlay insertion: old ledger operations
could otherwise mutate the attempt between those two transactions.

After claiming, resolve only the stored service receipt and call the existing
bounded Git object exporter outside the transaction. Verify that its commit is
the pinned job/snapshot commit. Bind its actual tree, source and manifest/input
hashes to the execution. Never read executable bytes from a mutable checkout,
caller path, branch name, receipt dictionary or task description.

Inspect profile identity again at the execution boundary. An absent/mismatched
profile or invalid snapshot must not reach Docker create. Git export failure is
recorded with a fixed safe error; do not invent missing hashes or a successful
test count. Expected values remain in the trusted host comparator.

## Minimal private Docker lifecycle

Preserve M5B1 behavior and signature compatibility when no lifecycle object is
provided. Add only an internal trusted lifecycle/capability, inaccessible through
agent or owner request payloads. It may provide generated ownership identity and
fixed phase notifications; it cannot supply Docker flags, commands, mounts,
environment variables or candidate paths.

| Boundary | Required behavior |
|---|---|
| Before sending create | Check current attempt/token/version/lease/cancel; persist exact generated owner/name and create intent; commit before issuing Docker create |
| After complete create response | Validate and persist the full container ID before start; bind it to that execution's owner/name |
| Before start | Recheck attempt fencing, cancellation and sufficient remaining lease; failure forbids start and still cleans up a created container |
| After cleanup observation | Record exact observed identity and cleanup confirmation safely; persistence failure cannot turn an unknown outcome into success |
| Backend return | Submit the real bounded structured result through the private attempt capability, never a caller-provided completion body |

Put the after-create persistence callback inside the verifier's owned-container
cleanup `try/finally`. If callback persistence fails after creation, cleanup still
runs. Cleanup must run before reporting a callback error; a callback exception
must not bypass or replace the cleanup obligation. Failure to save cleanup
evidence leaves the durable execution pending even if the live process attempted
removal. Preserve safe error codes and do not expose raw callback exceptions.

The current create-response-loss recovery can inspect the exact name and remove
an observed matching full ID. Record that observation, but do not silently equate
an incomplete create response or one not-found observation with proof that a late
daemon create is impossible. Do not change the standalone verifier's proven
behavior accidentally while integrating the stricter durable execution boundary.

## Fencing and cancellation races

Each worker transition checks project, job ID, current attempt ID/number, constant
time token-hash equality, lease validity and the expected revision. Treat clock
rollback as unsupported progress requiring conservative interruption; do not
extend or revive a stale lease. No Git/Docker work occurs while holding a database
transaction. Lease duration and control deadlines must be bounded; an expired
lease cannot finish successfully merely because the candidate passed earlier.

Keep the worker's claimed/revised version explicitly in its private capability.
Do not reload the latest job version and thereby restore a stale worker's ability
to submit success. A new attempt, replaced token, owner recovery or unrelated
mutation invalidates the old capability.

Execution cancellation uses its own owner-authenticated conditional operation,
not the old ledger cancellation path. Persist a cancel flag/revision and audit
event atomically. The worker checks it before create/start and in the final result
transaction. Running cancellation may wait for the fixed candidate timeout and
cleanup; do not promise an immediate stop.

There is one narrowly permitted finalization exception to an expected-version
match: the same current attempt/token with an unexpired lease may acknowledge an
explicitly recorded cancellation-only revision change and transition to genuine
`cancelled` after confirmed cleanup. The finalizer must prove the intervening
change was that cancellation, using the saved prior version/cancel revision and
attempt binding. It must not generalize this exception to arbitrary newer
versions, takeover, recovery, expired tokens or successful completion.

If cancellation commits first, a candidate's passing backend result cannot become
passed execution assessment. If final completion commits first, a subsequent
cancellation reports a terminal conflict. Duplicate cancellation requests are
idempotent and cannot revive or replace the execution.

## Terminal result and unknown cleanup

Successful finalization requires all of the following in one short transaction:

- current attempt/token/version and valid lease;
- exact job/snapshot/commit/profile/image binding;
- matching actually exported tree/source/input hashes;
- a trusted backend result with execution started, all finite cases checked and
  passed, supported effective isolation and normal completion;
- no winning cancellation and confirmed exact-owned-container cleanup;
- atomic safe result persistence, neutral ledger completion and audit event.

Do not derive success from an exit code, result-file existence, hash alone or
candidate-generated report. Unsupported platform/preflight outcomes may finish
without candidate execution, but must have `execution_started=false`, explicitly
unsupported assessment and no fabricated input/process observations.

Lost ownership, lease expiry after create intent, process crash, partial create
reply, unknown container identity or unconfirmed cleanup produces
`cleanup_pending/unverified`, not normal completion. A worker may still try to
remove its exact owned container after losing success-writing authority. That
cleanup attempt does not restore permission to submit passed evidence.

This stage provides no automatic recovery/retry for those states. Preserve the
durable intent for later reviewed reconciliation. Do not call ledger
`recover_interrupted` to clear an executable attempt or label it cleaned. Do not
delete by broad label, prefix or name glob. Database fencing cannot atomically
cancel an already issued Docker daemon request, so exactly-once execution is not
claimed.

## Compatibility and safe inspection

All old ledger mutations, including claim/renew/cancel/acknowledge/interrupt/owner
recovery, must reject jobs with execution overlay records before modifying them.
This applies to finished/pending executions as well as currently running ones.
Cached mutation replay cannot bypass that guard. New execution control owns the
attached attempt for the remainder of this stage.

Old ledger `get`, `list` and enqueue replay must detect attached execution records.
Return a bounded safe execution summary or an explicit
`execution_control_required` indication; do not continue claiming
`execution_connected=false` for a job that has been connected. Do not expose case
expectations, raw result/daemon configuration, ownership nonce, token hash or
worker capability. Ledger-only historical jobs continue to report
`execution_connected=false` and `unverified` unchanged.

Linux-only execution remains explicit. On Windows/macOS or unavailable isolation,
do not start Docker or candidate code and never fall back to the host. A connected
executor is not itself proof that a candidate process ran; retain separate
`execution_started` and assessment fields in every safe summary.

## Local acceptance matrix

| Area | Required evidence |
|---|---|
| Migration | Schema 7 with real historical queued/running/cancel-requested/cancelled/interrupted records upgrades without changing original columns, tokens, versions, request bindings or FK/index semantics; injected mid-migration failure rolls back |
| Concurrency | Two owner executions of one queued job yield one attempt/overlay; overlay creation and claim are atomic; no double create |
| Boundary | Wrong owner/project/profile/snapshot/commit rejected before backend work; no execution/finish operation in public dispatch |
| Old API compatibility | Every old mutation and cached mutation replay rejects attached executions; get/list/enqueue replay show safe execution-aware state; ledger-only records preserve old responses |
| Real input | Actual managed Git commit/tree/manifest/source hashes match durable result; tampered objects and mismatched profile cannot pass |
| Lifecycle | Inject failures before intent, after committed intent, after create, during ID persistence, before start, during run, during cleanup and before final commit; known containers still cleaned when callbacks fail |
| Fencing | Wrong/expired token, stale version, replaced attempt and clock rollback cannot submit passed; reloading current state never grants success authority |
| Cancellation | Explicit cancellation-only revision can be acknowledged by the same live token after cleanup; unrelated revision/takeover cannot; cancel/finish race has one truthful terminal outcome |
| Unknown state | Partial/late create, lost process, identity mismatch and cleanup/persistence failure stay cleanup_pending; no implicit retry/recovery or false cleanup claim |
| Real Docker | Local Linux VM normal cases, wrong/forged output, time/output/memory/PID/scratch bounds and exact-ID cleanup; policy mocks are labelled separately |
| Unsupported | Non-Linux/missing daemon/image/required controls never execute candidate on host and remain unsupported/unverified |
| Audit/storage | Safe result plus audit commit atomically; audit/storage failure cannot leave passed state without evidence; credentials/cases/raw output excluded |
| Packaging | Source/wheel/sdist local suites save separate JUnit, logs, exact implementation/commit/package/image hashes and real execution observations |

All destructive fixtures use temporary projects and owned disposable containers.
Debugging environments and artifacts stay on D:; project sources remain under
F:\syuc. GitHub is upload/storage only. Do not run, rerun, dispatch or debug Actions.
Report tests as passed, failed, skipped, restricted or unverified accurately.

M5B2B success is a bounded implementation checkpoint. Independent task acceptance,
approved source application, real client adapters/relay and the M9 release gate
remain separate outstanding requirements.
