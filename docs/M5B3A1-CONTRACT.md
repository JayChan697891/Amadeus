# M5B3A1: immutable candidate metadata binding

This bounded stage adds only `OwnerCandidateBindings(core).capture(...)`, an
internal owner seam. It is not registered in Core, HTTP, MCP, CLI or SDK dispatch.
There is no migration, job creation, execution, approval, completion gate or apply.

The caller supplies project ID, admin token, candidate ID and a complete expected
candidate SHA. Strict request validation precedes one read transaction. Owner
authentication precedes candidate lookup. Candidate, both worktrees, their common
snapshot, both tasks and creator sessions/agents must belong to that project.
Snapshot/create/candidate receipt operations and IDs, task/snapshot/base relations,
repository identity/config metadata and the exact existing `operation=merge`
input binding must agree. Create receipts retain their original base HEAD; they
are deliberately not compared with later candidate branch SHAs.

Stored JSON must be an object, at most 65536 UTF-8 bytes per receipt, with no
duplicate keys, non-finite numbers, invalid Unicode or excessive recursion.
Malformed metadata produces a fixed safe error; database failures produce a fixed
storage error. Foreign linked rows disclose no row contents. No token is returned.

The frozen dataclass contains only strings, integers and tuples. Receipt order is
snapshot, left create, right create, candidate. Creator session ID order matches
that receipt order. Receipt strings are canonical sorted compact JSON. The
SHA-256 provenance uses canonical JSON containing schema
`agentsync.candidate-binding.v1`, all scalar dataclass fields except the digest,
receipt SHA-256 values and creator session IDs. Captured task versions are part of
the digest, so later capture after task changes differs; old returned values do
not mutate. This is a metadata fingerprint, not a signed attestation.

`source_kind=managed_merge_candidate_metadata` explicitly excludes filesystem,
Git object, current HEAD, clean state, disk receipt, parent, candidate bytes or
execution verification. No backend construction or filesystem work occurs, apart
from opening the existing SQLite database. Future exporter stages must validate
disk/Git evidence and recheck database/task state before using candidate content.

Unit tests use synthetic metadata in real temporary SQLite databases and must
never count as real Git or Docker verification. Root-owned integration tests may
check compatibility with actual existing Git-generated receipts separately.
Debug caches/temp/logs live on D:, source on F:, GitHub is storage only.
