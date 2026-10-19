# Source file tree

Portable source inventory. Excludes local environments, scratch data, caches, .git and built packages.

```text
AgentSync/
├── .env.example
├── .gitattributes
├── .github/
│   └── workflows/
│       └── ci.yml
├── .gitignore
├── AGENTS.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── MANIFEST.in
├── README.md
├── README.zh-CN.md
├── SECURITY.md
├── WORKFLOW.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── COMPATIBILITY.md
│   ├── CONTRACT.md
│   ├── DECISIONS.md
│   ├── DELIVERY.zh-CN.md
│   ├── ERRORS.md
│   ├── FILE-TREE.md
│   ├── PLAN.md
│   ├── PROGRESS.md
│   ├── SOURCES.md
│   ├── SPECIFICATION.md
│   ├── TEST-REPORT.md
│   ├── THIRD-PARTY-LICENSES.md
│   ├── THIRD-PARTY-NOTICES.txt
│   ├── claude-host-probe.json
│   ├── codex-host-probe.json
│   ├── dependency-inventory.json
│   ├── pytest-python312.xml
│   └── pytest-results.xml
├── examples/
│   ├── mcp_clients/
│   │   ├── README.md
│   │   ├── claude-desktop.json
│   │   └── codex.toml
│   └── two_mock_agents.py
├── pyproject.toml
├── requirements-dev-lock.txt
├── requirements-lock.txt
├── src/
│   └── agentsync/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── core/
│       │   ├── __init__.py
│       │   └── service.py
│       ├── errors.py
│       ├── integrations/
│       │   ├── __init__.py
│       │   ├── http.py
│       │   └── mcp.py
│       ├── models.py
│       ├── py.typed
│       ├── sdk/
│       │   ├── __init__.py
│       │   └── client.py
│       └── storage/
│           ├── __init__.py
│           └── database.py
└── tests/
    ├── concurrency/
    │   └── test_claims.py
    ├── integration/
    │   ├── test_acceptance.py
    │   ├── test_live_http.py
    │   └── test_transports.py
    ├── manual/
    │   ├── probe_claude_host.py
    │   └── probe_codex_host.py
    ├── security/
    │   ├── test_core_security.py
    │   └── test_http_boundary.py
    └── unit/
        └── test_core.py
```
