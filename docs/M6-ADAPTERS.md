# M6 host-factory adapter prototype

`agentsync.adapters.codex.CodexAdapter` implements the six generic `AgentAdapter`
methods. It composes `CapturedProcess` and the bounded Codex JSONL parser. The
default adapter has no launcher. The explicit trusted-host helper described below
can connect a pinned plan to a process; no credential reader, Core dispatch or
network client is added to the adapter.

```python
adapter = CodexAdapter("project", "session")
capabilities = await adapter.capabilities()
assert capabilities.supports_start is False
```

Without a factory, `start_task` returns `unsupported` before registering a run.
An explicitly supplied trusted-host async factory receives a validated
`AdapterTask` and must return a fresh, exclusively owned `CapturedProcess` created
after that request. Its argv must come from trusted host code; task instructions
are data, never scripts. A callback or process ID is not human authorization.
Freshness uses a private process-local creation ordinal plus same-event-loop
association, rather than strict timestamp inequality: coarse clock ticks may give
a fresh capture the same public start time as its run. Older, reused and foreign-
loop captures remain unowned/uncancelled. Ordinals are not serialized, credentials
or restart identities; public timestamps and timers retain their original meaning.
Actual client integration still requires the existing M5 safety gates and a new
explicit live-test authorization. Both separately authorized single real CLI tests are now consumed.

## Opt-in pinned Codex process factory

`agentsync.adapters.codex_process.CodexProcessFactory(profile, environment=explicit_env)`
copies a `CodexHostProfile` and a filtered explicit environment without launching.
A trusted host can pass it as `CodexAdapter(..., contextual_factory=factory)`;
it cannot combine this with the existing `factory` argument. Each invocation
prepares the task afresh, including binary/root checks, then forwards the exact
fixed argv, cwd, stdin, timeout, output limit and explicit environment to capture.
No CLI command, automatic workflow or Core operation enables this path.

The adapter issues a `LaunchContext` for that exact task/run/event loop. Before
capture entry it synchronously checks observed stop state and the original run
deadline, and consumes one local attempt. Failed or uncertain starts consume it
too. The check and capture entry have no intervening await. This is an in-memory
observation, never human/Core authorization, approval consumption or a persistent
reservation. Fresh authorization remains required for every actual model run;
attaching the reusable factory authorizes none. The earlier two grants are spent.

Preparation uses a worker thread, which can continue after a stop and has no hard
I/O deadline. A stop observed before capture entry prevents that attempt; OS
creation already scheduled can still finish late. Keep the loop alive for owned
late-parent cleanup. The original adapter deadline and the plan's capture timeout
are separate observations, not a hard end-to-end execution bound. The helper is
not an OS sandbox or proof of subscription-only billing, unreadable credentials,
client compatibility, server cancellation or descendant cleanup. Tests with a
start spy establish fixed argument wiring; owned Python children establish local
lifecycle behavior. Neither is an actual Codex invocation or formal acceptance.

## Lifecycle and result semantics

- Start returns `starting`; the independent background driver invokes the factory
  once. Caller cancellation and request replay do not spawn another process.
- Namespace mismatch, conflicting request inputs, active/unknown duplicate task,
  running capacity and retained-history limits reject before another factory call.
- States are `starting`, `running`, `succeeded`, `failed`, `unknown`. Complete
  protocol plus exit0 permits protocol success, never Core task acceptance.
  Nonzero exit records process failure, not an authoritative server-task result.
- Invalid UTF-8/JSON, incomplete output, capture limits, local timeout/cancel or
  uncertain factory outcomes become `unknown`; partial messages are not promoted.
  Unknown runs retain their instance slot and cannot be automatically replaced.
- Reused or preexisting captures are rejected without cancelling them: another
  task or caller may own that handle. Capture ownership is per instance only.
- `cancel_task` can request only owned-parent termination. It does not acknowledge
  server cancellation or prove descendant cleanup. `resume_task` is unsupported.
- A late factory result can be observed and its fresh owned parent stopped, but
  cannot rewrite a frozen unknown result or release that uncertain slot.

