> Published archive: versions and checksummed files are in [releases/](releases/). See [RECOVERY.md](RECOVERY.md) and [PUBLICATION-MANIFEST.json](PUBLICATION-MANIFEST.json). Earlier no-publication statements in historical development reports describe the pre-publication checkpoint.

# Amadeus

**Try the packaged preview:** [download the a122 ZIP](releases/0.3.0a122/owner-preview-7085ec0-r3/Amadeus-owner-preview-a122.zip)
and follow its short README. It includes the original frozen wheel and reviewed
terminal examples; Python 3.12 is required for the Windows quick start. The default
demo uses simulated Agents, with no model calls. Its Windows dependency constraints
match the tested environment. Formal Release remains BLOCKED.

Current development continues under [AGENTS.md](AGENTS.md), [WORKFLOW.md](WORKFLOW.md)
and [progress](docs/PROGRESS.md). The previous Claude handoff package was cancelled.

Free, MIT-licensed local coordination for multiple agents. Python SDK, MCP stdio and HTTP API
share one SQLite task system. No paid model, API key, cloud server or GUI is needed.

Status: **0.3.0a122 development source. Formal Release BLOCKED.** The unchanged
0.3.0a116 candidate completed all six available Windows/Linux matrix rows; macOS
remains untested. Its evidence
does not certify new development changes. See [delivery priorities](docs/PLAN.md).

The a122 development preview fixes premature timeouts in shared adapter scheduling
and pre-launch waits. Early callbacks recheck the absolute deadline before
cancelling work. The original wheel and source archive each passed the same 97 targeted
cases on Windows 3.12 and Linux 3.14. Windows passed 19 native build and installation
checks, and Linux passed 16 installation checks. The first complete Windows wheel
suite subsequently passed2539 cases with57 explicit skips and no failures/errors.
The first complete Linux wheel suite passed2589 cases with7 explicit skips and
no failures/errors; [actual results](docs/acceptance/evidence/core-preview-a122/full-linux314/root-review.json).
Real same-vendor Codex handoff, persisted-result controller recovery and independent
completion of the same task have scoped evidence. This does not certify all
clients, lifecycle controls, platforms or formal Release.
[Windows full result](docs/acceptance/evidence/core-preview-a122/full-windows312/root-postcheck.json),
[real flow and limits](docs/acceptance/evidence/core-preview-a122/composed-recovery/verification/summary.json),
[Preview packages](releases/0.3.0a122/preview-5232e9e/),
[source repair evidence](docs/acceptance/evidence/core-preview-a121/adapter-deadline/summary.json),
[Windows results](docs/acceptance/evidence/core-preview-a122/windows/summary.json), and
[Linux results](docs/acceptance/evidence/core-preview-a122/linux/summary.json).

For a first local trial, use the [packaged Windows installation and demo steps](releases/0.3.0a122/preview-5232e9e/README.md).
That offline demo uses simulated agents and reports `simulation_only: true` and
`verification: unverified`; it does not call a model. The archived preview README
records its original validation checkpoint; use [current progress](docs/PROGRESS.md)
for subsequent results. The real Codex flow above is a separate, owner-approved experiment.

The current source also fixes demo/owner JSON output on legacy Windows streams:
Chinese paths and recovery reasons survive round-trip decoding. Two actual
failures and19 passing targeted source checks are recorded in the
[repair evidence](docs/acceptance/evidence/core-preview-a120/cli-output-encoding/summary.json).
The [a121 preview](releases/0.3.0a121/preview-4b82494/) includes this correction:
fresh wheel/source-package installs each passed23 targeted cases on Windows3.12
and Linux3.14, using the same archives. Windows19 and Linux16 native checks pass;
the complete matrix and real clients remain unverified for a121. Archived a120
packages below are unchanged.

