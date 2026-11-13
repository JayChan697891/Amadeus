"""Explicit owner setup for legacy scenarios; no implicit permission changes."""

import subprocess


def owner_grant(core, project, actor, roles=("worker", "reviewer")):
    """Deliberately grant only the requested legacy test roles through owner API."""
    members = core.execute_owner("list_members", {**project, "limit": 100, "offset": 0})["members"]
    current = next(member for member in members if member["agent_id"] == actor["agent_id"])
    if set(current["roles"]) != set(roles):
        core.execute_owner(
            "set_agent_roles",
            {
                **project,
                "agent_id": actor["agent_id"],
                "roles": list(roles),
                "expected_version": current["version"],
                "request_id": "legacy-explicit-grant-"
                + actor["agent_id"]
                + "-"
                + str(current["version"]),
            },
        )


def drop_candidate_queue_schema(db):
    """Remove schema additions from v10 onward for older migration fixtures."""
    drop_mock_workflow_schema(db)
    db.execute("DROP TABLE IF EXISTS project_usage")
    db.execute("DROP TABLE IF EXISTS task_verification_requests")
    db.execute("DROP TABLE IF EXISTS task_verifications")
    db.execute("DROP TABLE IF EXISTS candidate_executions")
    db.execute("DROP TABLE IF EXISTS candidate_intent_abandonments")
    db.execute("DROP TABLE IF EXISTS candidate_execution_intents")
    db.execute("DROP TABLE IF EXISTS candidate_claim_recoveries")
    db.execute("DROP TABLE IF EXISTS candidate_verification_claims")
    db.execute("DROP TABLE IF EXISTS candidate_verification_requests")
    db.execute("DROP TABLE IF EXISTS candidate_verification_jobs")
    indexes = db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND (name LIKE 'candidate_queue_%' OR name LIKE 'candidate_claim_%' OR name LIKE 'candidate_intent_%')"
    ).fetchall()
    for row in indexes:
        db.execute('DROP INDEX "' + row[0].replace('"', '""') + '"')


def drop_mock_workflow_schema(db):
    for table in ("requests", "attempts", "tasks", "members"):
        db.execute(f"DROP TABLE IF EXISTS mock_workflow_{table}")
    db.execute("DROP TABLE IF EXISTS mock_workflows")


def run_owned_processes(commands, *, env=None, timeout=30):
    """Run trusted local test commands; reap only handles created by this call."""
    processes = []
    original_error = None
    try:
        for command in commands:
            processes.append(
                subprocess.Popen(
                    command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
            )
        return [(process.communicate(timeout=timeout), process.returncode) for process in processes]
    except BaseException as exc:
        original_error = exc
        raise
    finally:
        cleanup_errors = []
        for process in processes:
            try:
                if process.poll() is None:
                    process.kill()
            except ProcessLookupError:
                pass  # Parent exited between poll and kill; still reap below.
            except BaseException as exc:
                cleanup_errors.append(exc)
        for process in processes:
            try:
                process.communicate(timeout=timeout)
            except BaseException as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            errors = ([original_error] if original_error is not None else []) + cleanup_errors
            raise BaseExceptionGroup("Owned test process cleanup failed", errors) from None
