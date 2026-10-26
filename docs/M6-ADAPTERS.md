# M6 host-factory adapter prototype

`agentsync.adapters.codex.CodexAdapter` implements the six generic `AgentAdapter`
methods. It composes `CapturedProcess` and the bounded Codex JSONL parser. There
is no built-in CLI launcher, credential reader, Core dispatch or network client.

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
Actual client integration still requires the existing M5 safety gates and a new
explicit live-test authorization. Both separately authorized single real CLI tests are now consumed.

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
resume is unsupported. No built-in Claude command, SDK call or credential reader
exists. Known Python helpers prove mechanical composition, not Claude integration.

Codex public classes/fields and validation semantics remain compatible despite
the private extraction. The historical actual Codex CLI smoke is not a live
test of this new shared engine. A fresh real-client run still requires separate
authorization and the relevant M5 gates; previous one-call grants were consumed.