The [a120 development preview](releases/0.3.0a120/preview-859775b/)
adds missing-project protection for `workflow start` and structured database errors
for `owner`/`workflow`. Fresh wheel and source-package installs each passed21
focused cases on Windows3.12 and Linux3.14 using the same archives. macOS and
a120 real-client validation are NOT RUN; full formal acceptance remains incomplete.
Frozen a120 editable-source, wheel and source-package suites each passed2530 cases with57 skips
on Windows3.12 and2580 with7 skips on Linux3.14, with no failures/errors. Each has
2587 unique cases; all three forms have identical outcomes per platform.
See [Windows wheel](docs/acceptance/evidence/core-preview-a120/full-windows312/summary.json),
[Windows source package](docs/acceptance/evidence/core-preview-a120/full-windows312-sdist/summary.json),
[Linux wheel](docs/acceptance/evidence/core-preview-a120/full-linux314/summary.json) and
[Linux source package](docs/acceptance/evidence/core-preview-a120/full-linux314-sdist/summary.json).
The [Windows source](docs/acceptance/evidence/core-preview-a120/full-windows312-source/summary.json)
and [Linux source](docs/acceptance/evidence/core-preview-a120/full-linux314-source/summary.json)
complete those six selected suites, without certifying later a121 code or the full
formal matrix. Historical evidence originals
retain Ruff/format FAIL, and license review is pending; see the [current gates](docs/acceptance/RELEASE-ACCEPTANCE-REPORT.md).

For an existing stopped relay, use the [recovery guide](docs/RELAY-RECOVERY.md)
and interactive [helper](examples/recover_relay.py) to inspect the saved wave and
reconcile its exact ID. Tokens use hidden prompts and child stdin. This reuses
the installed CLI; it does not launch Agents or approve candidate execution.

The earlier [a119 development preview](releases/0.3.0a119/preview-4be5134/) includes the
owner CLI directory fix and same-task continuation verification bridge. The same
wheel/source packages passed15 focused cases per Windows install and16 per Linux
install, including real Docker verification with local protocol fixtures. These
are scoped installation results, not real-model or full-release acceptance.
Separately, the unchanged a119 wheel completed a
[real Codex interruption-to-verification flow](docs/acceptance/evidence/core-preview-a119/live-continuation/README.md):
two subscription calls, one Docker execution, and the same receiver task completed
verified after2 cases/19 isolation checks. This used a host-known checkpoint and
explicit approvals; whole-host crash, cross-vendor and unattended operation remain
unverified. The distinct host reviewer was not a third model call.
Permissions,
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
The trusted host flow now has a [current real Codex producer/reviewer example](docs/acceptance/evidence/durable-demo-a117/live/summary.json),
including exact approval gates, independent Docker verification and automatic context/task handoff.
The model review is accepted as a document only; it does not become test evidence.
Original-workspace source application and uncertain execution retries remain disabled.
The new `ProposalReviewInput` / `ProposalReviewQueueItem` path accepts a prepared
Codex, Claude Code or Cursor reviewer for a dependent task. It pins the current
verified producer artifact and accepts only `review.md` as an unverified document.
`ProposalHandoff` uses this restricted path for Claude/Cursor and preserves the
existing Codex handoff format. Each launch still needs exact host approval;
reported Codex/Claude tool events are rejected in this review mode. Cursor's
terminal response cannot prove that no tools ran, so fixed flags do not replace
host isolation requirements. Real Claude/Cursor compatibility remains NOT RUN.
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

For the frozen a122 owner trial, open PowerShell in this repository with Python
3.12 installed. Choose unused environment and data directory names:

```powershell
py -3.12 -m venv .venv-a122
& .\.venv-a122\Scripts\python.exe -m pip install .\releases\0.3.0a122\preview-5232e9e\agentsync_local-0.3.0a122-py3-none-any.whl
& .\.venv-a122\Scripts\amadeus.exe --data-dir "$PWD\local-data\amadeus-a122-01" demo --durable
```

No activation or execution-policy change is needed. Installation can download
runtime dependencies. The demo itself uses simulated Agents, requires no model
account or API call, and reopens the same saved task in fresh processes. Expect
`ok: true`, an accepted handoff, `simulation_only: true` and
`verification: unverified`. A distinct simulated reviewer is not independent
execution verification. [Observed CLI trial and read-only database check](docs/acceptance/evidence/core-preview-a122/owner-trial/root-review.json).
Use a new data directory for each demo; preserve its database if you want to inspect
the run later. The package hashes are in [SHA256SUMS](releases/0.3.0a122/preview-5232e9e/SHA256SUMS).
See [CONTRIBUTING.md](CONTRIBUTING.md) for development installation and tests.
Real Codex experiment evidence is linked above and is separate from this demo.

For your own bounded task, the [terminal host example](docs/VERIFIED-TASK-EXAMPLE.md)
uses the existing SDK with separate launch, staging, execution and completion
approvals. It requires a prepared isolated Linux project, Codex login and local
Docker; its new entry has separate validation from historical real-client runs.

## Try persisted collaboration

