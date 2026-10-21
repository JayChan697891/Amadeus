# Current M5B2A development checkpoint

Version0.3.0a3/schema7: internal owner-authorized durable verification job/attempt
ledger, no executable worker or successful verification outcome. Contract and
guide: M5B2A-CONTRACT.md / M5B2A-GUIDE.md. Separate branch from M5B1.
Developer preflight on the working tree:26new policy cases,28focused cases pass;
Windows full source766pass17explicit skips. Lead independently inspects code and
will run final frozen-source/wheel/sdist validation locally on D:. These preliminary
counts do not certify a later commit. No GitHub Actions is used; main is unchanged.
Full M5, real client relay and formal release remain BLOCKED.

---

# Verified local M5B1 checkpoint

Code cfb5304c3979fc1677c73618120c0d33f928018a, tree5e8580769ead8be5a6b4a21ee269aa0a0da01be6.
D:/agentsync-debug Linux collector18/18pass; source/wheel/sdist each754pass3Windows-onlyskip.
All14 real Docker tests executed in each interpreter;42 safe result records and42
independent exact-container absence checks. Windows same-product source740pass17skip.
Lead verified saved hashes, JUnit, installed origins and Git/wheel/sdist/verifier
module consistency. Evidence: acceptance/evidence/m5b1-local-inspection.json and
acceptance/RELEASE-ACCEPTANCE-REPORT.md. Work acceptance remains separate.
GitHub storage only; no new Actions execution. Private debug runtime stays D:.
Full M5, actual adapters/relay and formal release remain BLOCKED.

The observations below are historical checkpoints, including preserved RED evidence.

---

# Current M5B1 verifier foundation (Issue15)

Current local debug environment is D:/agentsync-debug (see LOCAL-DEBUG.md).
A verified QEMU/Alpine VM now runs Docker29.8.2, cgroupv2 and builtin seccomp.
Actual local reproduction isolated the environment predicate as the only mismatch:
Docker's bare expected ENV deletion markers were mistaken for extra process vars.
Recognize only markers derived from validated image metadata and guard the actual
container environment before reading candidate source. Move the canary to traversable
host /tmp. All14 real Docker cases then passed in9.80s. Final exact-commit source/
wheel/sdist collection is the next gate; this preliminary run does not certify a
later tree. No GitHub execution was used. Full M5 and formal release remain BLOCKED.

The observations below describe earlier checkpoints and are preserved as history.

Local source regression after resume:716 passed/17 skipped (14 unavailable real
Docker,3 Windows symlink privileges),162.81s. Ruff/format/mypy26files passed.
See acceptance/evidence/local-only-20261020.json and redacted JUnit/log. Real Docker
still unverified; no Actions run was requested.

2026-10-20 user override: GitHub is storage only; no more Actions debugging,
testing or benchmarks. Both workflows now have manual-only triggers and uploads
use [skip ci]; the agent must not dispatch them. Validation is local/other
authorized compute only. This host has no Docker/Podman and WSL reports it is not
installed. Real Linux isolation remains unavailable here and must not be bypassed.
Preserve historical failures; local policy/Git tests cannot certify real Docker.

Version0.3.0a2, feature/m5b-verifier based on PR14 headf1f13ded.
PR16 first head227512a ran actual Docker gate39437105068:14 cases failed with
isolation_mismatch before candidate execution; all reported cleanup confirmed.
Actual backend acceptance is FAILED, not skipped/passed. Preserve this failure;
add safe effective-control diagnostics, identify the actual mismatched control,
repair only with evidence, then rerun the complete final-head gates. Local first
head source715pass17skip does not erase the Docker failure. No next implementation
stage is accepted until this gate and Work review are complete.

