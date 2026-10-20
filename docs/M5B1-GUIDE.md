# M5B1 verifier foundation

Issue15 implements a trusted-owner library for one narrow contract:
`python-json-lines-v1`, a standalone root `solution.py` that accepts one JSON value
per stdin line and emits one JSON value per stdout line. It is not a general
project test runner or an agent-facing command API. The service does not yet queue
verification jobs, automatically accept tasks, consume approvals or apply changes.

The owner provides a preapproved local Linux Docker image's full content ID and
fixed input/expected-result pairs. Expected results stay outside the container.
`export_candidate` reads only pinned managed Git objects, checks every object's
identity, and returns an immutable content snapshot. `verify_python_json_lines`
sends only source and case inputs through stdin to a fixed container interpreter;
no host directory, database, credential, Git store or Docker socket is mounted.

Only an inspected Linux Docker backend can execute this profile. Windows/macOS,
missing Docker, missing image or unavailable security controls return unsupported.
There is no host execution fallback, dependency install or automatic image pull.
Finite case success cannot prove correctness outside those cases or certify a
real AI client. See M5B1-CONTRACT.md for exact limits and trusted components.

## Evidence tiers

- Unit policy tests use simulated Docker responses. They exercise refusal,
  comparison and error handling, and do not demonstrate OS isolation.
- Snapshot tests use real Git with disposable repositories. They do not execute
  the candidate program.
- `tests/integration/test_docker_verifier.py` executes real containers only when
  `AGENTSYNC_DOCKER_TEST_IMAGE` specifies a preloaded full image ID. It tests
  external assertions, false success, isolation, time/output/memory/PID/tmpfs limits
  and cleanup. An unconfigured ordinary matrix records these cases as skipped.
- The dedicated `verifier isolation` Linux CI sets
  `AGENTSYNC_REQUIRE_DOCKER_TESTS=1`; missing Docker/image/configuration fails that
  gate. Actual backend results and host-generated JUnit are saved in its artifact.

Raw candidate stdout/stderr is untrusted and is not copied into public result
JSON. Safe metadata includes identities, hashes, counts, fixed errors and effective
controls. A passing candidate exit status alone does not mean verification passed;
all external cases and normal completion must be observed, with cleanup confirmed.

The image preload in CI is trusted fixture preparation. It resolves a public
Python image to an exact ID, saves its registry digest, then passes only the ID to
the backend with `--pull=never`. Reproducing a run requires that recorded image,
the exact verifier code and profile, and the pinned candidate commit/tree.

## Remaining gates

Durable queued/running/result jobs, worker attempt fencing, restart/orphan recovery,
permission-controlled requests and evidence persistence remain a separate M5B
integration stage. Single-use approval consumption and safe application require
their own transaction/Git recovery design. M5-04, full M5, actual adapters, real
two-client relay and formal Release Acceptance remain incomplete/BLOCKED until
their own actual tests and independent Work acceptance pass.
