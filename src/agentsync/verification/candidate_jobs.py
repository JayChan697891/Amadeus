"""Owner-only candidate queue observations. No worker, execution or task gate."""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import math
import re
import sqlite3
import time
import unicodedata
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, NoReturn

from pydantic import Field, field_validator

from agentsync.errors import AgentSyncError
from agentsync.models import AdminAuth, CommitSHA
from agentsync.storage.database import connect
from agentsync.verification.binding import CandidateBinding, OwnerCandidateBindings, _receipt
from agentsync.verification.candidate import CandidateInput, OwnerCandidateExporter
from agentsync.verification.docker import DockerProfile

if TYPE_CHECKING:
    from agentsync.core.service import Core

MAX_METADATA = 4 * 1024 * 1024
MAX_RESPONSE = 16 * 1024
KIND = "managed_merge_candidate_input"
BINDING_FIELDS = {field.name for field in dataclasses.fields(CandidateBinding)}


class _Owner(AdminAuth):
    project_id: str = Field(min_length=1, max_length=200)
    admin_token: str = Field(min_length=1, max_length=4096)

    @field_validator("*")
    @classmethod
    def encoded_bounds(cls, value: Any, info: Any) -> Any:
        if isinstance(value, str):
            maximum = 4096 if info.field_name == "admin_token" else 800
            try:
                if not value or len(value.encode("utf-8")) > maximum:
                    raise ValueError("invalid text length")
            except UnicodeError:
                raise ValueError("invalid text encoding") from None
        return value


class _Enqueue(_Owner):
    candidate_id: str = Field(min_length=1, max_length=200)
    expected_candidate_sha: CommitSHA
    request_id: str = Field(min_length=1, max_length=200)


class _Lookup(_Owner):
    job_id: str = Field(min_length=1, max_length=200)


class _Cancel(_Lookup):
    expected_version: int = Field(ge=1, le=2**63 - 3)
    request_id: str = Field(min_length=1, max_length=200)


class _Page(_Owner):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)


def _error(code: str, message: str, status: int = 409) -> NoReturn:
    raise AgentSyncError(code, message, status)


def _corrupt() -> NoReturn:
    _error("corrupt_candidate_queue", "Stored candidate queue data is invalid.")


def _dump(value: Any, *, ascii_only: bool = False) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=ascii_only, allow_nan=False
    )


def _hash(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _corrupt()
        result[key] = value
    return result


def _depth(value: Any, depth: int = 0) -> None:
    if depth > 32:
        _corrupt()
    if type(value) is dict:
        for item in value.values():
            _depth(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _depth(item, depth + 1)
    elif type(value) is float and not math.isfinite(value):
        _corrupt()


def _load(raw: Any, maximum: int) -> Any:
    try:
        if type(raw) is not str or len(raw.encode("utf-8")) > maximum:
            _corrupt()
        result = json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: _corrupt())
        _depth(result)
        if _dump(result) != raw:
            _corrupt()
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _corrupt()


def _shape(value: Any, keys: set[str]) -> None:
    if type(value) is not dict or set(value) != keys:
        _corrupt()


def _text(value: Any, maximum: int = 200) -> None:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or len(value.encode("utf-8")) > maximum * 4
    ):
        _corrupt()


def _sha(value: Any, full: bool = False) -> None:
    pattern = r"(?:[0-9a-f]{40}|[0-9a-f]{64})" if full else r"[0-9a-f]{64}"
    if type(value) is not str or re.fullmatch(pattern, value) is None:
        _corrupt()