PR14 exact head passed9/9 quality jobs in run39433390898. Lead downloaded all9
ZIPs and verified every saved log/artifact hash, clean/stable source and matching
tree74072e7. Source/wheel/sdist each594cases: Windows594pass, POSIX591pass3skip.
Actual local collector18checks passed, three suites each592pass2permission skips.
Evidence: acceptance/evidence/rat14-ci-inspection.json and
F:/syuc/work/rat-followup/release-20261020T134712Z-3c60ae469b61. Work independent
reacceptance requested for this exact head; do not infer its decision.

M5B1 adds only an owner-controlled fixed black-box library: immutable managed Git
objects, bounded standalone solution.py, no host execution/mounts, inspected Linux
Docker isolation, trusted external JSON assertions and exact container cleanup.
See M5B1-CONTRACT.md / M5B1-GUIDE.md. Preliminary local source regression passed
703cases with16 explicit skips before the final cleanup repair; this is not final
head evidence. Actual Docker14cases are skipped locally because no backend exists.
Dedicated LinuxCI must execute them without skip/fallback before backend acceptance.

No agent-facing verifier API, job queue, restart recovery, task auto-acceptance,
approval consumption or source apply is added. M5B integration/M5B2, M6-M9 and
real autonomous relay remain open. Formal release BLOCKED; main unchanged.

---

# Release Acceptance package-install stage (Issue13 history)

Runtime version0.3.0a1 remains unchanged from M5A head7479dfa. Separatebranch
feature/release-sdist-acceptance improves tooling only. ParentPR12 nineCIjobs passed;
lead downloaded/hash-inspected all9 reports/JUnit/builds (see evidence/m5a-ci-inspection.json).
M5A local exacthead source+freshwheel each561pass2symlinkskip; all12checkspassed.
Work independently accepted the M5A scope at7479dfa (PR12 comment6286926323).
M5 stages remain partial until verifier/apply.

Issue13 adds fresh isolated sdistinstall/fulltests with exactarchiveSHA/PEP610origin,
independent wheel/sdist failure gates, installer-destination isolation and redacteddiff.
61 runner-policy unit cases passed; these mocks are not actualartifact/client proof.
At d8bc571, actual local source/wheel/sdist each585pass2symlinkskip, all18 checks
passed with clean stable source. Remote run39395631073 completed8/9: Ubuntu3.14
source failed because fixture Git spawned asynchronous maintenance and its lock
vanished between full fingerprints. Wheel/sdist passed. Fixture repair retains
every fingerprint assertion; newhead full local and nineCI gates remain pending.
See acceptance/INSTALLATION-REPORT.md and ERRORS.md for failure evidence.
Formalrelease remainsBLOCKED; actualadapter/autonomousrelay/sandboxverifier unverified.

---

# Current M5A stage (2026-10-20 America/Tijuana)

Version0.3.0a1, Issue11, feature/m5a-permissions. Contract: M5A-CONTRACT.md.
M4B exacthead98bd361c47f94b61ef03439651e2163ba6740a1f passed stable full12localchecks
(source+cleanwheel370pass/2Windowspermission skips), then nine remote CI jobs.
All9artifacts were downloaded and SHA256/contents checked; report trees match head
4df79c6dead14a86396f3957a24e79e4fbd2f376. Each source/wheel has372cases; Windows372pass,
Linux/macOS369pass/3Windows-only skips. See acceptance/evidence/m4b-ci-inspection.json.
Work independently accepted currentM4Bhead and closedIssue9; PR10receipt6284302265.
Approvedscope is prepare-only candidates; actualapply remainsM5B.

Current work: defaultviewer membership grants, owner-only role/approval control plane,
strict authorization before cachedresponses/objectlookup/Git, bound expiring approvals
and whitelist structured audit. Intentional security migration makes oldmembersviewer;
owner must explicitly regrant write/review roles. All existing tests must retain their
original assertions with explicit owner setup, never global permission monkeypatching.

