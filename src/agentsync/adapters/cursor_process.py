"""Opt-in trusted-host Cursor factory for the terminal JSON adapter.

A host can attach this factory as CursorAdapter's contextual_factory. Attaching
it grants no authority. Each real run still requires fresh human authorization
and the existing cost and isolation gates. OS process arguments can expose the
prompt, so use only separately approved synthetic, non-secret instructions.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.cursor_invocation import CursorHostProfile, _environment, prepare_invocation
from agentsync.adapters.launch_context import LaunchContext
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError


@dataclass(frozen=True, slots=True, init=False)
class CursorProcessFactory:
    """Prepare a fresh pinned plan before one context-checked owned capture.

    Threaded preparation can outlive a stop. The launch context rechecks stop and
    deadline before capture entry. OS creation already scheduled can finish late.
    """

    _profile: CursorHostProfile = field(repr=False)
    _environment: tuple[tuple[str, str], ...] = field(repr=False)

    def __init__(self, profile: CursorHostProfile, *, environment: dict[str, str]) -> None:
        if type(profile) is not CursorHostProfile:
            raise AgentSyncError("validation_error", "Invalid Cursor process factory input.")
        object.__setattr__(self, "_profile", replace(profile))
        object.__setattr__(self, "_environment", _environment(environment))

    async def __call__(self, task: AdapterTask, context: LaunchContext) -> CapturedProcess:
        if type(context) is not LaunchContext:
            raise AgentSyncError("validation_error", "Adapter-issued launch context required.")
        context.check(task)
        plan = await asyncio.to_thread(
            prepare_invocation, self._profile, task, environment=dict(self._environment)
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
