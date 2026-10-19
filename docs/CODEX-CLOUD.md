# AgentSync Codex Cloud

Execution: Codex. Date: 2026-10-19. Status: **Published**, independently observed
in the environment settings after saving and publishing. [UI evidence](codex-cloud-published.png).
Owner-only environment; one repository:
`JayChan697891/agentsync`. No API keys or personal desktop integrations are needed.

The prepared baseline is `fix/ruff-ci-quality` at
`36f289acca11f4a55f7ba3b35122b0f902fcb705`. Main has not been modified or merged.
The exact tested install script and start instructions are recorded in
[codex-cloud-config.json](codex-cloud-config.json). Actual command results are in
[codex-cloud-verification.json](codex-cloud-verification.json).

Environment ID:
`ccarenv_b64_Y2NhcmVudl9jNmY0MDQ2N2E5ODg4MTkxOGMyNTc4NGY4ODcxNjI5Zg`

Cloud setup used Python 3.12.14 and an isolated `/workspace/agentsync/.venv`.
The lead read the actual completed command output: 92 tests passed in 6.40s,
Ruff lint/format passed, mypy checked 15 source files, and build exited successfully.
The demo completed with duplicate-claim rejection and persistence verification;
the imported module was `/workspace/agentsync/src/agentsync/__init__.py`.
Pip check found no broken requirements, and the tracked working tree was clean.

The initial unsupported `gpt-5.5` setting was restored to the platform's recommended
model selection before successful setup. Package-manager network defaults were
retained; no additional domains, secrets, environment variables or other repositories
were added. Environment access is Only me.

After publication, select Work in > Cloud > agentsync to start future work there.
New cloud tasks have independent workspaces and can run while the desktop is off;
this existing local conversation and its F-drive files are not automatically moved
into a cloud task. Store authored changes on a new GitHub branch/PR and check the
actual Actions results before acceptance. Do not write or merge main directly.
Current implementation remains M0-M2; further milestones need an authorized scope.

Source baseline note: until PR #3 is accepted, main still contains the original
archive lint errors. Start from the tested repair branch rather than main.

Official setup reference: https://learn.chatgpt.com/docs/environments/cloud-environments
