"""Owner advisory and project accounting using owned, offline provider fixtures."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import agentsync
from agentsync.adapters.approved_launch import digest
from agentsync.model_usage import FlatRate
from agentsync.providers import (
    HTTPProvider,
    MockProvider,
    ProviderError,
    ProviderProfile,
    http,
    prepare_decomposition,
    prepare_handoff,
)
from agentsync.sdk import AgentSyncClient
from agentsync.storage.database import connect
from agentsync.usage import UsageLedger

SOURCE = "local_provider_calls"
MOCK_REPLY = '{"tasks":[{"id":"fixture","title":"Plan","summary":"Only advice","depends_on":[]}]}'


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    client = AgentSyncClient(tmp_path / "core")
    owner = client.call("create_project", name="Fixture", root_path=str(root))["data"]
    return client, owner, root


def stored(client, project_id):
    with connect(client.core.db_path) as db:
        row = db.execute(
            "SELECT checkpoint FROM project_usage WHERE project_id=?", (project_id,)
        ).fetchone()
    return None if row is None else row[0]


async def test_owned_advice_joins_existing_usage_and_replays_without_a_grant(project, monkeypatch):
    client, owner, root = project
    project_id = owner["project_id"]
    v1 = UsageLedger(project_id).to_json()
    v2 = {"schema_version": 2, "caller": json.loads(v1), "controlled_relay_receipts": []}
    with connect(client.core.db_path) as db:
        db.execute("INSERT INTO project_usage VALUES(?,?,?)", (project_id, json.dumps(v2), 0))

    provider = HTTPProvider(ProviderProfile("openai", "fixture-model", "owned-fixture-key"))
    advice = prepare_decomposition("private fixture prompt")
    calls = []

    def send(*_args):
        calls.append(1)
        current = json.loads(stored(client, project_id))
        assert current["schema_version"] == 3 and current[SOURCE][0]["status"] == "unknown"
        return json.dumps(
            {
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": MOCK_REPLY}}
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 3},
            }
        ).encode()

    monkeypatch.setattr(http, "send", send)
    request = dict(
        owner, request_id="owner-call", provider=provider, request=advice, rate=FlatRate(4, 5)
    )
    denied = await client.request_model_advice(**(request | {"admin_token": "wrong"}))
    assert denied["error"]["code"] == "unauthorized"
    denied = await client.request_model_advice(**request)
    assert denied["error"]["code"] == "owner_authorization_required"
    assert calls == [] and json.loads(stored(client, project_id)) == v2

    grant = provider.authorize(advice.model_request)
    admitted = await client.request_model_advice(**request, authorization=grant)
    assert admitted["ok"] and admitted["data"]["advice"]["advisory_only"]
    record = admitted["data"]["observation"]
    assert record["status"] == "succeeded" and record["remote_outcome"] == "response_received"
    assert record["estimated_cost_picodollars"] == 15 and record["input_tokens"] == 0
    assert record["cost_usd"] is None and record["billing_verified"] is False
    reopened = AgentSyncClient(client.core.data_dir)
    assert reopened.owner_call(
        "get_provider_usage_call", **owner, request_id="owner-call"
    )["data"] == record
    assert (await reopened.request_model_advice(**request))["data"] == {
        "replayed": True,
        "observation": record,
        "advice": None,
    }
    assert calls == [1]
    changed = await reopened.request_model_advice(**(request | {"rate": FlatRate(1, 1)}))
    assert changed["error"]["code"] == "idempotency_conflict"
    lookup = {"call_id": record["call_id"]}
    assert reopened.owner_call("get_provider_usage_call", **owner, **lookup)["data"] == record
    other = client.call("create_project", name="Other", root_path=str(root))["data"]
    denied = reopened.owner_call("get_provider_usage_call", **other, **lookup)
    assert denied["error"]["code"] == "not_found"
    summary = reopened.owner_call("get_usage_summary", **owner)["data"]
    assert summary["total_records"] == summary["controlled_relay_receipts"]["total_records"] == 0
    assert summary[SOURCE]["total_records"] == 1 and summary[SOURCE]["local_failure_rate"] == 0
    assert summary[SOURCE]["estimated_cost_picodollars"]["value"] == 15
    document = stored(client, project_id)
    assert all(
        secret not in document
        for secret in ("owned-fixture-key", "private fixture prompt", "Only advice", owner["admin_token"])
    )
    rejected = reopened.owner_call(
        "import_usage_checkpoint", **owner, checkpoint=document, request_id="forged"
    )
    assert rejected["error"]["code"] == "validation_error"
    assert stored(client, project_id) == document
    with connect(client.core.db_path) as db:
        events = db.execute(
            "SELECT operation,outcome FROM audit_events WHERE operation LIKE 'provider_usage_%' "
            "AND outcome IN ('allowed','succeeded') ORDER BY time"
        ).fetchall()
    assert [tuple(event) for event in events] == [
        ("provider_usage_admit", "allowed"),
        ("provider_usage_finish", "succeeded"),
    ]


@pytest.mark.parametrize("fault", ["throttled", "timeout", "invalid_advice", "exception"])
async def test_failed_call_is_retained_with_exact_observed_cost_sources(project, monkeypatch, fault):
    client, owner, _ = project
    provider = HTTPProvider(ProviderProfile("openai", "fixture-model", "owned-fixture-key"))
    advice = prepare_handoff("Bounded fixture notes")

    def send(*_args):
        if fault == "throttled":
            raise ProviderError("provider_rate_limited", http_status=429, retry_after_seconds=7)
        if fault == "timeout":
            raise ProviderError("provider_timeout")
        if fault == "exception":
            raise RuntimeError("private exception text")
        return json.dumps(
            {
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": "not advice"}}
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3},
            }
        ).encode()

    monkeypatch.setattr(http, "send", send)
    request = dict(owner, request_id=fault, provider=provider, request=advice, rate=FlatRate(4, 5))
    result = await client.request_model_advice(
        **request, authorization=provider.authorize(advice.model_request)
    )
    assert result["ok"] and result["data"]["advice"] is None
    record = result["data"]["observation"]
    assert record["status"] == "failed" and record["cost_usd"] is None
    assert record["remote_outcome"] == {
        "throttled": "http_error",
        "timeout": "unknown",
        "invalid_advice": "response_received",
        "exception": "unknown",
    }[fault]
    assert record["estimated_cost_picodollars"] == (23 if fault == "invalid_advice" else None)
    assert record["retry_after_seconds"] == (7 if fault == "throttled" else None)
    assert "private exception text" not in stored(client, owner["project_id"])
    assert (await client.request_model_advice(**request))["data"]["observation"] == record


async def test_pending_replay_and_cancellation_never_dispatch_again(project, monkeypatch):
    client, owner, _ = project
    provider = HTTPProvider(ProviderProfile("ollama", "owned-fixture"))
    advice = prepare_handoff("Bounded fixture notes")
    entered = asyncio.Event()
    blocked = asyncio.Event()

    async def complete(self, request, *, authorization):
        authorization._consume(self, request)
        entered.set()
        await blocked.wait()
        raise AssertionError("fixture is cancelled")

    monkeypatch.setattr(HTTPProvider, "complete", complete)
    request = dict(owner, request_id="cancelled", provider=provider, request=advice)
    first = asyncio.create_task(
        client.request_model_advice(**request, authorization=provider.authorize(advice.model_request))
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        replay = await client.request_model_advice(**request)
        assert replay["data"]["observation"]["status"] == "unknown"
    finally:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
    reopened = AgentSyncClient(client.core.data_dir)
    replay = (await reopened.request_model_advice(**request))["data"]
    assert replay["replayed"] and replay["observation"]["status"] == "cancelled"
    assert replay["observation"]["remote_outcome"] == "unknown"


async def test_process_loss_preserves_unknown_and_never_repeats_mock_advice(project, monkeypatch):
    client, owner, _ = project
    script = """