The newer [a118 development preview](releases/0.3.0a118/preview-7f0ba0a/) includes
the recovery-directory fix. Fresh Windows3.12 wheel and sdist installations each
passed12 focused cases. Its full/platform/client acceptance remains incomplete;
the a117 evidence below stays tied to that older frozen runtime.

The [preview directory](releases/0.3.0a117/demo-fc27f15/) contains a wheel and source
archive for the same frozen runtime. Windows3.12 editable-source/source-archive
and Linux3.14 source-archive installs each passed the same10 focused cases as the earlier wheel check; see
[package evidence and retained setup failures](docs/acceptance/evidence/durable-demo-a117/sdist/summary.json).
[Linux installation evidence](docs/acceptance/evidence/durable-demo-a117/sdist/linux/summary.json)
uses the same archive without rebuilding it.
This is focused demonstration validation, not a full a117 release matrix.
The later [Windows full regression and targeted traceability repair](docs/acceptance/evidence/durable-demo-a117/full-windows312/current-summary.json)
preserve the original failed run and its separate92-case correction check.
The [full Linux 3.14 installed-sdist regression](docs/acceptance/evidence/durable-demo-a117/full-linux314/current-summary.json)
completed with 2,538 passed and 7 skipped using the pinned local Docker image.
The a117 release matrix remains incomplete and formal Release remains blocked.

After the Windows installation above, run the following from the repository
directory (choose another new directory name for each run):

```powershell
& .\.venv-a122\Scripts\amadeus.exe --data-dir "$PWD\local-data\amadeus-demo-01" demo --durable
```

On Linux, an equivalent disposable location is `/tmp/amadeus-demo-01`.
This fixed, offline demonstration uses three simulated identities. It creates a
task, saves one retry, reopens the workflow in fresh processes, resumes it, hands
it to a second worker and records a distinct peer review. The report identifies
the same persisted task and accepted handoff. Existing directories are refused;
the new database remains available for local inspection and is not uploaded.

No model or API is called. Worker results and peer review are explicitly
`simulation_only/unverified`: this demonstrates coordination and saved-state
continuation, not code correctness or recovery of an interrupted real model.
Owner credentials stay in memory/stdin and are not printed or saved; this short
demo does not provide a credential-recovery service after its parent exits.
Use the owner-managed workflow API below for your own credential lifecycle.

The [current two-Codex flow](docs/acceptance/evidence/durable-demo-a117/live/summary.json)
records version0.3.0a117 at `fc27f15`: two real client sessions, four explicit host
decisions, independent Docker verification, pinned handoff and a fresh-process
reopen without another model call. Model review is accepted as a document only,
still unverified. This is separate from the offline demo and does not establish
live crash recovery, cross-vendor support, unattended approval or formal release.
The [earlier a109 evidence](docs/acceptance/evidence/m7-continuous-live/summary.json)
is preserved. See [delivery nodes A/B/C](docs/PLAN.md) for remaining requirements.

A separate [interrupted-client continuation](docs/acceptance/evidence/durable-demo-a117/interrupted-live-r2/summary.json)
also ran on this frozen runtime: one real Codex parent was interrupted during its
turn, and a second identity continued from a pinned, host-authored checkpoint.
One dependent task moved to the receiver; reopening launched nothing again.
The original received task remains unverified. A later
[independent Docker run](docs/acceptance/evidence/durable-demo-a117/interrupted-output-verification/summary.json)
verified its exact output in a new test project (eight cases and nineteen isolation
checks); importing that output did not change the original task. This proves the
controlled client-process scenario, not whole-computer or model-authored checkpoint recovery.

For a developer demonstration of actual isolated verification, the existing
Linux pilot also accepts a fixed `--demo` mode. Use the existing root user inside
the project's [dedicated local Linux test VM](docs/LOCAL-DEBUG.md): this fixture
requires a fresh `/root/amadeus-proposal-pilot-*` directory. Run from this checkout
with Amadeus installed, Git available and the trusted test image already present:

```sh
python -I -B tools/run_proposal_candidate_pilot.py --demo \
  --root /root/amadeus-proposal-pilot-demo-01 \
  --image-id sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
```

