"""Process-local admission only; SQLite remains the cross-process authority."""

import gc
import multiprocessing
import os
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor

import pytest

import agentsync.core.service as service
import agentsync.storage.admission as admission
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


def key(path):
    return os.path.normcase(str(path.resolve()))


def create(core, root, name="fixture"):
    return core.execute("create_project", {"name": name, "root_path": str(root)})


def test_same_database_core_instances_share_admission_while_other_database_progresses(
    tmp_path, monkeypatch
):
    first, same, other = Core(tmp_path / "one"), Core(tmp_path / "one"), Core(tmp_path / "two")
    entered, release = threading.Event(), threading.Event()
    original = service.connect

    def pause_first(path):
        if path == first.db_path and not entered.is_set():
            entered.set()
            assert release.wait(5)
        return original(path)

    monkeypatch.setattr(service, "connect", pause_first)
    with ThreadPoolExecutor(max_workers=3) as pool:
        held = pool.submit(create, first, tmp_path, "first")
        try:
            assert entered.wait(3)
            waiting = pool.submit(create, same, tmp_path, "same")
            independent = pool.submit(create, other, tmp_path, "other")
            assert independent.result(timeout=3)["project_id"]
            assert not waiting.done()
        finally:
            release.set()
        assert held.result(timeout=3)["project_id"]
        assert waiting.result(timeout=3)["project_id"]


def test_waiter_strong_reference_prevents_gate_replacement_and_unused_gate_is_reaped(
    tmp_path, monkeypatch
):
    trying, acquired, release = threading.Event(), threading.Event(), threading.Event()
    original = threading.Lock

    class ObservedLock:
        def __init__(self):
            self.lock = original()

        def acquire(self, **options):
            trying.set()
            return self.lock.acquire(**options)

        def release(self):
            self.lock.release()

    monkeypatch.setattr(admission, "Lock", ObservedLock)
    path = tmp_path / "private.db"

    def waiter():
        with admission.database_admission(path):
            acquired.set()
            assert release.wait(5)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with admission.database_admission(path):
            reference = weakref.ref(admission._gates[key(path)])
            trying.clear()
            future = pool.submit(waiter)
            assert trying.wait(3)
            gc.collect()
            assert reference() is admission._gates[key(path)]
        try:
            assert acquired.wait(3)
            gc.collect()
            assert reference() is admission._gates[key(path)]
        finally:
            release.set()
        future.result(timeout=3)
    gc.collect()
    assert reference() is None and key(path) not in admission._gates


def test_timeout_precedes_sql_or_denial_audit_and_payload_validation_precedes_gate(
    tmp_path, monkeypatch
):
    core = Core(tmp_path / "db")
    monkeypatch.setattr(admission, "_ACQUIRE_TIMEOUT", 0.01)
    monkeypatch.setattr(service, "connect", lambda *_: pytest.fail("Timeout reached SQL"))
    monkeypatch.setattr(Core, "_audit_denial", lambda *_: pytest.fail("Timeout became auth denial"))
    with admission.database_admission(core.db_path):
        with pytest.raises(AgentSyncError) as invalid:
            create(core, tmp_path, "")
        assert invalid.value.code == "validation_error"
        with pytest.raises(AgentSyncError) as error:
            create(core, tmp_path)
        assert (error.value.code, error.value.message, error.value.status_code) == (
            "storage_error",
            "Database operation failed.",
            503,
        )


@pytest.mark.parametrize(
    "phase", ["connection", "body", "rollback", "denial_audit", "close", "base_exception"]
)
def test_admission_releases_after_connection_body_audit_close_and_base_exceptions(
    tmp_path, monkeypatch, phase
):
    core = Core(tmp_path / "db")
    retained = []
    closed = []
    original = service.connect

    class Abort(BaseException):
        pass

    def fail_body(*_):
        assert retained[0].lock.locked()
        if phase == "denial_audit":
            raise AgentSyncError("fixture_error", "Fixture denial")
        raise Abort() if phase == "base_exception" else RuntimeError("Fixture body")

    class ClosingConnection:
        def __init__(self, db):
            self.db = db

        def __getattr__(self, name):
            return getattr(self.db, name)

        def rollback(self):
            self.db.rollback()
            assert retained[0].lock.locked()
            raise RuntimeError("Fixture rollback")

        def close(self):
            self.db.close()
            closed.append(True)
            assert retained[0].lock.locked()
            if phase == "close":
                raise RuntimeError("Fixture close")

    def connect(path):
        retained.append(admission._gates[key(path)])
        assert retained[0].lock.locked()
        if phase == "connection":
            raise RuntimeError("Fixture connection")
        db = original(path)
        return ClosingConnection(db) if phase in {"close", "rollback"} else db

    def fail_denial(*_):
        assert retained[0].lock.locked()
        raise RuntimeError("Fixture audit")

    monkeypatch.setattr(service, "connect", connect)
    if phase in {"body", "rollback", "denial_audit", "base_exception"}:
        monkeypatch.setattr(Core, "_create_project", fail_body)
    if phase == "denial_audit":
        monkeypatch.setattr(Core, "_audit_denial", fail_denial)
    with pytest.raises(
        Abort if phase == "base_exception" else RuntimeError,
        match="Fixture rollback" if phase == "rollback" else None,
    ):
        create(core, tmp_path)
    if phase == "rollback":
        assert closed == [True]
    with ThreadPoolExecutor(max_workers=1) as pool:
        acquired = pool.submit(retained[0].lock.acquire, timeout=1).result(timeout=2)
    assert acquired
    retained[0].lock.release()


def _fork_execute(core, root, sender):
    try:
        create(core, root)
        sender.send(True)
    except BaseException:
        sender.send(False)
    finally:
        sender.close()


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(), reason="Requires Linux/POSIX fork"
)
def test_inherited_core_fork_resets_gate_and_registry_mutex_held_by_parent(tmp_path):
    core = Core(tmp_path / "db")  # Migration connections are closed before forking.
    context = multiprocessing.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=_fork_execute, args=(core, tmp_path, sender))
    try:
        with admission.database_admission(core.db_path), admission._registry_lock:
            child.start()
            sender.close()
            assert receiver.poll(5), "Child blocked on inherited admission state"
            assert receiver.recv() is True
            child.join(timeout=5)
            assert child.exitcode == 0
    finally:
        if child.pid is not None and child.is_alive():
            child.terminate()
            child.join(timeout=5)
        receiver.close()
        sender.close()
