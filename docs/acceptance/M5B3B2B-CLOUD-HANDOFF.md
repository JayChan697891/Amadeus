# PR25 evidence completion and cloud handoff

执行方：Codex。Refs #11, #7. Documentation/static-inspection checkpoint only.
Date: 2026-10-23. Product and formal Release acceptance remain **BLOCKED**.

## Authoritative state inspected

PR25 is Draft at product `aac28a0f688962eca640b930e92eeaa608ff824f`, tree
`ea2937f959c224bf940852f73ca030a96112f98b`, version 0.3.0a11/schema12.
Its base is PR24 branch `feature/m5b3b2a-candidate-claim` at
`13fc7ecf73ff45ccf9204f91850a4da561ce0723`.
PR24's limited acceptance is already recorded; do not redo that stage.

PR25's existing [Work review](https://github.com/JayChan697891/agentsync/pull/25#issuecomment-6369038699)
found no definite code blocker in the bounded intent ledger, but explicitly
withheld acceptance because final package evidence was absent. This document
does not replace or upgrade that conclusion. Author-reported Windows 1071/30
and Linux source 1098/3 counts are leads to reconcile against raw results,
not independently verified pass totals. Wheel/sdist completion must not be
inferred from source results. Issues #11/#7 remain open.

## Work completed here

Read the exact GitHub bytes of AGENTS.md, WORKFLOW.md, SPECIFICATION, PLAN,
PROGRESS, intent contract, continuation handoff, intent/claim/queue/database
modules, the three intent test files, the existing evidence collector and both
workflow definitions. Python independently recomputed 17 Git blob IDs, sizes and
SHA256 values; all matched the frozen tree. Parsed test ASTs without importing
the product: 25 test definitions expand statically to 40 parametrized entries
across the three files. This is neither pytest collection nor execution.
The machine-readable input manifest and selector inventory are
`evidence/cloud-20261023-static.json`.

Only source inspection of `.github/workflows/ci.yml` and
`verifier-docker.yml` was performed: both declare `on: workflow_dispatch`.
No Actions API, dispatch, execution or benchmark was used. Uploads for this
checkpoint use `[skip ci]`; do not change these triggers.

No product tests, package build, candidate import/execution, Docker inspection,
local VM, local drive or desktop client was accessed. There is no product JUnit
or new build from this checkpoint. Missing package/Windows/Docker evidence stays
blocked until the original sanitized evidence is uploaded or an authorized
environment actually reruns the required checks. Saved old Docker evidence may
be checked statically; it cannot establish current daemon state.

## PR25 closeout matrix

Use the existing `tools/release_acceptance.py`, existing test suite, and the
intent contract. Do not build a second collector or silently weaken assertions.

| Gate | Existing source / required saved evidence | Current disposition |
| --- | --- | --- |
| Frozen identity | report commit/tree, clean working tree, source stability, all source-file hashes | Final report not uploaded at inspected head |
| Three Linux environments | source, fresh wheel, isolated sdist report/logs and complete JUnit; installation origins, direct_url and artifact SHA | Final package evidence missing; no cloud rerun asserted |
| Windows regression | full frozen-source JUnit/log and matching source snapshot | Requires saved local evidence or later authorized Windows run |
| Intent behavior | `tests/integration/test_candidate_intents.py`; match exact class/name and parameter entries in each full JUnit | Static definitions inspected; execution not_run here |
| Audit boundary | `tests/integration/test_candidate_intent_security.py::test_intent_audit_identifies_resource_revisions_without_plain_credentials` | Definition inspected; execution not_run here |
| Schema12 history | four tests in `tests/integration/test_candidate_intent_migration.py` | Definition inspected; execution not_run here |
| Actual raw observations | prepared and abandoned/recovered observation per Linux prefix, raw rows/proof/receipts/current views | Require six new intent JSON records, distinct from old claim evidence |
| Package identity | every Python module in frozen Git vs wheel vs sdist, installed origins, package archive hashes | Do not copy PR24's 33-module or 253-file counts; enumerate PR25 anew |
| Saved regressions | old queue/claim/metadata/input records and 78 full-ID Docker observations with saved exact-ID absence set | Preserve provenance; no new original-daemon inspection claim |
| Final archive | bounded sanitized archive, outer byte count/hash, self-excluding manifest with exact file set, all logs/artifacts/JUnit hashes | Absent from inspected product tree; no archive hash invented |
| Independent decision | Work reads actual final bytes; compare evidence descendant against frozen product; only docs/evidence may differ | Pending; not supplied by this design checkpoint |

