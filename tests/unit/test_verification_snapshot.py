"""Real Git object export checks, entirely within disposable test repositories."""

import dataclasses
import hashlib
import subprocess
import zlib
from pathlib import Path
from uuid import uuid4

import pytest

from agentsync.errors import AgentSyncError
from agentsync.verification.snapshot import export_candidate
from agentsync.workspaces.git import GitWorkspaceStore


def git(store, repo, *args):
    return store._git(repo, *args)[1].decode("utf-8").strip()


@pytest.fixture
def repository(tmp_path):
    source = tmp_path / "disposable-source"
    source.mkdir()
    store = GitWorkspaceStore(tmp_path / "service")
    git(store, source, "init", "--initial-branch=fixture-main")
    (source / "solution.py").write_bytes(b"def solve(value):\n    return value + 1\n")
    (source / "README.md").write_bytes(b"fixture\n")
    git(store, source, "add", ".")
    git(store, source, "commit", "-m", "fixture baseline")
    receipt = store.capture_repository(source, str(uuid4()))
    return store, receipt, source


def object_command(store, repo, *args, data):
    result = subprocess.run(
        [
            store.binary,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "gc.auto=0",
            "-c",
            "maintenance.auto=false",
            "-C",
            str(repo),
            *args,
        ],
        input=data,
        env=store._env(),
        capture_output=True,
        check=True,
        timeout=30,
    )
    return result.stdout.decode("ascii").strip()


def candidate(store, receipt, entries):
    repo = Path(receipt["repository_path"])
    records = []
    for path, content, mode in entries:
        blob = (
            receipt["base_sha"]
            if mode == "160000"
            else object_command(store, repo, "hash-object", "-w", "--stdin", data=content)
        )
        kind = "commit" if mode == "160000" else "blob"
        records.append(f"{mode} {kind} {blob}\t".encode() + path.encode() + b"\0")
    tree = object_command(store, repo, "mktree", "-z", "--missing", data=b"".join(records))
    return object_command(store, repo, "commit-tree", tree, data=b"isolated candidate\n")


