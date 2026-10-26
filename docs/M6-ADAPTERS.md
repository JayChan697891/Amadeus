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