No apply-to-user-branch endpoint or independent verification executor is added.
Owner credentials are a capability boundary, not proof of a physical human against
sameOS access. Actual unsafe submitted tests require a verifiedOSsandbox; Docker,
Podman/runhcs are unavailable in this local runtime; WSL presence alone is not proof
of safe isolation. M5B verifier remains blocked until proper execution isolation.
FormalReleaseAcceptance and actualmodelautonomous relay remain unverified/BLOCKED.

Next: finish exactsource/wheel/9CI/Work gates for M5A, then bounded M5B verifier
runtime/approvalconsumption. Continue M6-M9 only with their explicit test gates.

---

# Current M4B checkpoint (supersedes historical entries below)

Version 0.2.0a3, Issue #9, independent branch feature/m4-worktrees based on PR #8.
M4A exact head fe3ac7418413f4740f158035605ac2843b9c964d passed all12 local checks
(source/wheel326pass2skip) and9CI jobs. Nine artifact archives were independently
hash-verified; tested merge tree c593af08 equals head tree. Work independently accepted M3/M4A, closed Issues #4/#6 and kept #7 open.
Receipt: PR #8 issuecomment-6284092991. No main merge.

M4B implements independent Git object store/worktrees, real third-tree conflict
checks and awaiting_human_approval candidates. No original user-repository write
or approved apply endpoint exists. Source-config filter/include execution and
post-crash request rebinding were found in lead review and repaired with regressions.
Current final full source/wheel and CI evidence must be generated after edits freeze.
M4-05 approval/application and M5-M9 remain incomplete. Formal release BLOCKED.
All42 formal requirements remain tracked; new component coverage does not automatically
pass full acceptance cases. No real model/client autonomous relay has been verified.

Next: finish exact-SHA regression/installation/remote evidence and Work review, then
M5 approvals/audit/independent evidence verifier, M6 actual adapters, M7/M8 scheduler/
recovery and M9 full release run. Preserve every prior test and failure reproducer.

---

# Current checkpoint: M4A and Release Acceptance

Date: 2026-10-19 (America/Tijuana), version 0.2.0a2.
M3 source and installed-wheel tests passed (142 each), PR #5 CI passed 9/9 at
72ab6b5. Submission to Work is recorded; it is not a Work acceptance decision.

M4-01/02 implements canonical path inspection, SHA-256 file versions, cooperative
file/directory locks, lease ownership/replay/expiry protections and schema v4.
All three transports share Core. M4-03..05 remains pending; no user-file write or
merge API exists. Baseline before acceptance infrastructure: 211 passed / 1 skipped;
final evidence is generated by the acceptance runner after all edits.

