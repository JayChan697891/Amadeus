"""Observe a structured handoff through the native Codex MCP host without inference."""

import argparse
import hashlib
import json
import runpy
import sys
import tempfile
import traceback
from contextlib import contextmanager
from importlib import metadata
from pathlib import Path

import agentsync
from agentsync import cli
from agentsync.core.service import Core

DEBUG = Path("D:/agentsync-debug")
PREVIEW = DEBUG / "m121p"
VERSION = "0.3.0a121"
RUNTIME_COMMIT = "4b824949e60492e11756586c3a6ecd5a5f7811d8"
BINARY_SHA = "dce685d569526ef4712fa82d20ff20e1309baad5fcd34215e1126698f611242f"
HELPER_SHA = "59182e9f6ec9b61b10830be934df355e9c44baa9a89567d2574a2c5796db61e6"
WHEEL_SHA = "84eebc0b5d32c4f58f6638711d145f5919abc55cbc26eba58ed9173fe2808d71"
MEMBERS_SHA = "d51bb40232073acf69b4c9748eac2ffd674404c767dcbee8ab67ab237d88dea6"
METHODS = frozenset(
    {"initialize", "initialized", "thread/start", "mcpServerStatus/list", "mcpServer/tool/call"}
)
TOOLS = frozenset(
    {
        "create_project",
        "register_agent",
        "publish_context",
        "get_context",
        "create_task",
        "list_tasks",
        "claim_task",
        "update_task",
        "submit_handoff",
        "get_handoff",
        "resolve_handoff",
        "acquire_file_lock",
        "release_file_lock",
    }
)
LOCK_PATH = "lock-fixture.txt"
LOCK_CONTENT = b"Native MCP coordination metadata only.\n"
CONTEXT = "Continue from the original checkpoint."
CONTEXT_NEXT = "Later context; the saved handoff must retain version one."
RESULT = "The recipient continued the pinned handoff and submitted text for review."


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def verify_runtime():
    install = PREVIEW / "w"
    assert sys.platform == "win32" and sys.version_info[:3] == (3, 12, 16)
    assert sys.flags.isolated and sys.dont_write_bytecode and __debug__
    assert Path(sys.executable).resolve() == install / "Scripts/python.exe"
    assert Path(sys.prefix).resolve() == install
    site = install / "Lib/site-packages"
    assert Path(agentsync.__file__).resolve() == site / "agentsync/__init__.py"
    assert Path(cli.__file__).resolve() == site / "agentsync/cli.py"
    dist = metadata.distribution("agentsync-local")
    assert dist.version == agentsync.__version__ == VERSION
    assert Path(dist.locate_file("")).resolve() == site
    wheel = PREVIEW / f"dist/agentsync_local-{VERSION}-py3-none-any.whl"
    members = PREVIEW / "run/runtime-members.json"
    assert sha(wheel) == WHEEL_SHA and sha(members) == MEMBERS_SHA
    direct = json.loads(dist.read_text("direct_url.json"))
    assert direct["url"] == wheel.resolve().as_uri() and "dir_info" not in direct
    assert direct["archive_info"]["hashes"]["sha256"] == WHEEL_SHA
    actual = {
        path.relative_to(site).as_posix(): sha(path)
        for path in (site / "agentsync").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert len(actual) == 97 and actual == json.loads(members.read_bytes())
    return {
        "version": VERSION,
        "commit": RUNTIME_COMMIT,
        "runtime_members": len(actual),
        "wheel_sha256": WHEEL_SHA,
        "runtime_members_sha256": MEMBERS_SHA,
    }


@contextmanager
def native_host(helpers, binary, workspace, report, label):
    host = helpers["NativeHost"](binary, workspace / "data", workspace / f"{label}.private.log")
    observation = {"role": label, "pid": host.proc.pid}
    report["native_hosts"].append(observation)
    try:
        yield host
    finally:
        operation_error = sys.exception()
        try:
            host.close()
        except Exception as exc:
            observation["cleanup_error_type"] = type(exc).__name__
            if isinstance(exc, helpers["NativeHostBlocked"]):
                observation["cleanup_reason"] = exc.reason
            if operation_error is None:
                raise
        finally:
            observation.update(
                exit_code=host.proc.returncode,
                close_mode=host.close_mode,
                unexpected_turn=host.unexpected_turn,
                mcp_child_pids=sorted(int(marker.name) for marker in host.mcp_pids.iterdir()),
                mcp_children_ended=getattr(host, "mcp_children_ended", None),
            )
    assert observation["exit_code"] == 0 and observation["close_mode"] == "stdin_eof"
    assert not observation["unexpected_turn"]
    assert observation["mcp_children_ended"] == len(observation["mcp_child_pids"]) > 0


def tool(host, tid, operation, fields, denied=None):
    assert operation in TOOLS
    value = host.call(tid, operation, fields, expect_ok=denied is None)
    if denied is not None:
        assert value["code"] == denied
    return value


def audit_observations(core, owner, expected, secrets):
    result = core.execute_owner("list_audit", {**owner, "limit": 100})
    assert result["has_more"] is False
    events = result["events"]
    serialized = json.dumps(events)
    assert all(secret not in serialized for secret in secrets)
    observations = []
    for request, (actor, fields) in expected.items():
        pin = digest(request)
        (event,) = (event for event in events if event["request_id_digest"] == pin)
        assert event["project_id"] == owner["project_id"] and event["actor_kind"] == "agent"
        for field, value in fields.items():
            assert event[field] == value
        observations.append(
            {
                "request": request,
                "request_sha256": pin,
                "actor": actor,
                **{
                    name: event[name]
                    for name in (
                        "event_id",
                        "operation",
                        "outcome",
                        "code",
                        "target_id",
                        "pre_version",
                        "post_version",
                    )
                },
            }
        )
    return observations


def run_handoff(helpers, binary, workspace, report, secrets):
    project_root = workspace / "project"
    project_root.mkdir()
    with (project_root / LOCK_PATH).open("xb") as stream:
        stream.write(LOCK_CONTENT)
    statuses = report["mcp_status_checks"]
    expected_audit = {}

    def start(host, label):
        report["phase"] = f"connect_{label}"
        tid, status, tools = host.start(statuses.setdefault(label, []))
        assert status == "connected" and TOOLS <= set(tools)
        return tid

    with native_host(helpers, binary, workspace, report, "initial") as host:
        host.initialize()
        threads = {actor: start(host, actor) for actor in ("A", "B")}
        assert threads["A"] != threads["B"]
        report["phase"] = "create_project_and_identities"
        owner = tool(
            host,
            threads["A"],
            "create_project",
            {
                "name": "Native structured handoff fixture",
                "root_path": str(project_root),
            },
        )
        secrets.add(owner["admin_token"])
        sessions = {}
        for actor, tid in threads.items():
            session = tool(host, tid, "register_agent", {**owner, "name": f"Handoff {actor}"})
            secrets.add(session["session_token"])
            sessions[actor] = session
        assert all(
            len({s[key] for s in sessions.values()}) == 2 for key in ("agent_id", "session_id")
        )
        report.update(project_id=owner["project_id"], distinct_identities=True, initial_threads=2)
        auth = {
            actor: {
                "project_id": owner["project_id"],
                **{name: session[name] for name in ("session_id", "session_token")},
            }
            for actor, session in sessions.items()
        }
        core = Core(workspace / "data")
        members = core.execute_owner("list_members", {**owner, "limit": 2})["members"]
        assert len(members) == 2 and all(member["roles"] == ["viewer"] for member in members)
        for actor, session in sessions.items():
            member = next(row for row in members if row["agent_id"] == session["agent_id"])
            grant = core.execute_owner(
                "set_agent_roles",
                {
                    **owner,
                    "agent_id": member["agent_id"],
                    "roles": ["worker"],
                    "expected_version": member["version"],
                    "request_id": f"grant-worker-{actor}",
                },
            )
            assert grant["roles"] == ["worker"]
        report["owner_granted_roles"] = {"A": ["worker"], "B": ["worker"]}

        def call(actor, operation, *, request=None, denied=None, **fields):
            report["phase"] = request or operation
            if request is not None:
                fields["request_id"] = request
            reply = tool(host, threads[actor], operation, {**auth[actor], **fields}, denied)
            if request is not None:
                # Core audit reads the literal version field. Handoffs return task_version.
                post_version = None
                if denied is None and operation not in ("submit_handoff", "resolve_handoff"):
                    post_version = reply["version"]
                expected_audit[request] = (
                    actor,
                    {
                        "actor_id": sessions[actor]["agent_id"],
                        "operation": operation,
                        "outcome": "denied" if denied else "success",
                        "code": denied or "ok",
                        "target_id": None if denied else reply["id"],
                        "pre_version": fields.get("expected_version"),
                        "post_version": post_version,
                    },
                )
            if denied is not None:
                report["denials"][request] = reply["code"]
            return reply

        def observe(stage, task, status, version, actor=None):
            assert task["id"] == task_id and task["project_id"] == owner["project_id"]
            assert (task["status"], task["version"]) == (status, version)
            assert task["owner_session_id"] == (sessions[actor]["session_id"] if actor else None)
            assert task["task_verification"] == "unverified" and task["verification"] is None
            report["task_observations"].append(
                {
                    "stage": stage,
                    "status": task["status"],
                    "version": task["version"],
                    "owner": actor,
                    "verification": task["task_verification"],
                }
            )

        context = call(
            "A",
            "publish_context",
            request="context-v1",
            kind="progress",
            title="Handoff checkpoint",
            content=CONTEXT,
        )
        assert context["content"] == CONTEXT and context["version"] == 1
        assert context["author_agent_id"] == sessions["A"]["agent_id"]
        pin = {"context_id": context["id"], "version": context["version"]}
        task = call("A", "create_task", request="create-task", title="Continue saved work")
        task_id = report["task_id"] = task["id"]
        observe("created", task, "pending", 1)
        claimed = call(
            "A", "claim_task", request="sender-claim", task_id=task_id, expected_version=1
        )
        sender_lease = claimed["lease_token"]
        secrets.add(sender_lease)
        observe("sender_claimed", claimed, "claimed", 2, "A")
        running = call(
            "A",
            "update_task",
            request="sender-run",
            task_id=task_id,
            expected_version=2,
            lease_token=sender_lease,
            status="running",
        )
        observe("sender_running", running, "running", 3, "A")
        handoff = call(
            "A",
            "submit_handoff",
            request="handoff-submit",
            task_id=task_id,
            lease_token=sender_lease,
            expected_version=3,
            target_agent_id=sessions["B"]["agent_id"],
            package={"summary": "Continue from the fixed context", "context_refs": [pin]},
        )
        handoff_id = report["handoff_id"] = handoff["id"]
        assert handoff["status"] == "pending" and handoff["task_version"] == 4
        assert handoff["task_id"] == task_id and handoff["contexts"] == [context]
        assert handoff["sender_agent_id"] == sessions["A"]["agent_id"]
        assert handoff["recipient_agent_id"] == sessions["B"]["agent_id"]
        observe("handoff_submitted", call("B", "list_tasks")["tasks"][0], "handoff", 4)

        latest = call(
            "A",
            "publish_context",
            request="context-v2",
            kind="progress",
            title="Handoff checkpoint",
            content=CONTEXT_NEXT,
            context_id=pin["context_id"],
            expected_version=1,
        )
        assert latest["version"] == 2 and latest["content"] == CONTEXT_NEXT
        assert call("B", "get_context", **pin) == context
        assert call("B", "get_context", context_id=pin["context_id"]) == latest
        assert call("B", "get_handoff", handoff_id=handoff_id) == handoff
        report["context"] = {
            **pin,
            "pinned_sha256": digest(context["content"]),
            "latest_version": latest["version"],
            "latest_sha256": digest(latest["content"]),
        }
        call(
            "A",
            "update_task",
            request="old-sender-lease",
            denied="lease_denied",
            task_id=task_id,
            expected_version=4,
            lease_token=sender_lease,
            status="review",
            result="Denied fixture",
        )
        call(
            "A",
            "resolve_handoff",
            request="nonrecipient-resolve",
            denied="handoff_denied",
            handoff_id=handoff_id,
            expected_version=4,
            accept=True,
        )
        assert call("B", "get_handoff", handoff_id=handoff_id) == handoff
        accepted = call(
            "B",
            "resolve_handoff",
            request="recipient-accept",
            handoff_id=handoff_id,
            expected_version=4,
            accept=True,
        )
        assert accepted["id"] == handoff_id and accepted["status"] == "accepted"
        assert accepted["task_version"] == 5 and accepted["contexts"] == [context]
        assert accepted["package"]["context_refs"] == [pin]
        assert accepted["assigned_agent_id"] == sessions["B"]["agent_id"]
        reserved = call("B", "list_tasks")["tasks"][0]
        assert reserved["assigned_agent_id"] == sessions["B"]["agent_id"]
        observe("recipient_reserved", reserved, "pending", 5)
        report["handoff"] = {
            "status": accepted["status"],
            "sender": "A",
            "recipient": "B",
            "submitted_task_version": handoff["task_version"],
            "accepted_task_version": accepted["task_version"],
        }
        call(
            "A",
            "claim_task",
            request="nonrecipient-claim",
            denied="assignment_denied",
            task_id=task_id,
            expected_version=5,
        )
        claimed = call(
            "B", "claim_task", request="recipient-claim", task_id=task_id, expected_version=5
        )
        recipient_lease = claimed["lease_token"]
        secrets.add(recipient_lease)
        assert sender_lease and recipient_lease and recipient_lease != sender_lease
        report["recipient_new_lease"] = True
        observe("recipient_claimed", claimed, "claimed", 6, "B")
        running = call(
            "B",
            "update_task",
            request="recipient-run",
            task_id=task_id,
            expected_version=6,
            lease_token=recipient_lease,
            status="running",
        )
        observe("recipient_running", running, "running", 7, "B")
        review = call(
            "B",
            "update_task",
            request="recipient-submit",
            task_id=task_id,
            expected_version=7,
            lease_token=recipient_lease,
            status="review",
            result=RESULT,
        )
        assert review["result"] == RESULT and review["latest_review"] is None
        observe("recipient_submitted", review, "review", 8, "B")
        report["result_sha256"] = digest(review["result"])

        locks = report["lock_observations"]
        for actor in ("A", "B"):
            lock = call(actor, "acquire_file_lock", request=f"lock-acquire-{actor}", path=LOCK_PATH)
            token = lock["lease_token"]
            secrets.add(token)
            assert lock["owner_agent_id"] == sessions[actor]["agent_id"]
            assert (
                lock["owner_session_id"] == sessions[actor]["session_id"]
                and lock["path"] == LOCK_PATH
            )
            assert (lock["status"], lock["version"]) == ("active", 1)
            if locks:
                assert lock["id"] != locks[0]["lock_id"]
            locks.append({"actor": actor, "lock_id": lock["id"], "status": "active", "version": 1})
            if actor == "A":
                call(
                    "B",
                    "acquire_file_lock",
                    request="lock-contended",
                    denied="lock_busy",
                    path=LOCK_PATH,
                )
            released = call(
                actor,
                "release_file_lock",
                request=f"lock-release-{actor}",
                lock_id=lock["id"],
                lease_token=token,
                expected_version=1,
            )
            assert released["id"] == lock["id"] and (released["status"], released["version"]) == (
                "released",
                2,
            )
            locks.append(
                {"actor": actor, "lock_id": released["id"], "status": "released", "version": 2}
            )
        assert (project_root / LOCK_PATH).read_bytes() == LOCK_CONTENT
        report.update(
            lock_scope="file metadata only", lock_path=LOCK_PATH, lock_file_unchanged=True
        )

    with native_host(helpers, binary, workspace, report, "reopened") as host:
        host.initialize()
        thread = start(host, "reopened_B")
        report["phase"] = "reopen_same_handoff"
        assert tool(host, thread, "list_tasks", auth["B"])["tasks"] == [review]
        assert (
            tool(host, thread, "get_handoff", {**auth["B"], "handoff_id": handoff_id}) == accepted
        )
        assert tool(host, thread, "get_context", {**auth["B"], **pin}) == context
        observe("reopened", review, "review", 8, "B")
    report["phase"] = "owner_audit"
    report["audit_observations"] = audit_observations(core, owner, expected_audit, secrets)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-binary", required=True, type=Path)
    parser.add_argument("--scratch-parent", default=DEBUG / "m121-handoff-preparation", type=Path)
    args = parser.parse_args()
    scratch = args.scratch_parent.resolve(strict=True)
    assert scratch.is_relative_to(DEBUG.resolve(strict=True))
    workspace = Path(tempfile.mkdtemp(prefix="native-handoff-", dir=scratch))
    report = {
        "status": "blocked",
        "phase": "preflight",
        "desktop_ui_tested": False,
        "global_configuration_modified": False,
        "inference_requests": 0,
        "inference_turns": None,
        "rpc_method_allowlist": sorted(METHODS),
        "model_or_candidate_execution_requested": False,
        "scope": "Native Codex MCP structured handoff and metadata locks, review remains unverified",
        "probe_sha256": sha(Path(__file__)),
        "native_hosts": [],
        "mcp_status_checks": {},
        "task_observations": [],
        "denials": {},
        "lock_observations": [],
    }
    secrets = set()
    print(f"Probe evidence directory {workspace}", file=sys.stderr, flush=True)
    try:
        before = verify_runtime()
        report["installed_runtime"] = before
        binary = args.codex_binary.resolve(strict=True)
        assert binary.suffix.lower() == ".exe" and sha(binary) == BINARY_SHA
        helper = Path(__file__).with_name("probe_codex_collaboration.py")
        assert sha(helper) == HELPER_SHA
        helpers = runpy.run_path(str(helper))
        assert helpers["METHODS"] == METHODS
        report.update(codex_binary_sha256=BINARY_SHA, native_helper_sha256=HELPER_SHA)
        try:
            run_handoff(helpers, binary, workspace, report, secrets)
        except helpers["NativeHostBlocked"] as exc:
            report.update(
                error_type=type(exc).__name__,
                blocked_method=exc.method,
                reason=exc.reason,
                rpc_code=exc.rpc_code,
            )
            with (workspace / "failure.private.log").open("a", encoding="utf-8") as stream:
                traceback.print_exc(file=stream)
        else:
            report.update(status="passed_scoped", phase="complete", inference_turns=0)
        finally:
            assert verify_runtime() == before
            report["installed_runtime_unchanged"] = True
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status="blocked", error_type=type(exc).__name__)
        with (workspace / "failure.private.log").open("a", encoding="utf-8") as stream:
            traceback.print_exc(file=stream)

    payload = json.dumps(report, indent=2)
    if any(secret in payload for secret in secrets):
        payload = json.dumps(
            {"status": "blocked", "reason": "public_report_contains_fixture_secret"}
        )
        report["status"] = "blocked"
    with (workspace / "result.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload + "\n")
    print(payload, flush=True)
    return int(report["status"] != "passed_scoped")


if __name__ == "__main__":
    raise SystemExit(main())
