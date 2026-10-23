# M5B3B0 local acceptance report

Product `37b17a3d0c27b0a34ca93e03c4944f02a7a63071`, tree `4036fc4a1b19abb57fd6559f34e14e731412c170`.
Version 0.3.0a8, schema 9. This prerequisite extracts a private active-transaction
metadata capture seam; it adds no queue, attempt, lease, execution or task gate.

## Frozen verification

All 18 local checks passed. Linux source, fresh wheel and isolated sdist each
ran 973 cases: 970 passed, 3 Windows-only skips, zero failures/errors. Windows
ran 973 cases: 943 passed, 30 skipped, zero failures/errors. Windows skips are
26 Linux Docker cases, 3 link-privilege cases and 1 POSIX FIFO fixture; the FIFO
regression actually ran on Linux. All 7 new transaction cases passed in all four
complete suites. Development RED/GREEN and a separate independent audit are
labelled development evidence and do not increase those frozen suite counts.

The new tests use actual temporary Git-generated service records and SQLite
transactions: uncommitted task version is visible; caller rollback restores the
original binding; caller commit persists its own writes; uncommitted owner change
is denied without rolling back; invalid input/no transaction fail closed; same
binding/no database writes/no process invocation; auth precedes object lookup.
The independent development audit additionally provoked a real sqlite.Error and
verified the outer transaction, uncommitted writes and connection survived.
Root reran that supplemental case against the frozen source: 1 passed, with
module/driver/JUnit identity saved separately, outside the four full-suite counts.

Root checked every collector artifact/log hash and parsed all four JUnit files,
compared all 31 Git Python modules against wheel/sdist bytes, and compared the
233-file Windows/Linux source snapshots. Installation origin and source binding
are saved. Both full export and snapshot execution regressions retain their scope.
Six existing metadata and six existing candidate-object input observations have
recomputed fingerprints/manifests/source blob IDs. They are regression evidence,
not a new candidate execution or real autonomous client run.

The 78 existing isolated Docker observations (42 backend, 21 owner executor,
15 reconciliation) are separately indexed. Root independently inspected every
exact full ID after the suites: all absent, without issuing removal. Existing
cleanup distinctions remain: each environment 2 product removals, 2 unresolved
receipts and 1 ineligible case; fixture cleanup is separate. An original unverified
execution is not promoted by cleanup. No Docker capability was added in this stage.

## Scope and trust

The helper validates and authenticates on the supplied active connection, then
runs the original complete metadata checks. It never begins, commits, rolls back
or closes the caller connection. Public capture still validates before opening
its own connection, begins its read transaction and rolls back/closes in finally.
The connection must come from trusted service code and the correct Core database;
this is not authentication of arbitrary caller-created database files. Dataclass
and unkeyed provenance digest confer no permission. Git/filesystem checks, task
version gates, profile resolution and queue insertion are not implemented by this
helper; no OS-level filesystem ABA atomicity claim is made.

## Evidence and release conclusion

Archive `M5B3B0-37b17a3-local.tar.gz`: 687872 bytes,
SHA256 `b08af5ea334dd26b32070dec338b301cb4ed0857911e548d894dee527f6686f0`. Self-excluding manifest covers 135 files. Index:
acceptance/evidence/m5b3b0-local-inspection.json. Logs/JUnit/builds, dependencies,
source/package identities, separate regression observations and reproduction
scripts are preserved. No VM credentials, disks, seeds or fixture databases.

42 formal complete scenarios remain not_run. Component inventory remains
18 existing / 13 partial / 11 missing, with 38 not_run / 4 unverified evidence
statuses. Candidate queue/execution/task/reviewer binding, verified completion,
approval consumption/safe apply, general recovery, real adapters/autonomous relay,
full OS/Python matrix and M9 remain incomplete. Formal Release **BLOCKED**;
Issues #11/#7 remain open. Independent Work acceptance is separate and pending.
Later documentation descendants are not re-executed product commits.

Source F:/syuc; debug/cache/temp D:/agentsync-debug. GitHub storage only;
no Actions, paid calls, main changes or merge.

## Independent Work acceptance

Bounded prerequisite accepted in PR22 comment6329149589; reviewed evidence head
37720ee79fbace999130331a1a5d8d5e65b6665a. Saved assessment:
acceptance/evidence/m5b3b0-work-receipt.md. This is code/saved-evidence review,
not a reviewer rerun or daemon inspect. Issues11/7 open; Release BLOCKED.
