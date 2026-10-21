# M5B2B owner single-execution guide

Version0.3.0a4/schema8. Import OwnerVerificationExecutor from
agentsync.verification.executor and initialize it with the existing Core. This
is a trusted in-process owner library; no generic Core/HTTP/MCP/CLI dispatch or
agent-controlled finish operation is added. Read M5B2B-CONTRACT.md first.

Create a ledger job bound to a captured repository snapshot and its exact commit
using a directly supplied immutable DockerProfile. Call execute_once with project
admin credentials, job ID, expected version and that matching profile. The executor
atomically claims one attempt and execution overlay, exports only the managed
immutable Git objects, then calls the inspected Docker backend outside SQLite
transactions. It persists generated ownership/name intent before create, complete
ID acknowledgement before start and bound safe results after exact cleanup.

get returns bounded state and evidence hashes. cancel uses owner authentication,
expected version and an idempotent request ID; running cancellation may wait for
the fixed timeout/cleanup. Old ledger mutations reject attached executions; old
get/list/enqueue replay give execution-aware summaries. Ledger-only historical
records retain their non-executing interpretation. Schema7 upgrades preserve all
existing ledger rows and foreign keys; tests upgrade disposable databases only.

phase and assessment differ. A normally concluded attempt is finished, with finite
profile assessment passed/failed/unsupported/error/cancelled. Unknown create, lost
authority, expired lease or unconfirmed cleanup stays cleanup_pending/unverified.
No automatic retry/reconciliation is supplied. Never use ledger owner recovery to
clear an execution. A pending observation may preserve backend status=passed with
observation_only=true; that is evidence for diagnosis, not a passed durable result.
execution_started is a confirmed saved observation. false after a hard crash does
not prove nothing ran; execution_may_have_started preserves the start-intent risk.

Only Linux with the fixed local Docker controls can execute. Other platforms are
unsupported and never execute candidate code on the host. Profiles cannot load
commands, paths, expected values or setup from candidate/model content. This stage
verifies only bounded standalone solution.py cases. No task review/completion,
approval consumption, safe source apply, scheduler or real model relay is added.
Formal M5/release acceptance stays blocked until those separate gates are met.

Run local validation on D:/agentsync-debug, preserve code/deliverables in F:/syuc.
Set AGENTSYNC_REQUIRE_DOCKER_TESTS=1 and the explicit preloaded full image ID for
required Linux tests. AGENTSYNC_VERIFIER_EVIDENCE_DIR stores backend observations;
AGENTSYNC_OWNER_EXECUTOR_EVIDENCE_DIR stores separate real owner-execution records.
Use unique roots per run and independent source/wheel/sdist interpreters. GitHub
only stores uploaded [skip ci] commits; do not run Actions. Never upload VM keys,
seed images or disks.
