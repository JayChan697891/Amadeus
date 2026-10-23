# M5B3B2B: candidate execution intent and ledger recovery fence

Version0.3.0a11/schema12. Owner-only non-executing prerequisite. No Docker,
worker credential, renew/callback, result submission, task gate or apply.
Formal Release BLOCKED. Original B2A reservation is not execution authority.

## Fixed public seam

Internal OwnerCandidateExecutionIntents(core) in verification/candidate_intents.py:

```text
prepare_once(*, project_id, admin_token, job_id, expected_version, profile:DockerProfile)
get(*, project_id, admin_token, job_id)
abandon_once(*, project_id, admin_token, job_id, intent_id, expected_revision, request_id)
```

Reuse B1 strict identifier/auth/integer/profile bounds. expected_version/revision
are strict bounded positive ints. No supplied paths, source, command, proof,
CandidateInput or result. No transport dispatch. One intent per job forever;
prepare has no request replay or secret, uncertain caller uses authenticated get.
All destructive/fault/concurrency tests only disposable Git/SQLite projects.

## Prepare

Short authenticated DB read validates the complete queued metadata, claimed2
reservation/proof and absence of intent. Exact trusted profile kind/hash/image
must match. Finite non-regressed now must be >=job/claim update anchors and
strictly before claim deadline; otherwise reject before Git.

End read txn, freshly A2 export the stored candidateID/exact candidate SHA outside
writer. BEGIN IMMEDIATE, reauthenticate and revalidate claimed2/version, same claim
ID/proof/deadline, absence of intent, full pinned metadata and profile equality.
B0 binding capture on that connection must equal export binding; B1 re-encoded
fresh input/profile must exactly equal queued metadata. Before insert, perform
one final existing A2 bounded read-only _check over managed receipts/intents,
repository/worktree identity, HEAD/clean status and parent relationships using
GitWorkspaceStore(create=False) and this binding. Actual object export remains
outside the writer; this final check starts no DB transaction, mutates no workspace
and executes no candidate code. Its bounded filesystem/Git exceptions must become
static candidate_input_invalid errors. Holding the writer across this final
read-only Git check is an explicit lock-duration tradeoff to reject observed
post-export dirtiness. Afterwards re-read finite non-regressed time and recheck
unexpired reservation, then atomically insert intent/audit. No job or claim
status/version/proof change. Two preparers cannot both create a row. A recovery
winning before writer makes prepare fail; a prepared intent winning makes old
recovery reject. No OS-level Git/filesystem ABA atomicity claim.

## State, abandon and recovery guard

Intent states exactly prepared/revision1/reason empty and
abandoned/revision2/reason owner_abandoned. kind owner_candidate_execution_intent_v1.
No recreation, requeue, resume or renewal. Intent created>=claim.created and
created<original claim deadline; prepared.updated=created. No silent transitions
on read, expiry or restart. Future execution must freshly revalidate content,
profile, owner/task authority and enough remaining execution/cleanup time.

Abandon is only prepared/revision1 -> abandoned/revision2, owner-authenticated,
CAS guarded and atomic with immutable historical request receipt/audit. It is a
ledger operation, never container cleanup. Allow explicit abandon after expiry
or backwards clock using max(finite now,job/claim/intent update/create anchors).
Immutable original intent proof bytes/digest never change. Same request replays
exact authenticated DB-only receipt for matching fingerprint, different input
conflicts; different request cannot rewrite terminal intent.

Old Claims.recover_interrupted, in its same BEGIN IMMEDIATE before mutations,
rejects any validated prepared intent with execution_intent_active. Only absent
or valid abandoned intent permits ledger recovery; corrupt/unknown states fail
closed. If abandoned, recovery timestamp also includes intent update anchor.
Original no-intent recovery behavior and historical receipts stay byte-identical.
Abandon/recover serialize: recovery seeing prepared rejects; recovery after
committed abandon may succeed. Abandon receipt remains exact after claim recovery.
B1 queued cancel remains unchanged; claimed cancellation still requires recovery.

BEFORE connecting any real execution, add atomic prepared -> create_intent
fencing and dedicated lifecycle/container cleanup. From that point ledger-only
abandon/recover must be permanently rejected, including after lease expiry or
crash. This slice implements no create_intent transition, execution capability,
process discovery or cleanup; prepared proof is not executable authorization.

## Immutable proof and schema12

Add only candidate_execution_intents and candidate_intent_abandonments; no rebuild
or changed semantics of existing candidate/snapshot jobs/claims/executions.
Explicit composite project/job/claim/intent FKs, unique job/claim intent and unique
intent abandonment, transactional migration/FK check/rollback. Preserve every
existing schema11 record, proof, historical response/hash and timestamp byte.

