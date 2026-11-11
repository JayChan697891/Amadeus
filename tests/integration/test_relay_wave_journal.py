from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from agentsync.adapters.approved_launch import digest
from agentsync.errors import AgentSyncError
from agentsync.relay_wave_journal import RelayWaveJournal


def test_concurrent_journal_connections_keep_one_project_fence(tmp_path):
    root = tmp_path.resolve()
    journal = RelayWaveJournal(root)
    journal.location_identity(initialize=True)
    project = digest("fixture-project")
    start = Barrier(2, timeout=10)

    def admit(request):
        independent = RelayWaveJournal(root)
        start.wait()
        try:
            independent.admit(project, request, ("fixture-task",))
        except AgentSyncError as error:
            return request, error.code
        return request, "admitted"

    requests = [digest("first"), digest("second")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = dict(pool.map(admit, requests))
    assert set(outcomes.values()) == {"admitted", "wave_incomplete"}
    winner = next(request for request, state in outcomes.items() if state == "admitted")
    assert journal.pending(project) == (winner, "admitted", ["fixture-task"], None)

    with pytest.raises(AgentSyncError) as mismatch:
        journal.record(
            project,
            winner,
            incomplete=False,
            results=[{"task_id": "fixture-task", "state": "incomplete"}],
        )
    assert mismatch.value.code == "wave_receipt_mismatch"
    assert journal.pending(project) == (winner, "admitted", ["fixture-task"], None)
