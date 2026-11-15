"""Check pilot CLI mode selection without running the Docker verifier."""

import importlib.util
import sys
from pathlib import Path

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
