"""Real filesystem boundary checks, with no access to shared user data."""

import hashlib
import os
import subprocess
from types import SimpleNamespace

import pytest
from conftest import owner_grant

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


def test_macos_composed_and_decomposed_names_share_lock_identity(setup, monkeypatch):
    from agentsync.resources import paths

    core, auth, _ = setup
    monkeypatch.setattr(paths, "sys", SimpleNamespace(platform="darwin"))
    core.execute("acquire_file_lock", {**auth, "path": "caf\u00e9", "request_id": "nfc"})
    with pytest.raises(AgentSyncError) as exc:
        core.execute("acquire_file_lock", {**auth, "path": "cafe\u0301", "request_id": "nfd"})
    assert exc.value.code == "lock_busy"


def test_linux_distinct_unicode_names_have_distinct_lock_identity(setup, monkeypatch):
    from agentsync.resources import paths

    core, auth, _ = setup
    monkeypatch.setattr(paths, "sys", SimpleNamespace(platform="linux"))
    first = core.execute("acquire_file_lock", {**auth, "path": "caf\u00e9", "request_id": "nfc"})
    second = core.execute("acquire_file_lock", {**auth, "path": "cafe\u0301", "request_id": "nfd"})
    assert first["id"] != second["id"]


def test_explicit_project_symlink_root_is_canonicalized(tmp_path):
    root = tmp_path / "actual"
    root.mkdir()
    alias = tmp_path / "selected"
    try:
        alias.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Creating symlinks is unavailable on this host: {exc}")
    core = Core(tmp_path / "db")
    project = core.execute("create_project", {"name": "selected", "root_path": str(alias)})
    agent = core.execute("register_agent", {**project, "name": "reader"})
    owner_grant(core, project, agent)
    auth = {key: agent[key] for key in ("session_id", "session_token")}
    inspected = core.execute(
        "inspect_path", {**auth, "project_id": project["project_id"], "path": "."}
    )
    assert inspected["kind"] == "directory"


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "resources"
    root.mkdir()
    core = Core(tmp_path / "db")
    project = core.execute("create_project", {"name": "paths", "root_path": str(root)})
    registered = core.execute("register_agent", {**project, "name": "inspector"})
    owner_grant(core, project, registered)
    auth = {key: registered[key] for key in ("session_id", "session_token")}
    return core, auth | {"project_id": project["project_id"]}, root


@pytest.mark.parametrize(
    "path",
    [
        "",
        "../escape",
        "a/../b",
        "a/./b",
        "a//b",
        "/absolute",
        "C:/absolute",
        "C:relative",
        "\\\\server\\share",
        "\\\\?\\C:\\device",
        "a:stream",
        "a\x00b",
        "a\nb",
        "a\tb",
        "a.",
        "a ",
        "NUL",
        "con.txt",
        "aux",
        "COM1.log",
        "LPT9",
        ".git",
        "a/.GiT/config",
    ],
)
def test_rejects_escapes_aliases_and_windows_special_components(setup, path):
    core, auth, root = setup
    before = list(root.iterdir())
    with pytest.raises(AgentSyncError):
        core.execute("inspect_path", {**auth, "path": path})
    with pytest.raises(AgentSyncError):
        core.execute("acquire_file_lock", {**auth, "path": path, "request_id": "invalid"})
    assert list(root.iterdir()) == before


def test_unicode_backslashes_hash_changes_missing_and_directory(setup):
    core, auth, root = setup
    folder = root / "中文目录"
    folder.mkdir()
    target = folder / "源码.py"
    data = "原始内容\n".encode()
    target.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    inspected = core.execute("inspect_path", {**auth, "path": "中文目录\\源码.py"})
    assert inspected == {
        "path": "中文目录/源码.py",
        "exists": True,
        "kind": "file",
        "sha256": expected,
        "size": len(data),
    }
    assert (
        core.execute(
            "verify_file_version",
            {**auth, "path": "中文目录/源码.py", "expected_sha256": expected.upper()},
        )["matches"]
        is True
    )
    target.write_bytes(b"updated")
    assert (
        core.execute(
            "verify_file_version", {**auth, "path": "中文目录/源码.py", "expected_sha256": expected}
        )["matches"]
        is False
    )
    missing = core.execute(
        "verify_file_version", {**auth, "path": "missing/child.txt", "expected_sha256": None}
    )
    assert missing == {
        "path": "missing/child.txt",
        "exists": False,
        "kind": "missing",
        "sha256": None,
        "size": None,
        "matches": True,
    }
    directory = core.execute("verify_file_version", {**auth, "path": ".", "expected_sha256": None})
    assert directory["kind"] == "directory" and directory["matches"] is False
    assert directory["sha256"] is None
    assert not (root / "missing").exists()


@pytest.mark.parametrize("digest", ["bad", "g" * 64, "0" * 63, 12, "0" * 65])
def test_file_hash_schema_is_strict(setup, digest):
    core, auth, _ = setup
    with pytest.raises(AgentSyncError):
        core.execute("verify_file_version", {**auth, "path": "file", "expected_sha256": digest})


