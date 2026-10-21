# Release acceptance coverage review —0.3.0a4

Source: b5504e09bf1cb1c390d56cac11e68a8176d2091d. All observations below come from the indexed local run,
not from GitHub Actions or model assertions. See RELEASE-ACCEPTANCE-REPORT.md and
evidence/m5b2b-local-inspection.json for full evidence and immutable build hashes.

## Observed component checks

- 18 selected local checks passed; zero executed check failures.
- Linux editable source, wheel and sdist each ran850cases:847passed/3Windows-only skips.
- Windows source ran850cases:826passed/24skips (21Linux real cases and3link privileges).
- 63 real Docker observations:42existing backend cases plus21integrated owner cases.
- Each owner environment deliberately produces1passed,4failed,1cancelled and1unverified
  durable assessment; all7test expectations pass. Backend success after lease expiry
  remains observation_only evidence and cannot turn into a passed durable assessment.
- All63exact container IDs independently absent after execution.

These are component and bounded-library observations. Native development agents
and Work reviewers do not count as AgentSync control adapters or autonomous relay.

## Formal requirement coverage and execution gaps

The frozen register contains42formal M0-M9 requirements. Coverage inventory:
18existing, 13partial, 11missing. Existing means selectors cover the
stated implemented component; it does not mean full requirement acceptance passed.
All42complete formal scenario executions remain not_run in this staged report.
Formal evidence statuses: 38not_run and 4unverified. Historical limited Work
acceptances remain valid only for their exact bounded scope and product SHA.

| Release-critical area | Current limitation | Required next proof |
|---|---|---|
| Candidate and task applicability | Executor accepts captured baseline snapshots; review_task remains an asserted reviewer workflow | Immutable merge/worktree subject binding, task submission/version linkage and matching independent execution gate |
| Approved application | Approval records are metadata; no safe apply/consume operation | Single-use approval bound to actor/action/resource/expiry/target HEAD plus durable Git CAS intent and crash reconciliation |
| Recovery | Expired/crashed/unknown creates fail closed; no automatic retry/reconciliation | Real process termination/restart tests and exact-owner orphan recovery without late-create false absence |
| Actual client adapters | Codex/Claude historical discovery/health is limited; no current real model-driven control adapter/relay | Named client/version/interface/auth-category runs, genuine execution/session/exit/cancel evidence |
| Scheduler and budgets | Automatic capability scheduling, retries/decomposition and reliable budget accounting unfinished | Deterministic mock contract followed by separately authorized real-client coordination |
| Cross-platform/packages | Current run covers local Windows/Linux Python3.14; complete supported matrix not run | Every claimed OS/Python installation, package, concurrency and security gate |
| Final M9 | Full requirement scenarios, actual autonomous relay and final release evidence incomplete | Complete isolated end-to-end release candidate run and independent evidence-backed sign-off |

Real provider rate-limit behavior and paid API execution are not exercised.
Injected partial-create/clock/storage/crash tests are labelled policy tests.
No source apply, paid call or production-data migration occurred in these tests.

## Release decision

**BLOCKED.** Passing all implemented local checks cannot replace missing critical
requirements, actual adapters/relay, approved application or crash recovery.
M5B2B is a limited owner-library checkpoint awaiting Work's final evidence review;
Issue11/7 remain open. No formal release was published and main was not merged.

Continue in bounded stages: subject/applicability binding, verified task review,
approval/application and recovery, actual adapters/scheduler, then full M8/M9 gates.
Before starting a stage reserve quota for tests, fixes, storage and independent
review; near the limit finish the reviewable checkpoint instead of starting another.
