# M3 implementation contract

Authorized continuation after Work accepted PR #3. Current work: M3-01..04,
Issue #4, branch feature/m3-context-handoffs. Earlier M0-M2-only AGENTS.md
instructions were explicitly revoked by the user. No paid calls or main merges.
All operations use existing Core authentication, transaction and idempotency.

## API additions

All requests inherit Auth (project_id, session_id, session_token). Write requests
require request_id. Use strict models and bounds; version integers fit SQLite.

- publish_context: kind=requirement|decision|constraint|progress|note, title (1..1000),
  content (1..65536), summary="" (<=4000), source="" (<=4000), context_id=null,
  expected_version=0. New IDs are generated at creation, only version 0 allowed;
  updates need an existing project-scoped ID and its exact positive current version.
  Return the context revision dictionary directly. Retain immutable revision history
  including author agent/session IDs, source, summary, timestamps and version.
- get_context: context_id, version=null (latest or an exact positive historical revision).
  Return a revision dictionary directly, with id/context_id and project_id/version.
- search_context: query (1..500; nonblank), kind=null, limit=20 (1..100), offset=0
  (0..10000). Return {entries: [latest revisions only], has_more: bool}.
  SQLite FTS5 trigram handles >=3-character literal substring searches; 1-2-character
  queries use bounded, escaped/parameterized substring matching for Chinese short
  words. No caller-controlled FTS syntax or raw SQL. Scope and kind filters apply
  before pagination and on both paths. Search title, content, summary and source.
- submit_handoff: task_id, lease_token, expected_version, target_agent_id, package,
  request_id. Package: summary (1..2000), completed_work="" (<=20000),
  changed_files=[] (bounded metadata-only strings), open_questions=[], evidence=[],
  context_refs=[] of {context_id, version}. Validate all references belong to this
  project and exist at the explicit revision. Persist a stable package and context
  snapshots; never read/execute mentioned paths, source locators or commands.
- get_handoff: handoff_id. Authenticated project members may read. Return a direct
  handoff dictionary with id, project/task/sender/recipient IDs, package, fixed
  contexts, status, reason, creation/resolution timestamps and task_version.
- resolve_handoff: handoff_id, expected_version (task version), accept:bool,
  reason="" (<=2000; nonblank required for reject), request_id. Only the target
  agent identity (not merely arbitrary project session) can resolve pending handoffs.
- withdraw_handoff: handoff_id, expected_version, reason (1..2000), request_id.
  Only the submitting agent identity can withdraw a pending handoff.

## Handoff state and ownership

Submit requires an active task lease owned by the submitting session and task state
claimed/running/blocked; recipient must be a different same-project enrolled agent.
In one transaction invalidate the old lease, clear owner, increment task version,
set task status=handoff and create a pending handoff. No task writes/claims/renewals
can reuse the sender lease. Accept, reject and withdraw all atomically increment task
version and return it to pending. Accept reserves its next claim for recipient agent;
reject/withdraw reserve it for sender agent. Normal claim_task then issues a fresh
lease through its unchanged idempotency path. Reservations are identity-based and
expire on the successful claim's version change (including later lease expiry), or
after at most 300 seconds, capped at the assigned identity's currently valid session
expiry. If the returning sender has no valid session, no reservation blocks recovery.
After expiry any authenticated project member can claim the still-pending task.
Expose assigned_agent_id and assignment_expires_at on public tasks where a current
unexpired version-scoped reservation exists. Preserve the deadline in handoff history.
A version-scoped reservation from the immutable handoff record is acceptable and
avoids modifying historical task inserts. No extra lease token is returned by M3 calls.

Reject/withdraw -> sender reclaims -> sender submits to another recipient implements
reassignment without a new scheduler. Preserve old packages and decisions; never
rewrite an earlier handoff. Concurrent resolve/withdraw yields one winner. Use current
task version plus pending state checks; completed/old handoffs cannot affect new work.
Replays authenticate, return stored responses and do not mutate or revive old ownership.

## Owner recovery of abandoned handoffs

The owner SDK and existing authenticated `/owner/v1/{operation}` HTTP route expose:

- `list_handoffs`: owner credentials, optional `task_id`, `status` (defaults to
  `pending`; null selects all decisions), and the normal bounded limit/offset.
  It returns project-scoped identifiers, status, version and participant metadata
  without expanding packages or context bodies. Recovery does not depend on
  retaining either expired participant's credentials.
- `recover_handoff`: owner credentials, exact `task_id`, `handoff_id`,
  `expected_version` (both current task version and the handoff's task version),
  nonblank `reason`, and `request_id`.

Recovery requires a still-pending handoff and no unexpired session for either
participant identity. It rejects durable-workflow tasks. The owner transaction
records `recovered`, clears ownership/lease/reservation, and returns the task to
pending with a new version. It preserves the original package, context revisions,
sender/recipient identities and task result. Any newly authorized worker must
claim through the normal capability-independent Core lease/permission checks;
the operation neither impersonates the old sender nor grants an execution approval.
An exact request replay returns its historical receipt without changing later
task state. Audits record owner identity and task versions, without copying the
reason or package into audit text.

This is metadata recovery only. It does not prove an external process ended,
restart a model, clear receipt/intent fences, modify worktrees or accept results.
The new implementation and regression source are authored; execution remains
NOT RUN during the owner's code-first pass.

## Schema and transports

Transactional schema v3 upgrades empty/v1/v2 databases and rejects future versions.
FTS and revision inserts are atomic. Existing review history and tasks are preserved.
Expose all seven additions as explicit typed MCP tools (18 tools total); HTTP/SDK
continue dispatching through Core. No business logic in transport wrappers.

## Required evidence

Tests: historical context immutability, version races/idempotency, FTS latest-only,
Chinese short words/literal punctuation, project isolation, pinned snapshots,
expired/wrong/same-agent leases, receiver identity, stale resolve, rejected/withdrawn
reassignment, one winner under races, v1/v2 migration/reopen. Real separate MCP client
processes A/B share one DB, A publishes/submits, B reads the pinned revision, accepts,
claims and continues; an independent reviewer completes it. This is protocol/process
evidence, not proof of desktop host or model-driven compatibility. Full pytest/lint/
format/types/build and nine-job Actions before Work handoff. Keep all old tests.
