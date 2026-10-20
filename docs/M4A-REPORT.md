# M4A and Release Acceptance checkpoint

Version 0.2.0a2, Issues #6/#7. M3 parent: 72ab6b5a65bcb156dc1ddaba352dcf5def7445b7.
Current changes are a development checkpoint, not a formal release or completed M4.

## Actual execution

The isolated release runner executed all twelve local checks successfully: pytest,
Ruff lint/format, mypy, wheel/sdist build, source pip check, fresh wheel environment,
wheel install/pip check/CLI, isolated import/version/SDK smoke and installed-wheel pytest.
Source: **323 passed, 2 skipped**; fresh installed wheel: **323 passed, 2 skipped**.
Both skips require unavailable Windows symlink privilege 1314. Windows junction and
hardlink checks ran. The 325 collected cases include 87 traceability invariants and
22 runner-policy cases; they are not 325 completed product requirements.
Full JUnit, command logs, artifacts and hashes were generated under the run directory:
`F:/syuc/work/release-acceptance/release-20261020T052039Z-e15b07631c3d`.
Scratch/credentials were removed and excluded from durable evidence.
Actual installed origin was its fresh environment's site-packages, outside checkout.
The report records dirty source hashes; GitHub CI must rerun the final published SHA.

## Verified implementation boundary

M4-01/02 paths, SHA-256 versions and cooperative lease locks are implemented.
Schema v4 migration keeps prior tasks/reviews/context; typed tools total24.
No user files are written, no Git merge is performed. Root identity/link checks,
physical project overlap, hierarchy conflicts, lease expiry/replay/owner/version,
and real two-process lock contention have regressions.
Recovery test forces a real process exit, checks rollback and persistence from a
second process and verifies idempotency/integrity. Native development agents and
protocol subprocesses are not model-client control adapters.

## Release Acceptance conclusion: BLOCKED

42 formal requirements and all T01-T16 scenarios are traced. Coverage inventory:
14 existing component coverage,14 partial,14 missing. This is not execution status.
Formal requirement cases are not automatically passed by aggregate pytest results.
M4-03..05 and M5-M9 remain incomplete, real Codex/Claude/Cursor adapters and actual
autonomous two-Agent relay remain unverified; sdist installation and final current-SHA
platform/client evidence remain outstanding. No formal Release may be marked accepted.
See acceptance/DESIGN.md, requirements.json and CLIENT-MATRIX.md.

## Next

Run the same collector on the exact PR head on all nine platform/Python jobs. Preserve
failure artifacts with if:always. Hand the checkpoint to Work for independent review;
keep main unchanged. Continue M4B worktrees/conflicts/explicit safe-merge approval in
a separate bounded stage, then implement M5-M9 with the mapped acceptance cases.
