# M5B3A2 local acceptance report

Tested product `2ed3607de761f731ce8f80385af86260e126a4f4`; tree `59af2cb1af025394c722d46fd3e25f3cdc503f98`.
Version0.3.0a7/schema9. Scope: checked object export of an existing managed
candidate. No jobs, source execution, task gate, approvals/apply or transport changes.

## Frozen results

All18local checks passed. Linux source/fresh wheel/isolated sdist each ran966cases:
963passed/3Windows-only skips/0failures/errors. Windows same225-file source snapshot
ran966cases:936passed/30skipped (26Linux Docker cases,3link privilege limits and
1POSIX FIFO fixture). That FIFO case actually passed on Linux. All41new export/
storage/security cases ran in each Linux environment:36implementation checks plus
5independent adversarial cases. Some cases inject controlled races into actual
temporary Git/SQLite workflows; they are not autonomous model-client evidence.

Root independently inspected implementation, recomputed collector logs/artifacts
and four full-suite JUnit files, verified install origin and compared ALL31Python
modules from Git with wheel and sdist. Source installation binding and Windows/
Linux source snapshots match. Development logs are explicitly separate from
the frozen product certification; only the full frozen suites support these counts.

Two positive object cases per Linux environment preserve6actual input records:
merged two-parent input and legitimate single-parent ancestor input. Root recomputed
metadata fingerprints, input provenance, original input digest from manifest,
expected literal source SHA and solution.py Git blob ID. Candidate commit differs
from baseline; expected candidate bytes and full manifest match. These records
say execution_verified=false and filesystem_atomicity_verified=false.

Six prior DB-only metadata records and78prior Docker/owner/reconciliation regression
observations are stored separately. All78exact container IDs independently absent
after all fixtures; the inspection issues no removal. Existing cleanup product
removal6/fixture removal9 distinctions remain intact. This stage adds no Docker
candidate execution and does not reclassify those regressions as new relay evidence.

## Audit repair and trust limits

Independent audit reproduced that adding .git to a captured bare repository could
redirect the first Git lookup while its trusted config hash stayed unchanged.
The exporter now rejects every such entry before repository Git; implementation
and independent guards both test that no affected Git invocation occurs. Bare
config must also be a physical regular file before the inherited digest read,
with a Linux FIFO regression preventing a blocking-read false result. Missing
storage, strict receipt/intent failures, foreign common-dir/backpointer, dirty or
changed HEAD, invalid parents and owner/task/receipt races fail closed.

Git-object integrity and regular-file/UTF-8/manifest/root solution.py limits are
unchanged. Fingerprints are unkeyed and dataclasses caller-constructible; they do
not grant permission or successful execution. No missing evidence is reconstructed.
Git uses temporary output files but creates no persistent candidate/receipt/intent/
commit in this exporter. Service FS integrity remains trusted; repeated checks
cannot promise atomic resistance to arbitrary OS-level ABA replacement.

## Evidence and release decision

Archive `M5B3A2-2ed3607-local.tar.gz`: 665943bytes,
SHA256 `74b6c41c045d188078243f8fbd12769c7a189a8693f9b2ac03ee2e64983acfba`. Self-excluding manifest covers130files. Index:
acceptance/evidence/m5b3a2-local-inspection.json. Preserve raw sanitized logs,
JUnit/builds/requirements/source/package identities, metadata/input/actual
regression observations and reproduction scripts. No VM private keys, seeds,
disks or fixture DBs are uploaded. Source F:, debug/runtime/cache/temp D:.

Formal42whole scenarios remain not_run, with component inventory18existing/
13partial/11missing and evidence38not_run/4unverified. Existing executor jobs still
verify their original snapshot scope; this new input library is not wired into
candidate-aware jobs or a verified task submission/reviewer gate. Approval
consumption/safe apply, general recovery, actual client adapters/relay, full
OS/Python matrix and M9 remain incomplete. Formal Release **BLOCKED**. Issues11/7
stay open. GitHub storage only; no Actions/paid calls/main changes or merge.
Independent Work review is separate. Later doc/evidence trees are not claimed
to be re-executed product commits.
