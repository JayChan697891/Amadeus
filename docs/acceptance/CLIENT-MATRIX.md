# Real client acceptance matrix

This matrix records evidence boundaries for the current implementation. A stored
connection probe is historical evidence, not proof that a current client installation
still works. Native same-task Codex development agents are not AgentSync adapters.
No paid inference calls are authorized by this acceptance checkpoint.

| Client / interface | Existing evidence | Verified scope | Missing release evidence / status |
|---|---|---|---|
| Codex public app-server MCP | [a118 actual native probes](evidence/recovery-preview-a118/clients/summary.json); historical `../codex-host-probe.json` retained | Installed0.162.0 discovers34 tools; two deterministic identities create/claim/submit/text-review task v1→v5, share pinned context v1, reject duplicate claim, and reopen task/context through a new host. Zero inference; current package members unchanged | **SCOPED PASS**. Only recorded operations invoked; not all34 tools or structured handoff API. Text review stays unverified. Desktop UI and model-driven relay are not established by this probe. Original connection failure remains recorded with unknown concrete cause. |
| Codex public app-server MCP, a121 handoff supplement | [One native run and preserved failure](evidence/core-preview-a121/native-handoff/summary.json), probe36a672d; unchanged installed4b82494 runtime | Actual deterministic MCP calls observed submit/get/resolve_handoff, recipient fresh lease and review/v8, pinned context v1/latest v2, old-lease/nonrecipient/lock rejection, released metadata locks and fresh-host reads. Zero inference; two host EOF exits and seven MCP children ended. Root read-only inspection matched18 audit events. | **BLOCKED**: final owner-Core audit assertion expected null instead of schema default0. One-line probe fix a9cbcfe passes a separate local Core check. The corrected native run remains **NOT RUN on a121**. See the separate a122 result below. |
| Codex public app-server MCP, a122 frozen handoff | [One corrected native run](evidence/core-preview-a122/native-handoff/summary.json) on Windows 3.12 with Codex 0.162.0 and a122 wheel5232e9e | Two identities complete structured handoff and fresh-host reads. The recipient uses a fresh lease to reach review v8 with zero reviews recorded. Context stays pinned at v1 while v2 is latest. Four lease, identity and lock denials hold, and both metadata locks are released. Root verifies 18 audit events through a read-only owner inspection. Two hosts exit normally by EOF and seven MCP children end. | **SCOPED PASS**, accepted by Root and Astra, with zero inference and unverified task output. Desktop UI, the MCP audit tool, Git merge conflicts, independent candidate verification, real-model relay and formal Release remain unverified. |
| Claude Code CLI MCP | [a118 actual health check](evidence/recovery-preview-a118/clients/claude/result.json); historical `../claude-host-probe.json` retained | Installed2.1.295 public MCP CLI connects to the a118 installed server in a new isolated configuration;4 native commands exit0; zero model prompts/credentials | **SCOPED PASS** for health connection only. Tool calls, desktop UI, control adapter and model-driven relay remain **NOT RUN**. |
| Cursor MCP / CLI | Local inventory found desktop3.27.22; no standalone agent CLI on PATH or confirmed zero-inference MCP health interface | No execution claim | **NOT EXECUTED**. Desktop presence is not MCP/control-adapter compatibility. |
| Codex control adapter | [Continuous installed09425da flow](evidence/m7-continuous-live/summary.json); historical runs retain their own SHA scope | Two real pinned0.167 CLI identities in one continuous flow: immutable proposal, exact host decisions,8/8 local Docker/19isolation checks, independent Core verified producer, automatic dependent task/context handoff, full model review and separate host document acceptance; normal reopen with no new launch | **SCOPED PASS** for same-vendor gated collaboration, not whole-client/Release acceptance. Four explicit host decisions were involved; review text stays unverified. Cross-vendor behavior, unattended application and active-generation timeout remain unverified; unsupported cancellation/resume capabilities stay declared rather than inferred. Billing is owner-confirmed only. |
| Codex control adapter, a122 composed recovery | [Original real calls and final same-task verification](evidence/core-preview-a122/composed-recovery/verification/summary.json), frozen5232e9e and pinned0.167 CLI | Two real calls: interrupted producer and distinct receiver; persisted receiver proposal survives actual controller exit73 and fresh-controller reconciliation without new inference. One separately approved Docker run passes2/2 and19 isolation checks; a fresh independent Core reviewer completes that same task v6/verified. Root/Astra inspected exact records and cleanup. | **SCOPED PASS**, same vendor and owner-mediated decisions. Final verification made zero model calls and is not another model review. Source remains failed; full M6/M7/M8, in-flight generation recovery, provider cancellation, whole-machine recovery and formal Release remain unaccepted. |
| Claude Code control adapter | `evidence/claude-adapter-local-20261026.json`; known-Python-helper/Core tests; current fixture-tested opt-in process factory | Six-method protocol prototype plus pinned plan/capture wiring; default startup unsupported, Core tasks unchanged, actual client unverified | **ACTUAL CLAUDE NOT RUN**: owner has no subscription. Permissions, billing, server cancellation, tree cleanup and autonomous relay unverified. |
| Codex control adapter, a122 repaired terminal entry | [One real terminal flow](evidence/core-preview-a122/terminal-repaired/result/summary.json), frozen5232e9e runtime and7085ec0 example | Two real calls return proposals; one exact149-byte candidate passes2/2 Docker cases and19 isolation checks. A distinct Core identity completes the producer v6/verified before the receiver is created and receives pinned context. Temporary login cleanup, original-login identity and97 runtime members checked. | **SCOPED PASS**, Root/Astra accepted this manually approved Linux example. Receiver review remains unverified. Five effect decisions required seven manual lines. This is a pinned-proposal relay, not M3 same-task handoff, unattended autonomy, other clients or formal Release. |
| Cursor control adapter | Terminal JSON parser, host-factory CursorAdapter, pinned process/native Node-bundle planning and known local Python/Core fixtures; [bundle evidence](evidence/m6-cursor-node-bundle/summary.json) | Bounded protocol and opt-in host preparation; default startup unsupported; local fixtures do not establish a real client run | **ACTUAL CURSOR NOT RUN / NOT VERIFIED**: owner has no subscription. Supported real CLI execution and OS/permission/cancellation/relay evidence remain required. |
| Other compatible MCP clients | Generic protocol integration tests | Official SDK protocol interoperability only | Client-specific capabilities **NOT VERIFIED** until a named installed client is exercised. |
| Python SDK / HTTP | Existing integration tests in `tests/integration` | Actual Core calls, HTTP transport checks and real MCP process scenarios as identified by each test | These are transport evidence, not proof of an LLM client or autonomous model relay. |
| Mock adapter | Implemented MockAdapter and instance-local MockRunManager; unit and Core-boundary integration tests | In-memory simulation and public planning compatibility only; no real client execution or Core task mutation | Simulation-only, real client capability **UNVERIFIED**; never substitute for any row above. |

## Required real-client procedure

The a122 test used the corrected probe with a new fixture and a pinned installed
wheel. Its executed command and terminal receipt are preserved.
[a122 execution record](evidence/core-preview-a122/native-handoff/execution.json).
The original a121 run retains its BLOCKED result and its own command and source
identity. [a121 execution record](evidence/core-preview-a121/native-handoff/execution.json).

Current a118 probe commands, from the repository with an installed a118 environment:

```powershell
& D:\agentsync-debug\m118p\w\Scripts\python.exe -I -B tests\manual\probe_codex_collaboration.py
& D:\agentsync-debug\m118p\w\Scripts\python.exe -I -B tests\manual\probe_claude_host.py --claude-binary "$env:APPDATA\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"
```

Each creates a new D-drive fixture and retains its own result. Raw stderr, home/config
and databases stay local; only sanitized public evidence is archived. These probes
do not invoke inference or edit shared configuration. That boundary is supported by
code and actual fixture inspection, not a full hash inventory of shared files.
The older shared `probe_registered_codex.py` retains historical11-tool assumptions;
it was not run or updated by this checkpoint. Do not use it as current acceptance.

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
