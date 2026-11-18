"""Prepare a review declaration from saved real-client observations.

Read a JSON object on stdin with runs (client, client_version, agent_sha256,
run_sha256, session_sha256) and artifact (path relative to the evidence root,
sha256, size). Save stdout as a receipt and cite it alongside the artifact.
The tool checks declarations and saved bytes and does not authenticate runs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__:
    from .acceptance_evidence import _Evidence, read_json
    from .release_review import _REAL_EXECUTION_KINDS, _validate_execution_receipt
else:
    from acceptance_evidence import _Evidence, read_json
    from release_review import _REAL_EXECUTION_KINDS, _validate_execution_receipt

_LIMIT = 16 * 1024


def prepare_execution_receipt(
    evidence_root: Path,
    kind: str,
    commit: str,
    declaration: Any,
) -> dict[str, Any]:
    if (
        kind not in _REAL_EXECUTION_KINDS
        or not re.fullmatch(r"[0-9a-f]{40}", commit)
        or type(declaration) is not dict
        or set(declaration) != {"artifact", "runs"}
    ):
        raise ValueError("Invalid execution declaration.")
    artifact = declaration["artifact"]
    evidence = _Evidence(evidence_root, [artifact])
    if artifact["size"] <= 0:
        raise ValueError("Execution evidence must include a saved artifact.")
    receipt = {
        "schema_version": 1,
        "kind": kind,
        "commit_sha": commit,
        "runs": declaration["runs"],
        "artifact_sha256": artifact["sha256"],
    }
    _validate_execution_receipt(receipt, kind, commit)
    evidence.check(artifact["path"])
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=sorted(_REAL_EXECUTION_KINDS), required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(_LIMIT + 1)
        if len(raw) > _LIMIT:
            raise ValueError("Execution declaration exceeds its byte limit.")
        receipt = prepare_execution_receipt(
            args.evidence_root, args.kind, args.commit, read_json(raw)
        )
    except (OSError, RecursionError, TypeError, ValueError):
        parser.exit(2, "Invalid or inconsistent execution declaration.\n")
    print(json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