`get_result` is private caller data: completed messages, unverified counters and
an optional client thread ID. Do not blindly log it or treat an ID as a credential.
Snapshots contain no prompt, argv, stdout or stderr. Records are frozen and always
state `real_client_verified=False`, `verification=unverified`,
`core_authorization=unverified`, `tree_cleanup=unverified`.

## Explicit limitations

The factory is trusted Python code and may never return. Its logical deadline
freezes unknown, but does not prove that all its work stopped. Keep the same
event loop alive for late cleanup. The mechanical process layer inherits the
host environment by default or copies an explicitly supplied bounded dictionary.
Neither mode is a sandbox. A controlled factory-delay cancellation
test is not proof of a strict OS process-creation timeout.

History, request deduplication, capture ownership and capacity are in-memory for
this adapter instance; no cross-instance, cross-process, restart or server quota
guarantee is made. No persistence, approval consumption, safe apply or automatic
task verification was added. Mock records retain their existing simulation flags;
generic return types do not turn them into real-client evidence.

Offline tests use known local Python helpers and hand-authored JSONL. One separately
authorized actual installed-wheel adapter+plan+explicit-env run returned a synthetic
inline token successfully; it did not use tools or complete a Core task. Permissions,
server cancellation, real timeout, Claude, Cursor and autonomous relay remain
NOT RUN/UNVERIFIED. See RELEASE-ACCEPTANCE-REPORT.md for exact evidence.

## Optional pure host invocation preparation

`agentsync.adapters.codex_invocation` provides an immutable host profile and pure
`prepare_invocation(profile, task, environment=...)`. It validates namespace before
filesystem checks, hashes a bounded ordinary executable, rejects final symlinks/
Windows reparse paths, pins CLI0.164.0-alpha.11.1 and returns fixed readonly argv,
cwd, stdin data, bounded timeout/output and a copyable explicit environment.
It never executes the plan, probes login/version, discovers credentials or changes
`os.environ`. The version is a host assertion; binary/path checks can become stale.
No filesystem atomicity, credential isolation, billing or tool-permission guarantee
is inferred. API-key/base-URL/token keys are excluded from the plan allowlist.
`CapturedProcess.start(..., env=...)` separately copies/validates a strict dictionary;
`None` preserves prior inheritance. Raw values never appear in its public snapshots.
A caller still needs fresh authorization for every actual model execution.

## Offline Claude event projection

`agentsync.adapters.claude_events.parse_claude_jsonl(text, exit_code=...)` parses a
bounded, single-main-session subset: system/init, supported assistant blocks and
one result. It performs no filesystem, network, SDK, subprocess or Core operation.
It checks session correlation, duplicate JSON keys, UTF-8/size/depth/counter bounds,
subtype/is_error/API errors, interruption, permission denials and final assistant
stop reasons. Unsupported hook/user/partial/trailing-system records stay explicitly
unsupported; this is not general SDK stream compatibility or authenticated identity.
Only final protocol success with observed exit0 exposes result_text; failure,
incomplete/unknown exit keeps it empty. Usage is caller-reported, never a bill.

`python tools/inspect_claude_events.py --input <explicit.jsonl> --exit-code 0`
produces size/hash-only result summaries. Omit --exit-code to keep process status
unknown. CLI exit0 means parsing completed, including failed/incomplete reports;
it is not task success. No default log search, client launch or raw session/text
projection occurs. Built-in real Claude startup and server cancellation/resume remain unsupported.