### Critical selector groups

The JSON inventory contains the exact complete selector names. These existing
groups are the minimum trace for the package evidence reviewer:

| Boundary | Existing test function(s) in test_candidate_intents.py |
| --- | --- |
| No execution; immutable claim | `test_prepare_preserves_claim_and_does_not_execute`, both `test_actual_*_observation_never_executes` |
| Recovery fence; ordering | `test_prepared_intent_fences_recovery_until_explicit_abandon`, `test_recovery_winning_during_export_prevents_intent`, `test_two_preparers_create_one_intent` |
| Authentication/profile before Git | `test_invalid_owner_version_profile_rejected_before_git`, `test_valid_foreign_owner_cannot_prepare` |
| Freshness and deadline | `test_controlled_post_export_changes_reject_prepare`, `test_invalid_managed_git_prevents_intent`, `test_controlled_clock_rejects_prepare_before_git`, `test_controlled_deadline_crossing_after_capture_prevents_prepare` |
| History and terminality | `test_abandon_is_terminal_and_request_conflicts`, `test_restart_and_db_only_histories_preserve_original_receipts`, `test_explicit_abandon_then_recovery_uses_intent_anchor` |
| Atomicity and corruptions | audit/process-exit tests, intent/abandon corruption tests, `test_controlled_float_revision_in_abandon_receipt_is_not_integer` |

Names existing in source are not evidence that a selected run executed them.
For all four suites, reconcile every expected expanded case against the actual
JUnit, including skips/failures/errors; do not count development RED or the
earlier aggregate/download timeouts as final frozen GREEN.

## Raw intent record verification recipe

1. Read raw queue/claim/intent/abandonment/recovery rows as data only. Reject
   duplicate keys, nonfinite values and oversize input; use the contract's
   canonical UTF-8 rules. Never import a candidate or execute archive content.
2. Recompute SHA256 of the original proof/response JSON bytes; compare canonical
   encodings, not Python dict equality (revision 2.0 must differ from integer 2).
   Bind intent proof to exact job/claim IDs, immutable claim proof hash, full
   profile/content/metadata pins, creation and original claim deadline.
3. Prepared: revision1, empty reason, no abandonment/recovery, claimed job/claim,
   unchanged original claim proof. Abandoned/recovered: revision2,
   owner_abandoned, exactly one matching fingerprint/response and recovery;
   interrupted3 job/claim timestamps include the intent update anchor.
4. Recompute request fingerprint from schema/project/job/intent/original strict
   expected_revision1. Historical prepare/abandon receipts remain historical,
   current_state=false; current views remain separate and DB-only.
5. All four execution/real-client/worker-credential/cleanup flags remain false.
   Verify literal candidate source digest and candidate distinct from base.
   A fixed fake image ID in a non-executing fixture is not an installed image.
6. Verify old 78-ID evidence against its own saved cleanup record, distinguish
   this saved-record comparison from actually accessing the original daemon.

## Resume order

Re-read live PR25 head/comments first. If final evidence is still absent, upload
the already produced sanitized local results when available; do not access the
powered-off computer, declare incomplete tests green, or create a second product
implementation. Once evidence exists, independently verify it and record the
limited intent-ledger decision. Only after that gate may the separate execution
admission proposal in `../CANDIDATE-EXECUTION-ADMISSION-DESIGN.md` be finalized.
No product version/schema bump or execution capability is introduced here.

The whole 42-scenario matrix, real adapters/relay, candidate execution/task gate,
approval consumption/apply and full M9 remain unfinished. Formal Release BLOCKED.
