> Published archive: versions and checksummed files are in [releases/](releases/). See [RECOVERY.md](RECOVERY.md) and [PUBLICATION-MANIFEST.json](PUBLICATION-MANIFEST.json). Earlier no-publication statements in historical development reports describe the pre-publication checkpoint.

# Amadeus

Current development continues under [AGENTS.md](AGENTS.md), [WORKFLOW.md](WORKFLOW.md)
and [progress](docs/PROGRESS.md). The previous Claude handoff package was cancelled.

Free, MIT-licensed local coordination for multiple agents. Python SDK, MCP stdio and HTTP API
share one SQLite task system. No paid model, API key, cloud server or GUI is needed.

Status: **0.3.0a110 development source. Formal Release BLOCKED.** Permissions,
approvals, audit, isolated verification components and offline planning have
limited local evidence; see the [current report](docs/acceptance/RELEASE-ACCEPTANCE-REPORT.md).
The internal owner-only `OwnerCandidateExecutor` connects a pinned candidate and
prepared reservation to the fixed Linux Docker verifier, with one permanent
execution attempt, cooperative cancellation and one exact-ID cleanup. It has
limited local evidence and is not exposed through Core, MCP or HTTP. Unavailable isolation
fails closed. The internal `OwnerVerifiedTaskCompletion.complete_once` requires owner
authority, an independent reviewer and a passed execution bound to the exact current
candidate/task versions. Completion, durable proof and audit commit together.
Ordinary text reviews remain unverified, and historical receipts stay immutable.
The trusted host flow now has a [continuous real Codex producer/reviewer example](docs/acceptance/evidence/m7-continuous-live/summary.json),
including exact approval gates, independent Docker verification and automatic context/task handoff.
The model review is accepted as a document only; it does not become test evidence.
Original-workspace source application and uncertain execution retries remain disabled.
All checks run locally; GitHub Actions
are manual-only and are not used for development testing.

Codex host profiles may explicitly declare desktop CLI `0.167.0-alpha.3.2`,
`0.166.0-alpha.6`, or the legacy `0.164.0-alpha.11.1` default.
The same exact-version gate is used by plan
preparation and the opt-in process factory. Unlisted versions remain rejected.
Host version declarations and fixed CLI flags do not establish authentication,
billing or sandbox isolation; every real factory invocation still needs its
existing authorization and safety conditions. Local version/help/feature listing
is recorded separately from actual model-task evidence. The current real evidence
is limited to the pinned Linux Codex flow; Claude/Cursor remain unverified.

To obtain a handle before an adapter start finishes, await
`manager.dispatch_task(adapter_id, task)`. This admits the same request once and
returns its current dispatch snapshot. For a previously dispatched start, await
`manager.wait_dispatch(handle, timeout_seconds=5)` for a bounded receipt
observation, or use zero seconds to poll. A `pending` result leaves the start
running. Cancelling the waiter also preserves dispatched work; `returned` means
a start receipt, and callers still inspect the adapter's run status separately.

Project context has immutable revisions, source/summary
metadata and literal substring search. Structured handoffs pin context revisions,
invalidate the sender's lease and reserve a fresh claim for the designated recipient.
Reservations expire within 300 seconds so offline recipients cannot strand a task.
See [M3 contract](docs/M3-CONTRACT.md) and [progress](docs/PROGRESS.md),
[test evidence](docs/TEST-REPORT.md) and [compatibility](docs/COMPATIBILITY.md).
Protocol tests do not establish Codex/Claude/Cursor desktop compatibility.
The current desktop MCP connection was confirmed by the user; real native tool/collaboration
probes passed independently. See [M2 continuation](docs/M2-CONTINUATION.zh-CN.md).