Use a new directory each time. This Linux-only fixture verifies a fixed,
owner-authored `add.py` in Docker, then hands a dependent task and pinned proof
context to another Core identity and reopens Core before continuing. It does not
pull an image or execute candidate code on the host. The original baseline stays
unchanged. Its actors are deterministic, the downstream text review stays
unverified, and reopening Core in one process is not a crash demonstration.
The pilot is a repository tool, not bundled in the wheel. Validation status is
recorded in [progress](docs/PROGRESS.md). The [observed Linux demo](docs/acceptance/evidence/durable-demo-a117/verified-linux/lead-review.json)
passed 8 fixed cases and 19 isolation checks; it is not real-model or formal-release acceptance.

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

For a simulation that must survive a coordinator restart, use the owner-only
`start_mock_workflow`, `resume_mock_workflow`, `status_mock_workflow` and
`cancel_mock_workflow` operations through `AgentSyncClient.owner_call`. The CLI
equivalent is `amadeus --data-dir ABSOLUTE_PATH workflow start|resume|status|cancel`.
Provide `project_id` and `admin_token` through bounded stdin JSON, never command
arguments. Use a dedicated empty project; one durable run is bound to that project.
Keep the owner credential yourself: the driver stores no recoverable credentials.

To create your own project, use the SDK's regular `call("create_project", ...)`;
`owner create_project` is not an operation. The returned `data` contains the
`project_id` and one-time `admin_token`. Keep that mapping in your host's private
credential store; do not print it, put it in command arguments or commit it.
The short `demo --durable` intentionally does not return its owner credential.

The runnable [project bootstrap example](examples/persisted_workflow.py) shows the
complete input: SDK project creation, then three separate CLI processes for
`start`, `status` and `resume`, all using the same database. After installation,
from this repository run:

```powershell
& .\.venv-a122\Scripts\python.exe -I -B examples\persisted_workflow.py "$PWD\local-data\my-workflow-01"
```

Choose a new directory each time. Output shows the same `run_id`, first `waiting`
and then `completed`, with `simulation_only: true` and `verification: unverified`.
The example keeps its owner mapping only in parent-process memory and passes it
to children through stdin. It does not save credentials for a later host restart;
your integrating host must retain them privately before exiting. The example
runs no model and refuses existing state before opening the SDK.

Current development source and the a119 preview reject `owner` commands when their selected
database is missing, without creating empty state. Use `--data-dir` or
`AGENTSYNC_DATA_DIR` to select the project you created. The older frozen a118
packages retain their original behavior and version-bound checks.

Current development source and a120 also reject `workflow start` when the project database
is missing, without creating an empty directory or database. All four workflow
operations require a project created through the SDK. The frozen a119 packages
precede this final `start` correction; select your existing project explicitly.
They also return a JSON `storage_error` when `owner` or `workflow`
cannot open the database, instead of a Python traceback. A corrupt file is left
untouched; this error does not repair or replace the database.

`start` also takes `request_id` and `config`; `resume`/`cancel` take `request_id`
and `expected_version`. Set `expected_version` to the latest `data.version` in
the `status` response. A minimal config is:

```json
{
  "tasks": [{"label": "build", "priority": 1, "capability": "build"}],
  "budget": {
    "steps": 8, "calls": 8, "requested_output": 4096,
    "estimated_tokens": 50000, "estimated_cost": 500000, "concurrency": 2
  },
  "deadline_seconds": 60
}
```

Start/resume drives ready work and returns `waiting` when a retry is not yet due;
call resume with current version after its persisted `retry_at`. Reopening does not
reset reservations or the deadline. Missing results after dispatch remain unknown
and cannot be retried. Cancellation persists before stopping owned Mock activity.
`handoff_on_success` reuses the normal structured handoff and requires a distinct
third reviewer in the worker roster. The existing disposable entry below is unchanged.
All durable effects are Mock: cost units use the disclosed fixed synthetic tariff,
estimated token values are planning units, and neither represents a real bill or
permission to launch a model. See [progress](docs/PROGRESS.md) for validation status.

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

For project-persistent advice calls, use the local SDK's async
`request_model_advice(project_id=..., admin_token=..., request_id=..., provider=...,
request=..., authorization=..., rate=...)`. Supply an already constructed provider
and its exact, explicit one-use authorization; Mock needs no grant or rate.
The operation records an unknown intent before sending. Repeating the same request
returns saved observations and never sends again. Advice itself is returned only
by the original invocation and is not stored as trusted task instructions.
`owner_call("get_provider_usage_call", ..., request_id=...)` reads an interrupted
call without sending; its returned `call_id` can also be used for later lookups.
`get_usage_summary` keeps these `local_provider_calls` separate from client receipts
and imported usage. Reported token counts, measured elapsed time, optional flat-rate
estimates and remote uncertainty remain distinct; actual bills stay unknown.
This new connection is authored but NOT RUN during the current code-first pass.

