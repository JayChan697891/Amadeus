# Release acceptance coverage review —0.3.0a5

Source c1f2e83a61af5c267e3374dd46398b2a57b6abf1. Evidence and observed
results: M5B2C-REPORT.md and evidence/m5b2c-local-inspection.json.

18local checks pass; Linux source/wheel/sdist each895pass3skip; Windows869pass29skip.
78actual observations include15explicit cleanup cases after real executor process
termination. Lease expiry is a labelled fixture injection; policy mocks remain
separate. All78full IDs independently absent after all test-fixture cleanup.

The formal42requirement register remains18existing/13partial/11missing. Existing
selectors describe implemented components, not whole requirement acceptance.
All42formal scenarios remain not_run; evidence statuses38not_run/4unverified.

| Release-critical area | Current gap | Required proof |
| --- | --- | --- |
| Task applicability/gate | Passed baseline snapshot jobs are not task-submission evidence; review_task is asserted | Immutable applicable candidate/task/version/profile binding and independent verified acceptance |
| Application | Approval records are metadata | Bound single-use approval, Git CAS intent and crash recovery for safe apply |
| Recovery | Only one-shot acknowledged full-ID cleanup; intent crash cannot resume; unknown create remains unresolved | Bounded late-create/orphan policy and interruption recovery without false absence |
| Real clients/relay | Native development agents are not product adapters | Actual named Codex/Claude/other client execution, cancellation, handoff and independent relay evidence |
| Matrix/M9 | Linux current Python source/wheel/sdist and Windows current Python source only | Full supported OS/Python matrix, installation/release gates and M9 execution |

No critical executed component test failed, but these outstanding gates prevent
formal release. Conclusion: **BLOCKED**. Work limited-stage review remains separate.
