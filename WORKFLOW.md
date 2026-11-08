# Amadeus Work + Codex execution workflow

Build/use the debug runtime on D:\agentsync-debug per the current user instruction.
Use the local QEMU Linux VM for actual Docker isolation; preserve source and
sanitized delivery evidence in F:\syuc. See LOCAL-DEBUG.md. Validate the exact frozen
source and package installation environments; do not infer release or real-client
acceptance from the verifier foundation alone.

User override, 2026-10-20: GitHub is storage only; checks, execution, debugging and
benchmarks must use local or other authorized environments. Never dispatch hosted
Actions. Upload commits with [skip ci] and preserve manual-only workflow triggers.
Historical remote CI gates below are historical evidence, not current instructions.

1. Read the uploaded specification, docs/PLAN.md, docs/PROGRESS.md, docs/CONTRACT.md and Git status.
2. Classify complexity before a bounded stage. Sol High handles ordinary work;
   Astra High/Extra High handles major architecture, difficult unresolved failures,
   critical independent review, M5 acceptance and Release Gate decisions. Use
   native same-task delegation only when useful, with a small agent set and compact
   handoffs; then return routine implementation to Sol. Follow AGENTS.md's model
   capability limits; never claim a primary-chat model switch without evidence.
3. Wait for execution, inspect changed files, run relevant tests and checks independently.
4. Repair failures, repeat affected checks, then save an evidence-backed checkpoint.
5. Update progress with commands, results, limitations and exact remaining work.

Ask only for missing essential requirements, external blockers or high-impact authorization.
The user authorized GitHub branch/PR publication and continuous plan execution (M4 now).
Do not modify/merge main or make paid provider calls. Review submission is not acceptance.

6. Check available quota before a new bounded stage. Reserve completion capacity
   for local tests, repair, storage publication and Work review. Near the limit,
   finish the checkpoint without launching another task; report unfinished gates
   truthfully. Exact zero cannot be scheduled reliably.
