"""Load the exact inventory shipped with an independently approved CI release."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling.checks._ci_matrix_parse import parse_ci_jobs
from livespec_dev_tooling.incident_ci_payload import strict_json
from livespec_dev_tooling.incident_ci_policy import CiTarget

__all__: list[str] = ["decode_inventory", "load_inventory", "render_inventory"]
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
_PATH = Path(__file__).parent / "data/incident-ci-inventory.json"
_SHA256 = "15892d0739b4fbd1a5bf41da7b0f678f289f1478441d7d9aac363605ada0662b"
_FAST = {"check-lint", "check-format"}
_TEXT = re.compile(r"[a-z][a-z0-9-]*")


def render_inventory(*, workflow: str) -> str:
    """Derive every actual normal member through the shared workflow parser."""
    targets: list[CiTarget] = []
    for job in parse_ci_jobs(source=workflow):
        for name in sorted(job.contributed_check_slugs):
            targets.append(
                CiTarget(
                    name=name,
                    classification="fast" if name in _FAST else "unclassified",
                    batch=job.name,
                    needs=("check-per-file-coverage",) if name == "check-coverage" else (),
                    produces=("coverage-data",) if name == "check-per-file-coverage" else (),
                    consumes=("coverage-data",) if name == "check-coverage" else (),
                )
            )
    return (
        json.dumps(
            dict(
                schema=1,
                workflow_sha256=hashlib.sha256(workflow.encode()).hexdigest(),
                targets=[asdict(target) for target in targets],
            ),
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def decode_inventory(*, text: str) -> tuple[CiTarget, ...]:
    """Refuse incomplete, duplicate, ambiguous or malformed released inventory."""
    value = strict_json(text=text)
    data = cast("dict[str, Any]", value) if isinstance(value, dict) else {}
    if (
        set(data) != {"schema", "workflow_sha256", "targets"}
        or type(data["schema"]) is not int
        or data["schema"] != 1
        or not isinstance(data["workflow_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", data["workflow_sha256"]) is None
        or not isinstance(data["targets"], list)
        or not data["targets"]
    ):
        message = "invalid released incident CI inventory"
        raise ValueError(message)
    targets: list[CiTarget] = []
    for value in cast("list[object]", data["targets"]):
        row = cast("dict[str, Any]", value) if isinstance(value, dict) else {}
        if (
            set(row) != {"name", "classification", "batch", "needs", "produces", "consumes"}
            or any(not isinstance(row[key], str) for key in ("name", "classification", "batch"))
            or not row["name"].startswith("check-")
            or _TEXT.fullmatch(row["name"]) is None
            or _TEXT.fullmatch(row["batch"]) is None
            or row["classification"] not in {"fast", "slow", "unclassified", "spec", "coverage"}
            or any(
                not isinstance(row[key], list)
                or not all(isinstance(v, str) and _TEXT.fullmatch(v) for v in row[key])
                or len(set(row[key])) != len(row[key])
                for key in ("needs", "produces", "consumes")
            )
        ):
            message = "invalid released incident CI target"
            raise ValueError(message)
        targets.append(
            CiTarget(**(row | {key: tuple(row[key]) for key in ("needs", "produces", "consumes")}))
        )
    names = {target.name for target in targets}
    if len(names) != len(targets) or any(
        dependency not in names or dependency == target.name
        for target in targets
        for dependency in target.needs
    ):
        message = "duplicate or missing released incident CI dependency"
        raise ValueError(message)
    return tuple(targets)


def load_inventory() -> tuple[CiTarget, ...]:
    """Read only packaged bytes; callers cannot substitute a candidate inventory."""
    raw = _PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _SHA256:
        message = "released incident CI inventory digest mismatch"
        raise ValueError(message)
    return decode_inventory(text=raw.decode())