[Project repository](https://github.com/JayChan697891/Amadeus)

## Windows quick start

From this repository directory, with Python 3.11+ installed:

```powershell
py -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev-lock.txt
& .\.venv\Scripts\python.exe -m pip install -e . --no-deps
& .\.venv\Scripts\amadeus.exe --data-dir "$PWD\local-data\demo" demo
& .\.venv\Scripts\python.exe -m pytest
```

No activation or PowerShell execution-policy changes are needed. Demo uses two simulated agents,
rejects the second claim, submits a result, records separate review and checks persistence.
Use a dedicated empty data directory for repeatable demo runs.
For runtime-only installation use requirements-lock.txt instead of the development snapshot.
Both files are exact Windows-tested snapshots, not universal cross-platform resolver locks.

## Interfaces

`amadeus` is the preferred console command. Existing integrations can continue to use
`agentsync-local` as the Python distribution, `agentsync` for Python imports and
as a console command, and `python -m agentsync` for module launches. MCP identifiers,
`AGENTSYNC_*` settings, and the default `AgentSync` data directory and `agentsync.db`
file retain their existing names.

- Python: `from agentsync.sdk.client import AgentSyncClient`; use `.call(operation, **payload)`.
- MCP: `python -m agentsync --data-dir ABSOLUTE_PATH mcp`.
- HTTP: set a private `AGENTSYNC_HTTP_TOKEN`, then `amadeus serve`.
  Default bind is 127.0.0.1:8765. POST `/v1/{operation}` with bearer authorization and JSON.
- See `examples/`, [operation contract](docs/CONTRACT.md), and [Chinese guide](README.zh-CN.md).

Every MCP process must use the same absolute data directory. Defaults are independent of cwd.
Never put the live WAL database on a network share. Keep project admin/session tokens private.
Stdio MCP hosts have local process access; Alpha is not a hostile-agent sandbox.

## Read-only scheduling

`amadeus plan < dispatch-input.json` prints offline dispatch advice.
In PowerShell: `Get-Content -Raw -Encoding utf8 .\dispatch-input.json | amadeus plan`.
The bounded UTF-8 JSON input requires `state` (an explicit project-state snapshot),
`project_id`, `worker_agent_ids` (an array), and `now` (a caller-supplied timestamp).
Optional fields are `global_limit`, `per_agent_limit`, `limit`, and
`required_capabilities` (task IDs mapped to capability arrays). No database or
default state is opened. Output remains unverified planning advice; it neither
authorizes nor starts work. Extra command arguments and input fields are rejected.

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

The Python API also accepts a validated graph of 1–16 simulation tasks. Tasks may
arrive out of dependency order; duplicate labels, missing dependencies and cycles
are rejected before filesystem access. Only the two built-in Mock workers run:

```python
from pathlib import Path
from agentsync.mock_workflow import MockWorkflowTask, run_mock_workflow

result = await run_mock_workflow(
    Path("D:/agentsync-debug"),
    tasks=(
        MockWorkflowTask("check", 20, "test", ("build",)),
        MockWorkflowTask("build", 10, "build"),
    ),
    attempt_budget=4,
)
```

The default total attempt budget is 6, with a maximum of 16. An optional
`fail_first_attempt=True` injects one simulated failure for that task. These
graphs use a disposable owned project and always return simulation/unverified
markers; they do not attach to existing projects or launch real clients.

Use `amadeus mock-workflow --scratch-parent ABSOLUTE_DIRECTORY` to pass a
task graph as UTF-8 JSON on standard input. The scratch parent must already exist.
For example, a build followed by a check uses this input:

```json
{
  "tasks": [
    {"label": "build", "priority": 20, "capability": "build"},
    {"label": "check", "priority": 10, "capability": "test", "dependencies": ["build"]}
  ],
  "attempt_budget": 4
}
```

Optional top-level fields include `max_attempts_per_task`, `attempt_budget`, and
`max_elapsed_seconds`. Supply `workers` to define two to eight Mock workers, each
with a unique `label` and a `capabilities` array containing `build`, `test`, or
both. Every task capability needs a matching worker. `parallel_limit` defaults
to two and can be set from one to the worker count. Inspect `data.outcome` and
`data.stop_reason` to distinguish a completed simulation from a budget stop.
Set `handoff_on_success` on a task to simulate a structured transfer after its
first successful run. Use at least two workers with the task capability and a
third worker for review. The recipient takes a new lease and uses another
attempt from the same task and workflow budgets.

`amadeus demo --workflow --data-dir ABSOLUTE_SCRATCH_PARENT` runs a fixed
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

## Optional model assistance

`agentsync.providers` offers explicit Python host profiles for OpenAI, Anthropic,
Gemini, DeepSeek and local Ollama. A host supplies its chosen model and any API
key directly. It reviews the exact `ModelRequest` and obtains permission for
the possible cost before issuing an expiring one-use grant with
`provider.authorize(request)`. Each call sends at most one request. Timeout,
cancellation and rate limits leave retries to a separate host decision.

API references: [OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[Anthropic](https://platform.claude.com/docs/en/api/messages/create),
[Gemini](https://ai.google.dev/api/generate-content),
[DeepSeek](https://api-docs.deepseek.com/api/create-chat-completion/), and
[Ollama](https://docs.ollama.com/api/chat).

Use `prepare_decomposition`, `prepare_role_suggestions` or `prepare_handoff` to
build an advisory request. `get_advice` parses the reply into a bounded task graph,
role suggestions or handoff notes. `MockProvider` can return a supplied response
through the same interface without network access. The host controls what source
material is sent to a provider. Suggestions remain private advisory data.

`ModelCallMeter` from `agentsync.model_usage` can wrap either provider. It tracks
local invocation duration and failures, keeps Mock responses separate from token
and cost totals, and preserves unknown costs. Optional `FlatRate` inputs provide
an estimate in picodollars for the reported tokens. It does not read tariffs or
establish a bill.

## Retry advice

`agentsync.retry_planning.plan_retry(RetryPolicy(...), ...)` calculates deterministic
capped exponential backoff from a caller-reported failure. A numeric Retry-After
minimum is respected even above the backoff cap. Attempt/global budgets and the
next-attempt deadline can stop a retry. Unknown or unconfirmed outcomes never
produce a retry recommendation; a timeout requires a confirmed outcome.

This function never waits, starts an adapter or changes Core. Caller confirmation
is not authorization or proof an external action is safe to repeat. Advice is
unverified and must be rechecked before any later dispatch. Real provider limits
and autonomous retry remain unverified.

## Reported usage

`agentsync.usage.UsageLedger(project_id)` records typed adapter results through
`record_result(result)` and returns an immutable `summary()`. Identical run
observations count once; conflicting observations reject. Mock records are
separate from protocol totals. Each metric distinguishes a complete value,
known partial sum and unknown records, so missing usage is never reported as zero.
Elapsed time describes the adapter lifecycle interval, not provider/API duration.
These are caller-reported observations: costs remain unknown and billing/client
verification remains false. `ledger.to_json()` exports a bounded normalized
checkpoint; `UsageLedger.from_json(expected_project_id, text)` restores a new
ledger, revalidates records and recomputes totals. Replay deduplication, capacity,
unknown values and Mock separation survive restoration. Checkpoints include
caller-supplied identifiers; they contain no raw output/client metadata. The
32 MiB format grants no authenticity. Both methods perform no file, database or
network I/O: callers control storage and crash-safe writes. They do not restore
Agent processes or tasks and do not add transport/API-call accounting.

For an explicitly selected private file, `agentsync.usage_storage` provides
`save_usage_checkpoint(path, ledger)` and `load_usage_checkpoint(path, project_id)`.
Supply an absolute file path in an existing owner-controlled directory and use
a single writer. Save flushes a temporary file before replacing the checkpoint.
Load validates the saved data and rebuilds its totals for the expected project.

`amadeus usage --project-id PROJECT_ID` reads one UTF-8 checkpoint from stdin
and prints the same aggregate summary. This offline CLI accepts at most1 MiB;
larger checkpoints can use the Python interface's32 MiB limit. It opens no Core
database and writes no files. The project ID is a caller namespace assertion,
not authentication. Costs stay unknown and client/billing verification stays
false. Extra options, invalid input and a mismatched checkpoint project return
a fixed error with exit status2, without printing the private input.

## Local contention diagnostic

`python tools/benchmark_coordination.py --scratch-parent ABSOLUTE_EXISTING_DIRECTORY
--workers 8 --rounds 8 --p95-budget-ms 1000` (one command line) creates and removes
an owned child project. Each round measures simultaneous claims for one task and
checks one winner, expected version conflicts, persisted state and SQLite integrity.
It also checks exact claim-audit identities/outcomes after timing; missing, duplicate,
unexpected or mismatched events fail even when totals or latency look correct.
Only aggregate audit counts are reported.
The JSON report includes actual claim-attempt throughput and nearest-rank latency
percentiles. Setup, barrier wait, verification and cleanup are excluded from timing.
The declared p95 threshold is a diagnostic budget, not a Release SLO. Exit codes
are 0 for passing the declared workload, 1 for failure and 2 for invalid options.
No existing database or real Agent is selected; formal acceptance stays false.

## Core thread admission

Core agent operations group waiting threads by resolved database path before
opening SQLite, while retaining all existing transaction/auth/replay/lease/audit
logic. Admission is process-local; SQLite still controls cross-process writes.
A wait can time out after 30 seconds before SQL begins. That wait is additive to
SQLite waits and audit work, so it is not a whole-operation deadline. No fairness,
queue-size, recursion or security guarantee is added. Owner/migration paths are
unchanged. Unused gates are reclaimed, and fork children reset inherited gates.

## Quality checks

```powershell
& .\.venv\Scripts\python.exe -m ruff check .
& .\.venv\Scripts\python.exe -m mypy
& .\.venv\Scripts\python.exe -m build
```

Ordinary review evidence is stored text, not verified execution. Task submitters cannot accept
their own work. Verified completion separately requires the pinned Docker/Core proof.
M3 context and handoffs are implemented. M4 now adds read-only path/version inspection and
cooperative file/directory lease locks, shared across all transports. These do not enforce
OS locking or prevent external editors. Independent managed Git worktrees and real merge conflict detection are implemented.
Merge candidates await human approval; there is no apply-to-user-branch endpoint.
Independent Docker execution and a controlled real two-Codex handoff have limited evidence.
Cross-vendor compatibility and broader autonomous scheduling remain incomplete.
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
For verified candidate delivery, use `preview_candidate_delivery` and
`approve_candidate_delivery` through `owner_call` or `amadeus owner`. Call
`publish_candidate_delivery` separately with the approved version and exact plan
hash to create the private managed Git ref. Inspect the outcome with
`get_candidate_delivery_status`.
Approvals only store a pinned authorization decision: no user-repository apply or
arbitrary command execution endpoint exists. Existing task review remains asserted
evidence; verified completion uses its independent proof gate. Formal release remains blocked.
