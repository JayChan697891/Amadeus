"""Real Core document decisions; confirmation is a deterministic input fixture.

No model, candidate executor or native interactive-terminal acceptance.
"""

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_task_proposals import world as world

from agentsync.errors import AgentSyncError


@pytest.fixture
def document(world):
    core, owner, member, auth, request, _, _ = world
    host = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "examples/review_relay_document.py")
    )
    published = core.execute(
        "publish_task_proposal",
        {
            **request,
            "allowed_paths": ["review.md"],
            "proposal_json": json.dumps(
                {"files": [{"path": "review.md", "content": "Review text.\n"}]}
            ),
        },
    )
    task = core.execute(
        "update_task",
        {
            **auth,
            "task_id": request["task_id"],
            "lease_token": request["lease_token"],
            "expected_version": request["expected_version"],
            "status": "review",
            "result": host["DOCUMENT_MARKER"],
            "request_id": "document-submit",
        },
    )
    args = SimpleNamespace(
        task_id=task["id"],
        context_id=published["context_id"],
        content_sha256=published["content_sha256"],
        decision="accept",
        evidence="Owner inspected the fixed document; no code verification.",
    )
    return core, owner, member, auth, task, args, host, request


def task_state(document):
    core, _, _, auth, task, *_ = document
    return next(
        row for row in core.execute("get_project_state", auth)["tasks"] if row["id"] == task["id"]
    )


@pytest.mark.parametrize("decision,status", [("accept", "completed"), ("reject", "pending")])
def test_independent_document_decision(document, decision, status):
    core, owner, member, auth, task, args, host, _ = document
    args.decision = decision
    previous_agents = {row["id"] for row in core.execute("get_project_state", auth)["agents"]}
    records = []
    result = host["review_document"](
        core, owner, args, confirm=lambda _: records[-1]["plan_sha256"], output=records.append
    )
    assert result["review_submitted"] and result["status"] == status
    assert result["version"] == task["version"] + 1 and result["task_verification"] == "unverified"
    assert result["reviewer_agent_id"] not in previous_agents
    reviewed = task_state(document)
    assert (
        reviewed["latest_review"]["reviewer_agent_id"]
        == result["reviewer_agent_id"]
        != member["agent_id"]
    )
    assert reviewed["latest_review"]["accept"] is (decision == "accept")
    assert records[0]["review_plan"]["document"] == {
        "path": "review.md",
        "content": "Review text.\n",
    }
    assert owner["admin_token"] not in json.dumps(records)
    assert "session_token" not in json.dumps(records)
    with pytest.raises(ValueError, match="document_boundary"):
        host["review_document"](core, owner, args, confirm=lambda _: pytest.fail("No retry"))
    assert task_state(document) == reviewed


@pytest.mark.parametrize("boundary", ["code", "hash", "project"])
def test_document_boundary_refuses_other_inputs(document, tmp_path, boundary):
    core, owner, _, auth, _task, args, host, _request = document
    if boundary == "hash":
        args.content_sha256 = "0" * 64
    elif boundary == "project":
        other = tmp_path / "other-project"
        other.mkdir()
        owner = core.execute("create_project", {"name": "Other", "root_path": str(other)})
    else:
        # A real source publication is still code data even when the task has the document marker.
        context = core.execute("get_context", {**auth, "context_id": args.context_id, "version": 1})
        content = json.loads(context["content"])
        content["files"] = [{"path": "solution.py", "content": "raise RuntimeError('inert')\n"}]
        fake = core.execute(
            "publish_context",
            {
                **auth,
                "kind": "note",
                "title": "Wrong document",
                "content": json.dumps(content),
                "source": "amadeus:task-proposal",
                "request_id": "wrong-document",
            },
        )
        args.context_id = fake["id"]
        args.content_sha256 = host["hashlib"].sha256(fake["content"].encode()).hexdigest()
    before = task_state(document)
    with pytest.raises((ValueError, AgentSyncError)):
        host["review_document"](core, owner, args, confirm=lambda _: pytest.fail("No approval"))
    assert task_state(document) == before


@pytest.mark.parametrize("during", ["mismatch", "task-changed", "new-context-revision"])
def test_confirmation_and_fixed_revision_binding(document, during):
    core, owner, _, auth, task, args, host, _ = document
    records = []

    def confirm(_):
        if during == "mismatch":
            return "wrong"
        if during == "new-context-revision":
            core.execute(
                "publish_context",
                {
                    **auth,
                    "kind": "note",
                    "title": "Later note",
                    "content": "Unrelated revision, not the reviewed document.",
                    "context_id": args.context_id,
                    "expected_version": 1,
                    "request_id": "later",
                },
            )
        else:
            other = core.execute("register_agent", {**owner, "name": "Concurrent reviewer"})
            core.execute_owner(
                "set_agent_roles",
                {
                    **owner,
                    "agent_id": other["agent_id"],
                    "roles": ["reviewer"],
                    "expected_version": 1,
                    "request_id": "other-role",
                },
            )
            core.execute(
                "review_task",
                {
                    "project_id": owner["project_id"],
                    "session_id": other["session_id"],
                    "session_token": other["session_token"],
                    "task_id": task["id"],
                    "expected_version": task["version"],
                    "accept": False,
                    "evidence": "Changed before confirmation",
                    "request_id": "other-review",
                },
            )
        return records[-1]["plan_sha256"]

    if during == "task-changed":
        with pytest.raises(ValueError, match="document_boundary"):
            host["review_document"](core, owner, args, confirm=confirm, output=records.append)
        assert task_state(document)["latest_review"]["evidence"] == "Changed before confirmation"
    else:
        result = host["review_document"](core, owner, args, confirm=confirm, output=records.append)
        assert result["review_submitted"] is (during != "mismatch")
        current = task_state(document)
        assert current["status"] == ("review" if during == "mismatch" else "completed")
        assert current["version"] == task["version"] + (during != "mismatch")
        assert current["task_verification"] == "unverified"
        if during == "mismatch":
            assert current["latest_review"] is None
