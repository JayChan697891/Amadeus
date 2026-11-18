"""Real Core and owned Python protocol fixtures; no models or candidate execution."""

import json
import runpy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_codex_proposal_capture import pilot as pilot
from test_codex_proposal_relay_queue import cancel_fixture_load
from test_codex_proposal_relay_queue import proposal_wave as proposal_wave
from test_task_proposals import counts
from test_task_proposals import world as world
from test_unfinished_continuation import unfinished as unfinished

from agentsync.adapters import codex_invocation
from agentsync.adapters.approved_launch import digest
from agentsync.errors import AgentSyncError
from agentsync.relay_queue import RelayQueue


@pytest.mark.parametrize("unfinished", ["checkpoint_codex"], indirect=True)
@pytest.mark.parametrize("deny", [None, "receiver", "continuation", "launch", "fee", "secret"])
async def test_terminal_continues_saved_live_checkpoint(unfinished, pilot, monkeypatch, deny):
    flow, request, _, child, calls, approvals, _, key = unfinished
    core, owner, _, auth, source_task, _, source, receipts, profile = pilot
    host = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "examples/continue_codex_task.py")
    )
    private_home = source.parent / "private-home"
    private_home.mkdir()
    instruction = source.parent / "continue.txt"
    instruction.write_text("Finish the pinned unfinished total implementation.", encoding="utf-8")
    if deny == "secret":
        instruction.write_text(owner["admin_token"], encoding="utf-8")
    args = SimpleNamespace(
        root=source.parent,
        project_id=owner["project_id"],
        task_id=source_task["id"],
        receipts=receipts,
        instruction=instruction,
        codex=profile.executable,
        codex_sha256=profile.expected_binary_sha256,
        codex_version="0.167.0-alpha.3.2",
        codex_home=private_home,
    )
    records, prompts = [], []
    new_tokens = []
    execute = type(core).execute

    def observe_registration(self, operation, payload):
        response = execute(self, operation, payload)
        if operation == "register_agent":
            new_tokens.append(response["session_token"])
        return response

    async def answer(label):
        prompts.append(label)
        if label.startswith("Prepare"):
            return "wrong" if deny == "receiver" else "PREPARE"
        if label.startswith("Approve continuation"):
            return "wrong" if deny == "continuation" else records[-1]["plan_sha256"]
        if label.startswith("Confirm subscription"):
            return "wrong" if deny == "fee" else "CONFIRM"
        assert label.startswith("Approve this launch")
        return "wrong" if deny == "launch" else records[-1]["plan_sha256"]

    monkeypatch.setattr(codex_invocation, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(type(core), "execute", observe_registration)
    monkeypatch.setitem(host["run"].__globals__, "prompt_async", answer)
    monkeypatch.setitem(host["run"].__globals__, "emit", records.append)
    monkeypatch.setitem(host["approve_launch"].__globals__, "prompt_async", answer)
    source_receipts = {p.name: p.read_bytes() for p in receipts.glob("relay-" + key + "*.json")}
    before_members = core.execute_owner("list_members", {**owner, "limit": 100})["members"]
    if deny == "secret":
        with pytest.raises(ValueError, match="^private_value_in_report$"):
            await host["run"](args, owner["admin_token"])
        assert len(calls) == len(approvals) == 1
        assert owner["admin_token"] not in json.dumps(records)
    elif deny in ("launch", "fee"):
        assert await host["run"](args, owner["admin_token"]) == 1
        assert len(calls) == len(approvals) == 1
        assert not any(
            p.name.endswith("launch-approved.json") for p in args.root.glob("continue-*/*.json")
        )
    else:
        result = await host["run"](args, owner["admin_token"])
        assert result == int(deny is not None)
        assert len(calls) == (2 if deny is None else 1)
        assert len(approvals) == 1  # Receiver consent uses the terminal helper.
    if deny == "receiver":
        assert (
            core.execute_owner("list_members", {**owner, "limit": 100})["members"] == before_members
        )
        return
    output = args.root / ("continue-" + digest([args.project_id, args.task_id]))
    assert (output / "entry.json").is_file()
    public = "".join(path.read_text() for path in output.glob("*.json"))
    assert owner["admin_token"] not in public
    assert len(new_tokens) == 1 and all(token not in public for token in new_tokens)
    # A second invocation is status only, including after an approval denial.
    before_replay = len(calls), len(prompts), len(approvals)
    await host["run"](args, owner["admin_token"])
    assert (len(calls), len(prompts), len(approvals)) == before_replay
    assert {name: (receipts / name).read_bytes() for name in source_receipts} == source_receipts
    if deny is None:
        state = {row["id"]: row for row in core.execute("list_tasks", auth)["tasks"]}
        result = json.loads((output / "result.json").read_text())
        receiver_id = result["continuation"]["task_id"]
        assert state[source_task["id"]]["status"] == "failed"
        assert state[receiver_id]["status"] == "review"
        assert state[receiver_id]["task_verification"] == "unverified"
        assert state[child["id"]]["dependencies"] == [receiver_id]
        assert state[child["id"]]["version"] == child["version"] + 1
        assert result["continuation"]["publication"]["content_sha256"]
        assert any("UNFINISHED_CONTEXT_SENTINEL" in json.dumps(r) for r in records)
        assert counts(core)["merge_candidates"] == counts(core)["candidate_verification_jobs"] == 0


@pytest.mark.parametrize("source_state", ["pending", "normal-review", "no-checkpoint"])
async def test_terminal_rejects_ineligible_source_before_receiver(
    pilot, world, proposal_wave, monkeypatch, source_state
):
    core, owner, _, auth, task, _, source, receipts, _ = pilot
    relay, item, _, approvals, captures, _ = proposal_wave
    cancel_fixture_load(world)
    if source_state != "pending":
        item = replace(
            item,
            task=replace(
                item.task,
                instruction="Checkpoint fixture "
                + ("succeeded" if source_state == "normal-review" else "failed"),
                checkpoint_completed_proposal=source_state == "normal-review",
            ),
        )
        await RelayQueue(relay).run_ready_once(
            (item,), request_id="entry-refusal", admin_token=owner["admin_token"]
        )
    host = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "examples/continue_codex_task.py")
    )
    args = SimpleNamespace(
        root=source.parent, project_id=owner["project_id"], task_id=task["id"], receipts=receipts
    )

    async def no_prompt(_):
        pytest.fail("An ineligible source must not reach receiver preparation")

    monkeypatch.setitem(host["run"].__globals__, "prompt_async", no_prompt)
    before_tasks = core.execute("list_tasks", auth)
    before_members = core.execute_owner("list_members", {**owner, "limit": 100})
    before = len(captures), len(approvals)
    with pytest.raises(AgentSyncError if source_state == "normal-review" else ValueError):
        await host["run"](args, owner["admin_token"])
    assert core.execute("list_tasks", auth) == before_tasks
    assert core.execute_owner("list_members", {**owner, "limit": 100}) == before_members
    assert (len(captures), len(approvals)) == before
    assert not list(source.parent.glob("continue-*"))
