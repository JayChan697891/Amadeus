"""Owner-mediated add.py pilot in a fresh local Linux fixture, never a public API.

Input provenance is an owner-reviewed assertion, not cross-Core authentication.
Only the existing inspected Docker verifier executes candidate source. This tool
does not call a model, apply a candidate, or complete the original producer task.
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
from agentsync.proposals import parse_proposal
from agentsync.verification.candidate import OwnerCandidateExporter
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verification.owner_flow import OwnerCandidateFlow
from agentsync.workspaces.git import GitWorkspaceStore, physical

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


def run(root: Path, source: bytes, origin: dict, image_id: str) -> dict:
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

    def actor(name: str, roles: list[str]) -> dict:
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
        return {
            "project_id": owner["project_id"],
            "session_id": member["session_id"],
            "session_token": member["session_token"],
        }

    left_actor = actor("Owner import worker", ["worker"])
    right_actor = actor("Unchanged baseline worker", ["worker"])
    reviewer = actor("Distinct owner-mediated reviewer", ["reviewer"])

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
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--proposal-sha256", required=True)
    parser.add_argument("--origin", type=Path, required=True)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    root = args.root
    if (
        sys.platform != "linux"
        or not root.is_absolute()
        or root.parent != Path("/root")
        or not root.name.startswith("amadeus-proposal-pilot-")
    ):
        raise SystemExit("Use a fresh dedicated /root/amadeus-proposal-pilot-* local VM directory")
    physical(root.parent)
    os.umask(0o077)
    raw = args.proposal.read_bytes()
    if len(raw) > 32768 or sha(raw) != args.proposal_sha256:
        raise SystemExit("Reviewed proposal pin mismatch")
    files = parse_proposal(raw.decode("utf-8"), ["add.py"])
    source = files[0]["content"].encode("utf-8")
    origin = json.loads(args.origin.read_text(encoding="utf-8"))
    if origin["proposal_file_sha256"] != sha(source):
        raise SystemExit("Owner-reviewed source hash mismatch")
    root.mkdir(mode=0o700, exist_ok=False)
    result = run(root, source, origin, args.image_id)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "execution_assessment",
                    "fixture_task_verification",
                    "baseline_unchanged",
                    "formal_release",
                )
            }
        )
    )
    if (
        result["execution_assessment"] != "passed"
        or result["fixture_task_verification"] != "verified"
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