## Retry advice

The local host can continue saved unfinished code through
`agentsync.continuation.OwnerContinuation`. During a producer's live task lease,
`ControlledRelay.publish_progress_checkpoint` stores already-known, typed inert
progress through Core; it does not recover a partial response from failed stdout
or prove that the model authored it. After a positively ended failed attempt,
`pin_failed_progress` binds that exact historical publication and capture.
`preview` exposes the new recipient task and pending downstream dependency changes;
`run_once` requires that exact plan digest and a recipient factory with its own
fresh launch consent and independent managed worktree. The old task remains failed,
and the new task's output still requires normal staging and independent verification.
Unknown attempts do not qualify. A saved dispatch intent cannot be replayed into
another launch. The bounded [real interrupted-parent continuation](docs/acceptance/evidence/durable-demo-a117/interrupted-live-r2/summary.json)
used two Codex subscription calls and a host-known checkpoint; the original
receiver remains `review/unverified`. It does not prove whole-host crash recovery.

The development relay now offers explicit Codex continuation proposal observation and
staging entries, binding the original request, failed source and receiver receipts.
These connect the same receiver task to the existing owner-approved candidate
verification and different reviewer's completion. See the
[host integration contract](docs/M6-ADAPTERS.md#controlled-proposal-submission-and-staging-bridge).
Staging/execution/completion remain separate decisions. The verifier's supported
candidate format is root `solution.py` using its JSON-lines interface; arbitrary
model output is not silently adapted. The
[a119 live result](docs/acceptance/evidence/core-preview-a119/live-continuation/README.md)
now exercises this same-task bridge with two real Codex calls and one approved
Docker execution. The original R2 fixture remains unchanged, and formal Release
is still blocked. Reuse the recorded result; do not restart its consumed fixture.

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

To reconcile an existing controlled-relay task into Core project usage, call
`AgentSyncClient(data_dir).owner_call("sync_relay_usage", **payload)` or run
`amadeus --data-dir DATA_DIR owner sync_relay_usage` with a JSON object on stdin.
Supply `project_id`, `admin_token`, `task_id`, and the absolute `scratch_root` and
`receipts` directories originally bound to that project. The operation reads
saved receipts without starting a client. Historical two-leg dispatches can be
bound using Core's saved operations. Older single-client and proposal dispatches
without exact launch pins return `relay_usage_unsupported`.

`get_usage_summary` keeps caller-reported totals and reports a separate
`controlled_relay_receipts` subtotal. To inspect a receipt observation, pass its
returned `run_id` and `kind` to `get_usage_run` with
`provenance="controlled_relay_receipts"`. An admitted attempt without a terminal
receipt keeps its metrics unknown. Resync can fill in a matching terminal once.
The receipt failure rate counts failed and confirmed timed-out outcomes against
known outcomes and is available only when every outcome is known.
Elapsed time describes the adapter lifecycle. The receipt source does not verify
client execution, provider charges, or billing. Neither subtotal counts as a bill.

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

To integrate the same verified candidate into a local repository, request a
separate `apply_merge_candidate` approval. Use `preview_candidate_integration`
with `project_id`, `admin_token`, `approval_id`, `expected_version`, `task_id`,
`expected_task_version`, the requesting worker's `session_id` and `session_token`,
and `target_root`, `worktree_path` and `destination_branch`. Call
`approve_candidate_integration` with the returned `plan_sha256`, then
`integrate_candidate` with that hash and the approved version. These commands use
SDK `owner_call` or `amadeus --data-dir DATA_DIR owner OPERATION` with JSON on stdin.
The target must be an ordinary clean local repository at the verified candidate's
base. The destination branch and separate absolute worktree path must be new.
The new checkout contains the exact candidate blob bytes. Ordinary Git line-ending
attributes are supported. Filters, custom encodings, symlinks, submodules and
external Git configuration are unsupported. The target's current branch, index
and working files retain their contents.

`get_candidate_integration_status` takes the project owner credentials and
`approval_id`. It reads the saved intent and checks the result. An interrupted
operation can return `partial` or `unknown`; the consumed approval and destination
reservation persist. A status check never retries or removes a destination.
Existing task review remains asserted evidence. Verified completion uses its
independent proof gate. Formal release remains blocked.
