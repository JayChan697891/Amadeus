# Current continuation entry (2026-11-11)

The owner authorized continuous implementation, local tests, fixes and retests.
After each checkpoint, take the next authorized item in WORKFLOW.md without
waiting for another prompt. Record unrun validation as NOT RUN. Existing safety
gates and separately authorized real-client boundaries remain in effect.
See docs/PROGRESS.md for the recovery entry point.

Alpha29 exact desktop declaration is frozen at05a811a; see current PROGRESS and
acceptance/evidence/alpha29-local-summary.json. Four selected Windows source/
installed suites each184pass; full suites and real models NOT RUN. The once-authorized subscription task and temporary credential-copy permissions
were consumed at6a8ff41. The authenticated CLI exited0 but protocol_invalid left
an unknown/incomplete result. Temp auth removed, original unchanged; no retry.
080722e preserves sanitized parser diagnostics without changing acceptance.
See current PROGRESS; another live task requires separate explicit authorization.
PR33 Linux supplement at8671c2d has limited Work acceptance; alpha29 awaits review.

Read docs/acceptance/CANCELLATION-REPAIR-20261105.md for current security-repair
status. Earlier alpha26/27/28 component evidence does not cover internal cancellation.
Cancellation repair and Linux supplement have limited Work acceptance at8671c2d;
do not infer current alpha29 or formal acceptance from those historical results.

The user cancelled the Claude handoff/package and requested continued Codex work.
CLAUDE.md and docs/HANDOFF-CLAUDE.md are historical, not continuation instructions.
Read current PLAN/PROGRESS and live PR feedback before selecting the next bounded task.
Historical M5A/M4 statements below do not override current PLAN/PROGRESS or gates.

# Model allocation policy (owner instruction, 2026-10-26)

Default routine development, fixes, tests, documentation and ordinary decisions to
GPT-6.1 Sol with High reasoning when explicitly configurable. Use GPT-6 Astra
High or Extra High for major architecture changes, repeated unresolved failures,
important independent reviews, substantial safety/data-consistency decisions,
M5 final acceptance and Release Gate decisions. Return routine implementation to
Sol after the critical analysis. This supersedes the earlier Astra-only request.

Check actual tools before claiming a model switch. Current native delegation
supports explicit model and reasoning selection with a fresh-context child;
provide a compact handoff with current source, scope, evidence and constraints.
The primary chat has no callable self-model switch. Do not infer its reasoning
level from the model name. If designated delegation is unavailable, keep using
the actual model and identify which critical decision needs manual Astra review.
Reuse a small number of appropriately configured agents; reused agents retain
their existing settings unless a supported mechanism explicitly changes them.
Never substitute external paid APIs or treat a development subagent as evidence
that the Amadeus client adapter works. All existing acceptance gates remain.

# Quota-aware checkpoint policy

Owner instruction: choose bounded tasks and reserve enough quota for independent
local validation, fixes, evidence upload and Work review. As the available budget
nears its limit, finish the current reviewable checkpoint and do not start another
implementation task. Consumption/reset timing is not exactly predictable; never
promise exact exhaustion, burn tokens artificially or mark incomplete work done.
Persist tested code SHA, evidence and next-step status before the boundary.

# Amadeus continuation context

Repository: https://github.com/JayChan697891/Amadeus. Use `amadeus` in new CLI
examples. Keep existing package, Python import, MCP, environment and data names
for compatibility.

Debug-environment location (current user instruction): D:\agentsync-debug. Keep
VM disks, debug venvs, caches and temporary execution evidence there. Project
source/deliverables stay in F:\syuc. Local Linux Docker is now available inside the
dedicated D-drive QEMU/Alpine VM; see docs/LOCAL-DEBUG.md. Never upload VM credentials,
seeds or disks. This does not authorize GitHub-hosted execution.

Current user override (2026-10-20): GitHub is upload/storage only. Do not run,
dispatch, rerun or debug GitHub Actions, checks or benchmarks. Automatic workflow
triggers are disabled in this branch. Perform validation locally or in a separately
available authorized environment; upload with [skip ci] commit messages. No paid
compute/provider calls. An unavailable real sandbox stays unsupported/unverified;
never execute untrusted candidate code on the host as a fallback.

The user explicitly revoked the earlier AGENTS.md instructions and requested continuation
of the product plan. M3 is saved in PR #5 and M4A in PR #8; current development is M5A (Issue #11)
as specified in docs/M5A-CONTRACT.md. M4B head98bd361 passed all9 CI jobs; Work review is separate. The user requested continuous milestone-by-milestone work.
Earlier M0-M2-only/no-public-push statements describe historical batches.

Use the user's current instructions: work under F:\syuc, keep authored project changes
in GitHub branches/PRs, mark PRs `执行方：Codex`, link the task Issue and hand them to Work
for independent acceptance. Do not directly modify or merge main or make paid provider calls.
The project lead inspects actual files and test results. All transports use one Core.
Read the current plan, progress and operation contracts rather than inferring completion.
