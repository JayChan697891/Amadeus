# M5B3B1: candidate verification queue design

Status: design only. No schema, operation, job, attempt or execution below exists
as a result of this document. M5B3A2 acceptance covers checked candidate input
export only. Formal Release remains BLOCKED.

## Problem and implementation boundary

`VerificationJobs.enqueue` currently binds `repository_snapshots.base_sha`.
`OwnerVerificationExecutor._claim` and `execute_once` explicitly resolve that
snapshot receipt and export the baseline. Substituting a merge candidate SHA in
that ledger would violate those invariants and could certify the wrong content.

The next bounded implementation should persist a distinct candidate queue entry
using the accepted `OwnerCandidateExporter`, without connecting execution. Do not
alter existing snapshot jobs, attempts, executions or cleanup reconciliation.
No task submission/review gate, profile registry, worker loop, retry, lease,
approval consumption, safe apply or public transport is part of this slice.

Proposed trusted owner library (names remain a proposal):

```text
CandidateVerificationJobs(core)
enqueue(project_id, admin_token, candidate_id, expected_candidate_sha,
        profile: DockerProfile, request_id)
get(project_id, admin_token, job_id)
list(project_id, admin_token, limit, offset)
cancel(project_id, admin_token, job_id, expected_version, request_id)
```

Use existing strict ID/SHA/page/version validation and project owner auth. No
caller binding, receipt, path, source, command or result is accepted. `profile`
must be the exact trusted immutable DockerProfile type supplied by the owner
application. This in-process interface does not isolate hostile Python code
already running with service authority. Do not register it in Core dispatch,
HTTP, MCP, CLI or SDK passthrough.

## Transaction and replay boundaries

1. In a short authenticated DB read, check a project/operation/request replay.
   Authentication precedes replay lookup and disclosure. Replay fingerprint
   includes candidate ID, expected full SHA and exact profile kind/hash; it does
   not depend on mutable task versions discovered during a later export.
2. An already committed matching request returns its original safe enqueue
   receipt without invoking Git or reconstructing missing storage. Mark the
   response as a historical enqueue/cancel receipt, separate from get's current
   state: an enqueue replay after cancellation must not imply currently queued.
   Different
   payload under the same key is an idempotency conflict. This replay proves a
   historic enqueue only, never freshness or executability of its input.
3. For a new request, call OwnerCandidateExporter outside any write transaction.
   It must export actual checked Git objects; never accept a caller-constructed
   CandidateInput or trust an unkeyed digest as authorization.
4. Open BEGIN IMMEDIATE. Reauthenticate, recheck replay, and recompute the full
   metadata binding in THIS connection before insertion. Refactor an internal
   connection-bound helper from OwnerCandidateBindings.capture, preserving that
   public method's original semantics and all regressions. Calling capture on a
   separate connection before insertion does not establish this atomic boundary.
5. Compare the immutable exported binding with the in-transaction binding. A
   changed task version, owner, project relation, creator or receipt discards
   the export. Insert job, replay receipt and redacted audit in one transaction.
   A concurrent matching request returns the first committed resource; a
   different fingerprint conflicts. Crash/rollback cannot leave partial rows.

Git and SQLite do not share a transaction. A recorded input is an observation of
the accepted export, not a guarantee the files remain unchanged at DB commit or
after restart. Any later executor must freshly export, reauthenticate, compare
the complete pinned binding/content/profile, and fence its own durable claim.
The service filesystem is trusted; no OS-level filesystem ABA atomicity is
promised. No Git or long object reads belong inside BEGIN IMMEDIATE.

## Proposed additive schema 10

Add separate candidate queue/request tables through the existing migration lock
and rollback mechanism; do not rebuild the snapshot job tables or invent old
candidate records. Version 9 data and execution/reconciliation foreign keys stay
intact. Support fresh migration, upgrade, reopen and unsupported future rejection.

Candidate queue rows pin project/candidate/snapshot IDs, full candidate/base/
left/right SHAs, both worktree/task IDs and task versions, creator identities,
canonical metadata receipt/binding fingerprints, input provenance, tree/input/
source digests, bounded manifest, profile kind/hash/image ID, state/version and
timestamps. Store the exact
bounded canonical binding needed for later comparison, with a schema tag and
recomputed integrity digest; do not store source bytes, admin credentials,
profile cases, raw Docker responses or arbitrary diagnostic text. Proposed total
canonical input metadata limit is 4 MiB, retaining the exporter's 256-file and
4096-byte Git path limits and 64 KiB per receipt limit; measure serialized UTF-8
bytes before insertion/decoding and test both limit edges. Do not silently truncate.
The implementation contract must finalize these bounds before coding.
Digests detect accidental changes; they are not signatures or authority. Stored
references/digests do not preserve Git objects or source after storage loss. Read
operations never prepare, reconstruct or export missing content. Existing job
inserts include positional VALUES clauses; adding columns to their tables would
break that code and is expressly outside this additive-table design.

