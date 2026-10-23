# M5B3B2A: one-shot owner reservation of checked candidate input

Version 0.3.0a10 / schema 11. Bounded non-executing reservation prerequisite.
No worker credential, renewal, worker callback, Docker, result submission,
task gate, approval consumption or apply. Formal Release remains BLOCKED.

## Owner seam

OwnerCandidateClaims(core), internal verification/candidate_claims.py:

```text
claim_once(*, project_id, admin_token, job_id, expected_version,
           profile: DockerProfile, lease_seconds=300)
get(*, project_id, admin_token, job_id)
recover_interrupted(*, project_id, admin_token, job_id, expected_version,
                    request_id)
```

Owner authentication precedes any object/Git read. Reuse B1 strict parameter,
profile, canonical metadata and safe projection policies. IDs/request IDs are
1..200 characters / <=800 UTF-8 bytes, admin <=4096 bytes, expected version a
strict bounded positive integer, lease_seconds strict integer1..3600. No caller
paths, binding, receipt, commands, source or results. No public transport dispatch.

One reservation per queue job forever in this slice. There is deliberately no
claim request replay or returned secret: repeat claim fails by state/version,
and an uncertain caller uses authenticated get. No unused worker token is
generated or persisted. Later worker authority requires a separate contract and
fresh content/profile/task checks; an owner reservation is not executable proof.

## Fresh claim transaction

1. Short authenticated read checks queued/version and absence of a claim, validates
   the complete B1 metadata row and exact immutable trusted profile kind/SHA/image.
2. Finish read transaction. Freshly call A2 exporter for the stored candidate ID
   and exact candidate SHA outside any write transaction. No substitution of base
   snapshot SHA, caller CandidateInput or unkeyed digest as authorization.
3. BEGIN IMMEDIATE; reauthenticate, recheck version/state/no existing claim and
   complete pinned profile/metadata equality; recompute B0 binding on this same
   connection and compare with fresh exported binding. Re-encode fresh input with
   the same B1 profile envelope; require exact equality with pinned metadata.
4. Atomically insert one reservation, change job queued1->claimed2 and successful
   redacted audit. Partial claim/job/audit mutation rolls back on error or process
   exit. Two claimers cannot create two rows or both acquire a reservation.

Finite service clock is required and now must be >=job.updated_at. Deadline must
be finite and strictly greater than now after adding lease_seconds (reject float
precision/overflow failures). This is an owner reservation interval, not an
execution budget; future execution must separately ensure sufficient lease time.

## State and recovery

Queue states in this slice are exactly queued1, cancelled2 (old queued cancel),
claimed2, interrupted3. Claim records have claimed/interrupted states. Existing
B1 get/list expose current claimed/interrupted states with execution_connected=false
and assessment=unverified, without claiming an actual worker/process started.
Their DB-only reads must validate claim/job/profile/metadata/timestamp relations.
Shared row validation is bidirectional: queued/cancelled must have no claim;
claimed/interrupted must have exactly one matching claim with all immutable pins
and timestamps consistent; interrupted must also have exactly one valid matching
recovery record. Apply this to B1 get/list/replay/cancel too, not just new get.
An expired claim remains recorded claimed until explicit owner recovery; get
reports lease_expired without writing or inventing cleanup. Core reopening does
not automatically interrupt an active reservation in another service process.
Only Claims.get adds reservation timing; B1 get/list keep their existing safe
field shape with expanded states. Claims.get returns job plus reservation=null
for queued/cancelled; otherwise its reservation summary contains id/kind/status/
reason_code/created_at/updated_at/lease_expires_at/proof_sha256 and timing flags.
If now is less than job/claim anchors, clock_regressed=true and lease_expired=null;
otherwise clock_regressed=false and lease_expired=(now>=deadline). Never present
an unknown backwards-clock interval as a confirmed valid reservation.

B1 cancel retains its original queued->cancelled semantics. A claimed job cannot
be cancelled by that queue method: reject safely and require owner recovery.
Historic enqueue receipt still replays original queued1/current_state=false after
claim or recovery; existing v10 cancel receipts stay byte-identical cancelled2.
Do not weaken replay to arbitrary older versions or change original receipt hashes.

Owner recover_interrupted is allowed for active or expired reservation-only claims,
with exact current job version. It records claimed2->interrupted3 and claim state,
an immutable historical recovery receipt and audit in one transaction. Timestamp
is max(finite now, job/claim anchors), so explicit recovery remains possible after
clock regression. Terminal interrupted never returns to queued, never renews,
resumes or permits another claim. Recovery request replay is authenticated and
DB-only, returns its exact original receipt for matching inputs, and conflicts on
different inputs. A different request cannot rewrite an already interrupted claim.

