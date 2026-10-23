# Technical decisions

## M5B3A2: existing content without reconstruction or acceptance authority

Authenticate/capture DB provenance, open existing managed storage, validate strict
disk receipts/intents and Git indirection before commands, export actual pinned
candidate objects, repeat checks and finally recapture owner/task metadata. Reject
extra bare .git entries before repository discovery. Keep content/provenance
fingerprints separate from future execution/task authority; no caller object grants
permission. Read-only excludes persistent records/commits, not bounded temporary
Git output files. OS-level filesystem integrity remains trusted.

## M5B3A1: metadata capture before applicable input export

Keep this quota-bounded increment DB-only and explicitly metadata. Capture all
related project records in one authenticated read transaction, strictly validate
receipts and return frozen values with an unkeyed versioned digest. This does not
make a caller-constructible dataclass an authority or prove a current filesystem.
Do not attach arbitrary historical baseline passes to a merged task result.

## M5B2C: cleanup observations do not release execution authority

Persist an additive schema9 one-shot cleanup intent and revoke the old token
before Docker. Require expired current ownership plus full create ACK; inspect
exact ID/name/nonce/image, remove only by full ID and observe absence on the same
daemon. A missing initial object or unknown ACK cannot prove cleanup. Save a
separate bounded receipt, preserving the original backend result and permanently
unverified pending job. A consumed intent is never automatically resumed; this
bounded stage does not solve general crash reconciliation, late create or retry.

- D001: Execute M0-M2, not the entire v1.0 plan, matching the user's immediate scope.
- D002: Python >=3.11 and official `mcp==2.3.0` v2. Verify installed APIs, not v1 snippets.
- D003: stdlib SQLite instead of an ORM; small explicit migrations and transactional claims.
- D004: strict schemas, hashed credentials, project/session checks are included now because
  adding authentication after exposing task mutation would produce an unsafe foundation.
- D005: `review` differs from `completed`; require a distinct agent, version and evidence.
  Full test-evidence validation stays M5. Registration under one admin does not prove human independence.
- D006: Distribution `agentsync-local`, import `agentsync`; no claim that a public PyPI name is reserved.
- D007: Exact direct dependency pins plus generated lock files; no unnecessary model libraries.
- D008: No global desktop client configuration changes or restarts just to simulate acceptance.
  Record unavailable real-host tests as pending; official SDK tests are protocol evidence only.
- D009: Native same-task Codex subagents implement separate file sets; lead independently verifies.
- D010: Alpha stores dependencies and lease fields inside tasks rather than creating separate
  empty future-stage entities; reviews are a real schema-v2 history table. Versioned transactional
  migrations live in storage/database.py and reject future schema versions.
- D011: Review found missing review attribution, unbounded SQLite integers, and inconsistent
  loopback host handling. Fixed with schema v2, strict numeric bounds and consistent CLI host choices.
- D012: Verified Codex through its public app-server with ephemeral thread and direct MCP tool calls,
  without starting a model turn. Claude Code was tested with isolated CLAUDE_CONFIG_DIR and only
  MCP registration/health commands. No existing user MCP configuration was edited.
- D013 (a2): Add a safe public CLI installer and intentionally register the real shared entry.
  D012's no-config-edit statement describes a1 only. The native CLI omits an unrelated empty args
  list; verified semantics otherwise match the backup. No credentials or raw config enter artifacts.
- D014 (a2): Close M2-05 connection acceptance using separate evidence: actual registered native
  discovery/calls and direct user-confirmed desktop connected status. Computer Use guidance
  forbids automating ChatGPT desktop UI, so no automated UI evidence is claimed.

## Full repository quality gate

Keep all archived Python scripts within Ruff scope. Add format --check to every
matrix job; retain test XML and builds in Actions artifacts. Preserve historical
version branches and release archives, and submit repair through a PR only.

## M3 immutable context and explicit handoff ownership

Use local SQLite FTS5 trigram, with escaped LIKE for queries shorter than three
characters. Save immutable context revisions and fixed snapshots in handoffs.
Submit revokes the old task lease; decisions reserve a fresh claim for at most
300 seconds. No file, URL or command in a package is executed. Schema v3 upgrades
previous data atomically. Transport wrappers dispatch only to the shared Core.

## M4A and formal release acceptance