def test_pinned_snapshot_is_frozen_content_only_and_deterministic(repository):
    store, receipt, source = repository
    first = export_candidate(store, receipt, receipt["base_sha"])
    assert first.source == b"def solve(value):\n    return value + 1\n"
    assert len(first.tree_sha) == 40 and len(first.input_sha256) == 64
    assert first.commit_sha == receipt["base_sha"]
    assert [item[0] for item in first.manifest] == ["README.md", "solution.py"]
    assert isinstance(first.manifest, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.source = b"replacement"
    # Dirty source checkout content and newer commits are never read for this SHA.
    (source / "solution.py").write_bytes(b"raise RuntimeError('must never execute')\n")
    git(store, source, "add", ".")
    git(store, source, "commit", "-m", "unrelated mutable source change")
    assert export_candidate(store, receipt, receipt["base_sha"]) == first


def test_worktree_receipt_exports_committed_objects_despite_dirty_worktree(repository):
    store, receipt, _ = repository
    tree = store.create_worktree(receipt, str(uuid4()))
    path = Path(tree["path"])
    (path / "solution.py").write_bytes(b"def solve(value): return value * 2\n")
    git(store, path, "add", ".")
    git(store, path, "commit", "-m", "managed candidate")
    sha = git(store, path, "rev-parse", "HEAD")
    first = export_candidate(store, tree, sha)
    (path / "solution.py").write_bytes(b"raise RuntimeError('dirty host file')\n")
    assert export_candidate(store, tree, sha) == first
    baseline = export_candidate(store, tree, tree["base_sha"])
    assert first.input_sha256 != baseline.input_sha256
    assert first.tree_sha != baseline.tree_sha
    assert first.source == b"def solve(value): return value * 2\n"


def test_archive_attributes_never_filter_or_substitute_exported_bytes(repository):
    store, receipt, _ = repository
    sha = candidate(
        store,
        receipt,
        [
            ("solution.py", b"$Format:%H$\n", "100644"),
            (".gitattributes", b"solution.py export-ignore export-subst\n", "100644"),
        ],
    )
    snapshot = export_candidate(store, receipt, sha)
    assert snapshot.source == b"$Format:%H$\n"
    assert len(snapshot.manifest) == 2


@pytest.mark.parametrize("revision", ["HEAD", "HEAD^{commit}", "-bad", "0" * 40])
def test_rejects_revision_expressions_or_absent_commits(repository, revision):
    store, receipt, _ = repository
    with pytest.raises(AgentSyncError):
        export_candidate(store, receipt, revision)


def test_rejects_blob_object_in_place_of_commit(repository):
    store, receipt, _ = repository
    blob = git(store, Path(receipt["repository_path"]), "rev-parse", "HEAD:solution.py")
    with pytest.raises(AgentSyncError, match="commit object"):
        export_candidate(store, receipt, blob)


@pytest.mark.parametrize("mode", ["120000", "160000"])
def test_rejects_symbolic_links_and_submodules(repository, mode):
    store, receipt, _ = repository
    sha = candidate(store, receipt, [("solution.py", b"../host-file", mode)])
    with pytest.raises(AgentSyncError):
        export_candidate(store, receipt, sha)


@pytest.mark.parametrize(
    "path", ["unsafe:stream", "NUL", "back\\slash", "trailing.", "control\x7f"]
)
def test_rejects_unsafe_git_names_without_extracting_them(repository, path):
    store, receipt, _ = repository
    sha = candidate(store, receipt, [("solution.py", b"pass\n", "100644"), (path, b"x", "100644")])
    with pytest.raises(AgentSyncError):
        export_candidate(store, receipt, sha)


@pytest.mark.parametrize("names", [("A", "a"), ("\u00e9", "e\u0301")])
def test_rejects_case_and_unicode_aliases(repository, names):
    store, receipt, _ = repository
    sha = candidate(
        store,
        receipt,
        [("solution.py", b"pass\n", "100644"), *((name, b"x", "100644") for name in names)],
    )
    with pytest.raises(AgentSyncError, match="aliases"):
        export_candidate(store, receipt, sha)


@pytest.mark.parametrize("case", ["missing", "source_size", "total_size", "file_count"])
def test_rejects_missing_source_and_size_or_count_overflows(repository, case):
    store, receipt, _ = repository
    entries = [("solution.py", b"pass\n", "100644")]
    if case == "missing":
        entries = [("readme", b"x", "100644")]
    elif case == "source_size":
        entries = [("solution.py", b"x" * (128 * 1024 + 1), "100644")]
    elif case == "total_size":
        entries.append(("large.bin", b"x" * (4 * 1024 * 1024), "100644"))
    else:
        entries.extend((f"file{number}", b"x", "100644") for number in range(256))
    sha = candidate(store, receipt, entries)
    with pytest.raises(AgentSyncError, match="limit|required"):
        export_candidate(store, receipt, sha)


def test_rejects_config_tampering_before_reading_candidate(repository):
    store, receipt, _ = repository
    config = Path(receipt["repository_path"]) / "config"
    config.write_bytes(config.read_bytes() + b"\n[unexpected]\nvalue = changed\n")
    with pytest.raises(AgentSyncError, match="configuration changed"):
        export_candidate(store, receipt, receipt["base_sha"])


@pytest.mark.parametrize(
    "metadata", ["objects/info/alternates", "objects/info/http-alternates", "commondir"]
)
def test_external_object_metadata_is_rejected_before_git_runs(repository, monkeypatch, metadata):
    store, receipt, _ = repository
    forbidden = Path(receipt["repository_path"]) / metadata
    forbidden.parent.mkdir(parents=True, exist_ok=True)
    forbidden.write_text("/host/path/that/must/not/be/read\n", encoding="utf-8")

    def unexpected_git(*args, **kwargs):
        pytest.fail("Git must not run with externally redirected object metadata")

    monkeypatch.setattr(store, "_git", unexpected_git)
    with pytest.raises(AgentSyncError, match="forbidden"):
        export_candidate(store, receipt, receipt["base_sha"])


def test_tampered_blob_content_is_rejected_even_if_git_will_read_it(repository):
    store, receipt, _ = repository
    # A new loose object ensures the test does not depend on clone pack layout.
    sha = candidate(store, receipt, [("solution.py", b"print('safe')\n", "100644")])
    repo = Path(receipt["repository_path"])
    blob = git(store, repo, "rev-parse", sha + ":solution.py")
    content = b"print('evil')\n"
    object_file = repo / "objects" / blob[:2] / blob[2:]
    object_file.chmod(0o600)
    object_file.write_bytes(zlib.compress(b"blob " + str(len(content)).encode() + b"\0" + content))
    with pytest.raises(AgentSyncError, match="integrity"):
        export_candidate(store, receipt, sha)


def test_receipt_cannot_select_arbitrary_host_repository(repository):
    store, receipt, source = repository
    forged = {**receipt, "repository_path": str(source)}
    with pytest.raises(AgentSyncError, match="identity"):
        export_candidate(store, forged, receipt["base_sha"])
    with pytest.raises(AgentSyncError, match="trusted"):
        export_candidate(store, {**receipt, "operation": "unknown"}, receipt["base_sha"])


def test_unbounded_git_output_is_rejected(repository, monkeypatch):
    store, receipt, _ = repository
    original_git = store._git

    def overflowing(repo, *args, **kwargs):
        if args[:2] == ("cat-file", "-t"):
            return 0, b"x" * (4 * 1024 * 1024 + 1)
        return original_git(repo, *args, **kwargs)

    monkeypatch.setattr(store, "_git", overflowing)
    with pytest.raises(AgentSyncError, match="output exceeds"):
        export_candidate(store, receipt, receipt["base_sha"])


def test_export_has_no_checkout_side_effects(repository):
    store, receipt, source = repository
    repo = Path(receipt["repository_path"])
    source_before = (source / "solution.py").read_bytes()
    head_before = git(store, repo, "rev-parse", "HEAD")
    marker = source / "candidate-host-execution-marker"
    code = f"open({str(marker)!r}, 'w').write('must never run')\n".encode()
    sha = candidate(store, receipt, [("solution.py", code, "100644")])
    snapshot = export_candidate(store, receipt, sha)
    assert snapshot.source == code
    assert not marker.exists()
    assert (source / "solution.py").read_bytes() == source_before
    assert git(store, repo, "rev-parse", "HEAD") == head_before
    assert hashlib.sha256(code).hexdigest() != snapshot.input_sha256


def test_invalid_utf8_source_is_rejected_without_compilation(repository):
    store, receipt, _ = repository
    sha = candidate(store, receipt, [("solution.py", b"\xff\xfe", "100644")])
    with pytest.raises(AgentSyncError, match="UTF-8"):
        export_candidate(store, receipt, sha)


def test_duplicate_git_tree_entries_are_rejected(repository):
    store, receipt, _ = repository
    sha = candidate(
        store,
        receipt,
        [
            ("solution.py", b"pass\n", "100644"),
            ("duplicate", b"x", "100644"),
            ("duplicate", b"x", "100644"),
        ],
    )
    with pytest.raises(AgentSyncError, match="Duplicate"):
        export_candidate(store, receipt, sha)


def test_nested_directory_aliases_are_rejected(repository):
    store, receipt, _ = repository
    repo = Path(receipt["repository_path"])
    blob = object_command(store, repo, "hash-object", "-w", "--stdin", data=b"pass\n")
    subtree = object_command(store, repo, "mktree", "-z", data=f"100644 blob {blob}\tx\0".encode())
    tree = object_command(
        store,
        repo,
        "mktree",
        "-z",
        data=(
            f"040000 tree {subtree}\tA\0"
            + f"040000 tree {subtree}\ta\0"
            + f"100644 blob {blob}\tsolution.py\0"
        ).encode(),
    )
    sha = object_command(store, repo, "commit-tree", tree, data=b"nested aliases\n")
    with pytest.raises(AgentSyncError, match="aliases"):
        export_candidate(store, receipt, sha)


def test_tampered_commit_object_is_rejected(repository):
    store, receipt, _ = repository
    sha = candidate(store, receipt, [("solution.py", b"pass\n", "100644")])
    repo = Path(receipt["repository_path"])
    content = store._git(repo, "cat-file", "commit", sha)[1].replace(
        b"isolated candidate", b"tampered candidate"
    )
    object_file = repo / "objects" / sha[:2] / sha[2:]
    object_file.chmod(0o600)
    object_file.write_bytes(
        zlib.compress(b"commit " + str(len(content)).encode() + b"\0" + content)
    )
    with pytest.raises(AgentSyncError, match="integrity"):
        export_candidate(store, receipt, sha)


def test_nested_directory_objects_are_exported_from_git_only(repository):
    store, receipt, _ = repository
    repo = Path(receipt["repository_path"])
    blob = object_command(store, repo, "hash-object", "-w", "--stdin", data=b"pass\n")
    subtree = object_command(
        store, repo, "mktree", "-z", data=f"100644 blob {blob}\tnote\0".encode()
    )
    tree = object_command(
        store,
        repo,
        "mktree",
        "-z",
        data=(f"040000 tree {subtree}\tdocs\0" + f"100644 blob {blob}\tsolution.py\0").encode(),
    )
    sha = object_command(store, repo, "commit-tree", tree, data=b"nested safe\n")
    snapshot = export_candidate(store, receipt, sha)
    assert [entry[0] for entry in snapshot.manifest] == ["docs/note", "solution.py"]
    assert snapshot.source == b"pass\n"


def test_replaced_objects_directory_link_is_rejected_before_git_runs(repository, monkeypatch):
    store, receipt, source = repository
    repo = Path(receipt["repository_path"])
    objects = repo / "objects"
    retained = repo / "retained-objects"
    objects.rename(retained)
    try:
        objects.symlink_to(source, target_is_directory=True)
    except OSError:
        retained.rename(objects)
        pytest.skip("Creating directory symlinks requires unavailable host privileges")

    def unexpected_git(*args, **kwargs):
        pytest.fail("Git must not read a replaced objects directory")

    monkeypatch.setattr(store, "_git", unexpected_git)
    with pytest.raises(AgentSyncError, match="links|reparse"):
        export_candidate(store, receipt, receipt["base_sha"])
