"""Synthetic receipt fixtures exercise integrity policy, never real-client acceptance."""

import copy
import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(params=["Windows-test", "Linux-test"])
def bundle(tmp_path, monkeypatch, request):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    verifier = importlib.import_module("acceptance_evidence")
    path_type = PureWindowsPath if request.param.startswith("Windows") else PurePosixPath
    prefix = "D:/fixture" if path_type is PureWindowsPath else "/fixture"
    report = {
        "schema_version": 1,
        "version": "0.0.0",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "platform": request.param,
        "python": "3.12.16 fixture",
        "repo": prefix + "/source",
        "evidence_directory": prefix + "/original",
        "working_tree_status": "",
        "source_changed_during_execution": False,
        "checks": [],
        "distribution_installations": [],
        "composite_execution": {
            "schema_version": 1,
            "scope": "separate_runs_same_frozen_source",
            "single_collector_completed": False,
            "sources": {},
        },
    }
    blobs = {
        "working-tree.patch": b"",
        "source-snapshot.json": json.dumps(
            [{"path": "example.py", "size": 0, "sha256": digest(b"")}]
        ).encode(),
    }
    report["working_tree_patch_sha256"] = digest(blobs["working-tree.patch"])
    report["source_snapshot_sha256"] = digest(blobs["source-snapshot.json"])
    receipts, sources = {}, {}

    def pin(name):
        return {"path": name, "sha256": digest(blobs[name]), "size": len(blobs[name])}

    def process(identity, command, cwd, artifact):
        log = f"logs/{identity}.log"
        blobs[log] = b"synthetic policy fixture only\n"
        row = {
            "id": identity,
            "status": "pass",
            "command": command,
            "cwd": str(cwd),
            "exit_code": 0,
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:01+00:00",
            "log": log,
            "log_sha256": digest(blobs[log]),
            "credential_redactions": 0,
            "log_truncated": False,
            "provenance": "local_process",
            "artifact": artifact,
        }
        receipts[identity] = {
            "schema": "agentsync.local-process-attempt.v1",
            "phase": "finished",
            "check_id": identity,
            "formal_acceptance": False,
            "junit_validated": False,
            "outcome": "exited",
            "result": copy.deepcopy(row),
            "request": {key: copy.deepcopy(row[key]) for key in ("command", "cwd", "started_at")}
            | {"timeout_seconds": 900},
        }
        report["checks"].append(row)
        return row

    for kind, suffix in (("wheel", ".whl"), ("sdist", ".tar.gz")):
        base = path_type(prefix + ("/original" if kind == "wheel" else "/resumed"))
        name = "artifacts/package" + suffix
        blobs[name] = (kind + " synthetic archive").encode()
        artifact = {"kind": kind, **pin(name)}
        environment = path_type(prefix + f"/{kind}-venv")
        suffix_parts = (
            ("Scripts", "python.exe") if path_type is PureWindowsPath else ("bin", "python")
        )
        python = str(environment.joinpath(*suffix_parts))
        archive = base / name
        process(
            kind + "_venv",
            [str(path_type(prefix + "/host/python")), "-m", "venv", str(environment)],
            path_type(report["repo"]) if kind == "wheel" else base,
            artifact,
        )
        install = process(
            kind + "_install", [python, "-I", "-m", "pip", "install", str(archive)], base, artifact
        )
        probe = (
            f"assert direct_url.json == {archive.as_uri()!r}; assert sha == {artifact['sha256']!r}"
        )
        process(kind + "_origin_sdk", [python, "-I", "-c", probe], base, artifact)
        console = path_type(prefix + f"/{kind}-console")
        process(
            kind + "_console_smoke",
            [python, "-I", "-c", "fixture probe", str(console)],
            console,
            artifact,
        )
        report["distribution_installations"].append(
            {
                "kind": kind,
                "status": "pass",
                "artifact": artifact,
                "evidence_log": install["log"],
            }
        )
        sources[kind] = {
            key: report[key]
            for key in (
                "version",
                "commit_sha",
                "tree_sha",
                "source_snapshot_sha256",
                "platform",
                "python",
            )
        } | {"evidence_directory": str(base), "artifact": artifact, "process_receipts": {}}

    report["checks"].append(
        {"id": "wheel_pytest", "status": "unverified", "reason": "canonical receipt unknown"}
    )

    def persist():
        for identity, receipt in receipts.items():
            name = f"logs/{identity}.process.json"
            blobs[name] = json.dumps(receipt).encode()
            kind = identity.split("_", 1)[0]
            # Only refresh existing mappings after the initial creation: a
            # deliberate missing-reference mutation must remain missing.
            if not sources[kind].get("initialized"):
                sources[kind]["process_receipts"][identity] = pin(name)
            elif identity in sources[kind]["process_receipts"]:
                sources[kind]["process_receipts"][identity] = pin(name)
        for kind, source in sources.items():
            document = {key: value for key, value in source.items() if key != "initialized"}
            name = f"composite/{kind}.json"
            blobs[name] = json.dumps(document).encode()
            report.get("composite_execution", {}).get("sources", {})[kind] = pin(name)
            source["initialized"] = True
        for name, data in blobs.items():
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        report["artifacts"] = [pin(name) for name in sorted(blobs)]
        (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")

    persist()
    return (
        report,
        sources,
        receipts,
        blobs,
        persist,
        lambda: verifier.verify_report_evidence(tmp_path / "report.json", report),
    )


def test_composite_preserves_unknown_wheel_without_claiming_complete_matrix(bundle):
    report, _, _, _, _, verify = bundle
    audit = verify()
    assert set(audit["installed_artifact_sha256"]) == {"wheel", "sdist"}
    assert audit["junit_case_sets_match"] is None
    assert report["checks"][-1]["status"] == "unverified"
    assert audit["producer_authenticated"] is False


@pytest.mark.parametrize(
    "field", ["commit_sha", "tree_sha", "source_snapshot_sha256", "version", "platform", "python"]
)
def test_composite_rejects_mixed_frozen_inputs(bundle, field):
    _, sources, _, _, save, verify = bundle
    sources["sdist"][field] += "different"
    save()
    with pytest.raises(ValueError, match="frozen report identity"):
        verify()


def test_composite_directory_must_match_original_receipt(bundle):
    _, sources, _, _, save, verify = bundle
    sources["sdist"]["evidence_directory"] += "/invented"
    save()
    with pytest.raises(ValueError, match="working directory"):
        verify()


@pytest.mark.parametrize("change", ["uri", "sha", "interpreter", "cwd"])
def test_composite_rejects_other_origin_even_with_consistent_receipt(bundle, change):
    report, _, receipts, _, save, verify = bundle
    row = next(row for row in report["checks"] if row["id"] == "sdist_origin_sdk")
    if change in ("uri", "sha"):
        row["command"][3] = row["command"][3].replace(
            "resumed" if change == "uri" else row["artifact"]["sha256"], "different"
        )
    elif change == "interpreter":
        row["command"][0] += "-different"
    else:
        row["cwd"] += "/different"
    receipts[row["id"]]["result"] = copy.deepcopy(row)
    receipts[row["id"]]["request"].update(
        {key: copy.deepcopy(row[key]) for key in ("command", "cwd")}
    )
    save()
    with pytest.raises(ValueError):
        verify()


def test_composite_requires_all_process_references(bundle):
    _, sources, _, _, save, verify = bundle
    del sources["sdist"]["process_receipts"]["sdist_origin_sdk"]
    save()
    with pytest.raises(ValueError, match="mapping"):
        verify()


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_composite_rejects_created_environment_different_from_installed_one(bundle, kind):
    report, _, receipts, _, save, verify = bundle
    row = next(row for row in report["checks"] if row["id"] == kind + "_venv")
    row["command"][-1] += "-different"
    receipts[row["id"]]["result"] = copy.deepcopy(row)
    receipts[row["id"]]["request"]["command"] = copy.deepcopy(row["command"])
    save()
    with pytest.raises(ValueError, match="another installation"):
        verify()


def test_composite_rejects_console_directory_different_from_recorded_operand(bundle):
    report, _, receipts, _, save, verify = bundle
    row = next(row for row in report["checks"] if row["id"] == "sdist_console_smoke")
    row["cwd"] += "/different"
    receipts[row["id"]]["result"] = copy.deepcopy(row)
    receipts[row["id"]]["request"]["cwd"] = row["cwd"]
    save()
    with pytest.raises(ValueError, match="console probe directory"):
        verify()


def test_composite_does_not_promote_started_receipts(bundle):
    _, _, receipts, _, save, verify = bundle
    receipts["wheel_install"]["phase"] = "started"
    receipts["wheel_install"]["outcome"] = "unknown"
    save()
    with pytest.raises(ValueError, match="incomplete"):
        verify()


def test_composite_does_not_accept_changed_archive(bundle):
    _, _, _, blobs, save, verify = bundle
    blobs["artifacts/package.tar.gz"] = b"different archive"
    save()
    with pytest.raises(ValueError):
        verify()


def test_ordinary_report_still_rejects_two_execution_directories(bundle):
    report, _, _, _, save, verify = bundle
    del report["composite_execution"]
    save()
    with pytest.raises(ValueError, match="operand"):
        verify()


def test_ordinary_single_directory_report_remains_supported(bundle):
    report, _, receipts, _, save, verify = bundle
    del report["composite_execution"]
    for row in report["checks"]:
        if row["id"].startswith("sdist_"):
            row["cwd"] = row["cwd"].replace("resumed", "original")
            row["command"] = [value.replace("resumed", "original") for value in row["command"]]
            receipts[row["id"]]["result"] = copy.deepcopy(row)
            receipts[row["id"]]["request"].update(
                {key: copy.deepcopy(row[key]) for key in ("command", "cwd")}
            )
    save()
    assert set(verify()["installed_artifact_sha256"]) == {"wheel", "sdist"}


@pytest.mark.parametrize("mutation", ["completed", "scope", "missing", "unknown"])
def test_composite_declaration_does_not_bypass_bindings(bundle, mutation):
    report, _, _, _, _, verify = bundle
    value = report["composite_execution"]
    if mutation == "completed":
        value["single_collector_completed"] = True
    elif mutation == "scope":
        value["scope"] = "just trust me"
    elif mutation == "missing":
        del value["sources"]["wheel"]
    else:
        value["sources"]["unknown"] = value["sources"]["wheel"]
    with pytest.raises(ValueError, match="declaration"):
        verify()


def test_composite_does_not_accept_duplicate_junit_ids(bundle):
    report, _, _, blobs, save, verify = bundle
    report["checks"][-1]["junit"] = {"tests": 2, "failures": 0, "errors": 0, "skipped": 0}
    blobs["wheel-junit.xml"] = (
        b'<testsuites><testsuite><testcase classname="fixture" name="same"/><testcase classname="fixture" name="same"/></testsuite></testsuites>'
    )
    save()
    with pytest.raises(ValueError, match="identit"):
        verify()
