# Local MCP configuration templates

These are templates, not installed or activated configurations. Replace
`<ABSOLUTE_PYTHON_EXECUTABLE>` with the Python executable in the environment where
AgentSync is installed. Replace `<ABSOLUTE_SHARED_DATA_DIRECTORY>` with one dedicated
absolute directory, identical in all clients. The server creates `agentsync.db` there.
Do not use a demo directory or a network share for real shared state.

On Windows, forward slashes are accepted in Python paths, for example
`C:/AgentSync/.venv/Scripts/python.exe` and `C:/AgentSync/shared-data`.
On Linux/macOS use native absolute paths, for example `/opt/agentsync/.venv/bin/python`
and `/home/yourname/.local/share/agentsync-shared`. These paths are examples only.
No package downloads or model calls occur in these launch commands.

- `codex.toml`: a Codex `mcp_servers` entry. Review and merge into the appropriate
  configuration using the host's supported settings workflow.
- `claude-desktop.json`: a Claude Desktop `mcpServers` entry. Merge into the host's
  existing JSON configuration; preserve its other settings.

Keep project administrator/session/lease tokens out of these files. Register separate
agent sessions after connection. Stdio child processes coordinate through the same
database; each transport uses the same Core.

Template syntax and local protocol tests do not establish compatibility with a
particular desktop host/version. Actual host acceptance is tracked in
`../../docs/COMPATIBILITY.md`.

Configuration references:
- [Official OpenAI MCP configuration](https://developers.openai.com/codex/mcp/)
- [Official MCP desktop connection guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers)
