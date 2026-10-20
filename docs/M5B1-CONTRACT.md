# M5B1: bounded independent verifier backend

Status: implementation contract, not a claim of completed verification. Parent scope
is M5-04 and the still-open M5 issue. M5A permissions and approval metadata remain
unchanged. This stage implements an independent library, not an agent-facing API.
It neither completes tasks nor consumes approvals nor applies changes to a source
checkout. Full M5 and formal Release Acceptance remain blocked.

## Trust and scope

The host verifier, its fixed comparison logic, the owner's profile, the selected
local Docker daemon/image, and the host OS/kernel are trusted. Candidate code,
repository files, stdout/stderr, exit status and candidate-generated JUnit are
untrusted. Container isolation does not claim protection against a compromised
daemon/kernel, an administrator, or another process with equivalent host authority.

Never import, compile, install, discover tests from, or execute candidate code on the
host. A missing sandbox is an unsupported result, never permission to run locally.
No paid provider call or real model-client control is part of this stage.

The first and only executable profile is `python-json-lines-v1`. It verifies a
standalone `solution.py` through a fixed JSON-lines black-box interface. It does not
verify arbitrary Python projects, package installation, repository tests, or the
whole AgentSync application. Additional profile IDs fail closed.

## Owner-controlled profile

The owner supplies an immutable, validated profile object directly to the trusted
library. It contains:

- exact profile ID/version and a canonical profile SHA256;
- a full, preloaded local Docker image ID, `sha256:` followed by 64 lowercase hex
  characters; tags, shortened IDs and caller-selected registries are rejected;
- a nonempty bounded list of case inputs and corresponding expected JSON values;
- fixed resource/time/output bounds no greater than the implementation maxima.

Expected results stay in the trusted host comparator. Only the case input is sent
to the candidate. Profiles are never loaded from candidate files, task descriptions,
MCP arguments, model output, or environment variables. A profile cannot add commands,
shell fragments, dependencies, arbitrary environment variables, mounts, Docker flags,
credentials or a different entrypoint. Its digest covers cases, expected values,
image identity, limits and profile version. Record a separate canonical cases SHA256
as well. Changing any field changes the digest.

The image must already contain a trusted Python interpreter at the fixed path
selected by the implementation. There is no network pull, image build, dependency
installation or execution of a repository Dockerfile/setup script during validation.
Image inspection must confirm the exact ID, Linux OS, and absence of automatic
image volumes and unsupported execution configuration. Override image entrypoint,
working directory and healthcheck; reject unsafe inherited image configuration.

## Immutable Git input

The caller supplies an internal trusted managed-repository receipt and a complete
validated commit SHA. Resolve the commit and tree through the existing bounded,
sanitized Git mechanism. Use controlled `ls-tree` and `cat-file` to enumerate the
entire pinned tree and read its objects. Independently recompute commit, tree and
blob object hashes, including Git's object type/length framing. Read all included
blobs to confirm their identity and size. Reject external object stores, replaced
managed paths/configuration, and missing/corrupt objects. The receipt is not an
agent-submitted dictionary and is not an authentication boundary.

Do not use Git archive: candidate `export-ignore` and `export-subst` attributes must
not omit or transform input. Never read executable bytes from a mutable candidate
worktree, current branch name, user-supplied ref expression, or the source checkout.
Never extract or materialize a candidate directory tree. Only `solution.py` source
bytes and the content manifest are retained in host memory.

Validate every enumerated path and object before execution. Reject absolute/traversing
paths, empty/ambiguous names, backslashes, duplicate entries, case/Unicode aliases,
control characters, links, devices, FIFOs and gitlinks/submodules. Allow only ordinary
files and tree directories. Enforce at most 256 files, 4 MiB total file content,
512 total file/directory entries, 64 path components and 4096 raw bytes per path.
Input parsing is data handling and cannot invoke hooks, filters or candidate code.

Require one ordinary root `solution.py` with at most 128 KiB of UTF-8 source bytes.
Only this standalone module is executed; sibling files are validated and hashed but
are not exported, installed or available for local-module imports. Record full
commit/tree IDs, source SHA256, canonical content manifest and its input SHA256
binding. Recheck the managed repository's physical identity and integrity boundary
after reads. Reject unknown candidate/project identities at future orchestration.