def _manifest(value: Any) -> None:
    if type(value) is not list or not 1 <= len(value) <= 256:
        _corrupt()
    paths: list[str] = []
    aliases: dict[str, str] = {}
    total = 0
    solution = 0
    for entry in value:
        if type(entry) is not list or len(entry) != 3:
            _corrupt()
        path, oid, size = entry
        if type(path) is not str or not path or len(path.encode("utf-8")) > 4096:
            _corrupt()
        parts = path.split("/")
        if len(parts) > 64 or any(
            not p
            or p in {".", ".."}
            or p.casefold() == ".git"
            or p.endswith((".", " "))
            or any(ord(c) < 32 or ord(c) == 127 or c in "\\:" for c in p)
            or re.match(r"(?i)^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)", p)
            for p in parts
        ):
            _corrupt()
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            folded = unicodedata.normalize("NFC", prefix).casefold()
            if folded in aliases and aliases[folded] != prefix:
                _corrupt()
            aliases[folded] = prefix
        _sha(oid, True)
        if type(size) is not int or not 0 <= size <= MAX_METADATA:
            _corrupt()
        total += size
        if path == "solution.py":
            solution += 1
            if size > 128 * 1024:
                _corrupt()
        paths.append(path)
    if (
        total > MAX_METADATA
        or solution != 1
        or len(set(paths)) != len(paths)
        or paths != sorted(paths, key=lambda p: p.encode("utf-8"))
    ):
        _corrupt()
    if any(
        "/".join(path.split("/")[:i]) in paths
        for path in paths
        for i in range(1, len(path.split("/")))
    ):
        _corrupt()


def _metadata(raw: str) -> dict[str, Any]:
    """Recompute existing fingerprints exactly, without Git or current DB reads."""
    try:
        envelope = _load(raw, MAX_METADATA)
        _shape(
            envelope, {"schema", "binding", "snapshot", "provenance_sha256", "verification_profile"}
        )
        policy = envelope["verification_profile"]
        _shape(policy, {"kind", "sha256", "image_id"})
        _text(policy["kind"])
        _sha(policy["sha256"])
        if (
            type(policy["image_id"]) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", policy["image_id"]) is None
        ):
            _corrupt()
        if envelope["schema"] != "agentsync.candidate-job-input.v1":
            _corrupt()
        binding, snapshot = envelope["binding"], envelope["snapshot"]
        _shape(binding, BINDING_FIELDS)
        for key in (
            "project_id",
            "candidate_id",
            "snapshot_id",
            "left_worktree_id",
            "right_worktree_id",
            "left_task_id",
            "right_task_id",
        ):
            _text(binding[key])
        if binding["source_kind"] != "managed_merge_candidate_metadata":
            _corrupt()
        for key in ("candidate_sha", "base_sha", "left_sha", "right_sha"):
            _sha(binding[key], True)
        for key in ("left_task_version", "right_task_version"):
            if type(binding[key]) is not int or not 1 <= binding[key] <= 2**63 - 1:
                _corrupt()
        creators, receipts = binding["creator_session_ids"], binding["receipts"]
        if (
            type(creators) is not list
            or len(creators) != 4
            or type(receipts) is not list
            or len(receipts) != 4
        ):
            _corrupt()
        for creator in creators:
            _text(creator)
        for receipt in receipts:
            if _dump(_receipt(receipt)) != receipt:
                _corrupt()
        bound = {
            key: value
            for key, value in binding.items()
            if key not in {"receipts", "provenance_sha256"}
        }
        bound = {
            "schema": "agentsync.candidate-binding.v1",
            **bound,
            "receipt_sha256": [_hash(r) for r in receipts],
        }
        _sha(binding["provenance_sha256"])
        if _hash(_dump(bound)) != binding["provenance_sha256"]:
            _corrupt()
        _shape(snapshot, {"commit_sha", "tree_sha", "manifest", "input_sha256", "source_sha256"})
        for key in ("commit_sha", "tree_sha"):
            _sha(snapshot[key], True)
        for key in ("input_sha256", "source_sha256"):
            _sha(snapshot[key])
        if snapshot["commit_sha"] != binding["candidate_sha"]:
            _corrupt()
        _manifest(snapshot["manifest"])
        content = {
            "format": "agentsync-candidate-v1",
            **{k: snapshot[k] for k in ("commit_sha", "tree_sha", "manifest", "source_sha256")},
        }
        if _hash(_dump(content, ascii_only=True)) != snapshot["input_sha256"]:
            _corrupt()
        provenance = {
            "schema": "agentsync.candidate-input.v1",
            "source_kind": KIND,
            "binding_sha256": binding["provenance_sha256"],
            **{k: snapshot[k] for k in ("commit_sha", "tree_sha", "input_sha256", "source_sha256")},
        }
        _sha(envelope["provenance_sha256"])
        if _hash(_dump(provenance)) != envelope["provenance_sha256"]:
            _corrupt()
        return envelope
    except (AgentSyncError, ValueError, TypeError, UnicodeError, RecursionError, KeyError):
        _corrupt()


