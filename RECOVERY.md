# Restore AgentSync after local cleanup

Main contains current v0.1.0a2 source. The versions/v0.1.0a1 and versions/v0.1.0a2 branches
preserve exact source trees. Downloadable artifacts and original checksums are grouped under
releases/v0.1.0a1 and releases/v0.1.0a2. No public GitHub Release object is required to use them.

## Windows

```powershell
git clone https://github.com/JayChan697891/agentsync.git
Set-Location agentsync
py -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev-lock.txt
& .\.venv\Scripts\python.exe -m pip install -e . --no-deps
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe examples\mcp_clients\install_codex.py --dry-run
& .\.venv\Scripts\python.exe examples\mcp_clients\install_codex.py
```

The original local MCP entry points into the folder that the owner requested to delete.
It is removed only after remote verification; reinstall with the helper after restoring.
The shared user-data database outside the project is preserved; no credentials or runtime DBs
are uploaded. Do not upload or overwrite personal Codex configuration backups.

## Original Git history

`archive/AgentSync-development-history.bundle` preserves original commits and version tags.
Restore it with `git clone archive/AgentSync-development-history.bundle AgentSync-original`.
The published version branches may have GitHub-import commit IDs; their trees must match the
original source tree hashes in PUBLICATION-MANIFEST.json. The bundle preserves original commit IDs.

## Historical utility scripts

`archive/development-utilities/` contains original scratch build/audit helpers, not runtime
entrypoints. They assume their original work/ layout and baseline evidence counts. Prefer the
maintained tests/manual probes and normal build commands for current use. The original user
instructions are archived separately; the owner's 2026-10-19 request explicitly authorized this
publication and conditional local cleanup. Future publication remains subject to owner approval.
