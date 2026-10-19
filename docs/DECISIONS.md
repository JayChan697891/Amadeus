# Technical decisions

- D001: Execute M0-M2, not the entire v1.0 plan, matching the user's immediate scope.
- D002: Python >=3.11 and official `mcp==2.3.0` v2. Verify installed APIs, not v1 snippets.
- D003: stdlib SQLite instead of an ORM; small explicit migrations and transactional claims.
- D004: strict schemas, hashed credentials, project/session checks are included now because
  adding authentication after exposing task mutation would produce an unsafe foundation.
- D005: `review` differs from `completed`; require a distinct agent, version and evidence.
  Full test-evidence validation stays M5. Registration under one admin does not prove human independence.
- D006: Distribution `agentsync-local`, import `agentsync`; no claim that a public PyPI name is reserved.
- D007: Exact direct dependency pins plus generated lock files; no unnecessary model libraries.
- D008: No global desktop client configuration changes or restarts just to simulate acceptance.
  Record unavailable real-host tests as pending; official SDK tests are protocol evidence only.
- D009: Native same-task Codex subagents implement separate file sets; lead independently verifies.
- D010: Alpha stores dependencies and lease fields inside tasks rather than creating separate
  empty future-stage entities; reviews are a real schema-v2 history table. Versioned transactional
  migrations live in storage/database.py and reject future schema versions.
- D011: Review found missing review attribution, unbounded SQLite integers, and inconsistent
  loopback host handling. Fixed with schema v2, strict numeric bounds and consistent CLI host choices.
- D012: Verified Codex through its public app-server with ephemeral thread and direct MCP tool calls,
  without starting a model turn. Claude Code was tested with isolated CLAUDE_CONFIG_DIR and only
  MCP registration/health commands. No existing user MCP configuration was edited.
- D013 (a2): Add a safe public CLI installer and intentionally register the real shared entry.
  D012's no-config-edit statement describes a1 only. The native CLI omits an unrelated empty args
  list; verified semantics otherwise match the backup. No credentials or raw config enter artifacts.
- D014 (a2): Close M2-05 connection acceptance using separate evidence: actual registered native
  discovery/calls and direct user-confirmed desktop connected status. Computer Use guidance
  forbids automating ChatGPT desktop UI, so no automated UI evidence is claimed.

## Full repository quality gate

Keep all archived Python scripts within Ruff scope. Add format --check to every
matrix job; retain test XML and builds in Actions artifacts. Preserve historical
version branches and release archives, and submit repair through a PR only.
