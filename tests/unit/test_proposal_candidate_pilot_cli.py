"""Check the pilot CLI arguments without running the Docker verifier."""

import importlib.util
import json
import sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location(
    "proposal_candidate_pilot",
    Path(__file__).resolve().parents[2] / "tools" / "run_proposal_candidate_pilot.py",
)
assert SPEC and SPEC.loader
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        (["--demo", "--proposal", "proposal.json"], "not allowed with argument"),
        (["--demo", "--proposal-sha256", "sha"], "--demo cannot be combined"),
        (["--demo", "--origin", "origin.json"], "--demo cannot be combined"),
        (["--proposal", "proposal.json"], "--proposal requires"),
    ],
)
def test_pilot_requires_one_complete_input_mode(monkeypatch, capsys, tmp_path, mode, message):
    root = tmp_path / "new"
    monkeypatch.setattr(sys, "argv", ["pilot", "--root", str(root), "--image-id", "unused", *mode])
    with pytest.raises(SystemExit) as error:
        pilot.main()
    assert error.value.code == 2
    assert message in capsys.readouterr().err
    assert not root.exists()


def test_demo_keeps_the_dedicated_linux_root_gate(monkeypatch, tmp_path):
    root = tmp_path / "outside-dedicated-root"
    monkeypatch.setattr(
        sys, "argv", ["pilot", "--root", str(root), "--image-id", "unused", "--demo"]
    )
    with pytest.raises(SystemExit, match="fresh dedicated /root/amadeus-proposal-pilot-"):
        pilot.main()
    assert not root.exists()


@pytest.fixture
def dedicated_demo_root(monkeypatch):
    class FixturePath(PurePosixPath):
        mkdir = Mock()

    monkeypatch.setattr(pilot, "Path", FixturePath)
    monkeypatch.setattr(pilot, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(pilot, "os", SimpleNamespace(umask=Mock()))
    monkeypatch.setattr(pilot, "physical", Mock())
    monkeypatch.setattr(pilot, "run", Mock())
    return FixturePath("/root/amadeus-proposal-pilot-new")


@pytest.mark.parametrize(
    "image_id", ["python:3.14", "sha256:" + "a" * 12, "sha256:" + "A" * 64, ""]
)
def test_pilot_rejects_invalid_image_id_before_setup(
    monkeypatch, capsys, dedicated_demo_root, image_id
):
    root = dedicated_demo_root
    monkeypatch.setattr(
        sys, "argv", ["pilot", "--demo", "--root", str(root), "--image-id", image_id]
    )

    with pytest.raises(SystemExit) as error:
        pilot.main()

    assert error.value.code == 2
    assert "--image-id must be a full local Docker image ID" in capsys.readouterr().err
    pilot.physical.assert_not_called()
    root.mkdir.assert_not_called()
    pilot.run.assert_not_called()


def test_pilot_passes_valid_image_id_to_existing_demo(monkeypatch, capsys, dedicated_demo_root):
    root = dedicated_demo_root
    image_id = "sha256:" + "a" * 64
    monkeypatch.setattr(
        sys, "argv", ["pilot", "--demo", "--root", str(root), "--image-id", image_id]
    )
    origin = {"kind": "owner_authored_demo", "proposal_file_sha256": pilot.sha(pilot.DEMO_SOURCE)}
    result = {
        "execution_assessment": "passed",
        "fixture_task_verification": "verified",
        "baseline_unchanged": True,
        "formal_release": "BLOCKED",
        "owner_reviewed_origin": origin,
        "model_calls": 0,
        "handoff_demo": {"status": "completed"},
    }
    pilot.run.return_value = result

    pilot.main()

    pilot.physical.assert_called_once_with(root.parent)
    root.mkdir.assert_called_once_with(mode=0o700, exist_ok=False)
    pilot.run.assert_called_once_with(root, pilot.DEMO_SOURCE, origin, image_id, demo=True)
    assert json.loads(capsys.readouterr().out) == result
