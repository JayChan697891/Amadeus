"""Explicit owner setup for legacy scenarios; no implicit permission changes."""


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
