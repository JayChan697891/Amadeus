# M0-M2 implementation contract

Python >=3.11. Distribution name agentsync-local; import agentsync. Version 0.1.0a1.
MCP official SDK mcp==2.3.0, v2 MCPServer (verify installed API).

Core is `agentsync.core.service.Core(data_dir: str | Path | None = None)`.
`Core.execute(operation: str, payload: dict[str, Any]) -> dict[str, Any]` dispatches
only the allowlisted operations below with Pydantic strict schemas (extra forbid).
Raises `agentsync.errors.AgentSyncError(code, message, status_code=400)`.
All entrypoints use this method; no transport-specific business logic.
Output envelopes: success `{"ok": true, "data": {...}}`, error
`{"ok": false, "error": {"code": "...", "message": "..."}}` at transport/SDK boundary.
Core.execute returns raw data (not envelope).

Data path: explicit absolute data_dir or AGENTSYNC_DATA_DIR (absolute required), otherwise
platform user-data directory / AgentSync (absolute and cwd-independent); database agentsync.db.
Do not store demo/test state in the user's default data directory.

Operations and payloads (all identifiers are strings):
- create_project: name, root_path (absolute existing directory); returns project_id, admin_token (one time).
- register_agent: project_id, admin_token, name, capabilities: list[str]=[]; returns agent_id, session_id, session_token, expires_at.
- heartbeat: project_id, session_id, session_token; returns expires_at.
- create_task: project_id, session_id, session_token, title, description="", priority=0,
  dependencies: list[str]=[], request_id (required); returns task dict.
- list_tasks: project_id, session_id, session_token; returns tasks list.
- get_project_state: project_id, session_id, session_token; returns project and agents/sessions/tasks without credentials.
- claim_task: project_id, session_id, session_token, task_id, expected_version:int,
  lease_seconds:int=300, request_id; returns task dict including lease_token, lease_expires_at.
- renew_lease: project_id, session_id, session_token, task_id, lease_token, expected_version,
  lease_seconds:int=300, request_id; returns task dict.
- update_task: project_id, session_id, session_token, task_id, lease_token, expected_version,
  status (running/review/blocked/failed/cancelled), result: str="", request_id; returns task dict.
- review_task: project_id, session_id, session_token, task_id, expected_version,
  accept:bool, evidence:str, request_id; separate agent required, review -> completed or pending.
- reclaim_expired: project_id, session_id, session_token; expired claimed/running/blocked
  -> pending, invalidate lease and increment version; returns reclaimed task IDs.

Task dict must include id, project_id, title, description, priority, status, version,
owner_session_id, result, dependencies, created_at, updated_at.
Public task dictionaries also include latest_review (null or reviewer IDs, evidence, decision,
timestamp and resulting task version). Schema v2 keeps append-only review history;
v1 migration preserves existing evidence without inventing unknown reviewer identity.
Only the owner gets lease_token in claim/renew responses; no tokens in list/state.
Session TTL 3600s; online derived from heartbeat (e.g. <=120s) and not expired.
Lease 1..3600s. Claim pending only after all dependencies completed. Use BEGIN IMMEDIATE,
conditional version checks, hashed session/admin/lease credentials, expiry/ownership checks.
Idempotency scoped to project/session/operation/request_id; different payload on same key rejected.
Replay writes must authenticate and never resurrect an expired lease. Timestamps epoch seconds.
Review evidence is a human/reviewer assertion in Alpha, not automatic test execution.
Never run arbitrary submitted commands. Full independent evidence verification is M5.

SDK: `AgentSyncClient(data_dir=None).call(operation, **payload)` returns envelope.
HTTP: `create_app(data_dir=None, api_token=None)`; bearer api_token required for all /v1 operations,
  POST /v1/{operation}; /health returns only status/version; CORS off; local host validation.
MCP: `build_server(data_dir=None)` registers explicit typed tools (same operation names).
Concrete modules: agentsync.integrations.http, agentsync.integrations.mcp and
agentsync.sdk.client (class also exported from agentsync.sdk).
CLI: `python -m agentsync mcp`, `serve --host 127.0.0.1 --port 8765`, `demo --data-dir PATH`.
Global `--data-dir PATH` before subcommand supported. serve requires AGENTSYNC_HTTP_TOKEN.
Demo uses A/B sessions, rejected duplicate claim, review, reopen DB and assert persistence.

Lead owns packaging/docs/CLI (CLI may be delegated), reviewers own independent tests;
core implementer owns core/, storage/, errors.py, config.py, models.py;
integration implementer owns integrations/, sdk/, cli.py, __main__.py, examples/.
