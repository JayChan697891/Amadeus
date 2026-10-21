# M5B2C: one-shot exact acknowledged-container cleanup receipt

This bounded owner-only internal library accepts `project_id`, `admin_token`,
`job_id`, `expected_version`, and `request_id` through
`OwnerExecutionReconciler(core).reconcile_once(...)`; `get(...)` reads its safe
summary. Neither operation is registered in any transport or generic dispatch.

Only expired current attempts with complete create acknowledgement, a full
container ID, generated ownership nonce/name, and pinned image identity qualify.
Authenticate before replay or lookup. In one short transaction record a unique
per-execution intent, invalidate the old worker token, increment job/execution
revisions and quarantine job/attempt/execution. No Docker runs in transactions.
Same request replay only reads; another request cannot retry. Clock rollback,
invalid clocks, wrong version, active leases, terminal jobs and missing identities
fail closed before Docker. Database failure rolls back intent and audit together.

The trusted Linux Docker seam uses a fixed local socket, trusted CLI, empty owned
config and clean environment. Read a valid daemon ID; inspect the stored full ID
and require exact full ID/name/nonce label/image. Remove only that full ID and
require exact successful acknowledgement, then a successful full-ID-filtered all
container list with empty output and an unchanged valid daemon ID. Initial absence
or any uncertainty stays unresolved. No candidate starts, broad deletion, retries,
caller identities/results/commands or host execution are permitted.

A separate schema9 additive receipt stores bounded observations and their hash.
The original backend result is preserved. Even a confirmed removal leaves the job
and execution cleanup_pending/unverified, original cleanup_confirmed false, and
unusable. A crash consumes the single attempt; replay never resumes it. Unknown
or delayed create responses are outside scope, as are cleanup recovery, source
apply, task acceptance, scheduler and formal release acceptance.

Tests exercise public owner reconciliation/get and existing worker interfaces,
with real temporary SQLite. Fault injection at clock/subprocess boundaries is
policy evidence only. Root separately runs disposable real Linux Docker cases,
source/wheel/sdist suites, and independent evidence inspection. D: hosts debug,
temporary files and caches; F: hosts source. GitHub stores evidence only; no Actions.
