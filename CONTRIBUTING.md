# Contributing

Read AGENTS.md, WORKFLOW.md and docs/CONTRACT.md. Install `.[dev]` in a venv.
Run `python -m pytest`, `python -m ruff check .`, `python -m mypy` and `python -m build`.
Keep shared rules in Core, add regression tests for meaningful bugs, and update the progress log.
Do not commit local data, credentials, environment files or user-specific client configuration.
Public pushes and releases require the project owner's separate approval.