Proof canonical agentsync.candidate-execution-intent.v1, exactly:
schema,id,project_id,job_id,claim_id,kind,claim_version,claim_proof_sha256,
metadata_sha256,profile_kind,profile_sha256,image_id,candidate_sha,tree_sha,
input_sha256,source_sha256,created_at,claim_lease_expires_at.
kind fixed above, claim_version strict integer2. Strict canonical UTF-8 <=16KiB,
duplicate/nonfinite/deep/unknown/type rejection; SHA256 raw canonical proof.
Proof binds immutable IDs/pins/claim proof/deadline/creation. Mutable status,
reason,revision,updated_at are validated separately. No credentials/cases/source/
argv or free-form reason in storage/response/audit.

Abandon request pins project/request/job/intent IDs and payload fingerprint
canonical agentsync.candidate-intent-abandon-request.v1 with exactly schema,
project_id,job_id,intent_id,expected_revision (original1), plus bounded <=16KiB
original canonical response JSON/SHA256. Audit names candidate_intent_prepare /
candidate_intent_abandon only; audit allowlist is not transport capability.

Shared pure validate_intent(db, validated_job, validated_claim_or_none), lazy-called
by validate_claim after its existing validation, must not recursively call _row.
Validate bidirectionally on B1 get/list/enqueue replay/cancel, B2A reads/recovery
and new API too: absent claim -> no intent/abandon row; claimed allows prepared
or abandoned; interrupted requires absent or abandoned. Immutable proof/columns/
job/claim pins and timestamps must agree. Prepared -> no abandonment; abandoned
-> exactly one matching bounded canonical receipt/fingerprint/digest. After claim
recovery job/claim update time >=intent.updated. Corruption rejects every read/
mutation; do not mutate a damaged ledger to make it valid. Canonical historical
response equality must compare encoded bytes, not Python dict equality (which
would equate2.0 with integer2). A final filesystem check still cannot guarantee
OS-level atomicity between its return and SQLite commit; do not claim otherwise.

## Safe projections and immutable receipts

Reuse existing safe projections and leave their field formats unchanged.
New get shape current_state=true, execution_connected=false,
execution_assessment=unverified, job:existing current job projection, intent:null
or safe summary. No raw metadata/proof JSON. Summary contains immutable proof
IDs/pins/kind/claim_version/claim deadline/proof hash/created plus status/revision/
reason_code/updated_at, flags current_state and execution flags. Current summary
also has clock_regressed and lease_expired: if now<max(job/claim/intent anchors),
clock_regressed=true,lease_expired=null; else false and now>=original deadline.
Reads never imply a running worker or execution readiness.

Prepare/abandon receipt shapes schema agentsync.candidate-intent-receipt.v1,
receipt_kind historical_prepare|historical_abandon, current_state=false,
execution_connected=false,execution_assessment=unverified,intent:static safe
summary with nested current_state=false and no clock/expiry flags. No nested job
state that could rewrite history after recovery. All API responses <=16KiB.
Abandon receipt adds fixed reason_code owner_abandoned. get is DB-only; abandon
and historical replay are DB-only even if managed Git storage is unavailable.

## Required acceptance and evidence

Real disposable Git/SQLite public seam tests: actual candidate distinct from base;
wrong owner/project/version/profile before Git; stale task/owner/receipt/content
between export/writer; expired/regressed/nonfinite clock; prepare concurrency and
prepare/recover/abandon ordering; restart/read without mutation; irreversible
abandon and request conflict; old enqueue/recovery/claim histories; missing/dirty
Git; audit SQL failure and subprocess exit before commit; proof/pins/deadline/
status/revision/abandon receipt corruptions across public readers. Controlled
faults/races/clocks are labelled. No mock result becomes real execution evidence.
Root migration tests build true schema11 DDL with populated queued/cancelled/
claimed/interrupted and old history, verify upgrade/reopen/failure/FK/future.

Save two actual observations per Linux environment (prepared and abandoned then
claim recovered): raw job/claim/intent/abandon rows, original proof and receipts,
current owner views, literal candidate source hash, explicit execution/real-client/
cleanup/worker-credential flags false. AGENTSYNC_CANDIDATE_INTENT_EVIDENCE_DIR,
subdirectory sha256(sys.prefix)[:16]. Preserve safe raw evidence and logs/JUnit.

Freeze SHA/tree; root independently run Ruff/format/mypy and full Linux source,
fresh wheel/isolated sdist, Windows regression and OLD78 Docker observations with
exact-ID absence. Verify all modules/source/package bytes, raw records and hashes;
archive sanitized evidence. Independent Work acceptance separate and required.
No Actions/paid/main edits/merge. F:source/D:debug/cache/VM/temp. Keep42 formal
scenarios/M5/M9/real-client relay gate open and formal Release BLOCKED.
