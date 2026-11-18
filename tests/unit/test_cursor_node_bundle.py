"""Synthetic package fixtures: no Cursor client, credentials or model requests."""

import hashlib
import os
from dataclasses import replace

import pytest

import agentsync.adapters.cursor_invocation as invocation
from agentsync.adapters.approved_launch import digest, prepare_launch_review
from agentsync.adapters.base import AdapterTask
from agentsync.adapters.cursor_invocation import (
    CursorHostProfile,
    inspect_node_bundle,
    prepare_invocation,
)
from agentsync.errors import AgentSyncError


def fixture(tmp_path):
    bundle = tmp_path / "vendor"
    bundle.mkdir()
    binary = bundle / ("node.exe" if os.name == "nt" else "node")
    binary.write_bytes(b"Non-executable runtime fixture")
    entrypoint = bundle / "index.js"
    entrypoint.write_bytes(b"Synthetic entrypoint")
    (bundle / "dependency.js").write_bytes(b"Synthetic dependency")
    project = tmp_path / "project"
    project.mkdir()
    profile = CursorHostProfile(
        "project",
        "session",
        binary,
        project,
        hashlib.sha256(binary.read_bytes()).hexdigest(),
        "fixture-version",
        node_entrypoint=entrypoint,
        expected_bundle_sha256=inspect_node_bundle(bundle),
    )
    task = AdapterTask("project", "session", "task", "request", "--force fixture", 10)
    return profile, task, bundle


def test_node_bundle_plan_pins_native_entrypoint_and_isolated_environment(tmp_path):
    profile, task, _ = fixture(tmp_path)
    env = {"USERPROFILE": "private-home", "CURSOR_CONFIG_DIR": "private-config"}
    plan = prepare_invocation(profile, task, environment=env)
    assert plan.argv[:3] == (str(profile.executable), str(profile.node_entrypoint), "--print")
    assert plan.argv[-1] == "Instruction:\n--force fixture"
    assert plan.bundle_sha256 == profile.expected_bundle_sha256
    assert plan.binary_sha256 == profile.expected_binary_sha256
    assert plan.child_env() == env
    assert plan.sandbox_verified is plan.real_client_verified is False
    for name in ("NODE_OPTIONS", "NODE_PATH", "CURSOR_API_KEY", "CURSOR_API_URL"):
        with pytest.raises(AgentSyncError):
            prepare_invocation(profile, task, environment={name: "untrusted"})


@pytest.mark.parametrize(
    "change", ["entrypoint_only", "hash_only", "different_parent", "wrong_script", "wrong_runtime"]
)
def test_partial_or_mislocated_bundle_is_rejected_without_file_reads(tmp_path, monkeypatch, change):
    profile, _, _ = fixture(tmp_path)
    changes = {
        "entrypoint_only": {"expected_bundle_sha256": None},
        "hash_only": {"node_entrypoint": None},
        "different_parent": {"node_entrypoint": tmp_path / "index.js"},
        "wrong_script": {"node_entrypoint": profile.executable.parent / "other.js"},
        "wrong_runtime": {"executable": profile.executable.parent / "other.exe"},
    }

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Structural validation must not inspect files")

    monkeypatch.setattr(type(tmp_path), "lstat", forbidden)
    with pytest.raises(AgentSyncError):
        replace(profile, **changes[change])


@pytest.mark.parametrize("change", ["entrypoint", "dependency", "add", "remove"])
def test_changed_bundle_never_reuses_an_old_pin(tmp_path, change):
    profile, task, bundle = fixture(tmp_path)
    if change == "entrypoint":
        profile.node_entrypoint.write_bytes(b"Changed entrypoint")
    elif change == "dependency":
        (bundle / "dependency.js").write_bytes(b"Changed dependency")
    elif change == "add":
        (bundle / "new.js").write_bytes(b"New dependency")
    else:
        (bundle / "dependency.js").unlink()
    with pytest.raises(AgentSyncError) as error:
        prepare_invocation(profile, task, environment={})
    assert error.value.code == "bundle_pin_mismatch"