## Fixed black-box protocol

For each case, the program receives one UTF-8 JSON value terminated by a newline on
stdin and must emit exactly one UTF-8 JSON value terminated by a newline on stdout.
The host sends all inputs in a deterministic order, closes stdin, and checks every
response against the corresponding owner expectation. It must observe exactly the
expected number of results and normal process completion before success.

Reject invalid UTF-8/JSON, duplicate object keys, nonfinite numbers, excessive nesting
or size, missing/extra/blank output lines, a nonzero exit, timeout, or output overflow.
Comparison is structural and type-aware: object key order is irrelevant, array order
is significant, and booleans are not equal to numbers. Specify numeric equivalence
explicitly in the implementation/tests; never use permissive Python `True == 1` as
the comparator. Inputs and expectations use the same bounded strict JSON validation.

The trusted driver remains outside the candidate process. Candidate `exit(0)`, an
empty report, forged JUnit, and candidate assertions cannot satisfy missing or failed
host comparisons. Passing means only that the fixed profile's finite cases passed;
it is not a proof of arbitrary correctness or real autonomous Agent collaboration.

Source delivery must not introduce any host mount. The standalone profile must use
a fixed trusted Python bootstrap that reads a bounded length prefix and exactly that
many source bytes from `stdin.buffer`, followed by JSON-lines input. Compile/execute
the source only inside the container, preserving the remaining stdin for `solution.py`;
the host never executes the bootstrap against
candidate code. Bootstrap command text is fixed by the library, not constructed from
the candidate. No expected output, owner secret, repository path, or service state is
included. Supporting a directory of candidate imports requires a separately reviewed
read-only delivery design. Do not assume `docker cp` can populate a read-only rootfs.

## Required Linux Docker isolation

Only a supported Linux host with a local Linux Docker daemon using cgroup v2 is
executable. Cgroup v1 is unsupported in this foundation. Windows,
macOS, missing Docker, remote endpoints/contexts, missing image, or unavailable
required isolation controls return `unsupported` or a specific infrastructure error.
The library must select the trusted local endpoint explicitly and sanitize its CLI
environment; it must not inherit caller Docker contexts/configuration or silently
switch to another daemon. Use `--pull=never` and the inspected full image ID.

Construct argv as a list with no shell. All executable paths, flags, bootstrap code
and container paths are fixed trusted values. The candidate cannot choose them.
The container must have all of these controls:

- non-root numeric UID/GID; no supplementary privilege grants;
- read-only root filesystem and no host-path, socket, device or service-data mounts;
- network disabled, no published ports, and private process/IPC/cgroup namespaces;
- all Linux capabilities dropped and no-new-privileges enabled;
- Docker's supported default seccomp policy or a reviewed stricter policy;
- bounded memory/swap, CPU, PID count, tmpfs space and writable scratch;
- a fixed working directory, disabled image healthcheck, and no inherited secrets;
- externally enforced wall-clock time and separate bounded stdout/stderr capture.

No privileged mode, host namespaces, added devices, unconfined seccomp, Docker socket,
SSH agent, host environment pass-through, or persistent volume is permitted. Only
explicit harmless runtime variables may exist in the candidate environment. Reject
images carrying credentials or automatic writable volumes; inspection metadata must
not be dumped into reports, because its environment may contain secrets.

Use implementation-wide hard maxima, with a conservative initial policy of at most
100 cases, 128 KiB solution source, 4 MiB total Git file content, 256 files, 10 seconds
wall time, 1 CPU, 128 MiB RAM with no extra swap, 32 PIDs, 8 MiB tmpfs, and 64 KiB each
for stdout/stderr. Exceeding a bound is failure, not truncated success. If an initial
backend needs different maxima, document and test them before accepting its evidence.

Stdout/stderr capture is file-backed and size-polled. The configured output threshold
is an acceptance/processing limit, not a hard temporary-disk quota: a process can
write beyond it before the next poll detects the overflow. Report overflow as failure,
and do not claim that temporary disk consumption is capped at exactly 64 KiB.

