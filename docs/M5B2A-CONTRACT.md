# M5B2A: durable verification job and lease ledger

Status: implemented bounded ledger, awaiting final frozen-source validation and independent Work acceptance. This document does not establish an
implemented worker, a successful verification, completed M5, or release acceptance.
The implemented M5B1 Docker library remains a separate execution tier.

## Requirement mapping and boundary

This increment supports M5-04 independent evidence checks, M5-01 authorization,
M5-03 redacted audit and M5-05 security regression. It reuses M1-03 idempotency and
M1-04 lease principles, but introduces separate job leases. A task lease is never
a verification-worker credential.

Implement only durable job creation, project-scoped inspection, conditional
attempt claim/renewal, cancellation and fail-closed interruption records. Do not
start Docker, read candidate source, run a queue loop, retry crashed execution,
accept a task, consume an approval, or modify a source checkout in this increment.
Do not change the meaning of existing `review_task` evidence assertions.

There is deliberately no successful verification completion operation in M5B2A.
Job ledger tests and synthetic attempts cannot create `passed` evidence. The
public execution assessment is always `unverified` with
`execution_connected: false`. A running ledger attempt means ownership of a
record; it does not claim that a container or candidate process was started.

## Smallest input boundary

Start with one subject type: an existing project-scoped `repository_snapshots`
record and its exact captured `base_sha`. This is intentionally narrower than
arbitrary worktree or merge-candidate verification. Resolve the record from the
service database, verify project membership, and compare the supplied expected
commit with the stored receipt before insertion. Never accept a caller receipt,
repository path, branch/ref expression or raw candidate source.

The enqueue operation stores the snapshot ID, pinned commit and immutable profile
hash. Do not invent a tree, source or input-manifest hash: those will be established
by actual Git object export in the later execution integration. Existing snapshot
metadata is an input binding, not proof that the current objects were read or run.

For a minimal implementation, use a trusted owner library next to Core:

```text
VerificationJobs(core)
enqueue(project_id, admin_token, snapshot_id, expected_commit,
        profile: DockerProfile, request_id)
get(project_id, admin_token, job_id)
list(project_id, admin_token, limit, offset)
cancel(project_id, admin_token, job_id, expected_version, request_id)
recover_interrupted(project_id, admin_token, job_id, expected_version, request_id)
```

`DockerProfile` is supplied directly by the trusted owner application. Require
the exact existing validated immutable profile type; use its canonical SHA256.
Do not load profiles from an agent message, candidate file, environment variable,
job JSON or caller-selected path. No agent/MCP operation or generic HTTP dispatch
is added. Do not expose worker methods through `Core.execute`, `execute_owner`,
SDK passthrough, HTTP, MCP or the existing generic owner CLI.

The library is part of the trusted service, not an authentication boundary against
arbitrary Python code running with service authority. Owner-facing methods must
still authenticate the project admin token using the existing digest comparison
inside the same transaction as project-scoped lookup/mutation. Worker handles are
internal capabilities and must never contain an admin token or agent session.

Profile definitions and expected outputs are not persisted in this first ledger.
Only their binding hash is stored. After restart, no execution is possible merely
because a job contains that hash. A later trusted profile registry must resolve
and revalidate it before any executable worker is connected.

## Schema 7 proposal

Add a transactional incremental migration after schema 6. Preserve all existing
tables and records, including roles, approvals, reviews and audit events. New
tables start empty; do not fabricate historical verification results.

`verification_jobs`:

- UUID primary key, project foreign key, snapshot foreign key;
- canonical captured commit, fixed profile kind and profile SHA256;
- status, monotonically increasing version and attempt number;
- created/updated timestamps and current attempt ID, nullable before claim.

`verification_attempts`:

- UUID primary key, project ID, job ID and positive attempt number;
- unique `(job_id, attempt_number)`;
- lease token hash, lease deadline and created/updated timestamps;
- status and fixed reason code, without freeform diagnostic text.

`verification_requests`:

- `(project_id, operation, request_id)` primary key;
- canonical payload fingerprint and stable resource ID/response metadata;
- never raw tokens, profile cases, source, environment values or command text.

Use CHECK constraints for bounded versions/attempts and documented status values,
indexes for `(project_id, created_at, id)` and `(status, lease_expires_at)`, and
foreign keys for job/attempt ownership. Resolve every related object with project
ID as well as object ID. A globally unique UUID alone does not enforce isolation.
If using separate project/job foreign keys, explicitly check that both refer to
the same project inside each mutation transaction; composite keys are preferable.

Reuse the existing migration locking/rollback behavior. Accept schema 7 on
reopening; do not leave schema-version checks hardcoded to 6. Migration failure
must roll back both schema changes and `user_version`.

## State machine and lease fencing

Job states in this increment are `queued`, `running`, `cancel_requested`,
`cancelled` and `interrupted`. No `passed`, `verified` or automatic task-completion
state is supported. Attempts may be `running`, `cancel_requested`, `cancelled` or
`interrupted`. Bounded reason codes include `owner_cancelled`, `lease_expired`
and `service_interrupted`.

Internal trusted methods may claim a specific queued job, renew an attempt,
acknowledge cancellation, or interrupt an attempt. They are tested directly and
are not an external worker protocol. Return the opaque random lease token only
to the trusted claimant, persist its hash, and exclude it from public responses,
audit events and idempotency responses. Redact token values from exceptions.

Claim uses one short `BEGIN IMMEDIATE` transaction and a conditional update on
project, job ID, `queued` status and expected version. Increment job version and
attempt number and create the attempt atomically. Exactly one concurrent claimant
wins. Claiming an already-running job does not create another attempt.

