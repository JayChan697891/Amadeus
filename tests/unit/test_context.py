"""Context revision and literal search regressions for M3."""

import pytest

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


@pytest.fixture
def context_setup(tmp_path):
    core = Core(tmp_path / "db")
    project = core.execute("create_project", {"name": "context", "root_path": str(tmp_path)})
    registered = core.execute("register_agent", {**project, "name": "author"})
    auth = {key: registered[key] for key in ("session_id", "session_token")}
    auth["project_id"] = project["project_id"]
    return core, auth


def publish(core, auth, request_id, **extra):
    return core.execute(
        "publish_context",
        {
            **auth,
            "kind": "note",
            "title": "Context",
            "content": "Body",
            "request_id": request_id,
            **extra,
        },
    )


def test_context_history_idempotency_and_metadata(context_setup):
    core, auth = context_setup
    first = publish(core, auth, "first", summary="source summary", source="file:///never-open")
    assert first["version"] == 1
    assert (
        publish(core, auth, "first", summary="source summary", source="file:///never-open") == first
    )
    second = publish(
        core, auth, "second", context_id=first["id"], expected_version=1, content="Updated"
    )
    assert second["version"] == 2
    assert core.execute("get_context", {**auth, "context_id": first["id"], "version": 1}) == first
    assert core.execute("get_context", {**auth, "context_id": first["id"]}) == second
    assert first["summary"] == "source summary"
    assert first["source"] == "file:///never-open"
    assert first["author_session_id"] == auth["session_id"]
    with pytest.raises(AgentSyncError):
        publish(core, auth, "stale", context_id=first["id"], expected_version=1)
    reopened = Core(core.data_dir)
    assert (
        reopened.execute("get_context", {**auth, "context_id": first["id"], "version": 1}) == first
    )


def test_search_latest_only_fields_and_kind_before_pagination(context_setup):
    core, auth = context_setup
    old = publish(core, auth, "old", content="obsolete-needle")
    publish(core, auth, "replace", context_id=old["id"], expected_version=1, content="new body")
    for index, field in enumerate(("title", "content", "summary", "source")):
        publish(core, auth, f"field-{index}", kind="decision", **{field: "unique-search-text"})
    publish(core, auth, "excluded", kind="constraint", content="unique-search-text")
    assert core.execute("search_context", {**auth, "query": "obsolete-needle"})["entries"] == []
    pages = [
        core.execute(
            "search_context",
            {
                **auth,
                "query": "unique-search-text",
                "kind": "decision",
                "limit": 2,
                "offset": offset,
            },
        )
        for offset in (0, 2, 4)
    ]
    assert [len(page["entries"]) for page in pages] == [2, 2, 0]
    assert [page["has_more"] for page in pages] == [True, False, False]
    assert len({entry["id"] for page in pages for entry in page["entries"]}) == 4


@pytest.mark.parametrize(
    "query",
    ["中文", "中", "中文短语", "alpha beta", 'a"b', "x%_", "OR", "NEAR(foo)", "x-y", "' OR 1=1 --"],
)
def test_search_treats_short_chinese_and_fts_punctuation_literally(context_setup, query):
    core, auth = context_setup
    matching = publish(core, auth, "matching", content=f"prefix {query} suffix")
    publish(core, auth, "decoy", content="Unrelated plain document")
    result = core.execute("search_context", {**auth, "query": query})
    assert [entry["id"] for entry in result["entries"]] == [matching["id"]]


@pytest.mark.parametrize(
    "extra",
    [
        {"query": "   "},
        {"query": "x", "limit": 0},
        {"query": "x", "offset": -1},
        {"query": "x", "kind": "unknown"},
    ],
)
def test_search_rejects_invalid_bounds(context_setup, extra):
    core, auth = context_setup
    with pytest.raises(AgentSyncError):
        core.execute("search_context", {**auth, **extra})


@pytest.mark.parametrize(
    "extra",
    [
        {"title": "   "},
        {"content": "\u0000"},
        {"content": "x" * 65537},
        {"summary": "x" * 4001},
        {"expected_version": 1},
        {"expected_version": 2**100},
        {"expected_version": "0"},
        {"extra_field": "unexpected"},
    ],
)
def test_publish_strict_validation_does_not_insert(context_setup, extra):
    core, auth = context_setup
    with pytest.raises(AgentSyncError):
        publish(core, auth, "invalid", **extra)
    assert core.execute("search_context", {**auth, "query": "Body"})["entries"] == []