import asyncio, json, os, sys
from agentsync.providers import MockProvider, prepare_decomposition
from agentsync.sdk import AgentSyncClient
async def stop(*args, **kwargs):
    os._exit(74)
MockProvider.complete = stop
asyncio.run(AgentSyncClient(sys.argv[1]).request_model_advice(
    **json.load(sys.stdin), request_id='lost', provider=MockProvider(sys.argv[2]),
    request=prepare_decomposition('Fixture prompt'),
))
"""
    child = subprocess.run(
        [sys.executable, "-s", "-B", "-c", script, str(client.core.data_dir), MOCK_REPLY],
        cwd=client.core.data_dir,
        env=os.environ | {"PYTHONPATH": str(Path(agentsync.__file__).resolve().parents[1])},
        input=json.dumps(owner),
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert child.returncode == 74

    async def unexpected(*args, **kwargs):
        pytest.fail("Saved provider intent must never be executed a second time.")

    monkeypatch.setattr(MockProvider, "complete", unexpected)
    reopened = AgentSyncClient(client.core.data_dir)
    replay = await reopened.request_model_advice(
        **owner,
        request_id="lost",
        provider=MockProvider(MOCK_REPLY),
        request=prepare_decomposition("Fixture prompt"),
    )
    assert replay["data"]["replayed"] and replay["data"]["observation"]["status"] == "unknown"
    summary = reopened.owner_call("get_usage_summary", **owner)["data"][SOURCE]
    assert summary["total_records"] == summary["simulated_records"] == 1
    assert summary["simulated_statuses"]["unknown"] == 1
    call_id = digest([owner["project_id"], "lost"])
    observation = reopened.owner_call("get_provider_usage_call", **owner, call_id=call_id)
    assert observation["data"]["elapsed_ms"] is None
