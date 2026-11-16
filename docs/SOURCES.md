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

Historical invocation records (2026-10-19; not current reproduction commands):

```powershell
& .\.venv\Scripts\python.exe tests\manual\probe_codex_host.py
& .\.venv\Scripts\python.exe tests\manual\probe_claude_host.py
```

Those historical probes used work/. Current a118 probes use a new D-drive fixture,
an installed package, isolated empty client settings and explicit native binaries.
See [the current commands and actual evidence](acceptance/CLIENT-MATRIX.md).
No inference is requested; desktop GUI and model-control acceptance remain separate.
