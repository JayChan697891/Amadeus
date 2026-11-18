# Real model checkpoint recovery — one bounded document experiment

Status at preparation: NOT RUN. This is the existing P0 recovery verification,
not a new M phase. The public a122/r5 preview and formal Release BLOCKED remain.

## Frozen inputs and authority

- Runtime: `7e160bbc7c282cd55f3dbbb44377d8456f8a8c66`; existing wheel
  `0113065f0eef9b039a6b9cb78d111f0621a78683e17994d2154e7f08c352266c`.
- Existing terminal examples: `6cd580752d3a4feaf0052c130235190f04168df8`.
- Actual ready: `df59b0b464adaa8776404859a35dff222793c7dec04f57148d40d779be5b6181`.
- Producer plan: `cd60e58deaf267a243da9350a3751e64ff100bd6236ccf8dc0a4270c036b0240`.
- Project: `30fc789f-c636-44dd-8e3b-63e9b7dd2735`; source task
  `e5fafea3-9913-4ad9-994b-141be100d2b9`. Exact argv/prompt/env in
  [document-plan.json](document-plan.json); exact source hashes in the manifest.
- The [derived grant](host/owner-grant.json) records the owner's existing
  standing permission. It is not a new owner reply or an independent billing audit.
  Maximum two existing-subscription calls, no paid API/additional fees, no retry,
  no candidate execution. Expiry remains mandatory.

## Execution and stop conditions

1. Recheck the exact helper/plan hashes, prepared task and physical directories.
   Create the host private directory with current-user/SYSTEM access only.
   Copy the existing ChatGPT login only into the dedicated guest RAM home
   `/root/amadeus-document-continuation-a123-20261118/private-home/auth.json`.
   Keep the original unchanged. A failed cost/login/isolation check stops launch.
2. Start the producer once: inert `review.md`, explaining 2+3 and independent
   checking. No tools, execution, file changes or artificial output delays.
   Runtime budget remains90 seconds. The two-message protocol is unchanged.
3. Observe an actual protocol checkpoint, its durable receipt and matching Core
   publication. Require the same reviewed capture/owned parent still running,
   with no final message or terminal event. Save the boundary, recheck it and
   interrupt only that one parent. Original capture must confirm ended failure.
   Unknown, natural completion, timeout, cancellation, missed window or mismatch
   stops the experiment: no second model and no retry.
4. Only a successful existing `pin_failed_progress` may create the receiver
   command. Root inspects that actual command/hash and the producer result.
   The existing continuation entry runs in a real PTY: privately supply the owner
   token, then separately approve PREPARE, exact continuation SHA, subscription/
   isolation confirmation and exact launch SHA. No approval is inferred from
   model text or the presence of a checkpoint. At most one receiver call.
5. Inspect the actual receiver result, fixed context and original receipts.
   Success is same-vendor model-authored progress continued into a new
   `review/unverified` task, with the source failed. It is not verified code,
   whole-host crash recovery, cross-vendor collaboration or unattended autonomy.
6. Wait for authoritative producer/receiver host and Core terminal evidence.
   Remove the temporary login and unmount its RAM home only after those checks.
   Preserve failures/unknown results; raw output is bounded and local-only.

## Evidence and limitations

Root/Astra inspected23 passing offline checks:14 observer cases,8 cleanup
judgment cases and one real Core/local Python checkpoint/interruption/pin case.
That proves preparation scope only. Actual readiness creation used zero model
calls and zero account copies. The archived original149/150-byte experiment
remains NOT_VERIFIED; this document recovery experiment neither retries nor
changes its byte-consistency requirement. Store actual receipts, selected
non-sensitive results and cleanup outcome separately after execution; never
upload owner/session tokens, model login files, databases or raw model streams.
