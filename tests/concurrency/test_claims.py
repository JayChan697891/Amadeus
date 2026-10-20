import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from conftest import owner_grant

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


def test_only_one_concurrent_claim_wins(tmp_path):
    core = Core(tmp_path / "state")
    project = core.execute("create_project", {"name": "Concurrent", "root_path": str(tmp_path)})
    actors = []
    for i in range(12):
        session = core.execute("register_agent", {**project, "name": str(i)})
        owner_grant(core, project, session)
        actors.append(
            {
                "project_id": project["project_id"],
                "session_id": session["session_id"],
                "session_token": session["session_token"],
            }
        )
    task = core.execute("create_task", {**actors[0], "title": "One winner", "request_id": "create"})
    barrier = Barrier(len(actors))

    def attempt(actor):
        independent = Core(core.data_dir)
        barrier.wait(timeout=20)
        try:
            return independent.execute(
                "claim_task",
                {**actor, "task_id": task["id"], "expected_version": 1, "request_id": "claim"},
            )
        except AgentSyncError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=len(actors)) as pool:
        results = list(pool.map(attempt, actors))
    winners = [r for r in results if isinstance(r, dict)]
    assert len(winners) == 1
    assert all(isinstance(r, dict) or r == "version_conflict" for r in results)
    persisted = core.execute("list_tasks", actors[0])["tasks"][0]
    assert persisted["version"] == 2
    assert persisted["owner_session_id"] == winners[0]["owner_session_id"]


@pytest.mark.parametrize("iteration", range(5))
def test_concurrent_first_process_migrations(tmp_path, iteration):
    data_dir = tmp_path / "new-database"
    code = "from agentsync.core.service import Core; import sys; Core(sys.argv[1])"
    env = os.environ.copy()
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(data_dir)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(8)
    ]
    results = [(process.communicate(timeout=30), process.returncode) for process in processes]
    assert all(code == 0 for (_, code) in results), results
    core = Core(data_dir)
    assert core.db_path.is_file()
