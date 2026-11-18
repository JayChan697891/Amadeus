# Reviewed interrupted-client continuation experiment

Status: IMPLEMENTED / OFFLINE CHECKS PASSED / LIVE NOT RUN / OWNER AUTHORIZED.
Owner grant recorded in owner-grant-20261116.json; runtime readiness must still be
rechecked before the bounded execution. Prior consumed grants remain historical.
This is the next evidence item for existing P0/M7-02/M8-02, not a new product phase.
The original M0–M9 requirements and formal Release BLOCKED status remain unchanged.

The unchanged a117 runtime is `fc27f15f47fa92ed5edcd764a573c1d84a68c107`;
the package has not been rebuilt.
Preparation is preserved at `/root/amadeus-interrupted-a117-20261115` in the local
D-drive Linux VM. The checked producer plan is
`b8efeeca180296d41322a4dc332b89ce1b3c057998a63a594fc4e3f838423928`.
The original preparation, plan and readiness bytes must not be overwritten.

## Explicit bounds before execution

- A fresh owner grant must allow at most two existing-subscription model calls,
  zero paid credits, auto-recharge off, and no paid API/key. All earlier grants
  are consumed. A grant file is not itself owner permission.
- Only the fixed add(a, b) proposal goal is sent. Both CLI instructions prohibit
  tools, file access/modification and code execution. No candidate is applied or
  executed by this experiment; received source remains review/unverified.
- Explicitly authorize one interruption of the producer's exact owned CLI parent
  after complete turn.started output, while the controlling process survives.
  This is not a host crash, server cancellation or descendant-cleanup experiment.
- Only this experiment may copy the existing Windows login from
  `C:/Users/JayChan/.codex/auth.json` into
  `/root/amadeus-interrupted-a117-20261115/private-home/auth.json` on a private
  root-owned0700 tmpfs; file mode0600. Original credentials remain unchanged.
  No authentication or private raw output is uploaded. The model CLI login
  status must positively identify ChatGPT before each launch.
- Each call retains at most1MiB raw output locally. No additional call after
  failure, unknown outcome or missed interruption window. The receiver may run
  only after the first call has a matching confirmed-failed, ended-parent receipt.
- All stages and cleanup hold the same native exclusive lifecycle lock. Cleanup
  first closes further launches and re-reads current actor receipts, never a stale
  aggregate. Unknown termination blocks removal. Never force/lazy-unmount, kill a
  whole process tree, or alter the original user workspace.

## Execution and inspection order

Use only `/root/amadeus-demo-a117-sdist-r1/installed/bin/python -I -B` with the
reviewed helper file paths. Before any mount/copy, recheck runtime97 members,
fixed CLI bytes, all eight authorization-bound files and current session/plan
readiness. No optimized Python is permitted because these fixed-fixture checks
use assertions.

1. After fresh permission, create a private, exclusive `live-authorization.json`
   matching cleanup.py's exact schema and reviewed hashes; expiry is finite.
   Run `cleanup.py mount`, copy only the authorized login, and check its mode.
2. Run `live.py producer-once PRODUCER_PLAN`. Its exclusive entry and exact
   single-use consent precede launch. It publishes the explicitly host-known
   unfinished add.py checkpoint under the running task lease. The checkpoint is
   not model output. Persist the observation before one owned-parent interruption;
   let the original process capture and Core classify the actual result.
3. Inspect the native exit, final raw-stream digest/state, both attempt receipts
   and confirmed-failure binding. `kill_call_returned` alone is insufficient.
   Any absent/unknown/mismatched evidence ends the experiment without retry.
4. In a new native process run `live.py continuation-preview`. Inspect the
   resulting exact continuation plan: same project, baseline, source goal and
   checkpoint; only the existing dependent task transfers to the single new task.
   Preserve private request bytes locally; publish only sanitized evidence.
5. In another process run `live.py continue-once CONTINUATION_PLAN`. The authority
   callback writes `receiver-request.json` and remains pending while the project
   lead checks the exact dynamic CLI plan. Supply one exclusive decision bound to
   request bytes, plan, stage and expiry. The approval window is at most30seconds;
   approval, the at-most20-second login check and actual execution share the
   adapter's90seconds. The outer230seconds does not extend that adapter deadline.
   A late decision stops this one attempt; do not restart to obtain another plan.
6. Inspect receiver result/capture, source receipt preservation, unique task and
   dependency transfer, original fixture hashes and review/unverified status.
   In a fresh process run `live.py replay`: zero receiver callbacks/model calls,
   unchanged task graph and exact receipt bytes are required.
7. Run `cleanup.py cleanup` after current termination proofs. Delete only that
   exact temporary login, ordinarily unmount tmpfs, confirm the underlying home
   empty, original login unchanged and no owned workers remain. A failed proof
   retains the evidence and permanently closes further fixture launches; resolve
   the exact blocker before making any cleanup claim.

Success is limited to an interrupted CLI parent followed by one controlled
same-vendor continuation and zero-launch replay. The supervisor stays alive,
the checkpoint is supplied by the host, and receiver code is not independently
executed or accepted here. Full B, cross-vendor collaboration, unattended
approval, whole-host recovery, independently verified billing and formal Release
remain outside this result.

Offline evidence:14 cleanup cases (including real flock between inert native
processes) and8 live-driver cases. The replay case uses real run_once request
binding but a synthetic cached status. Temporary auth is a harmless test string;
unmount is substituted. These tests cannot be reported as real-client acceptance.
