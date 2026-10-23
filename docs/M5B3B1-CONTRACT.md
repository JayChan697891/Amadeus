# M5B3B1: durable candidate verification queue

Implementation contract, version 0.3.0a9 / schema 10. Bounded queue only, not a
worker or successful verification. Formal Release remains BLOCKED. This follows
M5B3B1-DESIGN and the independently accepted transaction-capture prerequisite.

## Seam and authority

`CandidateVerificationJobs(core)` in verification/candidate_jobs.py provides:

```text
enqueue(*, project_id, admin_token, candidate_id, expected_candidate_sha,
        profile: DockerProfile, request_id)
get(*, project_id, admin_token, job_id)
list(*, project_id, admin_token, limit=20, offset=0)
cancel(*, project_id, admin_token, job_id, expected_version, request_id)
```

Strict schemas reject unknown fields/coercion. IDs/request IDs are 1..200 Unicode
characters and at most 800 UTF-8 bytes; admin token 1..4096 UTF-8 bytes. Invalid
Unicode is rejected without echoing input. Expected commit is exactly 40 or 64
hex characters, normalized lowercase. Page size 1..100, offset 0..10000, expected
version 1..2**63-3. Owner authentication precedes object/replay/storage access.
The exact immutable DockerProfile type is supplied by trusted owner code; cases
and commands cannot come from candidate messages or serialized job content.
Reject invalid profile properties safely without echoing input. Profile kind is
1..200 characters/800 UTF-8 bytes, SHA256 64 lowercase hex, image fixed sha256:
plus 64 lowercase hex. No CLI/HTTP/MCP/SDK/Core dispatch operation is added.

No caller-supplied input, binding, receipt, path, source or test result is accepted.
This is an internal service library and does not isolate hostile in-process Python
code. No Docker invocation, worker loop, claim, lease, retry, task review, approval
or apply capability is added. Old snapshot jobs/executor/reconciliation retain
their original behavior and cannot claim rows in the candidate queue.

## Enqueue and transaction sequence

1. Validate parameters; short BEGIN authenticates owner before request lookup.
   Fingerprint schema/operation/candidate ID/expected SHA/profile kind/hash/image.
   Do not include exported mutable task versions in this request fingerprint.
2. Matching committed request returns its exact original bounded historical
   receipt without Git/export/reconstruction or new successful-mutation audit.
   Different fingerprint under the same project/operation/request key conflicts.
3. For a new request, finish that transaction and call OwnerCandidateExporter.
   No long Git/object read occurs inside a write transaction. No dataclass/digest
   supplied by the API caller substitutes for a fresh exporter invocation.
4. BEGIN IMMEDIATE; reauthenticate, recheck request for a concurrent winner,
   then call OwnerCandidateBindings._capture_in_transaction on THIS connection.
   Compare complete binding equality with the exported binding; reject changed
   task versions/owner/creators/receipts/relations. Git/FS is not atomically bound
   to SQLite commit: this row records an export observation, not future freshness.
5. Insert queue row, request receipt and redacted successful audit atomically.
   Rollback any partial mutation on error. Existing separately recorded redacted
   denial audit is allowed. All clocks must be finite. New enqueue has no prior
   clock anchor and cannot detect every backwards jump. Cancel rejects now less
   than that job's updated_at. Use exact version fencing for cancellation.

Concurrent matching requests return the first committed receipt; changing
payload conflicts. A restart preserves data but provides neither resolved profile
definitions nor an executable input cache. Future executors must freshly export,
compare full pinned content/binding/profile and establish their own durable fence.
No missing Git object/receipt is reconstructed. Trusted service FS / OS-level ABA
limitations of A2 remain unchanged.

## Schema 10 and integrity

Only add candidate_verification_jobs, candidate_verification_requests and required
indexes through the existing incremental transaction/migration lock. Preserve
v9 rows and table shapes. Add UNIQUE(id,project_id) indexes to candidate, snapshot,
worktree and task source tables as needed for composite foreign keys; no column
is added to old verification tables with positional INSERT statements.

Queue columns pin IDs/project/candidate/snapshot/left-right worktrees and tasks,
full candidate/base/left/right SHAs and task versions, binding/provenance hashes,
commit tree/input/source digests, immutable profile kind/hash/image, full bounded
metadata envelope plus its digest, state/version/created/updated. Metadata schema
is agentsync.candidate-job-input.v1 and includes exact canonical binding fields,
four receipts and creator IDs, manifest and input provenance. Preserve all data
needed for a later exact comparison. Never store source bytes, credentials,
profile cases, command text or raw Docker results. Digests are integrity checks,
not signatures or permission. Stored references do not preserve lost Git objects.
The new envelope also pins verification_profile={kind,sha256,image_id}; its full
metadata digest covers all three, and every row read cross-checks profile columns
against that envelope. A valid-looking profile column changed alone is corruption.
This new queue binding does not alter the accepted A2 input-provenance format.

