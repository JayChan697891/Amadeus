> Published archive: versions and checksummed files are in [releases/](releases/). See [RECOVERY.md](RECOVERY.md) and [PUBLICATION-MANIFEST.json](PUBLICATION-MANIFEST.json). Earlier no-publication statements in historical development reports describe the pre-publication checkpoint.

# AgentSync

Free, MIT-licensed local coordination for multiple agents. Python SDK, MCP stdio and HTTP API
share one SQLite task system. No paid model, API key, cloud server or GUI is needed.

Status: **0.3.0a2 M5B1 verifier foundation (under verification)**. M5A permissions,
approvals and audit passed their limited Work acceptance. M5B1 adds an owner-only
fixed JSON black-box verification library, with no host execution or host mounts.
It requires inspected Linux Docker; unavailable backends fail closed. The dedicated
real-container CI gate is separate from simulated policy tests. See the
[verifier scope](docs/M5B1-GUIDE.md). Verification queue/recovery, approval consumption,
source application and actual-client relay remain incomplete.

Project context has immutable revisions, source/summary
metadata and literal substring search. Structured handoffs pin context revisions,
invalidate the sender's lease and reserve a fresh claim for the designated recipient.
Reservations expire within 300 seconds so offline recipients cannot strand a task.
See [M3 contract](docs/M3-CONTRACT.md) and [progress](docs/PROGRESS.md),
[test evidence](docs/TEST-REPORT.md) and [compatibility](docs/COMPATIBILITY.md).
Protocol tests do not establish Codex/Claude/Cursor desktop compatibility.
The current desktop MCP connection was confirmed by the user; real native tool/collaboration
probes passed independently. See [M2 continuation](docs/M2-CONTINUATION.zh-CN.md).

## Windows quick start

From this repository directory, with Python 3.11+ installed:

```powershell
py -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev-lock.txt
& .\.venv\Scripts\python.exe -m pip install -e . --no-deps
& .\.venv\Scripts\python.exe -m agentsync --data-dir "$PWD\local-data\demo" demo
& .\.venv\Scripts\python.exe -m pytest
```

No activation or PowerShell execution-policy changes are needed. Demo uses two simulated agents,
rejects the second claim, submits a result, records separate review and checks persistence.
Use a dedicated empty data directory for repeatable demo runs.
For runtime-only installation use requirements-lock.txt instead of the development snapshot.
Both files are exact Windows-tested snapshots, not universal cross-platform resolver locks.

## Interfaces

- Python: `from agentsync.sdk.client import AgentSyncClient`; use `.call(operation, **payload)`.
- MCP: `python -m agentsync --data-dir ABSOLUTE_PATH mcp`.
- HTTP: set a private `AGENTSYNC_HTTP_TOKEN`, then `python -m agentsync serve`.
  Default bind is 127.0.0.1:8765. POST `/v1/{operation}` with bearer authorization and JSON.
- See `examples/`, [operation contract](docs/CONTRACT.md), and [Chinese guide](README.zh-CN.md).

Every MCP process must use the same absolute data directory. Defaults are independent of cwd.
Never put the live WAL database on a network share. Keep project admin/session tokens private.
Stdio MCP hosts have local process access; Alpha is not a hostile-agent sandbox.

## Read-only scheduling

Read-only scheduling helpers `agentsync.scheduling.plan_tasks` and
`agentsync.dispatch_planning.plan_dispatches` accept optional
`required_capabilities={task_id: ("python", "tests"), ...}`. An explicit mapping
must cover every task in the snapshot, including terminal tasks; an empty tuple
means no requirement. Dispatch compares all required tokens with each worker's
self-reported capabilities, preserving dependencies, priority and load limits.
Tokens are case-sensitive. Omitting the mapping preserves the previous behavior.
The returned `capability_filter` identifies the mode, while capability verification
and Core authorization remain unverified. Recommendations never claim or run work.

## Isolated simulated workflow

`python -m agentsync demo --workflow --data-dir ABSOLUTE_SCRATCH_PARENT` runs a fixed
four-task diamond with two Mock workers, capability/dependency planning, one failed
attempt followed by retry, and peer simulated reviews. The scratch parent must
already exist. Each invocation creates and removes its own private child database;
existing parent projects are never selected. The original `demo` behavior is unchanged.

The Python API `agentsync.mock_workflow.run_mock_workflow_demo` also accepts bounded
`max_attempts_per_task` (1..3), `attempt_budget` (1..16), and optional
`max_elapsed_seconds` (greater than zero, at most 60). The elapsed admission budget
includes private setup. Once expiry is observed, new claims/starts stop, active
Mock runs are cancelled and owned tasks fail; unstarted dependents stay pending.
It cannot preempt synchronous operations or hanging awaited calls. Omit it to
preserve the original behavior. Reports explicitly mark all results
as simulation-only/unverified. This does not enable real clients, production
automatic review, durable recovery, AI decomposition or paid services.

## Reported usage

`agentsync.usage.UsageLedger(project_id)` records typed adapter results through
`record_result(result)` and returns an immutable `summary()`. Identical run
observations count once; conflicting observations reject. Mock records are
separate from protocol totals. Each metric distinguishes a complete value,
known partial sum and unknown records, so missing usage is never reported as zero.
Elapsed time describes the adapter lifecycle interval, not provider/API duration.
These are caller-reported observations: costs remain unknown and billing/client
verification remains false. The ledger is bounded and in memory, without recovery
or transport/API-call accounting.

## Quality checks

```powershell
& .\.venv\Scripts\python.exe -m ruff check .
& .\.venv\Scripts\python.exe -m mypy
& .\.venv\Scripts\python.exe -m build
```

Review evidence is stored text, not verified execution. Task submitters cannot accept their own
work, but Alpha does not independently run or validate tests submitted by other agents.
M3 context and handoffs are implemented. M4 now adds read-only path/version inspection and
cooperative file/directory lease locks, shared across all transports. These do not enforce
OS locking or prevent external editors. Independent managed Git worktrees and real merge conflict detection are implemented.
Merge candidates await human approval; there is no apply-to-user-branch endpoint.
Independent evidence execution, control adapters and autonomous scheduling remain incomplete.
See [the plan](docs/PLAN.md) and [release acceptance design](docs/acceptance/DESIGN.md).
Passing local checks does not establish formal release acceptance.
Model fees, if later enabled, are the user's.
The owner authorized this public source archive on 2026-10-19; no model services were called for publication.

## Permissions and upgrade

New agents and agents migrated from schema v1-v5 start with `viewer` access.
A separate project owner must explicitly grant `worker` and/or `reviewer` before
writes or review. Existing tasks, contexts and history remain; legacy write grants
are not inferred. See [M5A guide](docs/M5A-GUIDE.md) before upgrading a live database.
Owner role/approval operations use SDK `owner_call`, CLI JSON stdin or the separate
loopback HTTP `/owner/v1/` route. They are absent from MCP discovery. Possession of
the admin credential is an owner capability, not proof of a physical human.
Approvals only store a pinned authorization decision: no user-repository apply or
arbitrary command execution endpoint exists. Existing task review remains asserted
evidence; sandboxed independent verification and formal release are still blocked.
