# Run your own bounded Codex task

`examples/verified_codex_task.py` is a terminal host for the existing
`VerifiedProposalFlow` SDK. It accepts your task and expected input/output cases,
captures a `solution.py` proposal, asks for separate staging and Docker execution
decisions, then offers independent Core completion. Only after verified completion
may a second Codex identity receive the pinned proposal and return `review.md`.
That review document remains unverified. No candidate is applied to your source.

This is an advanced local example, not the first-run simulated demo. It requires
Linux with the existing local Docker verifier. Windows users can run the
[packaged durable demo](../README.md#windows-quick-start); this new
example does not claim native Windows candidate execution.

## Prepare once

First install the frozen a122 wheel in a Python environment; no editable
installation is needed. For a new dedicated Linux project, use that Python with the
repository initializer (the parent directory must already exist):

```sh
/path/to/venv/bin/python -I -B /path/to/Amadeus/examples/initialize_terminal_project.py /path/to/new-project
```

It creates a clean `ROOT/repo` Git repository and registers it in `ROOT/core`.
The result prints your project ID and the location of `ROOT/private-owner.json`;
it does not print the owner token. Keep that file private and locally available:
use its `admin_token` at the hidden owner prompt below. The root is mode 0700 and
the credential file mode 0600. Never upload the credential file or database.
No model login, model launch or candidate execution occurs during initialization.

An existing root is refused unchanged. If initialization fails after creating
files, retain the entire directory for inspection; the credential file may be
incomplete. Do not run tasks until initialization succeeded, and do not delete
or reuse partial state to retry automatically. Windows users should use the
packaged durable demo; this initializer supports Linux only.

- Use an existing, dedicated local project: its database is
  `ROOT/core/agentsync.db`, and its registered clean Git repository is inside
  `ROOT`. Keep project ID and owner token in your private credential store.
  The SDK `create_project` operation returns them once; the simulated demo's
  disposable credentials cannot be reused. Do not select your normal workspace.
- Prepare a private Codex login home separately. Confirm the supported CLI
  version (this Linux path requires **0.167.0-alpha.3.2**), exact binary SHA-256,
  subscription-only billing and effective host
  isolation. This example does not copy, read, recover or clean up login files.
  Read-only CLI flags alone do not establish isolation or prevent extra fees.
- Use a preloaded, independently checked Docker image ID (`sha256:` plus its
  full digest). The verifier does not pull images or fall back to host execution.
- Write your task in a UTF-8 file (at most 1000 bytes). Task and case files are read
  only up to their limit plus one byte; oversized input is refused before any
  owner prompt or model launch. The supported output is a
  standalone `solution.py` that reads and writes one JSON value per line.
  Write owner-defined cases as a JSON array of at most32768 bytes, for example:

```json
[{"input": [2, 3], "expected": 5}, {"input": [-7, 4], "expected": -3}]
```

These example cases describe addition; replace the task and cases together for
your own bounded problem. Cases are verification data, never shell commands.

## Run in a private terminal

Replace all uppercase values below with your actual reviewed values. Paths must
be absolute; the example file is in this checkout, outside the isolated project.

```sh
/path/to/venv/bin/python -I -B /path/to/Amadeus/examples/verified_codex_task.py \
  --root /path/to/isolated-project --project-id PROJECT_ID \
  --task /path/to/task.txt --cases /path/to/cases.json \
  --codex /path/to/codex --codex-sha256 BINARY_SHA256 \
  --codex-version 0.167.0-alpha.3.2 --codex-home /path/to/private-codex-home \
  --image-id sha256:IMAGE_SHA256
```

Enter the owner token at the hidden prompt, never as an argument. Inspect each
displayed plan and type its exact SHA only if you approve that operation. Both
model launches also require a fresh cost/isolation confirmation. Inspect the
actual candidate source before staging, the image and cases before execution,
and the execution proof and reviewer before completion. There is no `--yes`.

On the development branch, `--checkpoint-completed-proposal` requests the fixed
`amadeus-proposal-checkpoint-v1` contract, bound into the exact launch approval.
It defaults to off. The producer must emit exactly two complete JSON messages:
first a commentary `{"phase":"checkpoint","files":[...]}` containing a complete
draft, then, after its own checks without tools, a final
`{"phase":"final","files":[...]}`. Both must satisfy the same declared paths and
byte limits. Only the final files proceed to staging. The published a122/r5 ZIP
and wheel do **not** contain this development feature. One bounded a123 Codex
observation saved the checkpoint receipt about16.86 seconds before terminal
observation. Its exact149-byte fixture remained NOT_VERIFIED because both messages
contained150 source bytes (an extra LF); no recovery or candidate execution ran.
See the [limited actual observation](acceptance/evidence/core-preview-a123/live-checkpoint-observation/actual/summary.json).

The host saves the checkpoint as unverified Core context only if the entire live,
bounded UTF-8 JSONL prefix ends on a complete line, contains just the checkpoint
message and no terminal, in-turn error or tool event. Existing supported completed
startup warnings before `turn.started` remain permitted. Partial token streams and
reasoning are never assembled into a draft. Cancellation, truncation or expiry
prevents publication. If both messages and the terminal arrive together, a valid
final can still succeed, but no checkpoint is saved afterward.

With the flag enabled, `ROOT/terminal-run/result.json` or `stopped.json` includes
`producer_checkpoint`: `saved` means a saved checkpoint receipt, `not_observed`
with `checkpoint_observed=false` comes only from an explicit successful terminal
observation, and `unknown` means inspection could not establish either. Missing
receipts after a crash never imply false. SDK hosts can read the same unverified
metadata through `ControlledRelay.observe_codex_checkpoint(actor, task_id)`.
A saved receipt is neither continuation authorization nor task verification.
The existing confirmed-failure, Core publication witness and owner continuation
checks still apply; unknown/cancelled/timed-out attempts do not become eligible.
There is no automatic resume, extra model call or artificial delay to create a window.
The running/deadline observation is checked immediately before calling Core's
publication operation. Core then performs its own synchronous checks; this is
not a guarantee that its database commit precedes the OS process exit or deadline.

Approval input is hidden and cancellable. Waiting for launch approval shares the
existing 90-second task budget; the complete flow has a 600-second budget. If a
deadline expires, the pending input is cancelled and terminal settings restored.
Review the fixed inputs before starting; do not enlarge these limits to replay
an interrupted attempt. Approval lines are bounded to 256 UTF-8 bytes including
their newline. The initial owner-token prompt runs before the timed flow.

At most two model launches are attempted. A refused or mismatched decision stops
that part of the flow. Denial, failure, interruption or an unknown result never
causes an automatic retry. The existing `ROOT/terminal-run` directory prevents
another run of this example against the same saved attempt.

## Inspect and retain

Keep the whole isolated project and your original owner credentials. Local
`terminal-run` plans/results and receipts identify the tasks and exact decisions;
they may contain your task and proposed source and must remain private. Model raw
output and owner/session credentials are not written to these reports. Do not
upload the database, login home or private records with a bug report.

Use [recover_relay.py](../examples/recover_relay.py) for status/history with
`--data-dir ROOT/core --scratch-root ROOT --receipts ROOT/terminal-run/receipts`
and the original project ID. Inspect existing owner services before any recovery
action. This example does not automatically resume a producer or verifier.

## Continue a confirmed failed producer (development checkout)

`examples/continue_codex_task.py` connects an authentic saved protocol checkpoint
to the existing `OwnerContinuation` service. Keep it beside
`verified_codex_task.py` from the same checkout: it reuses that file's hidden,
cancellable terminal input and exact launch approval. This entry is not included
in published a122/r5. It requires Linux, the supported read-only Codex profile
`0.167.0-alpha.3.2`, and the original project, scratch root and receipt directory.

First inspect the original task through `recover_relay.py task TASK_ID`.
Only an observed `saved` checkpoint plus an authentic, dispatch-pinned, non-timeout
failed capture with a positively ended parent can proceed. A pending task alone,
unknown/cancelled/timed-out capture, missing checkpoint, or normal successful
review is not eligible. In particular, the150-byte observation above is **not**
a confirmed failed producer: a later fixture assertion cannot relabel its model
result. Do not retry that experiment.

Write your continuation instruction (at most1000 UTF-8 bytes) to a local file:

```sh
python -I -B /CHECKOUT/examples/continue_codex_task.py \
  --root /ABSOLUTE/ROOT --project-id PROJECT --task-id FAILED_PRODUCER_TASK \
  --receipts /ABSOLUTE/ROOT/terminal-run/receipts \
  --instruction /ABSOLUTE/continue.txt --codex /ABSOLUTE/codex \
  --codex-sha256 REVIEWED_BINARY_SHA256 --codex-version 0.167.0-alpha.3.2 \
  --codex-home /ABSOLUTE/private-codex-home
```

Enter the existing owner token privately. The helper validates the checkpoint's
Core publication and failure receipts **before** asking `PREPARE` to register one
new independent receiver. It then shows the actual pinned draft and instruction
with JSON escaping. Inspect them and the dependency-transfer plan before typing
the exact continuation-plan SHA. The actual receiver launch separately requires
`CONFIRM` for cost/isolation and its own exact launch SHA. No approval is inferred
from checkpoint inspection, and no candidate/Docker execution occurs.

Successful admission marks the source failed and transfers its pending
dependents once; success ends with the new receiver in `review/unverified`, not
verified code completion. This is at most one new model launch. Denial, expiry,
failure or unknown outcome stops without another launch. After `PREPARE`, the
exclusive `ROOT/continue-<project-and-task-digest>/entry.json` fences the attempt;
rerunning the command reads owner status only, even if no receiver was dispatched.
A stop after preparation does not automatically resume or recreate the receiver.
Keep the marker and original receipts; inspect before any separately authorized
action. Local launch plans may contain your instruction/draft and remain private;
owner/session tokens and raw model streams are not saved. The owner retains its
original credentials and remains responsible for parent-safe temporary-login
cleanup. Deterministic local-process tests do not establish real-client recovery.

## Accept or reject the returned document

Use `examples/review_relay_document.py` to close the receiver's `review.md` task
with a new independent Core reviewer. This performs no model call, candidate
execution or code verification. It does not resume or rerun the receiver.

Take the receiver task ID from `ROOT/terminal-run/result.json` at
`flow.handoff.task_id`. Select that receiver's `relay-*-proposal-stored.json`
receipt in `ROOT/terminal-run/receipts` and use its `context_id` and
`content_sha256`. Check that the selected context belongs to the receiver task;
the producer proposal pin in `flow.handoff.pin` is a different document.
Only the exact `review.md` publication at context version1 is supported.

```sh
/path/to/venv/bin/python -I -B /path/to/Amadeus/examples/review_relay_document.py \
  --root /path/to/isolated-project --project-id PROJECT_ID \
  --task-id RECEIVER_TASK_ID --context-id RECEIVER_CONTEXT_ID \
  --content-sha256 RECEIVER_CONTENT_SHA256 --decision accept \
  --evidence "I inspected this fixed document; this is not code verification."
```

Use `--decision reject` to reject it instead. Enter the existing owner token at
the hidden prompt. Each invocation registers and authorizes a fresh reviewer;
its credentials remain in memory, including when you decline confirmation.
The preview shows the actual document, task version, fixed context hash,
reviewer, decision and evidence. Type its exact SHA only to submit that decision.
A mismatch submits no review. The helper rereads the same context version and
current task before its single `review_task` call; unrelated newer context
revisions do not replace the reviewed version.

Acceptance changes the document task to `completed`; rejection returns it to
`pending`. The output reports Core's actual `task_verification`, which remains
`unverified` for ordinary document review. Code candidates, a different project,
a stale task/publication or an incorrect content hash are refused. Keep the
owner credentials; none are printed or saved by this helper. If interrupted or
the outcome is unknown, inspect the task before another decision. There is no
automatic retry or receiver restart.

This document-review entry does not repair a failed model turn. The published
a122/r5 terminal publishes a proposal only after a successful model result; it
does not publish an unfinished progress checkpoint. Earlier composed-recovery evidence
used an explicitly host-authored checkpoint and does not establish automatic
model-progress recovery for this example.

The current entry adds bounded task/case reads, with14 passing affected Windows
checks and4 Linux-only skips. No new Linux or real-model run accompanied that
input-reading change. [Repair evidence](acceptance/evidence/core-preview-a122/terminal-input-bounds/summary.json).

The earlier repaired terminal entry (7085ec0) completed one authorized real
run on the frozen a122 runtime: two Codex subscription calls, one exact149-byte
addition candidate execution,2/2 cases and19 isolation checks. The producer is
completed/v6/verified by a distinct Core identity; the receiver submitted review.md
and remains review/v5/unverified. Five effect decisions used seven manual input
lines. This proves a controlled pinned-proposal relay, not unattended operation
or an M3 same-task handoff (the M3 handoffs table has no row in this experiment).
Both model processes ended normally; temporary login cleanup and unchanged
original credentials were confirmed. [Actual evidence](acceptance/evidence/core-preview-a122/terminal-repaired/result/summary.json).
Formal Release gates remain unchanged and BLOCKED.

[Recorded checks](acceptance/evidence/core-preview-a122/terminal-host/summary.json)
cover both installed Windows/Linux runtimes, the exact approval refusals and
the receiver's actual local process exit. A resolved wave alone is not success:
the receiver must actually reach review with its matching ready-for-review result.
The first real terminal-entry attempt stopped before launch admission when
blocking input outlasted the task deadline. Its adapter remains unknown, and its
Core task remains running without verification; no candidate was executed.
Temporary login cleanup was confirmed. The input repair subsequently passed
12 local Linux cases and8 Windows cases (4 Linux-only skips), including real PTY
cancellation and terminal restoration. Those offline checks are distinct from
the newly authorized successful real run above. Do not replay the failed fixture.
[Actual attempt](acceptance/evidence/core-preview-a122/terminal-live/result-summary.json) ·
[Repair evidence](acceptance/evidence/core-preview-a122/terminal-live/input-fix/summary.json).
