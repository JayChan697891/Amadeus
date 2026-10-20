# M5A permissions, owner approvals and audit (Issue #11)

Parent PR10 head98bd361, version0.3.0a1, schema6. Scope M5-01/02/03 plus security
regression; M5-04 sandbox verifier and actual approved application are separateM5B.
No paid calls, main writes, arbitrary command execution or source merge/apply API.

## Permission boundary

Membership roles is exact bounded SET viewer,worker,reviewer (viewer implied by
worker/reviewer); empty set revokes. New and migrated legacy agents default viewer,
version1; owner must deliberately regrant write/review roles after migration. Preserve
all existing history/tokens/tasks. This is an intentional security migration. Same-agent
self-review still forbidden. New operation permissions fail closed. Check current roles
after session authentication and BEFORE idempotency replay/object lookup/Git construction.
Session/agent names, capabilities and model assertions never grant roles.

Viewer operations: heartbeat,list_tasks,get_project_state,get_context,search_context,
get_handoff,inspect_path,verify_file_version,list_file_locks,inspect_worktree,
get_approval,list_approvals (approvals restricted to requesting agent).
Worker adds all existing task/context/handoff/lock/workspace mutations/compare plus
request_approval. Reviewer adds review_task,list_audit. Empty roles deny even heartbeat.
create_project/register_agent retain explicit bootstrap admin semantics, no roleparam:
register_agent always viewer. Current review_task is ASSERTED evidence, never rename
it independent verified execution; M5B must add actual verification gate.

## Separate owner control plane

Core.execute_owner(operation,payload) / SDK.owner_call use AdminAuth(project_id,
admin_token). HTTP /owner/v1/{operation} retains loopback+bearer AND admin credential.
CLI owner OP reads one JSON object from stdin (not credential command args/env echo).
Owner operations are NOT in MCP discovery or ordinary Core.execute OPERATIONS.
Admin capability is separate owner authority, not proof of physical human identity
against same-OS-user access. Do not place admin credentials in normal agent state.

Owner operations:
- set_agent_roles(agent_id,roles,expected_version>=1,request_id): exact replacement,
  project scoped, version increment, optimistic concurrency, bounded valid unique roles.
- list_members(limit<=100,offset<=10000): bounded role/version membership metadata.
- decide_approval(approval_id,expected_version,accept:bool,request_id): pending to
  approved/denied only, no expiry extension. Approval NEVER executes anything.
- revoke_approval(approval_id,expected_version,request_id): pending/approved to revoked.
- list_audit(limit<=100,offset<=10000): current project, safe structured records only.
All owner mutations have own project/operation/request idempotency and payload digest;
no cleartext admin in cached response. Authenticate owner before any replay/lookups.
Replayed decisions must recheck current status/version/expiry; never revive approvals.

Agent operations (four typed MCP additions,33total):
- request_approval(action='apply_merge_candidate',subject_id,subject_sha(fullhex),
  reason<=2000,expires_in1..3600 default300,request_id): worker only, resolves current
  same-project immutable candidate and exact SHA; derive subject_version1. Approval
  authorizes a future operation only. No apply endpoint is added in this stage.
- get_approval(approval_id): viewer, own requesting agent only, no foreign disclosure.
- list_approvals(limit,offset): viewer, own requesting agent only.
- list_audit(limit,offset): reviewer, current project only.
Public approval record: id,project_id,requester_agent_id,action,subject_id,subject_sha,
subject_version,version,status pending|approved|denied|revoked|expired,created_at,
updated_at,expires_at. Freeform reason is metadata only, not executed; never echo
into audit/errors/normal public response. Owner can inspect pinned resource separately.
Expiry derived at read, decisions deny expired; future consumption must be single-use
transactionally bound exact requester/action/resource/version/SHA and effective roles.
M5A does NOT claim consumption/application is implemented.

## Audit

Append-only API records via safe whitelist: event_id,project_id,actor_kind/id,
operation(enum/fixed unknown),target_id(if validated),outcome/code,pre/post_version,
request_id_digest,time. NEVER raw payload/result/reason/command/path/token or exception
repr. Successful writes and audit in same transaction. Denials after rollback use
bounded separate transaction for verified actor/project only; unauthenticated inputs
must not pollute/leak foreignproject or log credential-bearing text. Audit failure must
not permit an otherwise unauthorized write. No update/delete audit API. Do not claim
tamperproof against database owner/sameOS. Unknown malicious tool text remains data.

## Legacy tests and acceptance

Do not weaken old assertions or monkeypatch permissions globally. Update fixtures,
process demos and integration setup to explicitly ownergrant required worker/reviewer
roles through separate channel. Newtests must exercise true defaultviewer/revoked
behavior, every operation/role, grant optimisticversion/replay, owner/sessionboundary,
crossproject/invalidIDs, approvalexpiry/revoke/duplicate, rolesrevokedaftercachedwrite,
secret-free audits/errors and v1-v5 migrations preserving existinghistory. Real MCP
process test must prove owner methods absent and grants happen out of band; HTTP/SDK/
CLI owner semantics separately tested. All destructive fixtures under F temp projects.
Report new behavior and migration clearly; actual sandboxed verifier and real model
client relay remain not_run/unverified and formal Release Acceptance BLOCKED.
