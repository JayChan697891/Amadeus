# Real client acceptance matrix

This matrix records evidence boundaries for the current implementation. A stored
connection probe is historical evidence, not proof that a current client installation
still works. Native same-task Codex development agents are not AgentSync adapters.
No paid inference calls are authorized by this acceptance checkpoint.

| Client / interface | Existing evidence | Verified scope | Missing release evidence / status |
|---|---|---|---|
| Codex public app-server MCP | `../codex-host-probe.json`; `../M2-CONTINUATION.zh-CN.md` | Historical real installed host connected, discovered 11 original tools, called create_project/register_agent/create_task/list_tasks; zero inference turns | Current 33-tool client compatibility, complete task/handoff/review workflow and model-driven relay **NOT VERIFIED**. Desktop connected status was separately user-reported, not automated UI evidence. |
| Claude Code CLI MCP | `../claude-host-probe.json`; `../M2-CONTINUATION.zh-CN.md` | Historical real installed CLI health check connected using isolated configuration; zero model prompts | Tool calls explicitly not tested; full current tool workflow and model-driven relay **NOT VERIFIED**. |
| Cursor MCP / CLI | No real client execution evidence recorded | None | **NOT EXECUTED**; installation, supported interfaces and current OS support require verification. |
| Codex control adapter | `evidence/codex-adapter-integrated-smoke-20261025.json` and authentic JSONL; offline lifecycle/Core tests | One separately authorized installed-wheel host-factory + pinned readonly plan + explicit-env actual response: exit0,4 events, exact token;19 hashes/Core pending state unchanged | **LIMITED ACTUAL RESPONSE VERIFIED**; no default live launcher. Permissions, real timeout/server cancellation, restart and autonomous relay **UNVERIFIED**; no whole M6-03 acceptance. |
| Claude Code control adapter | M6-04 specification only | No implemented AgentSync control adapter | **NOT IMPLEMENTED / NOT VERIFIED**; require actual SDK/CLI run with explicit tool permissions and authentic result collection. |
| Cursor control adapter | M6-05 specification only | No implemented AgentSync control adapter | **NOT IMPLEMENTED / NOT VERIFIED**; require actual supported CLI run on each claimed OS, result/exit/timeout handling. |
| Other compatible MCP clients | Generic protocol integration tests | Official SDK protocol interoperability only | Client-specific capabilities **NOT VERIFIED** until a named installed client is exercised. |
| Python SDK / HTTP | Existing integration tests in `tests/integration` | Actual Core calls, HTTP transport checks and real MCP process scenarios as identified by each test | These are transport evidence, not proof of an LLM client or autonomous model relay. |
| Mock adapter | Implemented MockAdapter and instance-local MockRunManager; unit and Core-boundary integration tests | In-memory simulation and public planning compatibility only; no real client execution or Core task mutation | Simulation-only, real client capability **UNVERIFIED**; never substitute for any row above. |

## Required real-client procedure

For each claimed client and OS, use a dedicated temporary project and database,
record package version, commit SHA, OS, Python and client versions, supported public
interface and sanitized configuration. Discover tools and execute task creation,
claim, context publication, structured handoff, independent review and conflict
checks with two separately authenticated actors. Record tool responses and task
state transitions. Keep credentials and provider secrets out of logs.

For control adapters additionally collect actual process/session/run identifiers,
sanitized command/API inputs, stdout/stderr or SDK events, exit code, cancellation,
timeout and unsupported-operation results. Rate limits require an actual controlled
client/provider error or a separately labelled simulation; a simulated 429 does not
establish real provider behavior. Paid execution needs the user's authorization.

The final automatic relay gate requires two real supported agent executions to
transfer work without human copy/paste, collect result evidence, independently
accept/reject the work and settle the final task state. Preserve the complete
sanitized trace and explicitly record any human intervention. Two Python protocol
clients or a Mock adapter do not satisfy this gate. Until this exists, release
acceptance remains blocked even if all unit/integration checks pass.

Store new client runs under the release evidence directory's `clients/<client>/`
with a manifest and logs. A missing CLI, credential, interface, approval or network
dependency must produce **LIMITED / NOT EXECUTED**, with its reason, rather than a
passing test or a fabricated capability. Re-run historical probes for the release
candidate; do not silently promote them to current evidence.
