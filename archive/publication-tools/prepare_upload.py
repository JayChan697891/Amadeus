"""Prepare an allowlisted, credential-free GitHub publication payload."""
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "outputs/AgentSync"
WORK = Path(__file__).resolve().parent
VERSION_COMMITS = {"v0.1.0a1": "9b3a8d8", "v0.1.0a2": "27ea8af"}

def git(*args):
    return subprocess.check_output(["git", "-C", str(PROJECT), *args])

def blob_hash(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def build():
    WORK.mkdir(parents=True, exist_ok=True)
    blobs = {}
    snapshots = {}
    trees = {}
    commits = {}
    def add(path, data):
        sha = blob_hash(data)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        blobs[sha] = {"sha": sha, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                      "encoding": "base64" if text is None else "utf-8",
                      "content": base64.b64encode(data).decode() if text is None else text}
        return {"path": path, "mode": "100644", "type": "blob", "sha": sha}
    for version, ref in VERSION_COMMITS.items():
        commits[version] = git("rev-parse", ref).decode().strip()
        trees[version] = git("rev-parse", ref + "^{tree}").decode().strip()
        snapshots[version] = [add(path, git("show", ref + ":" + path))
            for path in git("ls-tree", "-r", "--name-only", ref).decode().splitlines()]
        existing = git("tag", "--list", version).decode().strip()
        if not existing:
            git("tag", version, ref)
        else:
            assert git("rev-parse", version).decode().strip() == commits[version]
    bundle = WORK / "AgentSync-development-history.bundle"
    git("bundle", "create", str(bundle), "--all")
    git("bundle", "verify", str(bundle))
    main = {item["path"]: item for item in snapshots["v0.1.0a2"]}
    asset_rows = []
    for version in VERSION_COMMITS:
        number = version[1:]
        names = [f"agentsync_local-{number}-py3-none-any.whl", f"agentsync_local-{number}.tar.gz",
                 f"AgentSync-{version}-source.zip", f"AgentSync-{version}-SHA256SUMS.txt"]
        for name in names:
            data = (ROOT / "outputs" / name).read_bytes()
            path = f"releases/{version}/{name}"
            main[path] = add(path, data)
            asset_rows.append({"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    main["archive/AgentSync-development-history.bundle"] = add(
        "archive/AgentSync-development-history.bundle", bundle.read_bytes())
    for name in ("finalize.py", "lock_dependencies.py", "verify_a2.py", "probe_claude.py", "probe_codex.py"):
        path = "archive/development-utilities/" + name
        main[path] = add(path, (PROJECT / "work" / name).read_bytes())
    for name in ("AGENTS.md", "WORKFLOW.md"):
        path = "archive/work-session-instructions/" + name
        main[path] = add(path, (ROOT / name).read_bytes())
    recovery = '''# Restore AgentSync after local cleanup

Main contains current v0.1.0a2 source. The versions/v0.1.0a1 and versions/v0.1.0a2 branches
preserve exact source trees. Downloadable artifacts and original checksums are grouped under
releases/v0.1.0a1 and releases/v0.1.0a2. No public GitHub Release object is required to use them.

## Windows

```powershell
git clone https://github.com/JayChan697891/agentsync.git
Set-Location agentsync
py -m venv .venv
& .\\.venv\\Scripts\\python.exe -m pip install -r requirements-dev-lock.txt
& .\\.venv\\Scripts\\python.exe -m pip install -e . --no-deps
& .\\.venv\\Scripts\\python.exe -m pytest -q
& .\\.venv\\Scripts\\python.exe examples\\mcp_clients\\install_codex.py --dry-run
& .\\.venv\\Scripts\\python.exe examples\\mcp_clients\\install_codex.py
```

The original local MCP entry points into the folder that the owner requested to delete.
It is removed only after remote verification; reinstall with the helper after restoring.
The shared user-data database outside the project is preserved; no credentials or runtime DBs
are uploaded. Do not upload or overwrite personal Codex configuration backups.

## Original Git history

`archive/AgentSync-development-history.bundle` preserves original commits and version tags.
Restore it with `git clone archive/AgentSync-development-history.bundle AgentSync-original`.
The published version branches may have GitHub-import commit IDs; their trees must match the
original source tree hashes in PUBLICATION-MANIFEST.json. The bundle preserves original commit IDs.

## Historical utility scripts

`archive/development-utilities/` contains original scratch build/audit helpers, not runtime
entrypoints. They assume their original work/ layout and baseline evidence counts. Prefer the
maintained tests/manual probes and normal build commands for current use. The original user
instructions are archived separately; the owner's 2026-10-19 request explicitly authorized this
publication and conditional local cleanup. Future publication remains subject to owner approval.
'''
    main["RECOVERY.md"] = add("RECOVERY.md", recovery.encode())
    publication = {"date": "2026-10-19", "repository": "JayChan697891/agentsync",
        "authorization": "Owner explicitly requested version-organized upload and local cleanup after complete verification.",
        "original_commits": commits, "original_trees": trees,
        "snapshot_file_counts": {v: len(items) for v, items in snapshots.items()},
        "artifacts": asset_rows,
        "excluded": ["virtual environments", "runtime and test databases", "private configuration backup", "caches and raw scratch logs"],
        "cleanup_scope": "Only this generated local project workspace; external shared AgentSync user data is preserved."}
    main["PUBLICATION-MANIFEST.json"] = add("PUBLICATION-MANIFEST.json", (json.dumps(publication, indent=2)+"\n").encode())
    for name in ("README.md", "README.zh-CN.md"):
        original = blobs[main[name]["sha"]]["content"]
        if name == "README.md":
            note = "> Published archive: versions and checksummed files are in [releases/](releases/). See [RECOVERY.md](RECOVERY.md) and [PUBLICATION-MANIFEST.json](PUBLICATION-MANIFEST.json). Earlier no-publication statements in historical development reports describe the pre-publication checkpoint.\n\n"
            original = original.replace("Nothing has been pushed to a public repository or released publicly.", "The owner authorized this public source archive on 2026-10-19; no model services were called for publication.")
        else:
            note = "> 已按所有者要求公开归档。两版交付文件见 [releases/](releases/)，恢复步骤见 [RECOVERY.md](RECOVERY.md)。历史报告中的“未公开发布”描述的是归档前状态。\n\n"
        main[name] = add(name, note + original if False else (note+original).encode())
    index = "# Versioned deliverables\n\n" + "\n".join(f"- [{v}]({v}/): {len(snapshots[v])} original source files; wheel, source distribution, source ZIP and original SHA256 sums." for v in VERSION_COMMITS) + "\n\nLatest source is at repository root. Exact original source trees are on the versions/* branches. See ../RECOVERY.md for original history and local reinstall.\n"
    main["releases/README.md"] = add("releases/README.md", index.encode())
    for item in main.values():
        assert not any(part in {".venv", "work", ".git", "__pycache__"} for part in Path(item["path"]).parts)
        data = blobs[item["sha"]]
        if data["encoding"] == "utf-8":
            assert not re.search(r"(?:sk-proj-|gh[pousr]_|github_pat_)[A-Za-z0-9_\-]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----", data["content"]), item["path"]
    manifest = {"blobs": blobs, "snapshots": snapshots, "main": list(main.values()), "publication": publication}
    path = WORK / "payload.json"
    path.write_text(json.dumps(manifest, ensure_ascii=True, separators=(",", ":")), encoding="ascii")
    report = {"files": len(main), "unique_blobs": len(blobs), "payload_characters": path.stat().st_size,
              "chunks": (path.stat().st_size + 11999)//12000, "original_trees": trees}
    print(json.dumps(report))

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--chunk":
        serialized = (WORK / "payload.json").read_text(encoding="ascii")
        index = int(sys.argv[2]); sys.stdout.write(serialized[index*12000:(index+1)*12000])
    else:
        build()
