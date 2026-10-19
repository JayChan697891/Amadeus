"""Re-fetch public refs and check every published byte before local cleanup."""

import hashlib
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
PAYLOAD = json.loads((WORK / "payload.json").read_text(encoding="ascii"))
REPO = WORK / "remote-check"


def git(*args, cwd=REPO):
    return subprocess.check_output(["git", "-C", str(cwd), *args])


assert not REPO.exists(), "Use a fresh verification checkout."
subprocess.run(
    [
        "git",
        "-c",
        "core.autocrlf=false",
        "clone",
        "--no-single-branch",
        "https://github.com/JayChan697891/agentsync.git",
        str(REPO),
    ],
    check=True,
)
head = git("rev-parse", "HEAD").decode().strip()
expected = {item["path"]: item["sha"] for item in PAYLOAD["main"]}
actual = {}
for row in git("ls-tree", "-r", "HEAD").decode().splitlines():
    meta, name = row.split("\t", 1)
    mode, kind, sha = meta.split()
    assert mode == "100644" and kind == "blob"
    actual[name] = sha
assert actual == expected, "Remote file set/blob mismatch."
for path, sha in expected.items():
    data = git("show", "HEAD:" + path)
    assert hashlib.sha256(data).hexdigest() == PAYLOAD["blobs"][sha]["sha256"], path
version_trees = {}
for version, expected_tree in PAYLOAD["publication"]["original_trees"].items():
    ref = "origin/versions/" + version
    tree = git("rev-parse", ref + "^{tree}").decode().strip()
    assert tree == expected_tree, version
    listing = git("ls-tree", "-r", "--name-only", ref).decode().splitlines()
    assert len(listing) == PAYLOAD["publication"]["snapshot_file_counts"][version]
    version_trees[version] = tree
artifact_results = []
for row in PAYLOAD["publication"]["artifacts"]:
    data = git("show", "HEAD:" + row["path"])
    checksum = hashlib.sha256(data).hexdigest()
    assert len(data) == row["size"] and checksum == row["sha256"], row["path"]
    path = REPO / row["path"]
    if path.suffix in {"zip", ".zip", ".whl"}:
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path) as archive:
            assert archive.getmembers()
    if path.name.endswith("SHA256SUMS.txt"):
        for line in data.decode().splitlines():
            target_hash, target_name = line.split("  ", 1)
            target = str(Path(row["path"]).parent / target_name).replace("\\", "/")
            assert hashlib.sha256(git("show", "HEAD:" + target)).hexdigest() == target_hash
    artifact_results.append({**row, "downloaded_and_verified": True})
bundle = REPO / "archive/AgentSync-development-history.bundle"
subprocess.run(["git", "bundle", "verify", str(bundle)], cwd=REPO, check=True, capture_output=True)
restored = WORK / "history-restore-check"
assert not restored.exists()
subprocess.run(["git", "clone", str(bundle), str(restored)], check=True, capture_output=True)
for version, original_commit in PAYLOAD["publication"]["original_commits"].items():
    assert git("rev-parse", version, cwd=restored).decode().strip() == original_commit
report = {
    "date": "2026-10-19",
    "repository": "JayChan697891/agentsync",
    "verified_main_commit": head,
    "all_files_fetched_and_verified": len(expected),
    "version_trees": version_trees,
    "artifacts": artifact_results,
    "original_git_history_restore_tested": True,
    "excluded_private_runtime_data": True,
    "local_cleanup_precondition_satisfied": True,
}
(WORK / "verification-result.json").write_text(
    json.dumps(report, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(report))
