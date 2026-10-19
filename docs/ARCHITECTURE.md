# Architecture

`MCP tools / HTTP routes / Python SDK -> Core.execute -> strict operation schemas -> SQLite`.
Business rules live in Core, not in adapters. The CLI only hosts transports and runs the demo.
There is no GUI, model provider, desktop injection or background scheduler in Alpha.

Identifiers are opaque random strings. Project admin credentials enroll independent sessions;
session credentials authenticate all project operations. Credentials are hashed at rest.
HTTP additionally requires a process bearer token and defaults to loopback only.
Stdio inherits the local host's process trust boundary. Same-user filesystem access is trusted;
this is not a sandbox against malicious local processes.

SQLite uses WAL, foreign keys, busy timeout, explicit schema versions and serialized writes.
Each Core instance opens the same absolute database path; caller working directories cannot
silently split state. Transactions protect task versions, dependencies, leases and idempotency.
Migration files and actual implemented table names are described in the source and contract;
future M3-M9 entities are not pre-created as empty functionality.

State flow: pending -> claimed -> running -> review -> completed. The claim owner submits
the result for review; a different registered agent accepts or rejects it with evidence.
Failure, blocking, cancellation and expired-lease recovery have explicit guards. A lease
token alone is insufficient: session identity, project, expiry and expected task version
must all match. Recovery invalidates the prior lease and advances the version.

Review evidence remains untrusted text. Alpha stores the review and its author; it does not
execute supplied commands, infer test success, or verify file contents. M5 adds independent
evidence verification. Documentation and test reports distinguish this product limit from
the project lead's actual checks of AgentSync's own code and test runs.
