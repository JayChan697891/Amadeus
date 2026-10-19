# Official implementation references

Retrieved 2026-10-19; package introspection and actual execution determine verified compatibility.

- Official MCP Python SDK v2: https://py.sdk.modelcontextprotocol.io/
- v2 changes: https://py.sdk.modelcontextprotocol.io/whats-new/
- Client stdio transport: https://py.sdk.modelcontextprotocol.io/client/transports/
- OpenAI Docs, Codex app-server public MCP methods: https://learn.chatgpt.com/docs/app-server
- Codex MCP configuration: https://developers.openai.com/codex/mcp/
- Claude Code environment isolation: https://code.claude.com/docs/en/env-vars

Probe results are in codex-host-probe.json and claude-host-probe.json. Neither result is a
test of manipulating a desktop GUI or an assertion of control over pre-existing conversations.

Reproducible, optional manual probes (Windows npm-installed CLIs expected):

```powershell
& .\.venv\Scripts\python.exe tests\manual\probe_codex_host.py
& .\.venv\Scripts\python.exe tests\manual\probe_claude_host.py
```

These create local test state under work/. Codex starts only an ephemeral connection and direct
MCP calls, never `turn/start`. Claude uses isolated settings, health checks and no model prompt.
