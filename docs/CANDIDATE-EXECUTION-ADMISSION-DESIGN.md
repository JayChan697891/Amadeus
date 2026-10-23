# Candidate execution admission: proposal after the intent evidence gate

执行方：Codex。Refs #11, #7. Design only, not an implemented contract.
Based on PR25 product aac28a0f688962eca640b930e92eeaa608ff824f.
PR25 final package evidence and independent acceptance remain prerequisites.
No schema number, public API, execution support or release pass is reserved here.

## Problem and invariant

The current owner reservation and prepared intent contain integrity evidence,
not executable worker authority. A future executor must never allow
ledger-only abandon/recover to remove the fence for a process that may exist.
The dangerous interval starts before Docker create, including lost create
acknowledgements and process exits before full-ID persistence. Lease expiry
does not prove absence, and a passing candidate result does not restore expired
owner/task authority.

The existing PR25 `prepare_once` does a fresh export outside the writer,
same-connection metadata/binding checks and final read-only Git check, then
stores a non-executing intent. Do not start Docker from that method or treat its
historical receipt as an execution permit. Its prepared/abandoned historical
records must remain readable and byte-stable.

## Proposed next bounded scope

First implement and accept a durable admission/fence prerequisite with a
deliberately non-executing backend. A later, separately accepted change may
connect a real sandbox. The admission prerequisite must reject ledger recovery
after authority is committed even when no create was attempted. Closing that
state requires a dedicated lifecycle decision, not reusing old abandon.

| Phase | Required behavior | Acceptance evidence |
| --- | --- | --- |
| Fresh admission check | Owner, active claim, exact prepared intent revision/proof, current task/session authority, profile/image/content and sufficient execution plus cleanup budget | Real disposable Git/SQLite checks; stale owner/task/profile/Git/clock faults fail closed |
| Durable fence | Atomically CAS prepared into an execution-owned lifecycle or add a unique execution-fence row, and audit before external side effects | Two admissions yield one durable owner; rollback/exit injection leaves no partial fence |
| Post-fence recovery | Permanently reject old ledger-only abandon/recover for execution-owned intent, regardless of elapsed lease or absent full ID | Every old path rejects after restart and clock rollback/expiry |
| External create (later slice) | Dispatch only from a committed durable intent, with exact content/image pins and tested isolation | Actual authorized sandbox required; never a host fallback |
| Terminal lifecycle (later slice) | Dedicated stop/cleanup and authority decision; unresolved create remains blocked | Real lost-ack/hard-exit/late-object fixtures plus independent exact-ID cleanup evidence |

Choose the additive schema and API only in the implementation contract after
review. Reuse current snapshot executor/backend/reconciliation mechanisms where
their identity and authority assumptions actually match candidate input; do not
point a candidate job at the old base-snapshot execution path by convenience.

## Transaction and side-effect sequence

1. Authenticate before any object/Git/receipt lookup; resolve only stored IDs.
   Read the current claim/intent and exact trusted profile; reject expired,
   regressed/nonfinite clocks and inadequate remaining budget.
2. Export the exact candidate object outside a writer. Reauthenticate in one
   BEGIN IMMEDIATE, validate all job/claim/intent relations, recapture binding,
   compare raw canonical metadata/proof pins and recheck bounded Git state.
   Reject changed owner/session/task revisions, profiles, Git receipts or files.
3. Commit the unique execution fence and audit before Docker create or any
   worker side effect. No DB transaction remains open across create/wait/stop.
   A failed commit means no create. Once committed, old ledger recovery stays
   disabled even if the service exits before it calls Docker.
4. Later execution must use immutable exported input with read-only mount,
   owner-installed fixed verifier profile and pinned actual image. No caller
   command/source/path/case/receipt can grant authority. Revalidate execution
   authority before start and before accepting a result; passing output alone
   remains insufficient.
5. Persist full container ID, exact daemon identity and lifecycle observations.
   On uncertain create acknowledgement, keep unresolved state. Name/label
   correlation alone must not authorize removing an arbitrary object. Resolve
   unknown or late-created objects under a separately reviewed ownership and
   reconciliation protocol; the old known-ID cleanup seam does not solve it.

The final Git check cannot make filesystem and SQLite atomic against OS-level
ABA. State that trusted-host limitation explicitly; do not market a digest as
a cryptographic owner authorization or assume external writers obey file locks.

## Mandatory race and failure matrix for the future contract

| Scenario | Required outcome |
| --- | --- |
| admission vs abandon / old recovery | One transaction wins; an execution-owned intent can never subsequently use ledger-only paths |
| two admissions | One unique execution owner; the loser starts nothing |
| DB/audit failure before commit | No fence and zero external create/start calls |
| exit after fence commit before create | Fence survives reopen; old abandon/recover blocked |
| create succeeds, acknowledgement lost | Unresolved, no automatic replacement create or assumed absence |
| ID saved, exit before start / while running | Exact-ID lifecycle recovery only; no implicit success or requeue |
| revoke owner/task after export or before start | Start/acceptance denied according to the finalized authority contract |
| lease expires during passing run | Result cannot grant verified task completion; cleanup still required |
| profile/image/metadata/proof corruption | All readers and mutations reject; never repair damaged rows by executing |
| unavailable sandbox, image or daemon | unavailable/blocked; no ordinary-host candidate import/pytest/setup fallback |
| cleanup fails / daemon mismatch / late create | Preserve unresolved fence; no unsafe deletion or ledger clearance |
| old schema/history migration | Preserve B1/B2A/B2B proof/response bytes, states and timestamps; rollback/FK/future-schema tests |

Use existing disposable Git/SQLite fixtures and controlled fault injection for
the non-executing admission prerequisite. Mock side-effect counters prove only
ordering/non-dispatch, never real containment or real clients. Actual sandbox
cases must remain blocked/not_run until an authorized environment exists.

## Evidence and scope limits

Freeze product SHA/tree before running the existing collector in source, fresh
wheel and isolated sdist environments; retain Windows regression separately.
Reconcile complete JUnit cases, package origins/hashes and all Git module bytes;
save raw fence/authority/lifecycle evidence with sanitized credentials and
per-file hashes. Independent Work reads actual bytes before accepting a slice.
Previous 78 Docker observations are regression evidence for earlier paths,
not proof of new candidate execution. No automatic retry/scheduler, task gate,
approval consumption/apply, real adapter/relay, complete M9 or Release is
authorized as completed by this design. Formal Release remains BLOCKED.
