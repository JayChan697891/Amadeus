"""Owner-mediated add.py pilot in a fresh local Linux fixture, never a public API.

Input provenance is an owner-reviewed assertion, not cross-Core authentication.
Only the existing inspected Docker verifier executes candidate source. This tool
does not call a model or apply a candidate. It completes tasks in its own fixture
and leaves any imported proposal's original producer task unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.proposals import parse_proposal
from agentsync.verification.candidate import OwnerCandidateExporter
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.docker import IMAGE_ID, DockerProfile, JsonCase
from agentsync.verification.owner_flow import OwnerCandidateFlow
from agentsync.workspaces.git import GitWorkspaceStore, physical

DEMO_SOURCE = b"def add(a, b):\n    return a + b\n"

# Owner-authored protocol adapter; not part of the model proposal. The exact
# proposal is prepended as bytes and both pieces are independently hashed.
DRIVER = b"""
import json
import sys

for line in sys.stdin:
    pair = json.loads(line)
    print(json.dumps(add(pair[0], pair[1])), flush=True)
"""
CASES = (
    ((0, 0), 0),
    ((2, 3), 5),
    ((-7, 4), -3),
    ((-8, -9), -17),
    ((17, -17), 0),
    ((2**63 - 1, 1), 2**63),
    ((-(2**63), -1), -(2**63) - 1),
    ((10**30, 10**30), 2 * 10**30),
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def fingerprint(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def demo_handoff(
    core: Core, completion: dict, sender: dict, receiver: dict, reviewer: dict, recipient_id: str
) -> dict:
    """Continue one dependent task after verified completion of the fixture."""
    if completion["task_verification"] != "verified":
        raise RuntimeError("The producer must have verified completion")

    def write(who: dict, operation: str, **payload: object) -> dict:
        return core.execute(operation, {**who, **payload, "request_id": f"demo-{operation}"})

    proof = completion["verification"]
    producer_id = completion["task_id"]
    proof_keys = ("task_id", "candidate_sha", "source_sha256", "execution_proof_sha256")
    artifact = {key: proof[key] for key in proof_keys}
    content = json.dumps(artifact, sort_keys=True)
    context = write(
        sender, "publish_context", kind="progress", title="Verified add.py", content=content
    )
    pin = {"context_id": context["context_id"], "version": context["version"]}
    task = write(sender, "create_task", title="Acknowledge add.py", dependencies=[producer_id])
    target = {"task_id": task["id"]}
    claimed = write(sender, "claim_task", **target, expected_version=task["version"])
    lease = {"expected_version": claimed["version"], "lease_token": claimed["lease_token"]}
    package = {"summary": "Continue from the pinned verification evidence", "context_refs": [pin]}
    handoff = write(
        sender, "submit_handoff", **target, **lease, target_agent_id=recipient_id, package=package
    )
    reference = {"handoff_id": handoff["id"]}
    decision = {**reference, "accept": True, "expected_version": handoff["task_version"]}
    accepted = write(receiver, "resolve_handoff", **decision)

    core = Core(core.data_dir)
    reopened = {row["id"]: row for row in core.execute("list_tasks", receiver)["tasks"]}
    reserved = reopened[task["id"]]
    if (
        reopened[producer_id]["verification"] != proof
        or reserved["dependencies"] != [producer_id]
        or reserved["status"] != "pending"
        or reserved["version"] != accepted["task_version"]
        or reserved["assigned_agent_id"] != recipient_id
        or accepted["status"] != "accepted"
        or accepted["sender_agent_id"] == accepted["recipient_agent_id"]
        or accepted["contexts"] != [context]
        or core.execute("get_handoff", receiver | reference) != accepted
        or core.execute("get_context", receiver | pin) != context
    ):
        raise RuntimeError("The verified dependency and pinned handoff did not reopen")

    claimed = write(receiver, "claim_task", **target, expected_version=reserved["version"])
    lease = {"expected_version": claimed["version"], "lease_token": claimed["lease_token"]}
    submitted = write(
        receiver,
        "update_task",
        **target,
        **lease,
        status="review",
        result="Recipient acknowledged the pinned artifact",
    )
    decision = {**target, "expected_version": submitted["version"], "accept": True}
    reviewed = write(reviewer, "review_task", **decision, evidence="Owner-mediated text assertion")
    if (
        reviewed["status"] != "completed"
        or reviewed["task_verification"] != "unverified"
        or reviewed["latest_review"]["reviewer_agent_id"]
        in {accepted["sender_agent_id"], recipient_id}
    ):
        raise RuntimeError("Expected a distinct downstream text reviewer")
    return {
        "status": "completed",
        "producer_artifact": artifact,
        "dependent_task_id": task["id"],
        "handoff_id": handoff["id"],
        "handoff_status": "accepted",
        "context": pin,
        "reopen_kind": "new_core_same_process",
        "actor_kind": "deterministic_core_fixture",
        "downstream_review": "owner_mediated_text/unverified",
    }


def run(root: Path, source: bytes, origin: dict, image_id: str, *, demo: bool = False) -> dict:
    core = Core(root / "core")
    store = GitWorkspaceStore(core.data_dir)
    baseline = root / "baseline"
    baseline.mkdir(mode=0o700)
    (baseline / "fixture.txt").write_bytes(b"Owner-mediated proposal verification fixture\n")
    for args in (
        ("init", "--initial-branch=fixture-main"),
        ("add", "--", "fixture.txt"),
        ("commit", "-m", "Isolated baseline"),
    ):
        store._git(baseline, *args)
    before = fingerprint(baseline)
    owner = core.execute(
        "create_project", {"name": "Owner-reviewed proposal artifact", "root_path": str(baseline)}
    )

    def actor(name: str, roles: list[str]) -> tuple[dict, str]:
        member = core.execute("register_agent", {**owner, "name": name})
        members = core.execute_owner("list_members", {**owner, "limit": 100, "offset": 0})[
            "members"
        ]
        current = next(item for item in members if item["agent_id"] == member["agent_id"])
        core.execute_owner(
            "set_agent_roles",
            {
                **owner,
                "agent_id": member["agent_id"],
                "roles": roles,
                "expected_version": current["version"],
                "request_id": "grant-" + member["agent_id"],
            },
        )
        auth = {
            "project_id": owner["project_id"],
            "session_id": member["session_id"],
            "session_token": member["session_token"],
        }
        return auth, member["agent_id"]

    left_actor, _ = actor("Owner import worker", ["worker"])
    right_actor, recipient_id = actor("Unchanged baseline worker", ["worker"])
    reviewer, _ = actor("Distinct owner-mediated reviewer", ["reviewer"])

    def call(who: dict, operation: str, **payload: object) -> dict:
        return core.execute(operation, {**who, **payload})

    snapshot = call(left_actor, "capture_repository", request_id="snapshot")
    trees = []
    tasks = []
    for index, who in enumerate((left_actor, right_actor)):
        task = call(
            who,
            "create_task",
            title="Imported artifact" if index == 0 else "Baseline",
            request_id=f"task-{index}",
        )
        tasks.append(task)
        trees.append(
            call(
                who,
                "create_worktree",
                snapshot_id=snapshot["snapshot_id"],
                task_id=task["id"],
                request_id=f"tree-{index}",
            )
        )
    left, right = trees
    left_path = Path(left["path"])
    if not left_path.resolve().is_relative_to((core.data_dir / "managed-git/worktrees").resolve()):
        raise RuntimeError("Unexpected managed destination")
    physical(left_path)
    solution = source + b"\n" + DRIVER
    for name, data in (("add.py", source), ("solution.py", solution)):
        with (left_path / name).open("xb") as stream:
            stream.write(data)
    store._git(left_path, "add", "--", "add.py", "solution.py")
    store._git(left_path, "commit", "-m", "Owner-reviewed exact proposal and protocol adapter")
    left_head = store._head(left_path)
    claimed = call(
        left_actor,
        "claim_task",
        task_id=tasks[0]["id"],
        expected_version=tasks[0]["version"],
        lease_seconds=3600,
        request_id="claim",
    )
    running = call(
        left_actor,
        "update_task",
        task_id=claimed["id"],
        expected_version=claimed["version"],
        lease_token=claimed["lease_token"],
        status="running",
        request_id="running",
    )
    submitted = call(
        left_actor,
        "update_task",
        task_id=running["id"],
        expected_version=running["version"],
        lease_token=claimed["lease_token"],
        status="review",
        result="Exact proposal imported by owner; isolated artifact verification required.",
        request_id="review",
    )
    candidate = call(
        left_actor,
        "prepare_merge_candidate",
        left_id=left["worktree_id"],
        right_id=right["worktree_id"],
        expected_left_head=left_head,
        expected_right_head=snapshot["base_sha"],
        request_id="candidate",
    )
    pins = {
        **owner,
        "candidate_id": candidate["candidate_id"],
        "expected_candidate_sha": candidate["candidate_sha"],
    }
    exported = OwnerCandidateExporter(core).export(**pins)
    if exported.snapshot.source != solution:
        raise RuntimeError("Exported candidate differs from reviewed input")
    repo = store.root / "repositories" / snapshot["snapshot_id"]
    _, imported = store._git(repo, "show", candidate["candidate_sha"] + ":add.py")
    if imported != source:
        raise RuntimeError("Original proposal missing from candidate manifest")
    profile = DockerProfile(
        image_id, tuple(JsonCase(list(pair), expected) for pair, expected in CASES)
    )
    job = CandidateVerificationJobs(core).enqueue(**pins, profile=profile, request_id="queue")
    record = {
        "schema": "amadeus.owner-proposal-pilot.v1",
        "started_at": datetime.now(UTC).isoformat(),
        "owner_reviewed_origin": origin,
        "automated_import": False,
        "model_calls": 0,
        "original_producer_task_changed": False,
        "reviewer_kind": "distinct Core identity, host-mediated; not a second model",
        "proposal_sha256": sha(source),
        "driver_sha256": sha(DRIVER),
        "solution_sha256": sha(solution),
        "target_project_id": owner["project_id"],
        "target_task_id": submitted["id"],
        "target_worktree_id": left["worktree_id"],
        "target_head": left_head,
        "candidate_id": candidate["candidate_id"],
        "candidate_sha": candidate["candidate_sha"],
        "candidate_provenance_sha256": exported.provenance_sha256,
        "manifest": exported.snapshot.manifest,
        "profile_sha256": profile.sha256,
        "cases": [{"input": list(pair), "expected": expected} for pair, expected in CASES],
        "image_id": image_id,
        "formal_release": "BLOCKED",
    }
    save(root / "prepared.json", record)
    flow = OwnerCandidateFlow(core)
    observation = flow.start_once(
        **owner,
        job_id=job["id"],
        expected_job_version=job["version"],
        expected_metadata_sha256=job["metadata_sha256"],
        profile=profile,
    )
    save(root / "execution.json", observation)
    record["execution_assessment"] = observation["execution_assessment"]
    if demo:
        record["handoff_demo"] = {"status": "not_run"}
    if observation["execution_assessment"] == "passed":
        execution = observation["execution"]
        completion = flow.complete_once(
            **owner,
            session_id=reviewer["session_id"],
            session_token=reviewer["session_token"],
            task_id=submitted["id"],
            expected_version=submitted["version"],
            job_id=job["id"],
            execution_id=observation["execution_id"],
            expected_execution_revision=execution["revision"],
            request_id="complete",
            profile=profile,
        )
        save(root / "completion.json", completion)
        record["fixture_task_verification"] = completion["task_verification"]
        if demo:
            try:
                record["handoff_demo"] = demo_handoff(
                    core, completion, left_actor, right_actor, reviewer, recipient_id
                )
            except (AgentSyncError, RuntimeError) as error:
                record["handoff_demo"] = {"status": "failed", "error": type(error).__name__}
    else:
        record["fixture_task_verification"] = "unverified"
    record["baseline_unchanged"] = fingerprint(baseline) == before
    if not record["baseline_unchanged"]:
        raise RuntimeError("Isolated source baseline changed")
    record["finished_at"] = datetime.now(UTC).isoformat()
    save(root / "summary.json", record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true", help="Verify a fixed owner-authored add.py")
    mode.add_argument("--proposal", type=Path)
    parser.add_argument("--proposal-sha256")
    parser.add_argument("--origin", type=Path)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    if args.demo and (args.proposal_sha256 is not None or args.origin is not None):
        parser.error("--demo cannot be combined with --proposal-sha256 or --origin")
    if not args.demo and (args.proposal_sha256 is None or args.origin is None):
        parser.error("--proposal requires --proposal-sha256 and --origin")
    root = args.root
    if (
        sys.platform != "linux"
        or not root.is_absolute()
        or root.parent != Path("/root")
        or not root.name.startswith("amadeus-proposal-pilot-")
    ):
        raise SystemExit("Use a fresh dedicated /root/amadeus-proposal-pilot-* local VM directory")
    if not IMAGE_ID.fullmatch(args.image_id):
        parser.error(
            "--image-id must be a full local Docker image ID (sha256: and 64 lowercase hex digits)"
        )
    physical(root.parent)
    os.umask(0o077)
    if args.demo:
        source = DEMO_SOURCE
        origin = {"kind": "owner_authored_demo", "proposal_file_sha256": sha(source)}
    else:
        raw = args.proposal.read_bytes()
        if len(raw) > 32768 or sha(raw) != args.proposal_sha256:
            raise SystemExit("Reviewed proposal pin mismatch")
        files = parse_proposal(raw.decode("utf-8"), ["add.py"])
        source = files[0]["content"].encode("utf-8")
        origin = json.loads(args.origin.read_text(encoding="utf-8"))
        if origin["proposal_file_sha256"] != sha(source):
            raise SystemExit("Owner-reviewed source hash mismatch")
    root.mkdir(mode=0o700, exist_ok=False)
    result = run(root, source, origin, args.image_id, demo=args.demo)
    keys = [
        "execution_assessment",
        "fixture_task_verification",
        "baseline_unchanged",
        "formal_release",
    ]
    if args.demo:
        keys.extend(("owner_reviewed_origin", "model_calls", "handoff_demo"))
    print(json.dumps({key: result[key] for key in keys}))
    if (
        result["execution_assessment"] != "passed"
        or result["fixture_task_verification"] != "verified"
        or (args.demo and result["handoff_demo"]["status"] != "completed")
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
