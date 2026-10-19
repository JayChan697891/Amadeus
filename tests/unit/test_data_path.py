from agentsync.config import resolve_data_dir


def test_inspect_data_path_does_not_create_directories(tmp_path):
    requested = tmp_path / "not-created" / "state"
    assert resolve_data_dir(requested, create=False) == requested
    assert not requested.parent.exists()
    assert resolve_data_dir(requested) == requested
    assert requested.is_dir()
