# M5B3A1 local acceptance report

Tested product: `65e97a3185a68b350aead0d364e69ced73df98f4`; tree `e008b5cfec9a9066f14f7a44c5530a08730eb66a`.
Version0.3.0a6/schema9. Limited scope: owner-only immutable DB metadata capture;
full M5B3A managed-candidate input bridge is not yet implemented.

All18local checks passed. Linux source/fresh wheel/isolated sdist each ran925cases:
922passed/3Windows-only skips/0failures/errors. Windows same frozen source:
896passed/29skipped (26Linux actual Docker cases and3link privilege limits).
New25synthetic SQLite policy cases and2actual Git-generated-record compatibility
cases execute in every environment. The six Linux metadata observations preserve
recomputable fingerprints with filesystem_verified=false/execution_verified=false.
Dirty candidate files deliberately do not change captured DB metadata. This
demonstrates the stage boundary, not acceptance of those changed files.

Root inspected code, recomputed logs/artifact hashes and all JUnit, verified
installation origins and compared7critical Git/wheel/sdist modules. Windows and
Linux source snapshots match exactly. Existing Docker/owner/reconciliation
regressions produced78container observations with all78full IDs independently
absent afterwards; these are existing capability regressions, not new metadata
code execution or client relay evidence. Product cleanup still only removes6of
the15cleanup fixtures; initial-absence and safety fixtures remove the other9.

Archive: `M5B3A1-65e97a3-local.tar.gz`, 636452bytes,
SHA256 `e6b1ba1ecb5962805b1326459f613f3b86854ea9e127783f15fee68ccfc4958d`, self-excluding manifest122files. Index:
acceptance/evidence/m5b3a1-local-inspection.json. Logs,4JUnit,builds,source/package
identity, metadata and existing actual observations are preserved. No private VM
keys, seeds, disks or fixture DBs are uploaded. Debug D:, sources/deliverables F:.

The fingerprint is unkeyed metadata, not a signature, permission or successful
verification. Returned dataclasses are caller-constructible. There is no new
dispatch, schema, Git/object validation, job execution, task gate or apply.
Future bridge code must independently authenticate/recapture, check disk
receipts/intents/physical/config/common-dir/HEAD/parents, export actual candidate
bytes and recheck state. It must not use baseline pass as merged-task evidence.

Formal42scenario executions remain not_run; coverage18existing/13partial/11missing
describes components only. Formal evidence38not_run/4unverified. Real clients,
autonomous relay, task acceptance, approval consumption/safe apply, full platform
matrix and M9 remain incomplete. Formal Release **BLOCKED**. Issues11/7remain
open. No Actions, paid calls or main modification/merge. Work review is separate.
Later documentation/evidence commits do not claim another product test run.
