"""Pure plan plus known Python helper; never executes the synthetic Codex binary."""

import hashlib
import json
import os
import sys

import pytest

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.codex_invocation import CodexHostProfile, prepare_invocation
from agentsync.adapters.process_capture import CapturedProcess


@pytest.mark.asyncio
async def test_invocation_data_drives_only_known_python_helper_without_client_execution(
    tmp_path, monkeypatch
):
    fake_binary = tmp_path / "synthetic-fake.exe"
    original_bytes = b"Synthetic profile hash fixture, never executable Codex.\n"
    fake_binary.write_bytes(original_bytes)
    expected_sha = hashlib.sha256(original_bytes).hexdigest()
    original_mtime = fake_binary.stat().st_mtime_ns
    monkeypatch.setenv("AGENTSYNC_COMPOSITION_PARENT", "unchanged-parent-dummy")
    request = AdapterTask("p", "s", "t", "r", "Known literal input 中文; not a command", 2)
    profile = CodexHostProfile("p", "s", fake_binary, tmp_path, expected_sha)
    environment = {
        "HOME": "fixture-home",
        "OPENAI_API_KEY": "dummy-api-key-not-a-credential",
        "UNRELATED_TOKEN": "dummy-token-not-a-credential",
    }
    if sys.platform == "win32" and "SystemRoot" in os.environ:
        environment["SystemRoot"] = os.environ["SystemRoot"]
    supplied = dict(environment)
    plan = prepare_invocation(profile, request, environment=environment)
    assert plan.argv[0] == str(fake_binary)
    assert plan.stdin_text == request.instruction
    assert os.environ["AGENTSYNC_COMPOSITION_PARENT"] == "unchanged-parent-dummy"
    # The argv in the plan is never passed to the process layer. Only this known
    # Python helper consumes the plan's data and explicit selected environment.
    helper_argv = (
        sys.executable,
        "-I",
        "-u",
        "-c",
        "import os,json,sys; print(json.dumps({'input':sys.stdin.buffer.read().decode('utf-8'),"
        "'home':os.getenv('HOME'),'api_present':'OPENAI_API_KEY' in os.environ,"
        "'token_present':'UNRELATED_TOKEN' in os.environ,"
        "'parent_present':'AGENTSYNC_COMPOSITION_PARENT' in os.environ}))",
    )
    assert helper_argv[0] != plan.argv[0]
    process = await CapturedProcess.start(
        helper_argv,
        cwd=plan.cwd,
        stdin_text=plan.stdin_text,
        timeout_seconds=plan.timeout_seconds,
        output_limit=plan.output_limit,
        env=plan.child_env(),
    )
    snapshot = await process.wait()
    result = await process.get_result()
    assert snapshot.state == "exited" and snapshot.exit_code == 0
    assert json.loads(result.stdout) == {
        "input": request.instruction,
        "home": "fixture-home",
        "api_present": False,
        "token_present": False,
        "parent_present": False,
    }
    assert result.stderr == b""
    assert environment == supplied
    assert os.environ["AGENTSYNC_COMPOSITION_PARENT"] == "unchanged-parent-dummy"
    assert fake_binary.read_bytes() == original_bytes
    assert hashlib.sha256(fake_binary.read_bytes()).hexdigest() == expected_sha
    assert fake_binary.stat().st_mtime_ns == original_mtime
    assert plan.executes is plan.version_verified is plan.auth_verified is False
    assert plan.billing_verified is plan.real_client_verified is False
    assert plan.verification == plan.core_authorization == "unverified"
    assert snapshot.real_client_verified is False and snapshot.tree_cleanup == "unverified"