def _encode_input(value: CandidateInput, policy: dict[str, str]) -> str:
    snap = value.snapshot
    envelope = {
        "schema": "agentsync.candidate-job-input.v1",
        "binding": dataclasses.asdict(value.binding),
        "snapshot": {
            "commit_sha": snap.commit_sha,
            "tree_sha": snap.tree_sha,
            "manifest": snap.manifest,
            "input_sha256": snap.input_sha256,
            "source_sha256": _hash(snap.source),
        },
        "provenance_sha256": value.provenance_sha256,
        "verification_profile": policy,
    }
    raw = _dump(envelope)
    _metadata(raw)
    return raw


PUBLIC_FIELDS = (
    "id",
    "project_id",
    "candidate_id",
    "snapshot_id",
    "candidate_sha",
    "tree_sha",
    "input_sha256",
    "source_sha256",
    "binding_sha256",
    "provenance_sha256",
    "metadata_sha256",
    "profile_kind",
    "profile_sha256",
    "image_id",
    "status",
    "version",
    "created_at",
    "updated_at",
    "source_kind",
)


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in PUBLIC_FIELDS} | {
        "current_state": True,
        "execution_connected": False,
        "execution_assessment": "unverified",
    }


class CandidateVerificationJobs:
    def __init__(self, core: Core):
        self.core = core

    @contextmanager
    def _transaction(
        self,
        p: dict[str, Any],
        *,
        write: bool = False,
        operation: str = "candidate_verification_get",
    ) -> Iterator[tuple[sqlite3.Connection, float]]:
        try:
            db = connect(self.core.db_path)
        except sqlite3.Error:
            _error("storage_error", "Candidate queue storage unavailable.", 503)
        actor = None
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            self.core._authenticate_owner(db, p)
            actor = (p["project_id"], "owner", p["project_id"])
            now = time.time()
            if type(now) not in {int, float} or not math.isfinite(now):
                _error("invalid_clock", "A finite service clock is required.")
            yield db, now
            db.commit()
        except AgentSyncError as exc:
            db.rollback()
            if write:
                self.core._audit_denial(actor, operation, p, exc.code)
            raise
        except (sqlite3.Error, UnicodeError, ValueError, TypeError, RecursionError):
            db.rollback()
            _error("storage_error", "Candidate queue operation failed.", 503)
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _row(db: sqlite3.Connection, project_id: str, job_id: str) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM candidate_verification_jobs WHERE id=? AND project_id=?",
            (job_id, project_id),
        ).fetchone()
        if row is None:
            _error("not_found", "Candidate verification job not found.", 404)
        try:
            data = _metadata(row["metadata_json"])
            if _hash(row["metadata_json"]) != row["metadata_sha256"]:
                _corrupt()
            binding, snapshot = data["binding"], data["snapshot"]
            policy = data["verification_profile"]
            if any(
                row[column] != policy[key]
                for column, key in (
                    ("profile_kind", "kind"),
                    ("profile_sha256", "sha256"),
                    ("image_id", "image_id"),
                )
            ):
                _corrupt()
            for key in (
                "project_id",
                "candidate_id",
                "snapshot_id",
                "left_worktree_id",
                "right_worktree_id",
                "left_task_id",
                "right_task_id",
                "left_task_version",
                "right_task_version",
                "candidate_sha",
                "base_sha",
                "left_sha",
                "right_sha",
            ):
                if row[key] != binding[key]:
                    _corrupt()
            for key in ("tree_sha", "input_sha256", "source_sha256"):
                if row[key] != snapshot[key]:
                    _corrupt()
            if (
                row["binding_sha256"] != binding["provenance_sha256"]
                or row["provenance_sha256"] != data["provenance_sha256"]
                or row["source_kind"] != KIND
            ):
                _corrupt()
            _text(row["id"])
            _text(row["profile_kind"])
            _sha(row["profile_sha256"])
            if (
                type(row["image_id"]) is not str
                or re.fullmatch(r"sha256:[0-9a-f]{64}", row["image_id"]) is None
            ):
                _corrupt()
            if (row["status"], row["version"]) not in {("queued", 1), ("cancelled", 2)}:
                _corrupt()
            if (
                any(
                    type(row[k]) not in {int, float} or not math.isfinite(row[k])
                    for k in ("created_at", "updated_at")
                )
                or row["updated_at"] < row["created_at"]
            ):
                _corrupt()
            return row
        except (KeyError, IndexError, ValueError, TypeError, UnicodeError):
            _corrupt()

    def _replay(
        self, db: sqlite3.Connection, operation: str, p: dict[str, Any], fingerprint: str
    ) -> dict[str, Any] | None:
        request = db.execute(
            "SELECT * FROM candidate_verification_requests WHERE project_id=? AND operation=? AND request_id=?",
            (p["project_id"], operation, p["request_id"]),
        ).fetchone()
        if request is None:
            return None
        _sha(request["payload_hash"])
        if not hmac.compare_digest(request["payload_hash"], fingerprint):
            _error("idempotency_conflict", "Request ID is bound to different candidate inputs.")
        row = self._row(db, p["project_id"], request["job_id"])
        response = _load(request["response_json"], MAX_RESPONSE)
        if _hash(request["response_json"]) != request["response_sha256"]:
            _corrupt()
        expected = _public(row) | {
            "current_state": False,
            "receipt_kind": "historical_" + operation,
        }
        if operation == "enqueue":
            expected.update(status="queued", version=1, updated_at=row["created_at"])
        elif row["status"] != "cancelled" or row["version"] != 2:
            _corrupt()
        if _dump(expected) != request["response_json"]:
            _corrupt()
        return response

    def _remember(
        self,
        db: sqlite3.Connection,
        operation: str,
        p: dict[str, Any],
        fingerprint: str,
        response: dict[str, Any],
    ) -> None:
        raw = _dump(response)
        if len(raw.encode("utf-8")) > MAX_RESPONSE:
            _error("response_too_large", "Candidate receipt exceeds its bound.")
        db.execute(
            "INSERT INTO candidate_verification_requests VALUES(?,?,?,?,?,?,?)",
            (
                p["project_id"],
                operation,
                p["request_id"],
                fingerprint,
                response["id"],
                raw,
                _hash(raw),
            ),
        )
        self.core._audit_event(
            db,
            p["project_id"],
            "owner",
            p["project_id"],
            "candidate_verification_" + operation,
            p,
            "success",
            "ok",
            response,
        )

    def enqueue(
        self,
        *,
        project_id: str,
        admin_token: str,
        candidate_id: str,
        expected_candidate_sha: str,
        profile: DockerProfile,
        request_id: str,
    ) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Enqueue,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "candidate_id": candidate_id,
                "expected_candidate_sha": expected_candidate_sha,
                "request_id": request_id,
            },
        )
        p["expected_candidate_sha"] = p["expected_candidate_sha"].lower()
        with self._transaction(p) as (db, _):
            try:
                if type(profile) is not DockerProfile:
                    raise ValueError("profile type")
                profile.__post_init__()
                profile_kind, profile_hash, image_id = (
                    profile.profile_id,
                    profile.sha256,
                    profile.image_id,
                )
                _text(profile_kind)
                _sha(profile_hash)
                if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
                    raise ValueError("profile image")
            except (
                AgentSyncError,
                ValueError,
                TypeError,
                UnicodeError,
                RecursionError,
                AttributeError,
                OverflowError,
            ):
                _error("invalid_profile", "A trusted immutable DockerProfile is required.", 400)
            fingerprint = _hash(
                _dump(
                    {
                        "schema": "agentsync.candidate-request.v1",
                        "operation": "enqueue",
                        "candidate_id": candidate_id,
                        "expected_candidate_sha": p["expected_candidate_sha"],
                        "profile_kind": profile_kind,
                        "profile_sha256": profile_hash,
                        "image_id": image_id,
                    }
                )
            )
            replay = self._replay(db, "enqueue", p, fingerprint)
            if replay is not None:
                return replay
        exported = OwnerCandidateExporter(self.core).export(
            **{
                k: p[k]
                for k in ("project_id", "admin_token", "candidate_id", "expected_candidate_sha")
            }
        )
        with self._transaction(p, write=True, operation="candidate_verification_enqueue") as (
            db,
            now,
        ):
            replay = self._replay(db, "enqueue", p, fingerprint)
            if replay is not None:
                return replay
            binding = OwnerCandidateBindings(self.core)._capture_in_transaction(
                db,
                **{
                    k: p[k]
                    for k in ("project_id", "admin_token", "candidate_id", "expected_candidate_sha")
                },
            )
            if binding != exported.binding:
                _error(
                    "stale_candidate_input", "Candidate metadata changed before queue insertion."
                )
            raw = _encode_input(
                exported, {"kind": profile_kind, "sha256": profile_hash, "image_id": image_id}
            )
            values = {
                k: getattr(binding, k)
                for k in (
                    "project_id",
                    "candidate_id",
                    "snapshot_id",
                    "left_worktree_id",
                    "right_worktree_id",
                    "left_task_id",
                    "right_task_id",
                    "left_task_version",
                    "right_task_version",
                    "candidate_sha",
                    "base_sha",
                    "left_sha",
                    "right_sha",
                )
            }
            values.update(
                id=str(uuid.uuid4()),
                tree_sha=exported.snapshot.tree_sha,
                input_sha256=exported.snapshot.input_sha256,
                source_sha256=_hash(exported.snapshot.source),
                binding_sha256=binding.provenance_sha256,
                provenance_sha256=exported.provenance_sha256,
                profile_kind=profile_kind,
                profile_sha256=profile_hash,
                image_id=image_id,
                metadata_json=raw,
                metadata_sha256=_hash(raw),
                source_kind=KIND,
                status="queued",
                version=1,
                created_at=now,
                updated_at=now,
            )
            db.execute(
                "INSERT INTO candidate_verification_jobs("
                + ",".join(values)
                + ") VALUES("
                + ",".join("?" for _ in values)
                + ")",
                tuple(values.values()),
            )
            response = _public(self._row(db, project_id, values["id"])) | {
                "current_state": False,
                "receipt_kind": "historical_enqueue",
            }
            self._remember(db, "enqueue", p, fingerprint, response)
            return response

    def get(self, *, project_id: str, admin_token: str, job_id: str) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Lookup, {"project_id": project_id, "admin_token": admin_token, "job_id": job_id}
        )
        with self._transaction(p) as (db, _):
            return _public(self._row(db, project_id, job_id))

    def list(
        self, *, project_id: str, admin_token: str, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Page,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "limit": limit,
                "offset": offset,
            },
        )
        with self._transaction(p) as (db, _):
            ids = db.execute(
                "SELECT id FROM candidate_verification_jobs WHERE project_id=? ORDER BY created_at,id LIMIT ? OFFSET ?",
                (project_id, limit + 1, offset),
            ).fetchall()
            return {
                "jobs": [_public(self._row(db, project_id, row["id"])) for row in ids[:limit]],
                "has_more": len(ids) > limit,
                "current_state": True,
                "execution_connected": False,
                "execution_assessment": "unverified",
            }

    def cancel(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        expected_version: int,
        request_id: str,
    ) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Cancel,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "job_id": job_id,
                "expected_version": expected_version,
                "request_id": request_id,
            },
        )
        fingerprint = _hash(
            _dump(
                {
                    "schema": "agentsync.candidate-request.v1",
                    "operation": "cancel",
                    "job_id": job_id,
                    "expected_version": expected_version,
                }
            )
        )
        with self._transaction(p, write=True, operation="candidate_verification_cancel") as (
            db,
            now,
        ):
            replay = self._replay(db, "cancel", p, fingerprint)
            if replay is not None:
                return replay
            row = self._row(db, project_id, job_id)
            if now < row["updated_at"]:
                _error("clock_regressed", "Clock moved backwards.")
            if row["version"] != expected_version:
                _error("version_conflict", "Candidate job version changed.")
            if row["status"] != "queued":
                _error("invalid_state", "Candidate job is already cancelled.")
            result = db.execute(
                "UPDATE candidate_verification_jobs SET status='cancelled',version=version+1,updated_at=? WHERE id=? AND project_id=? AND version=? AND status='queued'",
                (now, job_id, project_id, expected_version),
            )
            if result.rowcount != 1:
                _error("version_conflict", "Candidate job version changed.")
            response = _public(self._row(db, project_id, job_id)) | {
                "current_state": False,
                "receipt_kind": "historical_cancel",
            }
            self._remember(db, "cancel", p, fingerprint, response)
            return response
