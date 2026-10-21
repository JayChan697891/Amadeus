# Explicit cleanup receipt: owner operation guide

This internal trusted service library adds a single cleanup attempt for an
expired execution with a durably acknowledged full container ID. It is not a
scheduler, retry policy, task acceptance gate or general Docker management API.
See M5B2C-CONTRACT.md for the security boundary.

```python
from agentsync.verification.reconciliation import OwnerExecutionReconciler

service = OwnerExecutionReconciler(core)
current = service.get(project_id=project_id, admin_token=admin_token, job_id=job_id)
receipt = service.reconcile_once(
    project_id=project_id,
    admin_token=admin_token,
    job_id=job_id,
    expected_version=current["version"],
    request_id=request_id,
)
```

Credentials come from the owner's existing private channel. Do not place them in
command arguments, logs, Git, candidate content or agent messages. No equivalent
operation is exposed through HTTP, MCP, SDK or the generic owner CLI.

The lease must have expired. A live lease, wrong version, unknown create reply or
invalid identity fails before Docker. After an accepted request, the previous
worker is fenced and this execution's single cleanup opportunity is consumed.
Repeating the same bound request only reads the receipt; it never resumes Docker.
Another request cannot grant a second attempt.

Read `reconciliation.outcome` separately from `assessment`:

| Observation | Meaning | Execution assessment |
| --- | --- | --- |
| No receipt | Cleanup has not been claimed | Unverified for an expired execution |
| intent / unresolved | Cleanup process has not durably recorded its observation, including possible crash or storage failure | Unverified |
| recorded / unresolved | Identity, daemon, removal or absence was not established | Unverified |
| recorded / removed_and_absent | Matching object was removed by full ID, removal acknowledged and absence observed on the same daemon | Unverified |

Even the last row leaves job status `cleanup_pending`, original
`cleanup_confirmed=false` and candidate result unchanged. It permits neither job
reuse nor source application. A container already absent before this operation is
not counted as a proven removal; a lost create response may still arrive later.
An interrupted receipt requires future separately designed recovery, not a new
request or a manual edit of the service database.

## Local acceptance design

The seam under test is `reconcile_once/get` plus the existing executor's observable
fencing. Policy tests use disposable SQLite and injected clock/CLI failures;
they cannot establish Docker isolation. Real integration tests create dedicated
Git projects, terminate the actual trusted executor process, reopen the DB, and
invoke the real Docker cleanup. Lease expiry is injected into test-only data to
avoid a five-minute wait. Source, fresh wheel and isolated sdist run independently.

Save JUnit, sanitized logs, frozen source SHA/tree, package/module hashes,
reconciliation observations, image/daemon identity and a final exact-ID container
inventory under the run's evidence directory. Keep unsanitized private runtime on
D: only. The full supported OS/Python matrix, real model clients, autonomous relay,
safe apply and formal M9 release remain separate blocking gates.
