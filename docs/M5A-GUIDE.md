# M5A owner control and security migration

Version0.3.0a1 / schema6 development checkpoint. Consult the actual final PR and
Release Acceptance Report for executed status; this guide is not proof of acceptance.

## Upgrade behavior

Back up the stopped local database before upgrading an actual installation. Core
migrates schemas1-5 transactionally to6, preserving task/context/review/lock/worktree
history. All legacy agents initially receive viewer only, membership version1.
This intentionally removes implicit write/review permissions until the project
owner explicitly regrants them. Agent IDs/session credentials persist; possession
of an old session token does not bypass current role authorization or cached replay.
This development task changes only isolated test databases, not the user's live MCP
installation or its stored project grants.

## Roles

- viewer: project task/context/handoff/resource metadata and own approval reads;
  heartbeat allowed. No mutations, Git comparison/creation or review.
- worker: viewer plus task/context/handoff/lock/managed-worktree operations and
  approval requests. It does not grant review or owner authority.
- reviewer: viewer plus review_task and project audit queries. Self-review remains
  forbidden even if an agent also has worker.
- empty role set: revoked; all session operations, including heartbeat, denied.

Capabilities/names/model messages never grant roles. set_agent_roles replaces the
whole role set using optimistic expected_version. Current roles are checked before
idempotency cache, resource existence or Git construction. Unknown new operations
are denied until explicitly assigned a permission.

## Owner channel

Owner operations require project_id and admin_token, separately from session auth.
Use SDK owner_call, `agentsync owner OPERATION` with a JSON object on stdin, or
loopback HTTP POST /owner/v1/OPERATION with its bearer token plus owner body auth.
CLI stdin is limited to64KiBUTF8 and rejects deeply nested/reserved-field input
before creating state. Owner methods are absent from MCP and ordinary /v1 routes. Keep admin tokens in the
owner channel; never paste them into Agent prompts, files committed to Git or logs.
Do not pass secrets as command-line arguments. For a local SDK operation:

```python
from getpass import getpass
from uuid import uuid4
from agentsync.sdk import AgentSyncClient

client = AgentSyncClient(ABSOLUTE_PRIVATE_STATE_DIRECTORY)
owner = {"project_id": PROJECT_ID, "admin_token": getpass("Project owner token: ")}
members = client.owner_call("list_members", **owner)
# Inspect the selected member's current version before replacing its grants.
result = client.owner_call(
    "set_agent_roles",
    **owner,
    agent_id=SELECTED_AGENT_ID,
    roles=["worker", "reviewer"],
    expected_version=OBSERVED_MEMBER_VERSION,
    request_id=str(uuid4()),
)
assert result["ok"], result.get("error", {}).get("code")
```

The capitalized identifiers are local values to supply, not literal credentials.
A demo grants its two simulated actors explicitly using the separate owner SDK.
No global test patch or implicit auto-grant is part of the application.

## Approval metadata

A worker can request approval only for a same-project immutable merge candidate,
with exact subject SHA, bounded lifetime and request identity. The owner can approve,
deny or revoke with expected version; expired/revoked decisions cannot be revived.
Agent reads expose only its own requesting-agent records. Public responses omit
freeform reason. No submitted text/command is executed. The candidate remains
awaiting_human_approval: approval does not apply or merge into the original repo.
M5B must separately implement atomically consumed approval bound to exact action,
requester, resource/version/SHA and current roles before any risky operation.

The admin capability does not prove a real human against another same-OS-user
process. Do not advertise human-proof authorization or hostile-process isolation.

## Audit and independent review

API audit records are append-only and use a fixed metadata whitelist: actor IDs,
operation/outcome/code, validated target IDs, versions, request digest and timestamp.
No payload/result/reason/command/path/token is recorded. Business writes and successful
audit are one transaction. Authenticated denials record only safe metadata after
rollback; unauthenticated foreign-project inputs do not create cross-project events.
Owner/reviewer queries are project scoped. No tamper-proof claim against a DB owner.

review_task still records a distinct Agent's asserted evidence. It does not execute
or authenticate tests independently. A pytest/setup/import allowlist is insufficient:
submitted code requires an actual verified OS sandbox with no host credentials,
network, writable host workspace or service DB. No such verifier is implemented by
M5A; absence of a usable runtime must fail closed, not fall back to local execution.
The formal release and real autonomous two-client relay remain BLOCKED/unverified.
