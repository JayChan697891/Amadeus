"""Independently accept/reject one existing terminal receiver's review.md.

Uses a newly owner-authorized reviewer and Core.review_task, never a model or
candidate verifier. The fixed publication is context v1; newer unrelated context
revisions do not change what was reviewed. No credentials are saved.
"""

import argparse
import getpass
import hashlib
import json
import re
import sys
import warnings
from pathlib import Path

from agentsync.adapters.approved_launch import digest
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.proposals import parse_proposal

DOCUMENT_MARKER = "Dependent review stored as an unverified document. Independent review pending."


def prompt(label):
    if not sys.stdin.isatty():
        raise ValueError("secure_terminal_required")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(label)


def emit(value):
    print(json.dumps(value, ensure_ascii=True, allow_nan=False), flush=True)


def document_plan(core, auth, args, reviewer_id):
    state = core.execute("get_project_state", auth)
    task = next((row for row in state["tasks"] if row["id"] == args.task_id), None)
    if (
        task is None
        or task["status"] != "review"
        or task["result"] != DOCUMENT_MARKER
        or task["task_verification"] != "unverified"
    ):
        raise ValueError("document_boundary")
    context = core.execute("get_context", {**auth, "context_id": args.context_id, "version": 1})
    content = context["content"]
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    value = json.loads(content)
    owner = next((row for row in state["sessions"] if row["id"] == task["owner_session_id"]), None)
    if (
        len(content.encode("utf-8")) > 65536
        or content_hash != args.content_sha256
        or context["version"] != 1
        or context["source"] != "amadeus:task-proposal"
        or context["kind"] != "note"
        or owner is None
        or context["author_session_id"] != owner["id"]
        or context["author_agent_id"] != owner["agent_id"]
        or reviewer_id == owner["agent_id"]
        or type(value) is not dict
        or set(value)
        != {
            "format",
            "project_id",
            "task_id",
            "task_version",
            "worktree_id",
            "base_head",
            "execution_provenance",
            "files",
        }
        or value["format"] != "amadeus-source-proposal-v1"
        or value["project_id"] != auth["project_id"]
        or value["task_id"] != task["id"]
        or type(value["task_version"]) is not int
        or value["task_version"] + 1 != task["version"]
        or value["execution_provenance"] != "unverified"
    ):
        raise ValueError("document_boundary")
    files = parse_proposal(
        json.dumps({"files": value["files"]}, ensure_ascii=False, separators=(",", ":")),
        ["review.md"],
    )
    return {
        "project_id": auth["project_id"],
        "task_id": task["id"],
        "task_version": task["version"],
        "publication_task_version": value["task_version"],
        "owner_session_id": owner["id"],
        "author_agent_id": owner["agent_id"],
        "context_id": args.context_id,
        "context_version": 1,
        "content_sha256": content_hash,
        "document": files[0],
        "decision": args.decision,
        "evidence": args.evidence,
        "reviewer_agent_id": reviewer_id,
        "reviewer_session_id": auth["session_id"],
        "task_verification": task["task_verification"],
    }


def review_document(core, owner, args, confirm=prompt, output=emit):
    if args.decision not in ("accept", "reject") or not args.evidence.strip():
        raise ValueError("invalid_decision")
    if re.fullmatch(r"[0-9a-f]{64}", args.content_sha256) is None:
        raise ValueError("invalid_content_sha256")
    actor = core.execute("register_agent", {**owner, "name": "Terminal document reviewer"})
    core.execute_owner(
        "set_agent_roles",
        {
            **owner,
            "agent_id": actor["agent_id"],
            "roles": ["reviewer"],
            "expected_version": 1,
            "request_id": "document-reviewer-" + actor["agent_id"],
        },
    )
    auth = {
        "project_id": owner["project_id"],
        "session_id": actor["session_id"],
        "session_token": actor["session_token"],
    }
    secrets = (owner["admin_token"], actor["session_token"])

    def public(value):
        text = json.dumps(value, ensure_ascii=True, allow_nan=False)
        if any(secret in text for secret in secrets):
            raise ValueError("private_value_in_report")
        output(value)

    plan = document_plan(core, auth, args, actor["agent_id"])
    expected = digest(plan)
    public({"review_plan": plan, "plan_sha256": expected})
    if confirm("Approve this document decision by typing its plan SHA-256: ") != expected:
        summary = {"review_submitted": False, "reason": "confirmation_mismatch"}
        public(summary)
        return summary
    fresh = document_plan(core, auth, args, actor["agent_id"])
    if digest(fresh) != expected:
        raise ValueError("document_changed")
    result = core.execute(
        "review_task",
        {
            **auth,
            "task_id": fresh["task_id"],
            "expected_version": fresh["task_version"],
            "accept": fresh["decision"] == "accept",
            "evidence": fresh["evidence"],
            "request_id": "document-review-" + expected,
        },
    )
    summary = {
        "review_submitted": True,
        "plan_sha256": expected,
        "task_id": result["id"],
        "status": result["status"],
        "version": result["version"],
        "task_verification": result["task_verification"],
        "reviewer_agent_id": actor["agent_id"],
    }
    public(summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    for field in ("project-id", "task-id", "context-id", "content-sha256", "evidence"):
        parser.add_argument("--" + field, required=True)
    parser.add_argument("--decision", choices=("accept", "reject"), required=True)
    args = parser.parse_args(argv)
    try:
        if not args.root.is_absolute():
            raise ValueError("absolute_root_required")
        root = args.root.resolve(strict=True)
        database = root / "core/agentsync.db"
        if not database.is_file() or database.resolve(strict=True) != database:
            raise ValueError("existing_project_required")
        token = prompt("Project owner token: ")
        result = review_document(
            Core(root / "core"), {"project_id": args.project_id, "admin_token": token}, args
        )
        return 0 if result["review_submitted"] else 1
    except (Exception, KeyboardInterrupt) as error:
        emit(
            {
                "error_code": error.code
                if isinstance(error, AgentSyncError)
                else "document_review_stopped",
                "outcome": "Inspect task state before another decision; no automatic retry.",
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
