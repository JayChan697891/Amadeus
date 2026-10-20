# M4-01/02 resource boundaries and cooperative locks

Issue #6, feature/m4-resource-locks, version 0.2.0a2. Based on M3 PR #5.
This checkpoint implements paths, file versions and cooperative locks only.
M4-03..05 worktrees and Git conflict reports follow separately; no merge/apply API.

## Operations

All operations inherit existing Auth. All transports dispatch to the same Core.

- inspect_path: path (1..4096 relative characters). Return {path, exists, kind:
  file|directory|missing, sha256: string|null, size: int|null}. Do not return content.
- verify_file_version: path, expected_sha256 (null for expected missing, otherwise
  exactly 64 hex digits). Return inspection fields plus matches:bool. A directory
  never matches an expected missing file. SHA-256 comparison is case-insensitive.
- acquire_file_lock: path, kind:file|directory="file", lease_seconds=300 (1..3600),
  request_id. Return the new lock record plus lease_token once/on a valid replay.
- renew_file_lock: lock_id, lease_token, expected_version (1..2**63-2),
  lease_seconds=300 (1..3600), request_id. Return new version/expiry plus lease_token.
- release_file_lock: lock_id, lease_token, expected_version, request_id. Return a
  released record without token. Only the owning unexpired session/lease can release.
- list_file_locks: include_expired=false, limit=100 (1..100), offset=0 (0..10000).
  Return {locks:[public records], has_more:bool}. Only this project's records.

Public lock records: id, project_id, path (normalized relative), kind,
owner_agent_id, owner_session_id, version, status:active|released|expired,
created_at, updated_at, expires_at. Never expose hashes or tokens from lists.
Writes are authenticated/idempotent and run within Core's transaction. Acquire
tokens are deterministically derived with HMAC from session credential/request ID
and a lock-specific domain; SQLite stores only the hash. Existing Core redacts
top-level lease_token before caching. Acquire/renew replay must additionally load
the actual lock, check owning session/token, active expiry and cached response
version; superseded/expired/released locks cannot be revived by replay.

## Root and path boundaries

Schema v4 adds project_resource_roots and file_locks. Pin canonical project root
device/inode at new project creation. Legacy projects pin at first resource use;
future use verifies the same physical root. A replaced root or new link in its
ancestor chain is rejected. The recorded original project root must still exist.
Lock conflicts use global canonical absolute physical path keys, across projects,
so duplicate/overlapping project registrations cannot bypass locks. Foreign-project
conflicts return only a generic busy error, not owner identity or other data.

Accept forward/backslash relative paths but reject absolute/drive/UNC/device paths,
colon/ADS, NUL/control characters, empty or dot/dotdot components, trailing dot/space,
Windows reserved device names and every case-insensitive .git component. Only exact
path="." may represent the root directory; file-kind locks may not lock it.
Walk each existing component using lstat; reject symlinks/junction/reparse points,
nested repositories (a child directory has .git), and multiply-linked regular files.
Nonexistent targets are allowed after checking the closest existing ancestor.
Preserve actual path case for IO; canonical conflict keys case-fold on Windows and
conservatively on macOS, with slash component boundaries (a does not overlap ab).
Reject kind mismatches for existing objects. Never create/write/delete user files.

File inspection hashes at most 16 MiB, with before/after identity/size/mtime checks,
no-follow open where supported, and repeated path checks. Concurrent mutation returns
an explicit unstable-resource error, never a stable-looking hash. Directories and
missing targets do not have hashes. Report unsupported/oversized files explicitly.

## Lease semantics

One unexpired exclusive lock at a time per resource. File locks conflict with the
same file and any ancestor directory lock. Directory locks conflict with identical,
ancestor or descendant resources. Distinct files and sibling names may coexist.
Each acquire uses a new ID; old rows remain historical. BEGIN IMMEDIATE makes conflict
checking/insertion atomic across processes. Same-agent different sessions cannot
renew/release. Expired rows never block a new acquire, and old release/replay cannot
affect replacement locks. No secret is stored in responses cached by idempotency.

These locks are cooperative. They do not prevent unintegrated editors or malicious
external processes from replacing paths between checks. Do not claim OS-enforced
locking, hostile-process sandboxing, or race-free handle-based directory confinement.

## Acceptance

Retain all M0-M3 tests; update legacy migration version assertions to 4 without
removing their data-preservation checks. Test escape/aliases/links/nested repos,
root replacement, hash changes/missing/large/unstable files, cross-project physical
overlap, hierarchy boundaries, identities, tokens/expiry/version/idempotency,
two independent process acquire race, v1/v2/v3 upgrade and reopened locks/context.
Six explicit typed MCP tools make 24 total, plus HTTP/SDK same-Core coverage.
All nine CI jobs, source and clean-wheel tests, Ruff/format/mypy/build before Work.
