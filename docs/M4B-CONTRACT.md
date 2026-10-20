# M4B bounded contract (Issue #9)

Current scope M4-03/04 plus M4-05 prepare-only safety boundary. Parent PR8.
This stage never modifies the registered source repository or merges into it.
No external network, client control, model API or automatic apply endpoint.

## Operations (shared Auth)
- capture_repository(request_id): canonical registered root must itself be a Git
  repository root (not arbitrary parent). Read fixed full HEAD and original status;
  record an immutable snapshot ID, base_sha, source_dirty bool, source_status and
  managed independent bare repository path. Dirty source is allowed to inspect but
  uncommitted/untracked content is NOT imported; explicit result says committed_only.
- create_worktree(snapshot_id, task_id, request_id): same-project task and snapshot,
  service-generated owned worktree/branch paths only. Return id, snapshot_id,task_id,
  base_sha,head_sha,path,status,version. Separate agents get distinct owned trees.
- inspect_worktree(worktree_id): project auth; verify owned path/root identity;
  return current full HEAD and bounded NUL-parsed status, dirty bool, base_sha/version.
- compare_worktrees(left_id,right_id,expected_left_head,expected_right_head):
  same snapshot/project, exact full 40/64-hex pinned commits; reject dirty worktrees
  as dirty_worktree, changed HEAD as stale_snapshot. Return both SHAs, base SHA,
  overlapping_paths, mergeable bool, conflict_paths and actual merge exit code.
  Compute actual merge in fresh third owned tree/repo, never either actor tree.
- prepare_merge_candidate(left_id,right_id,expected_left_head,expected_right_head,
  request_id): same validations; only clean nonconflicting comparison. Return
  candidate_id, candidate_sha, base/left/right SHAs, changed_paths,
  status='awaiting_human_approval'. No approved bool, apply/merge original endpoint.

All expected SHAs are strict hex, never arbitrary revision expressions. Auth and
same-project checks precede any Git call; errors redact full commands/secrets.
All persistent identities project scoped; never echo foreign owner identities.
Deterministic managed paths/sidecar intent receipts must let retry identify completed
side effects after interruption; never silently delete unknown work or user paths.
No token secrets in receipts. Schema v5 migration preserves v1-v4 state. Public MCP
adds five typed wrappers (29 tools total), HTTP/SDK dispatch same Core.

## Backend boundary

Use a new service-owned independent bare repository and owned worktrees below
<data_dir>/managed-git; do not register worktrees in user's .git. Copy pinned
committed objects with no hardlink/shared-object/alternates dependency. Verify source
root and HEAD/status before/after capture; a concurrent change yields stale_snapshot.
No source stash/reset/clean/add/commit/merge or repo configuration edits.
Reject submodules, symlink/reparse committed entries and unsupported capabilities;
reject source alternate objects/external .git indirection in first bounded version.
Pin all managed root/path identities, no user-chosen targets, verify ancestors.

Use fixed trusted Git executable and argv (no shell). Clear GIT_* inheritance and
untrusted global/system configuration; empty hooks, disable fsmonitor, external diff,
textconv, credential prompts, replace refs and submodule recursion. Source-local
config must not execute hooks/pack commands/filter side effects. Only local fixed
source import; forbid all other protocols, transports and arbitrary remote URLs.
Bound runtime/output/repo sizes; unsupported Git returns explicit error. Keep state
only under private managed root, no credentials in logs. Cross-platform filenames
parsed with NUL and decoded without data loss; reject unsafe/unrepresentable names.

## Tests/evidence

All mutations in tmp_path dedicated Git repos; verify original status/HEAD/index/
content unchanged. Real two independent worktrees with conflicting same-line edits
must report actual Git conflict. Nonconflicting committed edits produce immutable
awaiting-approval candidate. Dirty files must be explicit and preserved. Regressions:
project/task auth, stale head, paths/links, malicious config/hooks never run, private
repo isolation, independent objects, concurrency/idempotency and interrupted intents.
M5 approval/application and true automatic relay remain unimplemented/releaseblocked.