Schema research used the official [headless guide](https://code.claude.com/docs/en/headless),
[agent lifecycle](https://code.claude.com/docs/en/agent-sdk/agent-loop) and
[SDK types](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/types.py).

## ClaudeAdapter and private shared lifecycle

`agentsync.adapters.claude.ClaudeAdapter` supplies client-specific capabilities,
ClaudeRun and ClaudeResult through the same private ownership/deadline/history
engine as Codex. It reads Claude JSONL directly; no synthetic Codex conversion
occurs. Public Claude results contain private result_text/client_session_id,
optional unverified ClaudeUsage and the fixed host-process/unverified markers.
Session IDs correlate output and never authenticate Core sessions.

Without a trusted host async factory, capabilities.supports_start=False and start
is unsupported. With a factory, the same six methods and instance-local safeguards
apply. Factory exceptions, malformed/incomplete captures and uncertain deadlines
retain unknown slots; shared/stale captures are rejected without stopping others.
Late fresh owned parents may be cleaned without rewriting frozen unknown history.
Cancel is owned-parent-only, never server acknowledgement or tree-cleanup proof;
resume is unsupported. The default Claude adapter has no launcher; the explicit
`ClaudeProcessFactory` below can connect its fixed plan to capture. No SDK call
or credential reader is added. Known Python helpers prove mechanical composition,
not actual Claude integration.

Codex public classes/fields and validation semantics remain compatible despite
the private extraction. The historical actual Codex CLI smoke is not a live
test of this new shared engine. A fresh real-client run still requires separate
authorization and the relevant M5 gates; previous one-call grants were consumed.

## Accidental never-started factory capture

Factories must return a fresh capture created by `CapturedProcess.start()`.
If trusted host code instead returns the bare public constructor, cancelling that
capture now freezes `unknown/capture_not_started` immediately. Adapter cancellation
or logical deadline can then settle unknown while retaining the uncertain slot.
No parent exit, execution, tree cleanup, Core authority or real client is inferred.
A pending actual start remains distinct and retains its existing late cleanup.

## Heterogeneous local run routing

`agentsync.adapters.manager.RunManager(project_id, session_id, adapters, max_runs=100)`
accepts a fixed trusted mapping of adapter names to existing adapter instances.
It routes `capabilities`, `start_task`, `get_status`, `get_result`, `cancel_task`
and `resume_task` without changing their protocol results or verification markers.
`start_task(name, task)` returns `ManagedRun(handle, adapter_id, run)`; subsequent
operations use this manager's opaque `handle`, not the underlying client run ID.
For a mixed registry, type checkers need an explicit annotation such as
`manager: RunManager[object, AdapterRun, object]` (`AdapterRun` is exported by the
same module). Results then require type narrowing; a concrete union annotation
can preserve client-specific result types. Homogeneous registries infer their types.
Replaying the same request returns its original start receipt; call `get_status`
for a fresh observation. Switching adapters or inputs under the same request ID
is a conflict. Returned run/result identities must match the registered request.

The manager keeps one project/session namespace and up to 32 registered adapters.
Its lifetime history is bounded, never evicted, and includes failed starts. Caller
cancellation stops waiting but does not relaunch or cancel the owned dispatch.
Concurrent duplicates share that dispatch, while independent adapters can proceed.
`history()` lists local handles; `get_dispatch(handle)` observes a pending,
returned or failed start without awaiting it. A returned receipt is not completed
work. Start errors retain only fixed codes, not original exception tracebacks.

This is trusted host routing, separate from the existing simulation scheduler
`MockRunManager`. It grants no permission, claims no Core task, and enforces no
running quota. There is no manager timeout, restart recovery or cross-instance
deduplication. Keep the event loop alive for unfinished starts; adapter cancellation
and cleanup limitations still apply. Known local Python protocol fixtures verify
composition only. Cursor startup, real clients and autonomous relay remain unverified.

## Cursor terminal JSON adapter

`agentsync.adapters.cursor.CursorAdapter` uses the same six-method lifecycle and
trusted host factory boundary. It supports only the standalone terminal object
from Cursor's explicit `--print --output-format json` mode. It does not consume
`stream-json`, tool events, or text deltas and does not launch the CLI itself.
The pure `parse_cursor_json(text, exit_code=None)` requires the documented success
schema and observed exit zero before exposing result text. Empty, unknown or
nonzero process observations never provide successful text. Malformed/unsupported
objects raise fixed errors; an invalid captured protocol retains an unknown slot.

Input is bounded to 1 MiB, strings to 64 KiB, IDs to 200 UTF-8 bytes and nesting
to depth 32. Duplicate keys, invalid UTF-8/NUL and invalid numeric fields reject.
`CursorReportedMetadata` contains caller-reported elapsed milliseconds and an
optional request correlation ID; these are neither measured billing nor Core
identity. All protocol/client verification markers remain unverified. Parent-only
cancellation, deadline behavior and unsupported resume match the shared engine.

An explicit `CursorAdapter(..., contextual_factory=factory)` can now pass its
task-bound `LaunchContext` to a trusted host factory, mutually exclusive with
the legacy `factory` argument. The host must use `context.start(...)` to obtain
the existing prelaunch stop/deadline and one-attempt checks. Default startup
remains unsupported. Scheduled OS creation and parent-only cleanup retain the
shared engine's documented limitations.

`CursorHostProfile` and `prepare_invocation` in `agentsync.adapters.cursor_invocation`
prepare a bounded plan for an explicit executable, binary SHA-256, host-declared
version and working directory. `CursorProcessFactory` can pass that plan to the
same contextual launch guard. The fixed flags select ask mode, terminal JSON
and request the client sandbox. The prompt is a positional OS argument, so this
prototype requires separately approved synthetic instructions without secrets.
It uses a caller-supplied system environment allowlist. Actual auth, billing,
tool restrictions, isolation and CLI/OS compatibility remain unverified.

The supported schema is based on the official
[Cursor output format](https://cursor.com/docs/cli/reference/output-format).
Invocation flags are based on [Cursor CLI parameters](https://cursor.com/docs/cli/reference/parameters).
Only synthetic known-Python fixtures have been exercised. Actual Cursor, CLI/OS
compatibility, permissions, server cancellation and autonomous relay are NOT RUN.

## Claude restricted invocation preparation

`agentsync.adapters.claude_invocation.ClaudeHostProfile` requires explicit native
executable/root paths, binary SHA256, model and project/session scope.
`prepare_invocation(profile, task, environment=...)` performs bounded file/hash
inspection and returns fixed argv, cwd, stdin and filtered environment data.
It never launches a process. Only CLI version assertion2.1.295 is currently planned.
Task text stays on stdin; no caller extra flags, resume or weaker fallback exists.
The prepared restricted/tool-deny/empty-MCP/settings flags include ordinary-hook
disabling. Managed hooks cannot be disabled this way; managed MCP policy may reject
strict configuration. No sandbox, subscription-only billing or authentication is
established. Home/config paths may still supply credentials/providers. All execution,
version/auth/billing/client/sandbox/tool-restriction verification markers stay false.

Primary references: [CLI](https://code.claude.com/docs/en/cli-reference),
[hooks](https://code.claude.com/docs/en/hooks#disable-or-remove-hooks),
[managed MCP](https://code.claude.com/docs/en/managed-mcp).
`--bare` is deliberately absent because the official
[headless guide](https://code.claude.com/docs/en/headless#start-faster-with-bare-mode)
states that it does not use subscription OAuth credentials.

An isolated empty-home help/version-only observation found installed2.1.295 and
listed most prepared flags; `--max-turns` was absent from help despite appearing
in current documentation. Complete flag-combination compatibility is NOT RUN.
A separate installed-binary hash/preparation check launched nothing and retained
all false markers. New real execution needs fresh cost authorization and M5 gates.
Default ClaudeAdapter startup remains unsupported. Earlier one-call grants are spent.

## Opt-in pinned Claude process factory

`agentsync.adapters.claude_process.ClaudeProcessFactory(profile, environment=explicit_env)`
can be passed explicitly as `ClaudeAdapter(..., contextual_factory=factory)`,
mutually exclusive with `factory`. Construction copies the profile and filtered
environment without launching. Each call prepares the existing restricted plan
afresh in a worker thread and forwards its exact fields through the same
`LaunchContext` checks as Codex. Defaults, flags, separate timeout observations,
unknown-slot retention and late owned-parent cleanup remain unchanged. Attaching
the factory authorizes no model execution; every actual run needs fresh human
authorization and the existing gates. Managed hooks are not disabled, managed MCP
may reject strict configuration, and home/config may supply credentials/providers.
Authentication, billing, tool restrictions, sandboxing and real-client compatibility
remain unverified. Start spies and synthetic Claude JSONL from known Python
helpers establish wiring and local lifecycle only; no actual Claude call was made.
