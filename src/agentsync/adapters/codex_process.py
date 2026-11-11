"""Opt-in trusted-host Codex launcher; never human/Core authorization.

Construction launches nothing. Fresh authorization is required for every actual
model execution; attaching this reusable factory authorizes none. The host must
also satisfy its cost and isolation gates. This factory can launch a real
executable when invoked: read-only flags and a binary hash are not a sandbox,
credential boundary, subscription/cost proof or actual-client acceptance.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.codex_invocation import (
    CodexHostProfile,
    _environment,
    prepare_invocation,
)
from agentsync.adapters.launch_context import LaunchContext
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError


@dataclass(frozen=True, slots=True, init=False)
class CodexProcessFactory:
    """Prepare afresh, then attempt one context-checked owned capture.

    Profile/environment are immutable copies; only explicit filtered variables
    reach the process. Preparation runs in a thread and may finish after a local
    stop, but the context rechecks before entering capture. This cannot retract
    an OS spawn already scheduled or prove descendant/server cancellation.
    """

    _profile: CodexHostProfile = field(repr=False)
    _environment: tuple[tuple[str, str], ...] = field(repr=False)

    def __init__(self, profile: CodexHostProfile, *, environment: dict[str, str]) -> None:
        if type(profile) is not CodexHostProfile:
            raise AgentSyncError("validation_error", "Invalid Codex process factory input.")
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
