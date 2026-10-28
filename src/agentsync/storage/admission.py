"""Private process-local admission per resolved database path.

The path key groups performance only; it is no security or cross-process lock.
Waiters retain a strong gate reference, while unused gates may be reclaimed.
No fairness, recursion, queue bound or hard total operation deadline is provided.
The acquisition wait is additive to SQLite waits and denial-audit work.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from weakref import WeakValueDictionary

from agentsync.errors import AgentSyncError

_ACQUIRE_TIMEOUT = 30.0


class _Gate:
    def __init__(self) -> None:
        self.lock = Lock()


_gates: WeakValueDictionary[str, _Gate] = WeakValueDictionary()
_registry_lock = Lock()


def _after_fork() -> None:
    global _gates, _registry_lock
    _gates = WeakValueDictionary()
    _registry_lock = Lock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


@contextmanager
def database_admission(path: Path) -> Iterator[None]:
    # Resolution may perform filesystem work; never hold the registry mutex here.
    key = os.path.normcase(str(path.resolve()))
    with _registry_lock:
        gate = _gates.get(key)
        if gate is None:
            gate = _Gate()
            _gates[key] = gate
    # This strong local spans waiting, the operation and release, preventing ABA
    # replacement of an active gate through the weak registry.
    if not gate.lock.acquire(timeout=_ACQUIRE_TIMEOUT):
        raise AgentSyncError("storage_error", "Database operation failed.", 503)
    try:
        yield
    finally:
        gate.lock.release()
