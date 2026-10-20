# M3 context and handoff checkpoint

Execution: Codex. Issue #4. Version 0.2.0a1. Based on Work-accepted PR #3.

## Implemented

| Plan item | Concrete behavior |
| --- | --- |
| M3-01 | Five context kinds, explicit summary/source, project/session authentication |
| M3-02 | Immutable revisions, expected-version updates, latest-only SQLite FTS5 search, historical reads |
| M3-03 | Structured package with fixed context snapshots, author/recipient identities, file/evidence metadata |
| M3-04 | Submit/accept/reject/withdraw; invalidated sender lease, fresh claims, identity reservations and reassignment |

All 18 typed MCP tools, HTTP and SDK share one Core. Schema v3 upgrades empty,
v1 and v2 databases transactionally, preserving original tasks, results and reviews.
SQLite's trigram tokenizer supports literal substring queries of at least three
characters; shorter queries use an escaped LIKE scan for Chinese short words and
literal punctuation. Project/kind filters apply before pagination on either path.
Summaries and sources are caller-authored metadata, not generated or authenticated
external facts. See [SQLite FTS5](https://www.sqlite.org/fts5.html#the_trigram_tokenizer).

## Lead review and verification

The lead inspected the actual Core, models, migration and transport changes and
ran the full test suite independently against F-drive source: **142 passed in
15.14s**. Ruff check passed; format check passed; mypy passed for 16 source files.
Wheel and sdist built successfully.
The wheel was then installed with development dependencies in a fresh environment
outside the checkout. Isolated Python imported agentsync from site-packages at
version 0.2.0a1; the full suite again passed: **142 passed in 15.23s**. Pip check
reported no broken requirements.

New tests preserve the original suite and cover
project isolation, immutable history, literal search, strict input/size limits,
pinned snapshots, old/expired leases, wrong identities, concurrent decisions,
idempotent replays, version conflicts, migration and reopening persisted state.

During review the lead found a recovery gap: an accepted-but-unclaimed handoff could
reserve a task forever if the recipient disappeared. Reservations now expire within
300 seconds and no later than the relevant valid session. Three dedicated regressions
prove timeout recovery, session-expiry capping, expired-sender fallback and replay
after a replacement claim. The old sender lease remains invalid throughout.

The suite launches independent Python MCP client and server processes: A publishes
context v1 and submits a handoff, context advances to v2, B reads the fixed v1 snapshot
and latest v2 separately, accepts and claims with a new lease, continues and submits
review; A records a separate-agent review. The example writes no credential files.
Run `python examples/m3_handoff.py --data-dir` followed by a fresh absolute disposable
directory to reproduce it.

This is real protocol/process evidence, not model-driven desktop-host acceptance.
M0-M2's saved native host evidence remains historical and is not relabeled as an
18-tool desktop validation. M4 file access/worktrees and M5 automatic evidence
verification are not provided by this M3 checkpoint. Handoff paths/commands are
metadata and are never executed. SQL storage remains local-machine-only.

## Publication gate

Author changes are saved on feature/m3-context-handoffs. The PR links Issue #4 and
states execution by Codex. The nine operating-system/Python CI jobs and their JUnit/
build artifacts must pass on the final PR commit before Work acceptance. Main is
neither directly modified nor merged. Subsequent M4 work proceeds on its own branch.