Recovery proves only a ledger reservation was interrupted. This slice never starts
execution and performs no container cleanup. Reservation kind is explicitly
owner_reservation_v1. Before any future real execution is connected, ledger-only
recovery/cancel operations MUST gain an execution-aware guard and dedicated cleanup
path; they must never interrupt a possibly running process by clearing DB authority.

## Schema and integrity

Transactional migration11 rebuilds only candidate jobs/requests as needed to extend
the candidate state CHECK, using explicit columns and new-table composite FKs.
Preserve all v10 job/request bytes, fingerprints, timestamps and original receipts.
No schema/table/behavior change to old snapshot jobs/attempts/execution/reconciliation.
Do not disable FK checks. Final foreign_key_check and rollback remain mandatory.

Add candidate_verification_claims and candidate_claim_recoveries. Claims have
UUID/project/job, one-per-job UNIQUE, fixed reservation kind, immutable pinned
metadata/profile/content identities, created time/deadline and canonical bounded
claim proof/digest, mutable state/reason/update anchors. Use composite ownership
FKs and strict state/version checks. Immutable proof includes IDs, claim version2,
metadata/profile identity, creation/deadline; changing a valid-looking deadline
or pin column alone must fail closed. Proofs are integrity checks, not signatures.
Recovery requests pin project/request ID, job/claim IDs, payload fingerprint,
exact historical response JSON/digest <=16 KiB, with composite foreign keys.
No source, credentials, cases, raw lease secrets or command text is stored.

The immutable claim proof is canonical agentsync.candidate-claim.v1 with exactly
schema/id/project_id/job_id/kind/claim_version/metadata_sha256/profile_kind/
profile_sha256/image_id/candidate_sha/tree_sha/input_sha256/source_sha256/
created_at/lease_expires_at; kind=owner_reservation_v1, claim_version=2.
Strict proof UTF-8 <=16 KiB; preserve immutable bytes/digest during recovery.
Mutable claim reason_code is initially empty, then exactly owner_interrupted;
never persist free-form reasons or infer container cleanup from this enum.

Owner responses are bounded <=16 KiB. Claims.get is current_state=true with
job's normal current projection and the summary above. Claim/recovery receipts
are fixed schema agentsync.candidate-claim-receipt.v1 or
agentsync.candidate-recovery.v1, receipt_kind=historical_claim|historical_recovery,
current_state=false, job and reservation summaries with all nested current_state
flags false and no dynamic clock/expiry flags. Recovery adds fixed reason_code
owner_interrupted. Every shape explicitly retains execution_connected=false and
execution_assessment=unverified; no unused worker credentials or authority fields.

Reuse bounded canonical parsing, duplicate/nonfinite/unknown/type rejection and
safe projections. Pure helper extraction is allowed to avoid copying the executor
or queue validation. B1 receipts/metadata byte formats remain unchanged. New
history/read shapes must be explicit and bounded; no digest grants authority or
OS-level filesystem ABA atomicity. Trusted service Python/database/FS required.

## Required acceptance

Real disposable Git/SQLite cases cover literal candidate/profile pinning, wrong
owner/project/profile/version before Git, stale task/receipt/content/owner between
export and claim, dirty candidate and unavailable storage, same-version concurrent
claims and queued-cancel race, restart/get/expiry boundaries without auto mutation,
explicit early/expired/clock-regressed recovery, conflicting recovery requests,
old enqueue replay after claim/recovery and unchanged v10 cancelled history,
crash/rollback without partial rows or success audit, single-column proof/deadline/
metadata corruption, no transport/executor access, no raw secrets in projections,
and migration11 populated-v10 preservation/reopen/failure rollback/FKs/future rejection.
Injected races/clocks/process exit are labelled; no real-client/relay claim.

Freeze SHA/tree; run local Ruff/format/mypy, full source/fresh wheel/isolated sdist,
Windows regression and old isolated Docker regressions. Preserve raw logs/JUnit,
build/origin/source/package identities, actual reservation/recovery observations
and reproduction scripts. Root inspection and independent Work acceptance are
required. Source F:/syuc; debug/cache/temp D:/agentsync-debug. GitHub storage only;
no Actions, paid calls, main changes or merge. M5/M9/42 formal scenarios remain open.
