# M5B3A2: existing managed candidate input export

Internal owner seam: `OwnerCandidateExporter(core).export(project_id,
admin_token, candidate_id, expected_candidate_sha)`. The caller cannot supply a
path, receipt, binding, result or source. There is no new transport operation,
migration, job, worker, task acceptance gate, approval, apply or execution.

1. Authenticate and capture immutable project-scoped database metadata using
   the accepted M5B3A1 seam. Its read transaction closes before any Git operation.
2. Open existing managed storage with `GitWorkspaceStore(..., create=False)`.
   Missing roots/groups fail without reconstruction. Default construction retains
   existing creation behavior for existing callers.
3. Require regular bounded UTF-8 disk receipts matching all four canonical DB
   receipts. Reject duplicate JSON keys/non-finite values. Require existing capture,
   create and candidate merge intents matching the recorded inputs. No permissive
   receipt helper, intent writer or candidate preparation method is called.
4. Validate the captured bare repository first using the existing object export
   boundary: physical local metadata, fixed captured config and no external object
   stores. Reject any `.git` entry inside the bare repository before running Git
   there, because Git would prefer that redirect over the validated bare metadata.
   Require a physical regular bare config before its bounded existing digest read;
   a nonregular config such as a FIFO must not block that host-side read.
   Before invoking Git in any linked directory, inspect its regular `.git`
   pointer, physical administrative directory under the captured repository's
   `worktrees` child, exact commondir and gitdir backpointer. Reject per-worktree
   config. Then check original worktree identities, current left/right SHAs and
   clean state. Require exact candidate path/identity, common repository, HEAD
   and clean state.
5. Require candidate parents exactly `[left,right]`, or `[left]` only if right is
   an ancestor of left. This supports the existing generator's allow-empty
   ancestor case; reversed/unrelated/extra parents fail.
6. Export the actual candidate SHA with the trusted captured receipt through the
   existing bounded Git-object exporter. Its regular-file, object-integrity,
   UTF-8, manifest and root `solution.py` bounds remain unchanged. Candidate source
   is never imported or executed.
7. Repeat receipt/storage/worktree/candidate/parent checks, then reauthenticate
   and recapture all DB binding metadata. Any changed receipt, task version,
   creator association or authority discards output.

The frozen `CandidateInput` exposes `source_kind=managed_merge_candidate_input`,
the immutable metadata `binding`, content `snapshot` and `provenance_sha256`.
The digest is SHA-256 of sorted compact UTF-8 JSON with schema
`agentsync.candidate-input.v1`, source kind, binding SHA-256, commit SHA, tree SHA,
input SHA-256 and source byte SHA-256. It is a content/provenance fingerprint,
not an authority token, execution result or signed attestation. Original snapshot
input digest semantics are preserved.

Read-only means no persistent managed directories, intents, receipts or commits
are created or repaired. Existing Git transport uses bounded ephemeral temporary
output files and disables optional locks. Service-owned filesystem integrity
remains trusted; before/after checks cannot provide atomic protection against
arbitrary OS-level ABA replacement. A returned object is not a future task-gate
authorization, and later use must account for changes after return.

Tests use real disposable Git/SQLite projects and literal candidate bytes. No
candidate code runs on the host. Tests exercise actual merges and the valid
single-parent case, mutation, missing evidence, malformed receipts, authority/task
races and storage opening. Existing object security tests remain applicable.
Runtime/cache/temp/evidence stay on D:, source stays on F:, GitHub is storage only.