def test_root_directory_and_kind_mismatches(setup):
    core, auth, root = setup
    (root / "file").write_text("data")
    (root / "directory").mkdir()
    for path, kind in ((".", "file"), ("file", "directory"), ("directory", "file")):
        with pytest.raises(AgentSyncError):
            core.execute(
                "acquire_file_lock", {**auth, "path": path, "kind": kind, "request_id": path}
            )
    lock = core.execute(
        "acquire_file_lock",
        {**auth, "path": ".", "kind": "directory", "request_id": "root-directory"},
    )
    assert lock["path"] == "." and lock["kind"] == "directory"


def test_replaced_pinned_root_is_rejected(setup):
    core, auth, root = setup
    # The root is pinned at project creation, before the first inspection.
    root.rename(root.with_name("original-root"))
    root.mkdir()
    (root / "file").write_text("replacement")
    with pytest.raises(AgentSyncError):
        core.execute("inspect_path", {**auth, "path": "file"})


def test_missing_original_root_is_rejected(setup):
    core, auth, root = setup
    root.rmdir()
    with pytest.raises(AgentSyncError):
        core.execute("inspect_path", {**auth, "path": "missing"})


@pytest.mark.skipif(os.name != "nt", reason="Windows junction-specific ancestor boundary")
def test_new_ancestor_junction_rejects_even_identical_physical_root(tmp_path):
    container = tmp_path / "container"
    root = container / "root"
    root.mkdir(parents=True)
    core = Core(tmp_path / "db")
    project = core.execute("create_project", {"name": "ancestor", "root_path": str(root)})
    actor = core.execute("register_agent", {**project, "name": "owner"})
    owner_grant(core, project, actor)
    auth = {key: actor[key] for key in ("session_id", "session_token")}
    auth["project_id"] = project["project_id"]
    saved = tmp_path / "saved-container"
    container.rename(saved)
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(container), str(saved)], capture_output=True, text=True
    )
    if created.returncode:
        pytest.skip(f"Junction creation unavailable: {created.stderr}")
    try:
        with pytest.raises(AgentSyncError):
            core.execute("inspect_path", {**auth, "path": "missing"})
    finally:
        container.rmdir()


@pytest.mark.parametrize("marker_kind", ["file", "directory"])
def test_nested_repositories_are_denied_even_for_nonexistent_descendants(setup, marker_kind):
    core, auth, root = setup
    child = root / "nested"
    child.mkdir()
    marker = child / ".git"
    marker.mkdir() if marker_kind == "directory" else marker.write_text("gitdir: elsewhere")
    for path in ("nested", "nested/missing.txt"):
        with pytest.raises(AgentSyncError):
            core.execute("inspect_path", {**auth, "path": path})


def test_symlink_and_nonexistent_target_through_link_are_denied(setup, tmp_path):
    core, auth, root = setup
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("secret")
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Creating symlinks is unavailable on this host: {exc}")
    for path in ("link/secret", "link/missing"):
        with pytest.raises(AgentSyncError):
            core.execute("inspect_path", {**auth, "path": path})


def test_multiply_linked_files_are_denied(setup):
    core, auth, root = setup
    original = root / "original"
    original.write_text("linked")
    try:
        os.link(original, root / "alias")
    except OSError as exc:
        pytest.skip(f"Hardlink creation is unavailable: {exc}")
    for path in ("original", "alias"):
        with pytest.raises(AgentSyncError):
            core.execute("inspect_path", {**auth, "path": path})


@pytest.mark.skipif(os.name != "nt", reason="Windows junction-specific boundary")
def test_junction_is_denied(setup, tmp_path):
    core, auth, root = setup
    outside = tmp_path / "junction-target"
    outside.mkdir()
    junction = root / "junction"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True, text=True
    )
    if created.returncode:
        pytest.skip(f"Junction creation unavailable: {created.stderr}")
    try:
        with pytest.raises(AgentSyncError):
            core.execute("inspect_path", {**auth, "path": "junction/missing"})
    finally:
        junction.rmdir()


def test_oversized_file_is_explicitly_rejected(setup):
    core, auth, root = setup
    with (root / "large").open("wb") as stream:
        stream.truncate(16 * 1024 * 1024 + 1)
    with pytest.raises(AgentSyncError) as exc:
        core.execute("inspect_path", {**auth, "path": "large"})
    assert exc.value.code == "resource_too_large"


def test_mutation_during_real_hash_read_is_explicitly_unstable(setup, monkeypatch):
    from agentsync.resources import paths

    core, auth, root = setup
    target = root / "mutable"
    target.write_bytes(b"a" * 100)
    original_fdopen = paths.os.fdopen

    class MutatingReader:
        def __init__(self, stream):
            self.stream = stream
            self.changed = False

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            chunk = self.stream.read(size)
            if not self.changed:
                target.write_bytes(b"b" * 101)
                self.changed = True
            return chunk

    monkeypatch.setattr(paths.os, "fdopen", lambda *args: MutatingReader(original_fdopen(*args)))
    with pytest.raises(AgentSyncError) as exc:
        core.execute("inspect_path", {**auth, "path": "mutable"})
    assert exc.value.code == "unstable_resource"
