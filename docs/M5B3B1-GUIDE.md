# Candidate verification queue: bounded owner library

This checkpoint records and cancels candidate verification requests. It does
not run candidate code or make a task verified. Final frozen validation and
independent Work acceptance are required before this stage is marked accepted.

The trusted owner application constructs CandidateVerificationJobs(core) and
supplies its project admin credential, an existing managed candidate ID, the
expected full candidate SHA and an already validated immutable DockerProfile.
No caller can submit a binding/receipt/path/source/result through this library.
The profile definition remains owner-controlled and is not stored in queue rows.

1. Enqueue with a stable request ID. The service authenticates, exports actual
   existing candidate objects, and stores checked immutable input metadata only
   after a second authenticated comparison inside the insertion transaction.
2. Retain the returned historical_enqueue receipt. Reusing the same request ID
   and inputs returns the original receipt without reading Git. Changing inputs
   under that request ID conflicts. A receipt proves that enqueue occurred; use
   get to learn the current queue state.
3. get/list are owner-authenticated DB-only reads. A current-state projection
   never claims current Git freshness, resolved profile availability or execution.
   Stored digest checks establish metadata consistency, not a new object export.
4. Cancel with a fresh request ID and the current expected version. The first
   cancellation moves queued to cancelled and increments its version atomically.
   Its historical_cancel receipt replays unchanged for the same request; another
   cancellation request cannot silently override a newer state/version.
5. Restarting the service preserves the queue and request receipts, but starts
   no worker. Lost Git objects/receipts are not reconstructed. A later executor
   must re-export and revalidate input/profile/task bindings and establish its
   own durable authority before any candidate execution.

All projections keep execution_connected=false and execution_assessment=unverified.
Historical receipts have current_state=false; get/list items have current_state=true.
An old queued enqueue receipt can still replay after cancellation: that is history,
not the current queue state. No source, profile cases, paths, credentials or creator
sessions are returned. Invalid stored envelopes or receipts fail closed rather
than being silently repaired. Audit records follow existing redaction rules.

Schema 10 adds a separate candidate queue and request ledger. Existing snapshot
jobs and their executor are unchanged and cannot consume these candidate rows.
The library is deliberately absent from public Core/HTTP/MCP/CLI/SDK dispatch.
Same-process Python code and the service database/filesystem remain trusted;
unkeyed hashes and dataclasses do not grant permission or OS-level ABA atomicity.

Use only disposable local projects for fault, concurrency and crash tests. Keep
source/deliverables on F:/syuc and debug/cache/temp on D:/agentsync-debug. Preserve
the exact tested SHA and evidence identities when submitting for Work review.
GitHub is storage only: no Actions, paid calls, main changes or merge. Full
Release remains BLOCKED pending candidate execution/task gates, actual adapters/
autonomous relay, safe apply, full platform coverage and M9 acceptance.