Use project-scoped lookup for every reference and enforce same-project relations
inside the final transaction. Prefer composite foreign keys where schema permits;
a globally unique ID plus unrelated project FK does not enforce this boundary.
Rows start queued/version1 and can only become cancelled in this slice; add
CHECK constraints and bounded monotonic versions. There is no passed/running/
verified state, attempt ID or lease token in this queue.

Request keys are unique on project/operation/request ID; pin stable fingerprint,
job ID and safe original response. All mutation audit/replay records commit with
the mutation. Cancel authenticates, checks expected version, records its own
idempotent response and never invokes Git, Docker or a future worker.

Owner projections expose only safe IDs, pinned hashes, queued/cancelled state,
version/timestamps and explicit source_kind=managed_merge_candidate_input,
execution_connected=false, execution_assessment=unverified. Never expose receipts,
filesystem paths, creator sessions, profile cases or credentials. A missing
profile definition after restart cannot be reconstructed from its hash, and no
worker may infer that one is available.

## Required evidence for the implementation

| Case | Method and expected evidence |
| --- | --- |
| Candidate differs from baseline | Real disposable Git/SQLite fixture; literal candidate bytes and manifest feed pinned digests; baseline digest differs |
| Authentication/project boundary | Wrong owner and foreign IDs rejected before Git/storage; project lookup and composite relations tested |
| Transaction race | Real second SQLite connection mutates task/owner/receipt between export and insertion; no job/request/successful-mutation audit survives rejection; existing redacted denial audit may remain |
| Replay and concurrent enqueue | Separate connections/processes with same request produce exactly one resource and stable receipt; changed fingerprint conflicts; no second Git export on committed replay |
| Restart after commit | Fresh Core/process reads the same queued binding, never starts a worker and never claims fresh source or verified execution |
| Crash/rollback before commit | Isolated child process/transaction injection leaves no partial job/request/audit; preserve failure reproduction |
| Cancel/version fencing | Exact version and request semantics; stale/foreign/replayed requests cannot change another row; no execution/task side effect |
| Schema migration | Real v9 fixture with jobs/attempts/executions/reconciliation, incremental v10, reopen, failure rollback and foreign_key_check; existing rows unchanged |
| Bounded/corrupt metadata | Oversize/invalid canonical data fails closed; no paths/secrets/source/profile cases in safe projections or audit |
| Regression isolation | All existing snapshot job/executor/cleanup tests retain original meaning; candidate rows cannot be claimed by those entry points |

Race/crash injection must be labelled as such. Never count it as a real client
or autonomous relay run. All destructive fixtures use temporary dedicated Git
repositories/databases under D: debug (or the owned local Linux VM).

For the implemented checkpoint, freeze source SHA/tree; run Ruff, format, mypy,
full source/fresh wheel/isolated sdist suites, Windows regression and existing
isolated Docker regressions. Save sanitized logs/JUnit/builds/package/source
identity and literal candidate queue observations. Root must inspect actual
files/results and Work must independently review. No test execution is needed
to claim that this document itself is a design; it claims no implementation pass.

## Later gates remain separate

After this queue is independently accepted, separately design candidate-aware
attempt/lease/execution/reconciliation, trusted profile resolution after restart,
fresh input/task binding at claim and result acceptance, then immutable task
submission and independent reviewer/version gates. Preserve the existing cleanup
identity and unverified failure semantics. Never connect the current baseline
executor by relabelling rows. Actual adapters/autonomous relay, safe apply,
cross-platform matrix and M9 remain unverified or incomplete.

Source/deliverables F:/syuc; runtime/cache/temp D:/agentsync-debug. GitHub storage
only with [skip ci]; no Actions, paid calls, main changes or merge.

## Design review checkpoint

Native independent peer read this design and the actual binding/jobs/executor/
database seams on 2026-10-21. Limited design review passed with no blocking item.
The review did not execute tests, implement the queue, or grant Work product
acceptance. Its clarifications are included above: same-connection recapture,
historical receipt versus current state, and successful mutation audit versus
permitted redacted denial audit. Before implementation, finalize strict field,
SHA/ID, canonical JSON/schema, total/per-field byte and replay-response bounds
in the implementation contract, with boundary test cases. Schema remains 9 and
version remains 0.3.0a7 at this design-only checkpoint.
