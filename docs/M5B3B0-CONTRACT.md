# M5B3B0: transaction-bound candidate metadata capture

Bounded implementation prerequisite for M5B3B1-DESIGN. Version 0.3.0a8,
schema 9. No queue, execution, worker lease, task gate, approval or apply changes.

Extract a private connection-bound capture helper from OwnerCandidateBindings.
It validates the same arguments, authenticates the owner and reads the complete
project-scoped metadata binding on the supplied active SQLite transaction.
It does not BEGIN, COMMIT, ROLLBACK or close the caller's connection, on success
or error. Without an active transaction it fails closed. It never reads Git or
service filesystem storage. Caller-owned writes remain uncommitted and visible
to that helper; the caller retains commit/rollback responsibility.

The connection is a trusted internal service capability, opened against the
correct Core database by the caller. This seam cannot authenticate the origin
of arbitrary caller-created database files and is not a transport or capability
against hostile Python code already executing inside the service.

The public capture API retains validation before opening its own connection,
owner authentication, complete metadata checks, output fingerprints, original
error behavior and read-transaction lifetime. Existing A1/A2 tests must retain
their meaning. No helper adds an authority-bearing signature or filesystem
atomicity claim. No call in this change inserts a candidate verification job.

Required real transaction tests: observe an uncommitted task version, detect
an uncommitted owner change, reject invalid input/no transaction, preserve the
outer transaction on successful and failed capture, and demonstrate caller
rollback/commit visibility from another connection. Preserve original public
capture validation/auth/relation/tampering and actual Git export regressions.
Use temporary projects/SQLite/Git only; no model client or autonomous relay
claim is supported by this prerequisite.

Freeze SHA/tree; locally verify source, fresh wheel, isolated sdist and Windows
source. Save raw sanitized logs/JUnit/builds/source/package identities and label
old Docker regressions separately. Lead inspection and independent Work review
are required; review submission alone is not acceptance. Full Release BLOCKED.
Debug/cache/temp D:/agentsync-debug, source F:/syuc; GitHub storage only, no
Actions, paid provider calls, main changes or merge.
