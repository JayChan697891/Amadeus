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
| Codex control adapter | [Actual Linux same-Core pipeline at a2634ec](evidence/m6-linux-live/summary.json); earlier actual fixed-reply and same-client relay evidence in the Release Acceptance Report | One actual pinned0.167 CLI proposal, immutable Core capture/review, owner-approved candidate,8/8 real local Docker inputs, distinct host-mediated Core completion and reopened completed/v6/verified state; exact source and runtime hashes | **SCOPED PASS**, not whole-client/Release acceptance. Independent model review, unattended application, active-generation timeout and server/descendant cancellation remain unverified. Billing was owner-confirmed, not independently verified. |
| Claude Code control adapter | `evidence/claude-adapter-local-20261026.json`; known-Python-helper/Core tests; current fixture-tested opt-in process factory | Six-method protocol prototype plus pinned plan/capture wiring; default startup unsupported, Core tasks unchanged, actual client unverified | **ACTUAL CLAUDE NOT RUN**: owner has no subscription. Permissions, billing, server cancellation, tree cleanup and autonomous relay unverified. |
| Cursor control adapter | Terminal JSON parser, host-factory CursorAdapter, pinned process/native Node-bundle planning and known local Python/Core fixtures; [bundle evidence](evidence/m6-cursor-node-bundle/summary.json) | Bounded protocol and opt-in host preparation; default startup unsupported; local fixtures do not establish a real client run | **ACTUAL CURSOR NOT RUN / NOT VERIFIED**: owner has no subscription. Supported real CLI execution and OS/permission/cancellation/relay evidence remain required. |
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