def test_bundle_change_requires_new_consent_and_legacy_digest_stays_exact(tmp_path):
    profile, task, bundle = fixture(tmp_path)
    first = prepare_launch_review(profile, task, environment={})
    (bundle / "dependency.js").write_bytes(b"Reviewed replacement")
    updated = replace(profile, expected_bundle_sha256=inspect_node_bundle(bundle))
    second = prepare_launch_review(updated, task, environment={})
    assert first.plan.argv == second.plan.argv
    assert first.plan.binary_sha256 == second.plan.binary_sha256
    assert first.plan_sha256 != second.plan_sha256
    legacy = replace(profile, node_entrypoint=None, expected_bundle_sha256=None)
    review = prepare_launch_review(legacy, task, environment={})
    p = review.plan
    old_digest = digest(
        [
            "cursor",
            task.project_id,
            task.session_id,
            task.task_id,
            task.request_id,
            task.timeout_seconds,
            task.instruction,
            p.argv,
            str(p.cwd),
            p.stdin_text,
            sorted(p.child_env().items()),
            p.timeout_seconds,
            p.output_limit,
            p.expected_cli_version,
            p.binary_sha256,
        ]
    )
    assert review.plan_sha256 == old_digest


@pytest.mark.parametrize("bound", ["entries", "depth", "bytes"])
def test_bundle_traversal_is_bounded(tmp_path, monkeypatch, bound):
    _, _, bundle = fixture(tmp_path)
    if bound == "entries":
        monkeypatch.setattr(invocation, "MAX_BUNDLE_ENTRIES", 2)
    elif bound == "depth":
        monkeypatch.setattr(invocation, "MAX_BUNDLE_DEPTH", 1)
        (bundle / "nested").mkdir()
        (bundle / "nested/file.js").write_bytes(b"x")
    else:
        monkeypatch.setattr(invocation, "MAX_BINARY_BYTES", 2)
    with pytest.raises(AgentSyncError) as error:
        inspect_node_bundle(bundle)
    assert error.value.code == "bundle_too_large"


def test_dependency_added_while_inventory_is_hashed_is_rejected(tmp_path, monkeypatch):
    _, _, bundle = fixture(tmp_path)
    original = invocation._bundle_inventory
    calls = 0

    def inventory(root):
        nonlocal calls
        calls += 1
        if calls == 2:
            (root / "added-during-hash.js").write_bytes(b"Unexpected dependency")
        return original(root)

    monkeypatch.setattr(invocation, "_bundle_inventory", inventory)
    with pytest.raises(AgentSyncError) as error:
        inspect_node_bundle(bundle)
    assert error.value.code == "bundle_changed"


def test_queued_directory_replacement_is_rejected_before_scanning(tmp_path, monkeypatch):
    _, _, bundle = fixture(tmp_path)
    child = bundle / "queued"
    child.mkdir()
    original_inspect = invocation._inspect_path
    original_scan = invocation.os.scandir
    scanned_child = False

    def inspect(path, *, directory):
        if path == child:
            child.rename(bundle / "moved")
            child.mkdir()
        return original_inspect(path, directory=directory)

    def scan(path):
        nonlocal scanned_child
        if path == child:
            scanned_child = True
        return original_scan(path)

    monkeypatch.setattr(invocation, "_inspect_path", inspect)
    monkeypatch.setattr(invocation.os, "scandir", scan)
    with pytest.raises(AgentSyncError) as error:
        inspect_node_bundle(bundle)
    assert error.value.code == "bundle_changed"
    assert scanned_child is False


@pytest.mark.parametrize("directory", [False, True])
def test_bundle_rejects_actual_links(tmp_path, directory):
    _, _, bundle = fixture(tmp_path)
    target = tmp_path / "outside"
    if directory:
        target.mkdir()
    else:
        target.write_bytes(b"Outside the pinned package")
    try:
        os.symlink(target, bundle / "link", target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("This host cannot create the actual symlink fixture")
    with pytest.raises(AgentSyncError) as error:
        inspect_node_bundle(bundle)
    assert error.value.code == "host_path_invalid"
