"""Owner public audit evidence must identify intent resources and revisions."""

import hashlib
import json

from test_candidate_claims import claim
from test_candidate_jobs import owner, profile
from test_candidate_jobs import prepared as prepared
from test_candidate_jobs import world as world

from agentsync.verification.candidate_intents import OwnerCandidateExecutionIntents


def test_intent_audit_identifies_resource_revisions_without_plain_credentials(prepared):
    reserved = claim(prepared)
    service = OwnerCandidateExecutionIntents(prepared[0])
    receipt = service.prepare_once(
        **owner(prepared), job_id=reserved["job"]["id"], expected_version=2, profile=profile()
    )
    intent_id = receipt["intent"]["id"]
    request_id = "private-owner-abandon-request"
    original = service.abandon_once(
        **owner(prepared),
        job_id=reserved["job"]["id"],
        intent_id=intent_id,
        expected_revision=1,
        request_id=request_id,
    )
    assert (
        service.abandon_once(
            **owner(prepared),
            job_id=reserved["job"]["id"],
            intent_id=intent_id,
            expected_revision=1,
            request_id=request_id,
        )
        == original
    )
    events = prepared[0].execute_owner(
        "list_audit", {**owner(prepared), "limit": 100, "offset": 0}
    )["events"]
    relevant = [
        event
        for event in events
        if event["operation"] in {"candidate_intent_prepare", "candidate_intent_abandon"}
    ]
    assert len(relevant) == 2
    prepare, abandon = sorted(relevant, key=lambda event: event["operation"], reverse=True)
    assert prepare["operation"] == "candidate_intent_prepare"
    assert abandon["operation"] == "candidate_intent_abandon"
    assert all(
        event["target_id"] == intent_id
        and event["actor_kind"] == "owner"
        and event["actor_id"] == owner(prepared)["project_id"]
        and event["outcome"] == "success"
        for event in relevant
    )
    assert (prepare["pre_version"], prepare["post_version"]) == (None, 1)
    assert (abandon["pre_version"], abandon["post_version"]) == (1, 2)
    assert abandon["request_id_digest"] == hashlib.sha256(request_id.encode()).hexdigest()
    raw = json.dumps(events)
    assert request_id not in raw and owner(prepared)["admin_token"] not in raw
