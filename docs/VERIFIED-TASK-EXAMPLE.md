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

- Install the frozen a122 wheel in a Python environment. Run this repository's
  example using that environment's Python; no editable installation is needed.
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
- Write your task in a UTF-8 file (at most 1000 bytes). The supported output is a
  standalone `solution.py` that reads and writes one JSON value per line.
  Write owner-defined cases as a JSON array, for example:

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

Validation of this terminal example is separate from the earlier bounded real
Codex experiments. Offline protocol/verifier fixtures do not establish real
client acceptance. Formal Release gates remain unchanged and BLOCKED.
