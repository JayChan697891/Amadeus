# M6 host-factory adapter prototype

## Controlled proposal submission and staging bridge

`CodexProposalInput(..., submit_for_review=True)` opts into lease-controlled
submission after inert publication. The flag is included in the launch contract
and approval digest; its default `False` preserves existing launch plans and the
running-task/storage-only behavior. The controller records review intent before
`update_task`, then a distinct submission receipt afterward. Missing final receipt,
expired lease, changed task/version/worktree or corrupted bindings remain incomplete;
publication can still be observed historically without implying submission success.

`run_codex_proposal_once` continues to return the historical storage outcome.
Use `observe_codex_proposal_review(actor, task_id)` to inspect the current exact
`submitted_for_review` state and its separate publication/review task revisions.
No task completion, ordinary fixed-reply relay success or execution authority is
inferred from this state. A completed/changed task no longer matches this observer.

The owner can call `preview_codex_proposal_staging(actor, task_id, admin_token=...,
staging_session_id=..., staging_session_token=...)`, inspect the returned plan,
then pass its hash as `expected_plan_sha256` to `stage_codex_proposal_once` with
the same explicit credentials. The controller requires current producer identity
and complete proposal/submission evidence; the staging service independently checks
owner/stager authority and all current pins. The helper never previews and approves
on the caller's behalf. If the producer session has expired, this convenience bridge
cannot reconstruct its authority; the separate owner service below remains its own
explicit publication-adoption boundary, not automatic model-provenance recovery.

After staging, feed the returned `candidate_id`/`candidate_sha` into the existing
owner `CandidateVerificationJobs.enqueue` with a trusted `DockerProfile`, then
review its exact job version/metadata digest before `OwnerCandidateFlow.start_once`.
Verified completion still requires a different reviewer via `complete_once`.
The controller does not enqueue or execute automatically, and it never restarts a
model or retries a staging effect to close an interrupted receipt gap.

## Owner-reviewed proposal staging

`agentsync.verification.proposal_staging.OwnerProposalStaging(core)` now exposes
`preview`, `stage_once` and `status` to trusted owner-side Python hosts. There is
no worker/MCP/HTTP staging operation. Supply project owner credentials plus an
active worker session for staging attribution. The original producer may have
expired; a different independent reviewer is still required for later completion.

Preview arguments are `project_id`, `admin_token`, `session_id`, `session_token`,
`task_id`, `expected_task_version`, `context_id`, `expected_content_sha256`,
`publication_session_id` and `publication_request_id`. The task must already be
in `review` through the existing producer lease-controlled submission operation.
The immutable first context revision, real `publish_task_proposal` response and
successful audit event must agree. A copied context source label is insufficient.
This authenticates publication, not model authorship; preserve separate real-client
capture evidence when making that claim.

Review `preview(**arguments)["plan"]` and its exact file hashes, producer baseline,
task revision and new destination IDs. Pass its `plan_sha256` as
`expected_plan_sha256` to `stage_once(**arguments, ...)`. That call commits a
permanent task-wide intent before Git and rechecks all pins. It creates a genuine
new managed worktree and candidate, paired with the untouched original worktree
on the same task/snapshot. Exact UTF-8 blobs are staged without content filters;
no generated code is executed and no task status is changed. Nothing is applied
to the registered source checkout or an existing actor worktree.

Use `status(project_id=..., admin_token=..., task_id=...)` after interruption.
`incomplete` retains both the intent and any partial private files; it does not
retry or repair them. `staged` is historical metadata, never fresh verification
or application authority. Every repeat mutation for that task is rejected.
Normal candidate export, owner queue/execution and independent completion gates
remain separate. In particular the current Docker profile still requires root
`solution.py` implementing its fixed JSON-lines interface; arbitrary proposals
are not silently wrapped, executed or called verified.

Supported staging trees exclude `.gitattributes` and `.gitmodules` in either the
snapshot/head or proposal, executable Git filters/drivers, links/reparse points,
path aliases and file/directory collisions. Existing executable file modes are
preserved; new files are mode100644. Git metadata/indirection/receipt checks run
before effects. The service and private managed storage are trusted; the checks
do not claim atomic protection against a malicious administrator replacing paths
between operating-system calls. Full M5/Release gates remain unchanged.

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

## Owner-controlled relay pilot

`ControlledRelay` in `agentsync.controlled_relay` takes a Core in an isolated
scratch tree, a retained private receipt directory and two enrolled actors with
separate managed worktrees. Supply an existing pending task, a pinned context
revision and two fixed synthetic instructions and expected replies. Worktree
comparison can stop the pilot before either client starts. Each `LaunchAuthority`
must independently establish the environment and cost boundary and approve the
exact pinned plan. The supplied actor session and lease are checked again at
capture entry. Core receives no raw client replies.

The first matching reply permits a versioned handoff to the second actor. The
second actor reads the pinned context and claims a new lease. Two matching replies
submit the task for review. `review_once` takes an explicit decision and evidence
from an enrolled reviewer who took part in neither client run. This uses Core's
ordinary review. Verified completion still uses its independent evidence gate.

Keep the same private receipt directory on restart. An unfinished fence remains
incomplete and prevents another launch for the task through this pilot. Existing
Core lease recovery is separate. Filesystem receipts and Core changes are separate
transactions, so a crash between them can require human reconciliation. Two actual
Codex sessions have now completed a fixed-text sequential relay at ee45690 with
structured handoff, pinned context and a distinct reviewer. Broader operating-system
isolation, cross-client compatibility and full M7 remain unverified.