Canonical metadata UTF-8 <=4 MiB; each receipt <=64 KiB with strict existing parser;
manifest <=256 unique paths sorted by UTF-8 bytes, each path <=4096 UTF-8 bytes,
safe relative regular-file names using the accepted exporter policy; sizes must
be nonnegative strict integers, total <=4 MiB and solution.py <=128 KiB. Root
solution.py exists exactly once. SHA fields have exact full hex formats. Metadata
JSON nesting <=32, rejects duplicates, nonfinite numbers, invalid Unicode, unknown
fields and type coercion. Validate bounds before decode/insert. Recompute metadata,
binding, input and input-provenance digests and cross-check against columns; do not
silently truncate or reconstruct. Read/get/list/replay fail closed on malformed or
inconsistent stored data without echoing content or invoking Git. These checks
detect ordinary corruption but do not defend against an administrator rewriting
both data and digests consistently.

Strict envelope/response unknown-field/depth rules are new queue restrictions;
embedded receipts retain existing strict parsing and complete canonical content.
Reuse each existing fingerprint's exact byte format: input_sha256 uses the
snapshot exporter's ensure_ascii=True representation, while binding/provenance
retain their existing schema encodings. No Git/source is reread by get/list:
digest recomputation establishes stored consistency, not current object validity.
List pages IDs first, then validates/project one bounded row at a time; never
fetchall a page of full 4 MiB metadata envelopes.

Queue constraints: fixed source_kind=managed_merge_candidate_input;
status queued or cancelled only; initial version1; bounded monotonic version;
finite timestamps; UNIQUE(id,project_id). Composite foreign keys enforce project
ownership of candidate/snapshot/worktree/task. Relationship checks also occur in
the final authenticated transaction, including left/right snapshot/task relations.
Do not insert historical queue rows during migration. Fresh/v9/reopen/failure
rollback/unsupported-future-version and foreign_key_check must be exercised.

Request table key(project_id,operation,request_id), operation enqueue/cancel;
fingerprint, job_id with composite FK, exact original safe response JSON/digest.
Response UTF-8 <=16 KiB, strict fixed shape/schema/types and digest check before
replay. Response and queue identities must agree; never replace a historic receipt
with current get state. A cancelled queue may still replay its original enqueue.
Compare historical response with immutable IDs/hashes and the operation's original
status/version relation, never require historical status/version to equal current
state. Reject corruption of either stored row or receipt without repairing it.

## Safe results, cancellation and audits

Safe projection: job/project/candidate/snapshot IDs, pinned candidate/tree/input/
source/profile/provenance hashes and profile kind/image, status/version/timestamps,
source_kind, execution_connected=false, execution_assessment=unverified.
Never project raw receipts, paths, creator/session IDs, cases or credentials.
get/list have current_state=true. Mutation receipt is explicitly historical with
receipt_kind=historical_enqueue|historical_cancel and current_state=false; original
and replay forms are equal, without a dynamic replay flag. Historical queued
receipt does not assert current queue state or executable/fresh input.

Cancel: authenticate, replay check, project lookup, expected version/clock check,
queued->cancelled/version+1, receipt+audit in one transaction. Already cancelled
under a different request is invalid_state; exact original request can replay.
All reads/cancels/replays are DB-only. Enqueue mutation audit and cancel audit use
new allowlisted candidate_verification_enqueue/cancel names. Do not register
these audit names as callable transport operations. Existing audit redaction
policy applies, with successful mutation audit exactly with its transaction.

## Required local acceptance

Use real disposable Git/SQLite records. Confirm literal candidate bytes differ
from baseline and recompute saved queue digests. Test wrong owner/foreign IDs
before Git, malformed requests/profiles, bounded/duplicate/nonfinite JSON,
tampered stored columns/envelope/replay, original replay after cancellation and
missing Git storage, owner rotation, stale task/owner/receipt changes injected
between export and insertion, concurrent same/different requests, version-fenced
cancel, persistence across reopen/process restart, transaction crash/rollback
without partial rows or successful audit, migration preserving real v9 populated
snapshot jobs/attempts/executions/reconciliation, unsupported future schema,
DB-only query paths and old executor rejection of candidate IDs. Race/crash
injection is explicitly labelled and never claimed as real autonomous clients.

Root inspects actual implementation/results. Freeze SHA/tree, run local Ruff,
format, mypy, full source/fresh wheel/isolated sdist suites, Windows regression
and existing isolated Docker regressions. Save logs/JUnit/builds/dependencies,
source/package origins/hashes and queue observations. Independent Work acceptance
is separate; formal 42 complete scenarios, real adapters/relay, verified task
completion, safe apply and M9 remain incomplete. Source F:/syuc, debug/cache/temp
D:/agentsync-debug. GitHub storage only, [skip ci], no Actions/paid calls/mainmerge.
