"""Small real local contention diagnostics, with disposable owned Core state."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from agentsync import __version__
from agentsync.core.service import Core

SPEC = importlib.util.spec_from_file_location(
    "benchmark_coordination",
    Path(__file__).resolve().parents[2] / "tools/benchmark_coordination.py",
)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_actual_two_worker_rounds_verify_claims_privacy_and_owned_cleanup(tmp_path, monkeypatch):
    existing = tmp_path / "agentsync.db"
    existing.write_bytes(b"existing-parent-state")
    secrets = []
    execute = Core.execute

    def observe(self, operation, payload):
        response = execute(self, operation, payload)
        secrets.extend(
            response[key]
            for key in ("admin_token", "session_token", "lease_token", "agent_id", "session_id")
            if key in response
        )
        if operation == "claim_task":
            secrets.append(hashlib.sha256(payload["request_id"].encode()).hexdigest())
        return response

    monkeypatch.setattr(Core, "execute", observe)
    report = benchmark.run_benchmark(tmp_path, workers=2, rounds=2, p95_budget_ms=60000)
    assert report["passed"] and all(report["functional_checks"].values())
    assert report["package_version"] == __version__
    assert report["workload"]["claims"] == 4 and not report["unexpected_errors"]
    assert report["claim_audit"] == dict(
        expected=4,
        observed=4,
        success=2,
        denied=2,
        missing=0,
        duplicate=0,
        unexpected=0,
        mismatch=0,
    )
    assert report["round_observations"] == [
        {"round": index, "winners": 1, "expected_version_conflicts": 1, "unexpected_errors": 0}
        for index in (1, 2)
    ]
    latency = report["claim_latency_ms"]
    assert 0 < latency["p50"] <= latency["p95"] <= latency["p99"]
    assert report["throughput_claim_attempts_per_second"] > 0
    serialized = json.dumps(report)
    assert secrets and all(secret not in serialized for secret in secrets)
    assert str(tmp_path) not in serialized and "session_id" not in serialized
    assert report["diagnostic_only"] and not report["formal_acceptance"]
    assert not report["real_client_verified"]
    assert (
        list(tmp_path.iterdir()) == [existing] and existing.read_bytes() == b"existing-parent-state"
    )


def test_cli_actual_tiny_latency_budget_fails_and_invalid_options_return_json(tmp_path, capsys):
    arguments = [
        "--scratch-parent",
        str(tmp_path),
        "--workers",
        "1",
        "--rounds",
        "1",
        "--p95-budget-ms",
        "1e-100",
    ]
    assert benchmark.main(arguments) == 1
    report = json.loads(capsys.readouterr().out)
    assert not report["passed"] and not report["p95_budget_passed"]
    assert all(report["functional_checks"].values()) and not report["unexpected_errors"]
    assert list(tmp_path.iterdir()) == []
    assert benchmark.main([]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "invalid_options"


def test_invalid_options_precede_filesystem_io(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "resolve", lambda *_args, **_kwargs: pytest.fail("Unexpected I/O"))
    for options in (
        {"workers": True},
        {"workers": 0},
        {"workers": 33},
        {"workers": 2.0},
        {"rounds": False},
        {"rounds": 0},
        {"rounds": 33},
        {"p95_budget_ms": True},
        {"p95_budget_ms": 0},
        {"p95_budget_ms": 60001},
        {"p95_budget_ms": float("nan")},
        {"p95_budget_ms": float("inf")},
        {"p95_budget_ms": 10**400},
    ):
        with pytest.raises(ValueError):
            benchmark.run_benchmark(tmp_path, **options)
    with pytest.raises(ValueError):
        benchmark.run_benchmark(Path("relative"))


def test_unexpected_claim_exception_fails_without_raw_exception_text(tmp_path, monkeypatch):
    execute = Core.execute

    def fail_claim(self, operation, payload):
        if operation == "claim_task":
            raise RuntimeError("private-exception-and-token")
        return execute(self, operation, payload)

    monkeypatch.setattr(Core, "execute", fail_claim)
    report = benchmark.run_benchmark(tmp_path, workers=2, rounds=1)
    assert not report["passed"] and report["unexpected_errors"] == {"claim_error": 2}
    assert "private" not in json.dumps(report) and list(tmp_path.iterdir()) == []


def test_missing_denial_audit_fails_even_when_claims_and_latency_pass(tmp_path, monkeypatch):
    original = Core._audit_denial

    def skip_claim_conflict(self, actor, operation, payload, code):
        if operation != "claim_task" or code != "version_conflict":
            original(self, actor, operation, payload, code)

    monkeypatch.setattr(Core, "_audit_denial", skip_claim_conflict)
    report = benchmark.run_benchmark(tmp_path, workers=2, rounds=1, p95_budget_ms=60000)
    assert not report["passed"] and not report["functional_checks"]["claim_audit_complete"]
    assert all(
        value for key, value in report["functional_checks"].items() if key != "claim_audit_complete"
    )
    assert report["p95_budget_passed"] and not report["unexpected_errors"]
    assert report["claim_audit"] == dict(
        expected=2,
        observed=1,
        success=1,
        denied=0,
        missing=1,
        duplicate=0,
        unexpected=0,
        mismatch=0,
    )
    assert "request_id_digest" not in json.dumps(report) and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("corruption", ["duplicate_instead_of_denial", "wrong_actor_kind"])
def test_equal_audit_totals_do_not_mask_identity_or_outcome_corruption(
    tmp_path, monkeypatch, corruption
):
    original = Core._audit_event

    def corrupt(
        db, project, actor_kind, actor_id, operation, payload, outcome, code, response=None
    ):
        if operation == "claim_task" and outcome == "denied":
            if corruption == "duplicate_instead_of_denial":
                return
            actor_kind = "owner"
        original(db, project, actor_kind, actor_id, operation, payload, outcome, code, response)
        if (
            operation == "claim_task"
            and outcome == "success"
            and corruption == "duplicate_instead_of_denial"
        ):
            original(db, project, actor_kind, actor_id, operation, payload, outcome, code, response)

    monkeypatch.setattr(Core, "_audit_event", staticmethod(corrupt))
    report = benchmark.run_benchmark(tmp_path, workers=2, rounds=1, p95_budget_ms=60000)
    audit = report["claim_audit"]
    assert not report["passed"] and not report["functional_checks"]["claim_audit_complete"]
    assert audit["expected"] == audit["observed"] == 2
    if corruption == "duplicate_instead_of_denial":
        assert audit["missing"] == audit["duplicate"] == 1 and audit["mismatch"] == 0
    else:
        assert audit["missing"] == audit["duplicate"] == 0 and audit["mismatch"] == 1
    assert not report["unexpected_errors"] and list(tmp_path.iterdir()) == []