Offline tests use known local Python helpers and hand-authored JSONL; their results
are separate from actual-client evidence. A repaired real single-Codex run and the
same-client relay reached ordinary Core review/completion at ee45690, with artifact
verification still unverified. At f74f29f, actual local cancellation and a15-second
deadline preserved unknown/incomplete state after parent termination. The deadline
capture also contains a completed turn, so timeout during active generation is not
verified. Permissions, server cancellation, descendant cleanup, Claude/Cursor and
full autonomous collaboration remain unverified. See RELEASE-ACCEPTANCE-REPORT.md
for the exact SHA-bound evidence and limits.

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

The official Windows package2026.11.11-b912975 invokes its sibling `node.exe`
and `index.js`. Optional `node_entrypoint` and `expected_bundle_sha256` must be
supplied together. `inspect_node_bundle(explicit_package_directory)` computes a
bounded versioned relative-path/content digest; it launches nothing. Preparation
rejects changed/missing/added dependencies, reparse/symlink entries and changed
queued directories, then inserts the entrypoint before the fixed Cursor flags.
The package hash is included in approval binding only for this mode, preserving
legacy plan hashes. HOME/USERPROFILE/APPDATA/LOCALAPPDATA/CURSOR_CONFIG_DIR can be
explicitly supplied for a private environment; Node injection and API variables
remain rejected. Package pinning does not prove Node's full external resolution
scope or eliminate filesystem races. Live authentication, cost and isolation gates
remain required. See [version-bound local checks](acceptance/evidence/m6-cursor-node-bundle/summary.json).

The supported schema is based on the official
[Cursor output format](https://cursor.com/docs/cli/reference/output-format).
Invocation flags are based on [Cursor CLI parameters](https://cursor.com/docs/cli/reference/parameters).
A real downloaded Cursor package passed version/help and native-bundle preparation
without model requests. Lifecycle fixtures remain synthetic; actual Cursor task,
permissions, server cancellation and cross-client relay are NOT RUN.

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

## Task-bound inert source proposals

`publish_task_proposal` is available through Core, SDK, loopback HTTP and MCP.
It checks an authenticated worker, a running task at the exact version, the live
lease and that worker's task-bound managed worktree at a clean expected Git head.
After Git inspection it checks lease expiry again. A new context revision, the
request's idempotency record and audit commit in one transaction. It leaves the
task running and returns only the context reference, binding and content SHA256.
An authenticated replay returns the original historical revision, even if the task
later advances or its lease expires; it never republishes or renews authority.

`proposal_json` is exactly `{"files":[{"path":"answer.py","content":"..."}]}`.
It must contain every caller-declared allowed path exactly once: at most8 files,
8192 UTF-8 bytes per content and32768 bytes per JSON envelope. Canonical context
is additionally limited to65536 bytes. Duplicate JSON keys, extra fields, Markdown
wrappers, aliases, path traversal and overlapping file/directory labels are rejected.
The data is never imported as Python, executed or written into a worktree.

This is authenticated publication of unverified data, not proof of a model run.
Worker-supplied allowed paths and the context source label are not authorization;
ordinary context publication can imitate labels. A later host importer must verify
its own approved contract, actual publication receipt/audit, pinned immutable context
revision and current source baseline. It must create a genuine managed candidate
before entering existing owner-only verification gates. Import, isolated artifact execution and verified completion remain outstanding.
The opt-in capture path below does not authorize those stages.

## Opt-in Codex proposal capture

`CodexProposalInput` declares a task revision, bounded instruction and exact file
labels. `preview_codex_proposal` binds the visible JSON contract, paths, task
revision, worktree and Git head into the existing exact launch approval. The host
still supplies an explicitly authorized private environment; preview never starts
a model. Existing fixed-text plans and scheduler/reviewer rules are unchanged.

`run_codex_proposal_once` shares the task-global attempt fence and lifecycle path.
Only a complete successful Codex result, owned parent exit0, no timeout and exactly
one strict final message can reach `publish_task_proposal`. The task stays running;
no code is written, evaluated or imported. Internal source and lease data are
excluded from object representations and private receipt contents.

`observe_codex_proposal` authenticates before reading receipts and returns historical
`proposal_stored` only when the observed canonical-files digest, final context hash,
exact immutable context revision, producer/task/worktree/head and launch bindings
match. It never equates this with `ready_for_review` or verified completion. Later
task or context revisions do not rewrite the historical proposal. A crash between
Core publication and final receipt leaves the attempt incomplete; the context/audit
may exist, but there is no automatic relaunch or fabricated successful recovery.

Local Python protocol fixtures test this integration separately from real-client
acceptance. Actual model-generated proposals and independent artifact execution
require their own recorded authorized execution; consult the current progress and
Release Acceptance Report instead of treating this API as an acceptance certificate.

## Explicit Linux single-task profile

For the pinned `0.167.0-alpha.3.2` CLI on Linux, a trusted host may select
`CodexHostProfile(..., linux_readonly=True)`. This is an opt-in plan, mutually
exclusive with `windows_mxc`; default and earlier-version plans remain unchanged.
It selects a named minimal/project read-only permission profile with network
disabled, the same restricted feature set as the native
Windows single-task plan, browser/computer default denial, no project instruction
loading and no collaboration-agent registration. The compact inline feature table
keeps the existing64-argument limit. A different plan requires its own consent.

Requested settings do not prove effective features or absent tools. The host must
check the actual pinned Linux CLI's configuration and tool projection before a
live run. Plan flags do not authorize credential copying, attest billing, contain
the whole CLI, or establish real-client/Release acceptance.