Every renewal, acknowledgement or interruption from an attempt holder must match
project, job ID, current attempt ID/number, token hash, expected version and an
unexpired lease. Use constant-time token hash comparison. Each successful mutation
increments version. Reject stale/expired tokens before changing state. Owner
cancellation instead uses current owner authentication and expected version.

Queued cancellation goes directly to `cancelled`. Running cancellation enters
`cancel_requested`, invalidates renewal, and cannot be labelled cancelled merely
because a request was accepted. In the current non-executing ledger, the trusted
holder may acknowledge cancellation; future execution integration must require
confirmed container cleanup before that acknowledgement is allowed.

Lease expiry or explicit service interruption leaves an `interrupted` record and
invalidates the current token. Do not silently recycle it to queued, recreate a
lease, or retain a successful assessment. Automatic expiry scans, restart
reconciliation, retry and queue scheduling are later execution stages. Explicit
owner `recover_interrupted` records interruption of a running/cancel-requested
non-executing ledger, including an expired lease; it invalidates the token and
does not enqueue another attempt. Its replay returns current state. A later
retry must create a new attempt number and token rather than resurrecting an old
attempt. Normal holder mutations reject `now < attempt.updated_at` (and job
timestamp rollback); this is rollback detection, not unconditional support for
clock changes. Explicit owner interruption can recover that state while retaining
the maximum observed timestamp. No backward clock change can revive the old token.

All ledger operations are bounded database work. Do not call Git, Docker, network
services or candidate code inside any transaction. Existing Core task operations
must remain available while a synthetic attempt holds a live job lease.

## Idempotency, responses and audit

Authenticate and resolve the project before looking up cached responses. A reused
request ID with a different operation payload/profile hash must conflict. Include
normalized snapshot/commit/profile identity in enqueue fingerprints. Never include
the admin token in the fingerprint or durable response.

Enqueue replay resolves the original stable job ID and returns its current public
state with the original immutable input binding; it does not enqueue or claim
again. Cancellation replay must not restore an earlier running/queued state. Claim
and renewal need no request-ID caching in this increment: their explicit version
and attempt token already make repeated stale requests fail closed.

Public responses contain only IDs, canonical commit/profile hashes, status,
version/attempt counters, timestamps, safe reason codes and the explicit
unverified execution assessment. No token hash, worker capability, private receipt,
filesystem path, profile expectation, claimed test count or fabricated container
identity belongs in these responses.

Successful owner mutations and their whitelist-only audit events share one
transaction; an audit insertion failure rolls back the mutation and idempotency
record. Reuse authenticated-denial handling without logging raw input. Add a small
explicit audit operation allowlist for this library; never solve integration by
allowing arbitrary caller operation strings into audit records.

## Later Docker ownership integration

M5B2A does not assign a random container label and then pretend it can recover a
container it never created. When an executable worker is added, extend attempt
records to persist generated ownership nonce, exact container name, create intent,
full container ID, cleanup phase and cleanup confirmation before acknowledging
execution completion.

Database fencing prevents stale result writes; it cannot atomically cancel a
previously issued Docker create request. A missing inspect result is not sufficient
proof against a late create. Crash windows with uncertain cleanup must remain
blocked until a separately reviewed reconciliation protocol establishes ownership
and cleanup. No broad container-name/label deletion, automatic source application
or host-execution fallback is permitted.

## Required local test matrix

| Area | Required observations |
|---|---|
| Migration | Fresh DB and schema 6 upgrade reach 7; old records unchanged; failed migration rolls back; concurrent startup remains safe |
| Owner authority | Missing/wrong/cross-project admin credentials rejected before cached replay; agent/MCP/HTTP execution dispatch cannot reach worker methods |
| Input binding | Unknown/cross-project snapshot rejected; mismatched commit rejected; arbitrary receipt/path/ref/source/profile rejected; valid profile hash is pinned |
| Idempotency | Same enqueue returns one job; changed commit/snapshot/profile conflicts; cancel replay cannot resurrect state; tokens absent from durable caches |
| Concurrency | Two threads and independent processes race one claim; one attempt wins; conditional rowcount and versions checked |
| Fencing | Wrong/expired token, wrong project/attempt, stale version and superseded holder cannot renew or transition records |
| Cancellation | Queued cancel terminal; running cancel remains requested until holder acknowledgement; renewal and cancel race has one consistent winner |
| Persistence | Close/reopen retains job and attempt; interruption invalidates lease; no automatic retry, success, task review or approval consumption |
| Audit | Mutation plus audit atomicity; fixed metadata only; insertion failure rolls back; no credentials/profile values in errors or records |
| Non-execution | Replace Git/Docker/backend entrypoints with fail-on-call probes; every ledger operation completes without invoking them; assessment remains unverified |
| Isolation | Every job/attempt lookup requires matching project; malicious IDs cannot access or mutate another project |
| Packaging | Existing source/wheel/sdist tests continue locally with independent reports; no GitHub Actions run/debug/benchmark |

Synthetic state-machine tests must be labelled policy/ledger tests. Keep the real
M5B1 Docker evidence separately identifiable. Save local JUnit, logs, source/package
hashes and exact commit with the implementation checkpoint. M5B2A passing neither
upgrades a queued job into real verification nor satisfies the complete M5-04 gate.

## Explicit remaining scope

Durable profile registry; worktree/merge-candidate subject resolution; external
worker process and API; actual Git export and Docker wiring; heartbeat supervision;
crash-safe orphan cleanup; automatic retries/budgets; independently verified task
review; single-use approval consumption and source application all remain future
work. M6 real client adapters, autonomous relay and M9 release acceptance also remain
open. User authorization requires local debugging on D:; GitHub remains storage
only, with no Actions execution or debugging.
