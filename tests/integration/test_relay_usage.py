"""Exercise owner reconciliation and storage with explicit local receipt fixtures."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from conftest import owner_grant

from agentsync.adapters.approved_launch import digest
from agentsync.adapters.codex import CodexResult, CodexRun
from agentsync.adapters.codex_events import CodexUsage
from agentsync.controlled_relay import ControlledRelay
from agentsync.sdk import AgentSyncClient
from agentsync.storage.database import connect
from agentsync.usage import UsageLedger

SOURCE = "controlled_relay_receipts"


@pytest.fixture
def project(tmp_path):
    scratch = tmp_path.resolve()
    receipts = scratch / "receipts"
    receipts.mkdir()
    client = AgentSyncClient(scratch / "core")
    core = client.core
    owner = core.execute("create_project", {"name": "Fixture", "root_path": str(scratch)})
    worker = core.execute("register_agent", {**owner, "name": "Worker"})
    owner_grant(core, owner, worker, ("worker",))
    auth = {
        "project_id": owner["project_id"],
        **{key: worker[key] for key in ("session_id", "session_token")},
    }
    relay = ControlledRelay(core, scratch, receipts)
    return client, owner, worker, auth, relay


def prepare(project, title="Task", *, legacy=False, mode="single_codex", reserve=True):
    client, owner, worker, auth, relay = project
    core = client.core
    project_id = owner["project_id"]
    task = core.execute("create_task", {**auth, "title": title, "request_id": title})
    task_id = task["id"]
    key = relay._task_receipt_key(project_id, task_id)
    relay._check_receipt_anchor(project_id, bind=True)
    relay._record(key, "incomplete", **({} if mode == "two_leg" else {"mode": mode}))
    claimed = core.execute(
        "claim_task",
        {
            **auth,
            "task_id": task_id,
            "expected_version": task["version"],
            "request_id": "claim:" + key,
        },
    )
    lease = {**auth, "task_id": task_id, "lease_token": claimed["lease_token"]}
    active = core.execute(
        "update_task",
        {
            **lease,
            "expected_version": claimed["version"],
            "status": "running",
            "request_id": f"relay:{key}:first:running",
        },
    )
    if reserve:
        core.execute(
            "renew_lease",
            {
                **lease,
                "expected_version": active["version"],
                "request_id": f"relay:{key}:first:capture",
            },
        )
    request = (
        f"relay:{key}:first:launch"
        if mode == "two_leg"
        else f"relay:{key}:single-codex:{digest('reply')}"
    )
    launch = digest([project_id, worker["session_id"], task_id, request])
    session = digest(worker["session_id"])
    pins = {} if legacy else {"relay_request_id": request, "session_sha256": session}
    relay._record(
        key,
        "first-dispatched",
        client="codex",
        launch_request_sha256=launch,
        agent_sha256=digest(worker["agent_id"]),
        **pins,
    )
    admission = {
        "plan_sha256": digest([title, "plan"]),
        "client": "codex",
        "request_sha256": launch,
        "consent_sha256": digest([title, "approval"]),
    }
    if reserve:
        relay._receipt_store.write(f"launch-{launch}.json", admission)
        relay._receipt_store.write(f"consent-{admission['consent_sha256']}.json", admission)
    payload = {
        **owner,
        "task_id": task_id,
        "scratch_root": str(relay._scratch),
        "receipts": str(relay._receipts),
    }
    terminal = {
        "status": "expected_reply",
        "exit_code": 0,
        "parent_ended": True,
        "timed_out": False,
        "run_sha256": digest([title, "run"]),
        "session_sha256": session,
        "adapter_elapsed_ms": 16,
        "reported_input_tokens": 0,
        "reported_output_tokens": 3,
        **({} if legacy else {"launch_request_sha256": launch}),
    }
    return payload, key, terminal, admission


def checkpoint(client, owner):
    with connect(client.core.db_path) as db:
        row = db.execute(
            "SELECT checkpoint FROM project_usage WHERE project_id=?", (owner["project_id"],)
        ).fetchone()
    return row[0] if row else None


def test_v1_and_receipt_sources_remain_separate_with_unknown_to_terminal_upgrade(project):
    client, owner, worker, _, relay = project
    payload, key, terminal, _ = prepare(project)
    run_id = "same-fixture-run"
    terminal["run_sha256"] = digest(run_id)
    ledger = UsageLedger(owner["project_id"])
    ledger.record_result(
        CodexResult(
            CodexRun(
                owner["project_id"],
                worker["session_id"],
                payload["task_id"],
                "caller-request",
                run_id,
                "succeeded",
                0.0,
                finished_at=1.0,
            ),
            usage=CodexUsage(9, 0, 8),
        )
    )
    assert client.owner_call(
        "import_usage_checkpoint", **owner, checkpoint=ledger.to_json(), request_id="v1"
    )["ok"]
    assert json.loads(checkpoint(client, owner))["schema_version"] == 1
    first = client.owner_call("sync_relay_usage", **payload)["data"]["attempts"][0]
    lookup = {**owner, "kind": first["kind"], "run_id": first["run_id"], "provenance": SOURCE}
    unknown = client.owner_call("get_usage_run", **lookup)["data"]
    assert unknown["status"] == "unknown" and unknown["terminal_recorded"] is False
    assert all(value == "unavailable" for value in unknown["field_provenance"].values())
    subtotal = client.owner_call("get_usage_summary", **owner)["data"][SOURCE]
    assert subtotal["failure_rate"] is None and subtotal["failure_rate_complete"] is False
    assert subtotal["failure_rate_denominator"] == 0
    assert subtotal["input_tokens"]["unknown_runs"] == 1

    relay._record(key, "first-observed", **terminal)
    reopened = AgentSyncClient(client.core.data_dir)
    synced = reopened.owner_call("sync_relay_usage", **payload)["data"]["attempts"][0]
    assert synced == dict(first, state="updated")
    summary = reopened.owner_call("get_usage_summary", **owner)["data"]
    assert summary["total_records"] == summary[SOURCE]["total_records"] == 1
    assert summary["input_tokens"]["value"] == 9 and summary[SOURCE]["input_tokens"]["value"] == 0
    assert summary[SOURCE]["terminal_records"] == 1
    assert summary[SOURCE]["failure_rate"] == 0 and summary[SOURCE]["failure_rate_complete"]
    assert summary[SOURCE]["cost_usd"] is None and summary[SOURCE]["real_client_verified"] is False
    final = reopened.owner_call("get_usage_run", **lookup)["data"]
    assert final["field_provenance"] == {
        "started_at": "unavailable",
        "finished_at": "unavailable",
        "input_tokens": "client_reported",
        "output_tokens": "client_reported",
        "adapter_elapsed_ms": "adapter_lifecycle",
    }
    assert (
        reopened.owner_call("get_usage_run", **owner, kind="codex", run_id=run_id)["data"][
            "output_tokens"
        ]
        == 8
    )
    original = checkpoint(reopened, owner)
    assert not reopened.owner_call(
        "import_usage_checkpoint", **owner, checkpoint=original, request_id="fake-source"
    )["ok"]
    assert (
        reopened.owner_call(
            "import_usage_checkpoint", **owner, checkpoint=ledger.to_json(), request_id="v1-again"
        )["data"]["duplicate_records"]
        == 1
    )
    assert checkpoint(reopened, owner) == original

    # Replaying a different terminal under the same historical binding rejects.
    path = relay._receipts / relay._receipt_name(key, "first-observed")
    original_receipt = json.loads(path.read_text())
    path.write_text(json.dumps(dict(original_receipt, reported_input_tokens=4)))
    assert (
        reopened.owner_call("sync_relay_usage", **payload)["error"]["code"]
        == "idempotency_conflict"
    )
    assert checkpoint(reopened, owner) == original
    path.unlink()
    assert (
        reopened.owner_call("sync_relay_usage", **payload)["data"]["attempts"][0]["state"]
        == "unchanged"
    )
    assert checkpoint(reopened, owner) == original


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("unauthorized", "unauthorized"),
        ("foreign_task", "not_found"),
        ("wrong_root", "relay_boundary"),
        ("missing_anchor", "relay_boundary"),
        ("wrong_agent", "relay_usage_boundary"),
        ("wrong_session", "relay_usage_boundary"),
        ("wrong_launch", "relay_usage_boundary"),
        ("wrong_consent", "relay_usage_boundary"),
        ("wrong_terminal_launch", "relay_usage_boundary"),
        ("timeout_without_capture", "relay_usage_boundary"),
        ("second_leg_conflict", "relay_usage_boundary"),
    ],
)
def test_sync_rejects_unbound_data_without_partial_admission(project, mutation, code):
    client, owner, _, _, relay = project
    payload, key, terminal, admission = prepare(project, mode="two_leg")
    if mutation == "unauthorized":
        payload["admin_token"] = "bad-token"
    elif mutation == "foreign_task":
        payload.update(
            client.core.execute(
                "create_project", {"name": "Other", "root_path": payload["scratch_root"]}
            )
        )
    elif mutation == "wrong_root":
        root = relay._scratch / "other-receipts"
        root.mkdir()
        payload["receipts"] = str(root)
    elif mutation == "missing_anchor":
        (client.core.data_dir / f"controlled-relay-{digest(owner['project_id'])}.json").unlink()
    elif mutation in ("wrong_agent", "wrong_session", "wrong_launch"):
        field = {
            "wrong_agent": "agent_sha256",
            "wrong_session": "session_sha256",
            "wrong_launch": "launch_request_sha256",
        }[mutation]
        path = relay._receipts / relay._receipt_name(key, "first-dispatched")
        path.write_text(json.dumps(dict(json.loads(path.read_text()), **{field: digest("wrong")})))
    elif mutation == "wrong_consent":
        path = relay._receipts / f"consent-{admission['consent_sha256']}.json"
        path.write_text(json.dumps(dict(admission, plan_sha256=digest("wrong plan"))))
    elif mutation == "wrong_terminal_launch":
        terminal["launch_request_sha256"] = digest("foreign terminal")
    elif mutation == "timeout_without_capture":
        with connect(client.core.db_path) as db:
            db.execute(
                "DELETE FROM idempotency WHERE request_id=?", (f"relay:{key}:first:capture",)
            )
        terminal.update(status="unknown", timed_out=True, exit_code=1)
    else:
        relay._record(key, "second-observed", **terminal)
    stage = "first-stopped" if mutation == "timeout_without_capture" else "first-observed"
    relay._record(key, stage, **terminal)
    assert client.owner_call("sync_relay_usage", **payload)["error"]["code"] == code
    assert checkpoint(client, owner) is None
    with connect(client.core.db_path) as db:
        denial = db.execute(
            "SELECT code FROM audit_events WHERE operation='sync_relay_usage'"
        ).fetchone()
    assert denial is None if mutation == "unauthorized" else denial["code"] == code


def test_legacy_binding_and_unreserved_attempt_have_explicit_outcomes(project):
    client, owner, _, _, relay = project
    denied, _, _, _ = prepare(project, "denied", reserve=False)
    assert (
        client.owner_call("sync_relay_usage", **denied)["data"]["attempts"][0]["state"]
        == "not_recorded"
    )
    assert checkpoint(client, owner) is None
    legacy_single, _, _, _ = prepare(project, "old single", legacy=True)
    assert (
        client.owner_call("sync_relay_usage", **legacy_single)["error"]["code"]
        == "relay_usage_unsupported"
    )
    legacy, key, terminal, _ = prepare(project, "old pair", legacy=True, mode="two_leg")
    relay._record(key, "first-observed", **terminal)
    attempt = client.owner_call("sync_relay_usage", **legacy)["data"]["attempts"][0]
    entry = client.owner_call(
        "get_usage_run", **owner, provenance=SOURCE, kind="codex", run_id=attempt["run_id"]
    )["data"]
    assert entry["binding"] == "legacy_two_leg" and entry["status"] == "succeeded"


def test_concurrent_sync_and_metric_overflow_are_atomic(project):
    client, owner, _, _, relay = project
    first, key, terminal, _ = prepare(project, "first")
    relay._record(key, "first-observed", **dict(terminal, reported_input_tokens=2**63 - 1))
    barrier = Barrier(2)

    def sync():
        barrier.wait(timeout=5)
        return client.owner_call("sync_relay_usage", **first)["data"]["attempts"][0]["state"]

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(
            result.result(timeout=15) for result in [workers.submit(sync) for _ in range(2)]
        ) == ["added", "unchanged"]
    original = checkpoint(client, owner)
    second, key, terminal, _ = prepare(project, "second")
    relay._record(key, "first-observed", **dict(terminal, reported_input_tokens=1))
    assert client.owner_call("sync_relay_usage", **second)["error"]["code"] == "usage_overflow"
    assert checkpoint(client, owner) == original


def test_stored_byte_limit_rejects_without_writing_partial_checkpoint(project, monkeypatch):
    client, owner, _, _, _ = project
    from agentsync.core import usage

    payload, _, _, _ = prepare(project)
    monkeypatch.setattr(usage, "_MAX_STORED_BYTES", 512)
    assert (
        client.owner_call("sync_relay_usage", **payload)["error"]["code"]
        == "history_capacity_exceeded"
    )
    assert checkpoint(client, owner) is None
