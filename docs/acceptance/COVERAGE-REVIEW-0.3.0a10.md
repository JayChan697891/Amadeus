# Coverage review0.3.0a10

# M5B3B2A local acceptance report

Product `0fd2041c8efd1c4fa348117e013c0c5b1f30e470`, tree `9a76e8c5280c34d38087f42fc35b702808d15c59`. Version0.3.0a10/schema11.
Bounded owner-only one-shot candidate reservation and explicit terminal ledger
interruption. No worker credential, callback, renewal, execution, task gate,
approval consumption or apply. Formal Release **BLOCKED**.

## Frozen local verification

All18 collector checks passed. Linux source, fresh wheel and isolated sdist
ran 1061 cases each: 1058 passed/3 Windows-only
skips/zero failures or errors. Windows: 1031 passed/30 skipped,
zero failures or errors. Its skips remain26 Linux Docker,3 unavailable Windows
link-privilege fixtures and1 POSIX FIFO; the FIFO case executes on Linux.
Every suite executes 34 new real Git/SQLite reservation cases
and4 populated-v10/fresh/failure/future migration cases. The v10 fixture uses
original historical DDL with copied disposable API records, not an old binary.

Ruff/format/mypy, all artifact/log hashes and all four full JUnit files checked.
All33 Python modules match Git/wheel/sdist bytes. New claim/migration tests are
byte-identical in the sdist; 253-file Windows/Linux source
snapshots match. Installation origin/version checks are saved in collector logs.
Development functional RED/GREEN and supplemental audit are separate from full
suite counts. The first migration selection was already green; no migration
RED claim is made. Setup missing-module errors are not behavioral RED evidence.

Tests cover owner/project/profile/version fences before Git, strict intervals,
nonfinite/overflow/precision-loss clocks, deadline boundary reads without writes,
explicit active/expired/backwards-clock recovery, one reservation forever,
historical receipt replay with unavailable Git storage, task/owner/receipt races,
dirty/missing candidate input, same-version concurrent claimers, cancellation
winning during export, audit-error rollback, process exit before commit and
stored immutable pin/recovery-response corruption. Controlled clock/race/audit/
process-exit hooks are explicit fault injection, not autonomous client evidence.

The root independently audited final code and ran two additional actual-Git
fault cases: change only the valid deadline column, or change proof version to
2.0 and recompute its unkeyed digest. Five public access paths reject both, and
no recovery is persisted. These2 supplemental cases are not added to full suite
counts. Huge integer service-clock rejection was repaired while developing:
finite checks catch OverflowError and avoid a second audit timestamp overflow;
invalid-clock failure writes no unreliable timestamp. No checks were disabled.

## Saved actual records and regression boundaries

Six new observations (two per Linux environment) preserve actual job metadata,
claim proof bytes/digest, historical claim/enqueue/recovery responses, raw recovery
rows and current views. Root recomputed canonical metadata, binding/input/source/
profile fingerprints, literal candidate blob SHA, immutable proof fields/digest,
recovery request fingerprint and response digest. Claimed2 and interrupted3
states remain distinct from original queued1 history. Recovery leaves immutable
proof bytes unchanged and explicitly records ledger interruption only.
execution_verified=false, real_clients_verified=false, worker_credential_issued=false
and cleanup_performed=false. No real candidate execution or automatic relay.

Six prior queue, six prior metadata and six prior object-input records remain
separate regressions. Existing78 Docker observations are42 backend/21 owner
executor/15 reconciliation. Root independently inspected every exact full ID
absent after all suites without issuing removal. Per environment old cleanup
product records2 removed/2 unresolved/1 ineligible; fixture cleanup is distinct.
These old snapshot executions do not prove new candidate execution.

## Integrity, limitations and release gates

Schema11 transactionally rebuilds only candidate jobs/requests to expand allowed
states, preserving original columns/rows/receipts/fingerprints and composite FKs;
new claim/recovery rows are independently validated in both directions. No old
snapshot verifier semantics change. Existing v10 cancelled history stays intact.
Owner authentication precedes Git or replay. Reads/reopen never auto-expire,
requeue, recover or start execution. Expired claims remain recorded claimed
until explicit owner interruption; backwards-clock timing is unknown.

This is owner_reservation_v1 only. Before future execution, recovery requires
an execution-aware guard and dedicated cleanup. It must never clear authority
for a possibly running process. Unkeyed hashes are integrity checks, not
signatures or authorization; trusted service Python/DB/FS and no OS ABA atomicity.
No candidate worker recovery/renewal, verified task completion, approval
consumption/safe apply, real adapter/autonomous relay, full platform/M9 acceptance.

Archive `M5B3B2A-0fd2041-local.tar.gz`: 792898 bytes; SHA256 `7e9022f64c43124b0b6cd7667ed4271feeaa5c6d2db821f3c64fd57083e3671f`.
Self-excluding manifest 154 files. Sanitized logs/JUnit/builds/source/
package identities and independent reproduction scripts retained; no VM keys,
disks/seeds or fixture databases. Index acceptance/evidence/m5b3b2a-local-inspection.json.

Formal42 complete scenarios remain not_run; component coverage remains18 existing/
13 partial/11 missing and evidence38 not_run/4 unverified. Issues11/7 stay open.
Independent Work acceptance is pending and separate; later documentation heads
are not re-executed product commits. F:source/D:debug. GitHub storage only;
no Actions, paid calls, main edits or merge.