Killing only the local Docker CLI does not stop the container. Timeout/error cleanup
must identify the exact full container ID and unguessable per-run ownership label,
then stop/remove only that owned container. Never delete by a broad name or label
glob. A failure to confirm cleanup is an explicit infrastructure error and is recorded.
Temporary files are isolated from user projects and removed only after verifying
their resolved paths and ownership. Crash-safe orphan reconciliation is future scope.

## Results and evidence

Return structured `passed`, `failed`, `unsupported` or `error` plus safe error codes.
Timeout, limit exhaustion, protocol violation or failed case cannot produce `passed`.
Keep candidate exit status distinct from the host's comparison outcome. Record:

- input commit/tree/source/manifest/cases hashes and profile/image identities;
- verifier version, platform/kernel and Docker daemon/server versions;
- requested and inspected effective isolation settings, without raw environment;
- expected/completed/passed case counts, timestamps, elapsed time and exit status;
- which limits fired, cleanup confirmation, bounded safe diagnostic metadata;
- hashes and locations of evidence saved by a trusted caller outside user projects.

Do not expose raw candidate stderr/stdout as trusted status or unrestricted exception
text. Candidate output can contain secrets, path-like text or control sequences; store
it only through an explicit bounded evidence policy, with safe rendering/redaction.
JUnit must be generated by the host from actual comparisons; candidate files cannot
replace it. Record test policy mocks separately from actual Docker execution.

## Acceptance before claiming this backend works

Reuse existing tests. Add focused unit/security tests for profile validation, exact
image identity, sanitized argv/environment, Git object/path boundaries, every protocol error,
output bounds, typed comparisons, early exit, forged success text, and cleanup errors.
Non-Linux/no-Docker tests must prove rejection without candidate host execution.

A dedicated Linux GitHub Actions job must actually provide Docker, preload and pin a
reviewed image, then run the real backend. That job must fail if Docker/image/security
controls are unavailable; skipping or substituting a mock is not a passing gate. Save
JUnit, logs, exact image/commit/profile hashes and effective container settings.

Real adversarial fixtures must demonstrate: host canary and Docker socket inaccessible,
no inherited sentinel secret, outbound networking unavailable, non-root identity,
read-only root, bounded scratch, PID/memory/time/output enforcement, exact case-count
checking, false-result rejection, and exact-owned-container cleanup. All destructive
fixtures use isolated temporary projects and disposable containers. Other CI platforms
can test policy/unsupported paths but cannot count as Linux Docker isolation evidence.

The current Windows environment has no verified Docker backend. Local policy tests
alone cannot establish successful sandbox execution. Report real Linux CI results
separately and leave unavailable probes explicitly unexecuted or restricted.

The actual Linux gate additionally reads kernel cgroup v2 CPU/memory/swap/PID limit
files, checks the root mount is read-only, and checks only loopback/no default route.
An unrelated permission or connection error alone is insufficient isolation evidence.
CPU evidence observes the effective kernel quota; it is not a throughput benchmark.

## Deferred M5 work

This independent synchronous library does not add schema migrations, owner/agent
operations, a job queue, task acceptance transitions or approval consumption. Future
orchestration needs short transactions around durable queued/running/result states,
attempt tokens, conditional completion, restart recovery and orphan reconciliation;
never wait for Docker while holding Core's `BEGIN IMMEDIATE` transaction.

M5B2 must separately bind a successful applicable verification to single-use approval,
requester/role/version/expiry/action/resource SHA and target expected HEAD; use durable
application intents and Git compare-and-swap with crash reconciliation. Existing
`apply_merge_candidate` approvals must not be consumed merely to verify a candidate.
Actual source application and independent Work acceptance remain unimplemented here.
M6 adapters, real two-client autonomous relay and M9 full release gates remain open.

## Primary references

The isolation flags and effective configuration must be checked against the Docker
version actually used, rather than assuming that flags alone prove enforcement:

- [Docker: running containers](https://docs.docker.com/engine/containers/run/)
- [Docker: seccomp security profiles](https://docs.docker.com/engine/security/seccomp/)
- [Linux kernel: cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)
