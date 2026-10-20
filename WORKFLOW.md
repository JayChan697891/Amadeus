# Work + Codex execution workflow

User override, 2026-10-20: GitHub is storage only; checks, execution, debugging and
benchmarks must use local or other authorized environments. Never dispatch hosted
Actions. Upload commits with [skip ci] and preserve manual-only workflow triggers.
Historical remote CI gates below are historical evidence, not current instructions.

1. Read the uploaded specification, docs/PLAN.md, docs/PROGRESS.md, docs/CONTRACT.md and Git status.
2. Plan a bounded stage and delegate implementation using native same-task agents.
3. Wait for execution, inspect changed files, run relevant tests and checks independently.
4. Repair failures, repeat affected checks, then save an evidence-backed checkpoint.
5. Update progress with commands, results, limitations and exact remaining work.

Ask only for missing essential requirements, external blockers or high-impact authorization.
The user authorized GitHub branch/PR publication and continuous plan execution (M4 now).
Do not modify/merge main or make paid provider calls. Review submission is not acceptance.
