# Coverage review 0.3.0a9

# M5B3B1 local acceptance report

Product `f65e134d672d4c4333701b982759cc86567a97a6`, tree `64c402b142ab10246e2dfa76e31cf0167c71acba`.
Version 0.3.0a9 / schema 10. Separate owner candidate queue only: enqueue, get,
list and cancel. No candidate worker, attempt, lease, execution or task gate.

## Frozen verification

All 18 local checks passed. Linux source, fresh wheel and isolated sdist each
ran 1023 cases: 1020 passed / 3 Windows-only skips / zero failures or errors.
Windows ran 1023 cases: 993 passed / 30 skipped / zero failures or errors. Its
skips are 26 Linux Docker cases, 3 unavailable link-privilege cases and one POSIX
FIFO fixture; the FIFO case ran on Linux. The 50 new cases ran in every suite:
40 actual Git/SQLite queue cases, 6 independent corruption/storage-policy cases,
and 4 real SQLite migration cases. The reused migration policy fixture simulates
Docker transport; it proves database preservation, not a new container execution.

Tests cover literal candidate input distinct from baseline, owner/project fences,
historical enqueue replay after cancellation and unavailable managed storage,
current-state projections after restart, strict stored metadata/response parsing,
request collisions, stale versions, injected second-connection mutations,
real concurrent requests on separate SQLite connections, rollback after audit
insertion and an isolated child process exiting before commit. Fault/race hooks
are explicitly injected; none is real autonomous model-client evidence.

Three storage-policy boundary cases independently recompute controlled stored
metadata to test 256/257 files, 4096/4097-byte paths and 65536/65537-byte receipts.
These synthetic stored-policy fixtures do not assert that their changed manifests
were valid Git objects. A separate actual-Git positive fixture establishes literal
candidate content. Oversize/deep/duplicate/nonfinite/unknown JSON cases remain
separate. The 4 MiB total envelope cap is defensive; no fabricated padding object
is claimed to be a valid maximum-size candidate envelope.

Root independently parsed four full JUnit files, checked every artifact/log hash,
compared all 32 Python modules from Git with wheel/sdist bytes, compared the
244-file Windows/Linux source snapshots and checked installation
origins. The sdist includes the exact new queue/security/migration tests from Git.
Development RED/GREEN and independent audit files are clearly labelled and are
not added to the frozen full-suite counts.

## Actual queue records and unchanged regression scope

Two actual queue observations per Linux environment give six records. Each
preserves the actual stored queue row, canonical metadata envelope and actual
request rows/response JSON. Root recomputed metadata, binding, input, provenance,
profile-column bindings, literal source SHA/blob ID, request fingerprints and
response digests. First case is queued with one enqueue request; second retains
its original queued historical receipt after cancel/restart, alongside cancelled
current state and two historical requests. execution_verified=false and
real_clients_verified=false remain explicit; DB reads assert no Git freshness.

Six earlier DB metadata and six earlier object-input observations are separate
regressions. The 78 existing Docker observations remain 42 backend, 21 owner and
15 reconciliation records. All 78 unique full IDs were independently inspected
after the suites and found absent, without issuing removal. Per environment the
cleanup product has 2 removed receipts, 2 unresolved receipts and 1 ineligible
case; fixture cleanup is distinct. Original unverified executions stay unverified.
This stage adds no Docker candidate execution and no autonomous relay evidence.

## Audit repairs and trust

Independent real Git/SQLite audit reproduced that a valid-looking profile SHA
or image column could change alone without rejection. The new metadata envelope
now includes verification_profile kind/SHA/image and every read cross-checks its
columns against that hashed envelope. Independent regression confirms get/list/
cancel/original replay reject all three single-column mutations without cancelling.
A separate corrupted trusted profile with an enormous timeout formerly leaked
OverflowError; it now maps safely to invalid_profile. Original audit passes mean
successful defect reproduction, not security acceptance; fixed-audit evidence
and frozen regressions are stored separately.

A2 export occurs outside the write transaction. Final owner authentication and
complete B0 binding comparison share the queue/request/audit insertion transaction.
Migration 10 only adds candidate tables/indexes and preserves historical records;
old snapshot job/executor tables and meaning remain unchanged. History receipts
are not current state or execution authority. Unkeyed hashes and dataclasses are
not signatures; service Python/database/filesystem integrity is trusted, without
OS-level filesystem ABA atomicity. Stored references cannot restore lost Git
objects or profile definitions. A later executor must freshly validate and fence
its own candidate/content/profile/task authority.

## Evidence and release conclusion

Archive `M5B3B1-f65e134-local.tar.gz`: 740239 bytes,
SHA256 `6c9a3ee933bda5b2cdbdc58769db0a09d9b1156f947e42a179d6ee1fc915a3c2`. Self-excluding manifest: 143 files. Index:
acceptance/evidence/m5b3b1-local-inspection.json. Raw sanitized logs/JUnit/builds,
dependencies/source/package identities, separate observations and reproduction
scripts are preserved. VM credentials/disks/seeds and fixture databases excluded.

Formal 42 complete scenarios remain not_run. Component inventory remains
18 existing / 13 partial / 11 missing; evidence 38 not_run / 4 unverified. Candidate
execution/lease/profile recovery and task/reviewer gates, approval consumption/
safe apply, general recovery, actual adapters/autonomous relay, complete platform
matrix and M9 remain incomplete. Formal Release **BLOCKED**. Issues #11/#7 stay open.
Independent Work acceptance remains separate and pending. Later documentation
heads are not re-executed product commits. Source F:/syuc; debug/cache/temp D:.
GitHub storage only: no Actions, paid calls, main changes or merge.
