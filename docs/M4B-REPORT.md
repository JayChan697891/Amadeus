# M4B development acceptance report

Version 0.2.0a3; Issue #9; parent M4A PR #8 head fe3ac7418413f4740f158035605ac2843b9c964d.
This is a staged development checkpoint, not final product acceptance.

## Implementation

Five shared-Core operations capture committed-only repository state, create owned
independent worktrees, inspect them, compare fixed commits in a third worktree and
prepare immutable candidates with status awaiting_human_approval. Schema v5 adds
project-scoped snapshots/worktrees/candidates without replacing existing records.
Public MCP tool count29. No apply/cleanup/reset/stash/user-repository write API.
Service state and registered source repository must be disjoint.

Source .git metadata and committed entries are bounded and inspected; external
Git directory/object indirection, submodules, symlink entries and executable
filter/include configurations are explicitly unsupported. Global config, hooks,
fsmonitor, external diff, credentials and inherited GIT variables are isolated.
Git runs use argv, a time/output watchdog and a fixed discovered executable.
These are cooperative local defenses, not a hostile-OS-process sandbox.

Original dirty/untracked files are reported but not imported. All worktree mutations
and actual merges are under service-owned independent object storage; original
files, index, refs and .git fingerprints are checked by isolated Git tests.
Conflicting merges produce actual Git conflict paths/exit codes, not merely path
overlap. Approval/application and independent command verification remain M5 work.

## Lead review and failure reproduction

Lead review identified source status clean/process filter execution and executable
include configurations. Capture now rejects these before any status/pack operation.
Further review reproduced durable sidecar receipt / SQLite rollback allowing a new
payload to reuse an old worktree/candidate; request inputs now bind snapshot, task,
ordered actors and exact revisions before replay. RED and GREEN regressions were
saved separately. Interrupted create/commit side effects recover without overwriting
unknown work. A nested source/service-state regression prevents managed directory
creation inside the user's registered source repository.

## Evidence and limits

Targeted independent Git suite:27 cases passed before the additional2 binding
regressions; both added cases were observed fail then pass after repair. Real
MCP subprocess/HTTP/SDK roundtrip covers all5 operations and preserves original
repository fingerprints. Exact v4-to-v5 lock/root/context migration and storage
overlap tests pass. Full stable-source/wheel runner and final published CI are the
aggregate acceptance evidence, recorded separately rather than inferred here.
All destructive tests run in temporary dedicated Git repositories under F locally.
Failed pytest/JUnit output must be redacted before durable evidence publication.

M4A9CI artifacts were actually downloaded and hash-checked; see
acceptance/evidence/m4a-ci-inspection.json. PR workflow merge tree equals its head
source tree. Those results do not certify this new M4B code.

## Release Acceptance conclusion

BLOCKED: the42formal requirement cases are not automatically accepted by component
checks. M4-05 approved application, M5-M9, real control adapters and real automatic
two-Agent relay remain unverified/incomplete. No Mock/protocol subprocess is claimed
as a real model client. No paid provider API calls, main modification or merge.
After final CI, Work must independently review the exact SHA and actual artifacts.
