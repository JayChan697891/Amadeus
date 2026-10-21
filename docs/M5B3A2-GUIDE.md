# Existing managed candidate input export

This trusted owner library reads an already prepared managed merge candidate,
validates its existing disk/Git evidence and exports its fixed Git object content.
It never prepares or repairs a missing candidate, executes source, starts a job,
marks a task completed or applies a change to a user branch.

```python
from agentsync.verification.candidate import OwnerCandidateExporter

candidate_input = OwnerCandidateExporter(core).export(
    project_id=project_id,
    admin_token=admin_token,
    candidate_id=candidate_id,
    expected_candidate_sha=expected_candidate_sha,
)
```

Supply the exact prepared candidate ID and full SHA through the owner's existing
private channel. No path, receipt, binding object, command or result is accepted
from the caller. The operation is not exposed through generic Core/HTTP/MCP/SDK
dispatch or the owner CLI. The credential must never be logged or stored in Git.

Metadata is authenticated and captured before opening storage. Missing directories,
receipts or intents fail without reconstruction. The captured bare repository,
left/right worktrees and candidate must retain their physical/config identities;
Git indirection is checked before Git can consult it. An extra `.git` entry in a
bare repository is rejected before the first repository Git command. Both original
worktrees and the candidate must be clean and retain their expected HEADs. Parent
commits must match the prepared branches, including the legitimate ancestor case.

The returned frozen object contains `source_kind=managed_merge_candidate_input`,
metadata `binding`, the actual immutable `snapshot` and an unkeyed provenance
fingerprint. `snapshot.source` comes from the candidate commit, not the original
checkout or baseline commit. Existing bounded regular-file/UTF-8/manifest/object
integrity rules and the root `solution.py` limit remain unchanged.

Receipt/storage/Git checks repeat after export, then the owner and all DB binding
metadata are recaptured. Changes discard output. This is a checked content export
at those observations, not an atomic filesystem guarantee against an OS-level
attacker. The service filesystem is trusted; Git commands use bounded temporary
output files and can read existing files, but create no persistent candidates,
receipts, intents or commits in this operation.

The returned dataclass and digest are not signatures or permission tokens. Python
callers can construct objects themselves. Future trusted job/task code must resolve
the candidate internally and authenticate/bind its own current inputs; serialized
caller objects cannot grant execution or acceptance. Existing snapshot jobs and
`review_task` are not silently upgraded by this library. No candidate execution,
real client relay, approved apply or formal Release acceptance follows from export.
