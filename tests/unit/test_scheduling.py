"""Planning-only snapshot rules; no task claim, execution, or authorization evidence."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest

from agentsync.errors import AgentSyncError
from agentsync.scheduling import plan_tasks


def task(task_id="task", **changes):
    return {
        "id": task_id,
        "project_id": "project",
        "title": "Task",
        "description": "",
        "priority": 0,
        "status": "pending",
        "version": 1,
        "owner_session_id": None,
        "result": "",
        "dependencies": [],
        "created_at": 10.0,
        "updated_at": 10.0,
        "lease_expires_at": None,
        "assigned_agent_id": None,
        "assignment_expires_at": None,
        "latest_review": None,
        **changes,
    }


def plan(rows, **changes):
    return plan_tasks({"tasks": rows}, project_id="project", agent_id="agent", now=20.0, **changes)


def test_public_tracer_returns_task_and_version_without_execution_authority():
    result = plan([task(version=7)])
    assert [(item.task_id, item.expected_version) for item in result.candidates] == [("task", 7)]
    assert result.scope == "planning_only" and result.execution_connected is False
    assert result.snapshot_freshness == "unverified" and result.capability_matching == "unverified"


def test_priority_then_created_at_then_id_sort_is_input_order_independent():
    rows = [
        task("b", priority=1),
        task("a", priority=1),
        task("older", priority=1, created_at=9.0),
        task("high", priority=2),
    ]
    expected = ["high", "older", "a", "b"]
    for snapshot in (rows, list(reversed(rows))):
        assert [item.task_id for item in plan(snapshot).candidates] == expected


def test_dependencies_require_completed_and_missing_is_never_completed():
    for status in (
        "pending",
        "claimed",
        "running",
        "handoff",
        "review",
        "blocked",
        "failed",
        "cancelled",
    ):
        result = plan(
            [task("dependent", dependencies=["prerequisite"]), task("prerequisite", status=status)]
        )
        assert "dependent" not in {item.task_id for item in result.candidates}
    assert plan([task(dependencies=["missing"])]).candidates == ()
    result = plan(
        [task("dependent", dependencies=["prerequisite"]), task("prerequisite", status="completed")]
    )
    assert [item.task_id for item in result.candidates] == ["dependent"]


def test_only_pending_rows_are_candidates():
    rows = [
        task(status, status=status)
        for status in (
            "claimed",
            "running",
            "handoff",
            "review",
            "blocked",
            "failed",
            "cancelled",
            "completed",
        )
    ]
    assert plan(rows).candidates == ()


@pytest.mark.parametrize(
    "assigned,expires,eligible",
    [
        (None, None, True),
        ("agent", 25.0, True),
        ("other", 25.0, False),
        ("other", 20.0, True),
        ("other", 19.0, True),
    ],
)
def test_explicit_reservation_expiry_matches_core_boundary(assigned, expires, eligible):
    result = plan([task(assigned_agent_id=assigned, assignment_expires_at=expires)])
    assert bool(result.candidates) is eligible


def test_recommending_parent_does_not_pretend_it_has_completed():
    result = plan([task("child", dependencies=["parent"], priority=100), task("parent")])
    assert [item.task_id for item in result.candidates] == ["parent"]


@pytest.mark.parametrize(
    "change",
    [
        {"project_id": "other"},
        {"id": ""},
        {"status": "unknown"},
        {"priority": True},
        {"version": 1.0},
        {"created_at": float("nan")},
        {"updated_at": True},
        {"lease_expires_at": float("inf")},
        {"dependencies": ["parent", "parent"]},
        {"dependencies": "parent"},
        {"assigned_agent_id": "other"},
        {"assignment_expires_at": 25.0},
    ],
)
def test_invalid_snapshot_fields_are_rejected_with_static_errors(change):
    with pytest.raises(AgentSyncError) as exc:
        plan([task(**change)])
    assert exc.value.code == "invalid_snapshot"
    assert "other" not in exc.value.message


@pytest.mark.parametrize(
    "options",
    [
        {"limit": True},
        {"limit": 0},
        {"limit": 101},
        {"now": float("inf")},
        {"now": True},
    ],
)
def test_invalid_planning_options_are_rejected(options):
    values = {"project_id": "project", "agent_id": "agent", "now": 20.0, **options}
    with pytest.raises(AgentSyncError):
        plan_tasks({"tasks": []}, **values)


def test_cycles_duplicate_ids_and_oversized_snapshots_are_invalid():
    for rows in (
        [task("a", dependencies=["b"]), task("b", dependencies=["a"])],
        [task(), task()],
        [task(str(number)) for number in range(4097)],
    ):
        with pytest.raises(AgentSyncError):
            plan(rows)


def test_snapshot_and_returned_plan_do_not_share_mutable_task_state():
    rows = [task("a"), task("b")]
    before = deepcopy(rows)
    result = plan(rows, limit=1)
    assert rows == before and len(result.candidates) == 1
    rows[0]["id"] = "changed"
    assert result.candidates[0].task_id == "a"
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        result.candidates[0].expected_version = 9
    with pytest.raises((TypeError, ValueError)):
        replace(result, execution_connected=True)


def test_deep_dependency_chain_is_bounded_and_does_not_use_recursion():
    rows = [task("0")]
    rows.extend(task(str(number), dependencies=[str(number - 1)]) for number in range(1, 2000))
    assert [item.task_id for item in plan(rows).candidates] == ["0"]


def test_pending_rows_with_existing_ownership_are_not_recommended():
    assert plan([task(owner_session_id="session")]).candidates == ()
    assert plan([task(lease_expires_at=25.0)]).candidates == ()


def test_optional_capability_filter_is_exact_conjunctive_and_does_not_mutate_inputs():
    rows = [task("both"), task("case"), task("free")]
    requirements = {"both": ("Python", "tests"), "case": ("python",), "free": ()}
    before = deepcopy((rows, requirements))
    assert len(plan(rows).candidates) == 3
    assert plan(rows).capability_filter == "not_requested"
    result = plan(rows, required_capabilities=requirements, agent_capabilities=("Python", "tests"))
    assert [item.task_id for item in result.candidates] == ["both", "free"]
    assert result.capability_filter == "caller_required_self_reported"
    assert result.capability_matching == "unverified"
    assert [item.task_id for item in plan(rows, required_capabilities=requirements).candidates] == [
        "free"
    ]
    assert (rows, requirements) == before
    requirements["both"] = ("changed",)
    assert [item.task_id for item in result.candidates] == ["both", "free"]


def test_requirements_must_cover_every_task_including_completed_and_blocked():
    rows = [task(), task("completed", status="completed"), task("blocked", status="blocked")]
    complete = {row["id"]: () for row in rows}
    assert [item.task_id for item in plan(rows, required_capabilities=complete).candidates] == [
        "task"
    ]
    for invalid in ({}, {"task": ()}, {**complete, "stale": ()}):
        with pytest.raises(AgentSyncError) as error:
            plan(rows, required_capabilities=invalid)
        assert error.value.code == "invalid_snapshot"


def test_capability_token_container_identifier_and_uniqueness_bounds_are_strict():
    invalid_tokens = (
        [],
        "Python",
        ("same", "same"),
        ("",),
        ("bad\n",),
        ("\x00",),
        ("\ud800",),
        ("你" * 67,),
        (True,),
        tuple(str(index) for index in range(129)),
    )
    for tokens in invalid_tokens:
        for options in (
            {"required_capabilities": {"task": tokens}},
            {"required_capabilities": {"task": ()}, "agent_capabilities": tokens},
        ):
            with pytest.raises(AgentSyncError) as error:
                plan([task()], **options)
            assert error.value.code == "invalid_snapshot"
    for requirements in ([], {"\ud800": ()}):
        with pytest.raises(AgentSyncError):
            plan([task()], required_capabilities=requirements)
    boundary = tuple(["x" * 200] + [str(index) for index in range(127)])
    assert plan(
        [task()], required_capabilities={"task": boundary}, agent_capabilities=boundary
    ).candidates


def test_capability_requirement_total_and_map_bounds_are_checked():
    tokens = tuple(str(index) for index in range(128))
    rows = [task(str(index)) for index in range(129)]
    requirements = {row["id"]: tokens for row in rows}
    with pytest.raises(AgentSyncError):
        plan(rows, required_capabilities=requirements, agent_capabilities=tokens)
    rows.pop()
    requirements.pop("128")
    assert (
        len(
            plan(
                rows, required_capabilities=requirements, agent_capabilities=tokens, limit=100
            ).candidates
        )
        == 100
    )
    with pytest.raises(AgentSyncError):
        plan([], required_capabilities={str(index): () for index in range(4097)})


def test_capability_mismatch_does_not_remove_dependency_nodes_or_hide_cycles():
    rows = [task("parent", status="completed"), task("child", dependencies=["parent"])]
    requirements = {"parent": ("unavailable",), "child": ()}
    assert [item.task_id for item in plan(rows, required_capabilities=requirements).candidates] == [
        "child"
    ]
    rows[0]["status"] = "pending"
    assert plan(rows, required_capabilities=requirements).candidates == ()
    rows[0]["dependencies"] = ["child"]
    with pytest.raises(AgentSyncError):
        plan(rows, required_capabilities=requirements)


def test_capability_filter_precedes_limit_and_keeps_deterministic_priority_order():
    rows = [task(f"high-{index}", priority=100) for index in range(105)]
    rows.extend([task("b"), task("a"), task("first", priority=1)])
    requirements = {row["id"]: ("unavailable",) if row["priority"] == 100 else () for row in rows}
    for source in (rows, list(reversed(rows))):
        result = plan(source, required_capabilities=requirements, limit=2)
        assert [item.task_id for item in result.candidates] == ["first", "a"]
