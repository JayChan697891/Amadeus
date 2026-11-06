# Cancellation privacy repair — 2026-11-05

执行方：Codex。This is a repair to Work's existing PR31 blocker, not a new M5 stage.
Work found that adapter-generated CancelledError bypassed ordinary Exception guards.
The old alpha26/27/28 artifacts retain their actual historical passing results but
do not cover this defect and must not be used to declare the repaired heads accepted.

The manager now denies callback/getter entry with an outstanding cancellation
request. Pending cancellation remains cancellation, with a fresh message-free
CancelledError raised outside handlers. Internal callback/receipt/result-property
CancelledError without a pending request becomes the existing fixed public error.
The count is policy, not authenticated exception provenance. A caller that swallowed
its cancellation must clear the request before resuming lifecycle work. Successful
callback returns also recheck pending requests. KeyboardInterrupt/SystemExit,
dispatch ownership, shielding, replay and no-retry behavior remain unchanged.

## Actual frozen local evidence

Each row executed Windows Python3.14 source, Python3.11 source, fresh offline Windows
wheel and rebuilt sdist: identical IDs within that row, all pass, zero failure/error/skip.
These are affected suites, not whole repository suites or cross-platform acceptance.

| PR | Frozen product/test commit | Cases passed in each of four environments | Retained + new |
|---|---|---|---|
| #31 | `09c2f059bdf13ff32eaf48f9c28af6bb80850d38` | 179 | 152 + 27 |
| #32 | `67454ca4772b223dd94910ccabad5efe07987b00` | 286 | 259 + 27 |
| #33 | `cc72e2cf2dbc3b27faba7ef50adcaf1ae2dfed38` | 178 | 151 + 27 |

Each branch has its own `docs/acceptance/evidence/cancellation-pr<PR>-<shortSHA>.json`
and `releases/<version>/checkpoints/cancel-pr<PR>-<shortSHA>.tar.gz`. The shared
`evidence/cancellation-stack-summary.json` indexes all three branch-specific
archives; an archive for another PR may require switching to that branch.
Raw logs/JUnit, packages, origin/hash records, drivers, RED26 + success-path RED1,
and Astra's hash-bound static review are preserved. Root independently checked
Git/source/install bytes, all63 runtime origins per environment, JUnit IDs,
artifact/log hashes and every archive-manifest member. Ruff/format/mypy63 passed.
Astra did not run tests; no open blocker in its bounded static review.

New heads contain the same reviewed manager and unit-test bytes. Later commits
only add evidence/docs or merge that repaired baseline. Existing version numbers
are unreleased development versions; SHA and archive hash identify each checkpoint.

## Remaining gates

Work revalidation is PENDING until its actual updated-head feedback is read.
This repair does not accept full B3 output auditing, M5 or Release. Whole-repository
Linux/macOS and full installed suites at these commits, real clients/model tasks,
autonomous relay and42formal requirements were NOT RUN. No Actions, paid API,
client task, VM startup, main modification/merge or account configuration change.
The Claude handoff/package remains cancelled.