Release Acceptance (Issue #7) adds complete formal requirement traceability,
separate real-client capability evidence, isolated process-death recovery tests,
fail-closed formal release gates and reproducible reports/logs/JUnit/build identity.
Current release conclusion is BLOCKED while real autonomous relay and M4B-M9 remain
unverified. See acceptance/DESIGN.md and acceptance/CLIENT-MATRIX.md.

Resume: read the current contract and generated report; repair any failed local or
remote checks, submit this checkpoint to Work, then implement M4-03..05 in a separate
bounded branch. Continue M5-M9, adding acceptance cases at each stage. No paid API
calls, main merge or formal Release without authorization. Do not infer a passed
requirement from a test file merely existing.

---

Historical evidence follows; the current checkpoint above supersedes old stage labels.

# Progress and recovery

Date: 2026-10-19 (America/Tijuana). Version: 0.2.0a1 under development.
Current execution scope: **M3-01..04**, Issue #4. M4-M9 remain planned.
M3 local verification: 142 tests passed, full-repository Ruff lint/format and mypy
(16 source files) passed; wheel/sdist built. Clean-wheel and remote CI acceptance
are recorded in M3-REPORT.md and the associated PR before Work signs off.
The table below records the historical M0-M2 checkpoint. Its Ruff repair PR #3 was
independently accepted by Work at 3c429ea, with all 9 CI jobs and their artifacts
verified. PR #3 remains unmerged. M3 development is based on that accepted branch.

| Work | Evidence / status |
|---|---|
| M0-01 | Windows Python 3.14 source install; Python 3.12 clean wheel install |
| M0-02 | CONTRACT.md, ARCHITECTURE.md; state/identity/version/lease rules in Core |
| M0-03 | Local Git repo, MIT, exact direct pins and runtime/dev snapshots; no remote push |
| M0-04 | 92 tests on each interpreter; Ruff clean; mypy clean (15 source files); CI configured |
| M0-05 | Plan, specification, progress, decisions, error log, compatibility and test report saved |
| M1-01 | Agent IDs, sessions, heartbeat, expiry and derived online state |
| M1-02 | Project-scoped access, tasks, immutable dependencies, priorities |
| M1-03 | SQLite atomic claims, expected versions, scoped idempotency; claim races tested |
| M1-04 | Renewable ownership leases, explicit expiration reclamation; stale owners rejected |
| M1-05 | WAL, transactional v1/v2 migrations, persistence, bounded startup contention handling |
| M2-01 | Official MCP SDK 2.3.0 stdio, 11 explicit typed tools |
| M2-02 | Two independent MCP server processes share the same absolute database; one claim winner |
| M2-03 | Python AgentSyncClient uses Core, consistent envelopes |
| M2-04 | Authenticated loopback HTTP, real TCP and ASGI tests, shared state with SDK |
| M2-05 | **Connection gate complete**: registered native config/tools verified; user confirmed current desktop UI shows agentsync connected; Claude Code CLI also connected |

Native same-task Codex agents implemented core and integrations and independently reviewed security.
The lead inspected actual source, ran full checks, repaired review provenance, numeric bounds and
startup concurrency, rebuilt the package and retested the installed wheel.

Current source Python 3.14.6: `python -m pytest -q --junitxml=docs/pytest-m2-followup.xml`:
**92 passed in 7.40s**. Clean installed a2 wheel Python 3.12.14:
`python -I -m pytest -q --junitxml=docs/pytest-m2-followup-python312.xml`: **92 passed in 7.55s**.
Ruff: all checks passed. Mypy: 15 files, no issues. Build: wheel and source distribution built.
Pip check: no broken requirements. Details and limits: TEST-REPORT.md, COMPATIBILITY.md.

M2-05 was closed in this continuation: the public CLI installed the actual shared MCP entry,
native probes loaded that entry without overrides, and the user directly confirmed the desktop
UI displayed agentsync connected. UI observation is user-reported, not automated clicking or
screenshot evidence. A complete model-driven two-desktop development session remains a later
end-to-end scenario; it is not needed to claim that this M2 connection gate is complete.
See M2-CONTINUATION.zh-CN.md and the distinct probe/confirmation JSON records.

Historical limitation updated: Windows/Linux/macOS x Python 3.11/3.12/3.14 passed
remote CI for PR #3. Independent verification of submitted in-product review evidence
remains M5. Project-enrolled identities are not external OAuth identities. GitHub
publication and owner-only Codex Cloud setup were subsequently user-authorized.
No paid provider API calls or public package Releases were made.

## Resume steps

1. Read AGENTS.md, WORKFLOW.md, PLAN.md, this file, CONTRACT.md and TEST-REPORT.md; inspect Git status.
2. Preserve verified coordination rules and the existing failure regressions.
3. M2-05 connection gate is closed; preserve distinction between user UI confirmation and native probes.
4. M3-01..04 is implemented; finish its independent wheel/remote/Work acceptance gate.
5. Continue M4 path boundaries, cooperative locks, isolated Git worktrees and conflict detection.
6. Continue M5-M9 from PLAN.md; record evidence and checkpoints at each stage.

## Ruff CI follow-up

Issue #2: Codex repaired full-repository Ruff violations without runtime changes.
Local 92 tests, lint, format, types and build passed. PR-head remote matrix is the
acceptance gate; see RUFF-CI-REPAIR.md. main remains unchanged.