Locks use canonical global physical keys to prevent overlapping projects bypassing
cooperative exclusion. Root identity is pinned; no user files are written. Release
acceptance separates coverage, execution and evidence strength. Local automated
checks cannot certify real model clients, adapters or autonomous relay. Missing or
unverified critical requirements block formal release regardless of pass counts.

## M4B Git isolation

Use independent bundle-seeded bare object storage; no worktree registration in user
.git and no import of uncommitted content. A third owned worktree checks actual merge
conflicts. Candidates await human approval; M5 must implement separately bound
approval before any apply endpoint. Sidecar receipts bind exact request inputs
across SQLite rollback. Unsupported executable source config is rejected explicitly.

## M5A separate owner authority

Persist bounded role sets and check before cached responses. Keep owner credentials
separate from Agent sessions and exclude owner operations from MCP. Approval is
authentication metadata only until M5B defines atomic consumed authorization and
verified execution isolation. Audit uses a metadata whitelist rather than trusting
freeform secrets redaction. Successful business state and audit share one transaction.

## M5B1 fixed external black-box verifier

Use an owner-controlled synchronous library before integrating durable workers.
Export bounded immutable Git objects, execute only standalone solution.py in an
inspected Linux Docker container, and keep all expected-output comparison on the
trusted host. Deliver source/input through stdin with no host mounts. Fixed finite
profile success is scoped evidence, not a claim of general correctness, arbitrary
project testing or actual model relay. Never fall back to host execution.

Daemon/kernel/image/verifier/owner profile are trusted infrastructure. Containers
do not defend against their compromise or equivalent host authority. Missing
Docker or effective controls fail closed. Create-response loss must not falsely
confirm cleanup; destructive cleanup requires exact full ID plus random owner.
Durable jobs and approval consumption/application remain separate designs.

## Local-only debugging on D:

The current owner instruction supersedes historical hosted-CI gates: GitHub is
storage only. Keep manual-only workflows, upload with [skip ci], and do not
dispatch Actions. A dedicated D:/agentsync-debug QEMU Linux VM provides real
Docker isolation with no host directory sharing; source/deliverables stay F:/syuc.
Only sanitized evidence is published; private keys, seed images and guest disks
are excluded. Final source/wheel/sdist each use independent interpreters and
unique evidence directories, with the exact frozen SHA/tree recorded.

Docker Config.Env may retain unique bare names representing explicit removal of
validated image metadata. Recognize only those expected markers while requiring
all valued settings to match the fixed runtime policy. Independently guard the
actual process environment inside the fixed bootstrap before reading candidate
bytes. Unknown, duplicate and valued-extra entries remain rejected.

## M5B2A ledger before executable recovery

Persist only snapshot/profile hash bindings and a fenced attempt ledger before
connecting an executor. Keep all states explicitly unverified and add no success
completion operation. Owner recovery invalidates a lease and records interruption;
it does not claim container cleanup or restart safety. Database fencing alone
cannot prevent delayed Docker create after a crash. Future execution integration
must separately solve that ownership/reconciliation boundary.

## M5B2B single execution with fail-closed uncertainty

Keep fixed owner snapshot/profile authority and short transactions. Persist exact
create intent and acknowledgement using private trusted hooks; hooks cannot choose
commands or flags. Rebuild schema7 ledger constraints transactionally without
dropping historical rows or disabling FK checks. Store execution phase separately
from finite-profile assessment. Unknown create/crash/expired authority remains
unverified and cannot be recycled by old ledger APIs. Preserve diagnostic backend
observations without granting success-writing authority. No exactly-once or
automatic crash cleanup guarantee is claimed.

## M5B3B0 capture inside the caller transaction

Extract the existing metadata read as a private authenticated seam, retaining
public capture's validation and transaction lifetime. Future queue insertion must
compare in its own write transaction; reading through another connection before
insertion is insufficient. This prerequisite creates no queue or successful
verification and does not extend trust to arbitrary caller-created databases.

## M5B3B1 candidate queue remains separate from snapshot execution

Persist checked candidate observations in new tables and preserve old snapshot
job shapes and semantics. Never substitute the baseline executor's commit with
a candidate SHA. History receipts are original mutation observations; current
state is a distinct get/list projection. Replay is owner-authenticated and DB-only,
not renewed Git freshness or execution authority. Final binding comparison and
insert/request/audit share the write transaction, while export stays outside it.
