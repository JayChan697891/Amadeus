"""Opt-in trusted-host Claude launcher; never human/Core authorization.

Construction launches nothing. Every actual model execution needs fresh human
authorization and the existing cost/isolation gates; attaching this factory
authorizes none. Managed hooks may still run, managed MCP may reject these flags,
and home/config can supply credentials/providers. No sandbox, subscription-only
billing, tool restriction or actual-client compatibility is established here.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.claude_invocation import (
    ClaudeHostProfile,
    _environment,
    prepare_invocation,
)
from agentsync.adapters.launch_context import LaunchContext
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError


@dataclass(frozen=True, slots=True, init=False)
class ClaudeProcessFactory:
    """Fresh pinned preparation followed by one context-checked owned capture.

    Profile/environment are immutable copies; only explicit filtered variables
    reach the process. Threaded preparation may finish after a stop, but context
    entry rechecks it. Already scheduled OS creation, server cancellation and
    descendant cleanup retain the shared lifecycle's uncertainty.
    """

    _profile: ClaudeHostProfile = field(repr=False)
    _environment: tuple[tuple[str, str], ...] = field(repr=False)

    def __init__(self, profile: ClaudeHostProfile, *, environment: dict[str, str]) -> None:
        if type(profile) is not ClaudeHostProfile:
            raise AgentSyncError("validation_error", "Invalid Claude process factory input.")
        object.__setattr__(self, "_profile", replace(profile))
        object.__setattr__(self, "_environment", _environment(environment))

    async def __call__(self, task: AdapterTask, context: LaunchContext) -> CapturedProcess:
        if type(context) is not LaunchContext:
            raise AgentSyncError("validation_error", "Adapter-issued launch context required.")
        plan = await context.wait_before_start(
            task,
            lambda: asyncio.to_thread(
                prepare_invocation, self._profile, task, environment=dict(self._environment)
            ),
        )
        return await context.start(
            task,
            plan.argv,
            cwd=plan.cwd,
            stdin_text=plan.stdin_text,
            timeout_seconds=plan.timeout_seconds,
            output_limit=plan.output_limit,
            env=plan.child_env(),
        )
