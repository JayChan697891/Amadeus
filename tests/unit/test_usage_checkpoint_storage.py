import os
from pathlib import Path

import pytest

from agentsync.errors import AgentSyncError
from agentsync.usage import UsageLedger
from agentsync.usage_storage import load_usage_checkpoint, save_usage_checkpoint


def test_failed_checkpoint_replacement_preserves_the_last_complete_file(tmp_path, monkeypatch):
    checkpoint = tmp_path.resolve() / "usage.json"
    save_usage_checkpoint(checkpoint, UsageLedger("first-project"))
    before = checkpoint.read_bytes()

    def unavailable(_source, _target):
        raise OSError("fixture replacement failure")

    monkeypatch.setattr(Path, "replace", unavailable)
    with pytest.raises(AgentSyncError) as interrupted:
        save_usage_checkpoint(checkpoint, UsageLedger("another-project"))
    assert interrupted.value.code == "checkpoint_unavailable"
    assert checkpoint.read_bytes() == before
    assert load_usage_checkpoint(checkpoint, "first-project").summary().total_records == 0
    assert list(checkpoint.parent.glob(".agentsync-*")) == []


def test_checkpoint_rejects_a_hard_link_without_touching_the_target(tmp_path):
    root = tmp_path.resolve()
    ledger = UsageLedger("project")
    original = root / "original.json"
    alias = root / "alias.json"
    save_usage_checkpoint(original, ledger)
    before = original.read_bytes()
    try:
        os.link(original, alias)
    except (NotImplementedError, OSError):
        pytest.skip("Fixture filesystem does not support hard links")

    with pytest.raises(AgentSyncError) as denied_read:
        load_usage_checkpoint(alias, "project")
    assert denied_read.value.code == "checkpoint_unavailable"
    with pytest.raises(AgentSyncError) as denied_write:
        save_usage_checkpoint(alias, ledger)
    assert denied_write.value.code == "checkpoint_unavailable"
    assert original.read_bytes() == before
    assert alias.samefile(original)
