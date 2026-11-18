# Inspect and recover a saved relay

Use this path when a controlled relay coordinator has stopped and you need to
inspect its saved work. It uses the existing `relay-status` and `relay-reconcile`
commands. It does not start an Agent, run candidate code, or approve completion.

The checkout includes an interactive helper:
[examples/recover_relay.py](../examples/recover_relay.py). Run it with the Python
environment where Amadeus is installed. The helper belongs to the checkout, not
the wheel. Use a real terminal: tokens are requested without echo, passed only to
the child command's standard input, and not saved. A terminal that cannot hide
input is rejected. These are **Amadeus project credentials**, not a Codex login or
provider API key.

## Find the existing project and pending wave

Use the original absolute paths recorded by your host:

- `--data-dir`: the directory containing `agentsync.db`.
- `--scratch-root`: the original relay working directory.
- `--receipts`: its original relay receipt directory.
- `--project-id`: the ID returned when that project was created.

Both state and the project's registered root must be inside the original scratch
root; receipts must be a strict subdirectory and state must not be inside receipts.
Do not move receipts, create replacement folders or initialize
a new project to recover an old run. The helper does not retrieve lost credentials.

For example, in PowerShell from this checkout, replace the paths and project ID
with your existing values:

```powershell
$location = @('--data-dir', 'D:\my-relay\core', '--scratch-root', 'D:\my-relay', '--receipts', 'D:\my-relay\receipts', '--project-id', 'YOUR_PROJECT_ID')
& .\.venv\Scripts\python.exe -I -B examples\recover_relay.py @location status
```

Enter the project's owner token at the hidden prompt. Do not put it in the command
line, a screenshot, or a repository file. On Linux, use the same arguments with
`.venv/bin/python`, forward-slash paths, and `examples/recover_relay.py`.

If `data` is non-null, save its exact `wave_id` and the task IDs in
`data.outcome.tasks`. `data: null` means there is no pending wave, not that all
tasks passed. Inspect saved history or a particular task separately:

```powershell
& .\.venv\Scripts\python.exe -I -B examples\recover_relay.py @location history
& .\.venv\Scripts\python.exe -I -B examples\recover_relay.py @location task YOUR_TASK_ID
```

In the development checkout, the task response also includes `data.checkpoint`.
It uses the project owner token, so an expired Agent session does not prevent
inspection. SDK hosts can call
`ControlledRelay.owner_observe_codex_checkpoint(project_id, task_id, admin_token=...)`.
The existing Agent-based observer still requires a valid session.

`saved` returns the recorded context ID, fixed version, content SHA-256 and task
version; these are **unverified receipt metadata**, not a check of the current Core
context's content. `not_observed` and `checkpoint_observed: false` require an explicit
terminal observation. Missing checkpoint receipts after a crash remain `unknown`,
and disabled capture is `not_enabled`. Malformed checkpoint JSON or inconsistent
progress/protocol metadata returns an error rather than being reported as absent. No token is included
in the response. This inspection does not renew a session, launch an Agent, or grant
continuation, staging, execution or completion permission. `OwnerContinuation`
still independently checks confirmed failure and the actual Core publication witness.
The owner inspection addition is not in the previously frozen a123 wheel or a122/r5 ZIP.

History is bounded to the existing CLI's default page. For more pages, use
`amadeus relay-status --help` and the existing `--history --before` options from
your trusted host, supplying owner JSON through standard input.

## Reconcile only the wave you inspected

Reconciliation updates the saved wave from existing task/context/terminal
receipts. It requires the owner token and a valid enrolled session for the same
project. Use credentials held by your host; do not edit the database to revive an
expired session.

```powershell
& .\.venv\Scripts\python.exe -I -B examples\recover_relay.py @location reconcile EXACT_WAVE_ID
```

The helper requests the session ID and its token, invokes reconciliation once,
and returns the command's JSON and exit code. It never picks a wave automatically
or retries. If interrupted or timed out, inspect status before doing anything
else; a missing response does not prove that no state changed.

| Result | Meaning and next action |
| --- | --- |
| `ok: true`, `state: resolved`, task `ready_for_review` | The saved wave is reconciled. The task is ready for review, not verified or completed. Return to the existing host's explicit staging/verification flow. |
| `ok: true`, `state: incomplete` or attempt `outcome_unknown` | Evidence is insufficient. Preserve the project and receipts; do not start another attempt just to clear this state. |
| `confirmed_failed` or `conflict` | The existing terminal failure/conflict remains visible. Reconciliation is not a new attempt or a conflict override. |
| `ok: false` | Read `error.code`. Correct the project/session/path input as appropriate; do not replace saved state or weaken approval checks. |

Check `history` and `task` again afterward. An exit code of zero means that the
inspection/reconciliation command completed, **not that the Agent task passed**.
For a continuation receiver, the trusted host still checks its original request,
task version, publication and resolved wave when preparing staging. This helper
does not submit a staging plan or authorize candidate execution.

## Evidence boundary

The checkout helper was also exercised through an actual Windows terminal with
the unchanged a120 installation: status, history, task, one exact-wave reconcile,
and status again all exited0. The real hidden prompts did not echo the temporary
project credentials. No prompt or CLI subprocess was mocked. This fixture had a
real pending task and an admitted journal wave, with no Agent dispatch; reconcile
correctly remained incomplete/unverified and preserved the pending task.
[Native terminal observations and limitations](acceptance/evidence/core-preview-a120/native-terminal/summary.json).
Linux/macOS terminal interaction is not covered by that check. Cleanup of this
local test's temporary project credential file was rejected before execution;
it remains a separate BLOCKED local cleanup, with no credentials in the evidence.

The [a120 native recovery case](acceptance/evidence/core-preview-a120/coordinator-review-recovery/summary.json)
observed coordinator exit after a deterministic receiver's review was saved,
then recovered the same task's staging-preview eligibility through a fresh CLI,
without another launch. The earlier
[a119 real Codex flow](acceptance/evidence/core-preview-a119/live-continuation/summary.json)
proved a different, explicitly scoped live interruption/continuation path.
The combined real-client coordinator-exit scenario is **NOT RUN**; formal Release
remains **BLOCKED**. Recovery does not turn unverified output into verified work.
