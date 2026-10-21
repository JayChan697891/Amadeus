# Candidate metadata capture: limited owner library

This stage captures project-owned candidate provenance from one consistent SQLite
read transaction. It does not read Git objects, files, live HEADs or disk receipts,
and does not verify candidate code, filesystem identity, execution or completion.
Its source_kind is deliberately `managed_merge_candidate_metadata`.

```python
from agentsync.verification.binding import OwnerCandidateBindings

binding = OwnerCandidateBindings(core).capture(
    project_id=project_id,
    admin_token=admin_token,
    candidate_id=candidate_id,
    expected_candidate_sha=expected_candidate_sha,
)
```

The owner credential must remain private. There is no generic Core/HTTP/MCP/SDK
or CLI operation. Caller-supplied paths, receipts, results and commands are not
accepted. The owner is authenticated before lookup; candidate/worktrees/common
snapshot/tasks and creator sessions are resolved within the project. Stored
receipt identities and merge bindings must agree. Malformed, duplicate, nonfinite
or oversized JSON fails with fixed safe errors.

The frozen result contains immutable values and canonical receipt strings. Its
versioned provenance digest detects a changed captured binding, including task
versions and receipt contents. It is an unkeyed fingerprint, not a signature,
proof of trusted provenance, permission token or verification result. A Python
caller can construct the dataclass independently; future trusted code must never
accept such a value as authority without recapturing and authenticating inputs.

Capture can legitimately return the same metadata after a candidate checkout is
modified: this stage never looks at the checkout. The next M5B3A step must validate
disk receipts/intents, physical/config/common-dir identity, live HEAD/clean state,
commit parents and actual bounded object export, with final DB/Git rechecks.
Only later can a task submission and independent execution be bound to a reviewer
gate. Historical asserted review remains distinct. Full Release stays BLOCKED.
