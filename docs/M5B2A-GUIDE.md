# M5B2A internal durable ledger

Version0.3.0a3, schema7. This is a trusted in-process owner library, not a new
MCP/HTTP/CLI/SDK dispatch operation. It does not run candidates. All public states
explicitly say execution_connected=false and execution_assessment=unverified.

Import VerificationJobs from agentsync.verification.jobs and initialize it with
an existing Core. Owner enqueue/get/list/cancel/recover_interrupted require the
project's admin credentials. Enqueue accepts only an existing project-scoped
repository snapshot ID, its exact captured commit, a directly supplied validated
DockerProfile and an idempotent request ID. It stores the profile hash, never
profile expected values, commands, paths or source. No agent-submitted receipt or
profile file is accepted. After restart a hash alone cannot execute anything.

Trusted internal claim returns an opaque attempt token once; only its hash is
stored. renew/acknowledge_cancel/interrupt require project/job/current attempt,
number, token, expected version and an unexpired lease. Renewal returns its new
expiry without re-exposing the token. Owner cancellation of a running ledger
enters cancel_requested; holder acknowledgement is a separate transition. Expiry
and observed wall-clock rollback fail closed and need explicit owner interruption;
there is no automatic retry. Terminal attempts cannot be revived.

Reopening a database transactionally migrates schema6 to7 and preserves old data.
Back up owner data before a deliberate upgrade; older binaries reject newer schema.
The tests upgrade disposable databases only. Successful mutations, fixed metadata
audit and idempotency records commit together. No Git/Docker/network work occurs
inside a ledger transaction. A lease does not hold an SQLite transaction open.

Ledger tests use synthetic snapshot metadata and attempts, with separately labelled
actual thread/process races. They are not actual container execution or autonomous
agent evidence. Future supervised workers need immutable Git export, trusted
profile resolution, create intent, exact-owned-container cleanup, crash/late-create
reconciliation and conditional result binding before any verified outcome exists.
Approval consumption/application and task acceptance remain further contracts.

Debug environment: D:/agentsync-debug; source: F:/syuc/agentsync-jobs. GitHub is
upload/storage only. Do not run Actions or paid provider calls. See LOCAL-DEBUG.md
and M5B2A-CONTRACT.md for the complete boundary and acceptance matrix.
