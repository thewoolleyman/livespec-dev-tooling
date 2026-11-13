"""Load the exact inventory shipped with an independently approved CI release.

The release carries one inventory per adopting repository, at
`data/incident-ci-inventory/<owner>/<repo>.json`; this repository's own
inventory stays at `data/incident-ci-inventory.json`. Each is rendered at build time
by `render_inventory` from that repository's own normal workflow and
`check-targets.txt` at a recorded commit of its default branch, and an adopter's
file records that commit as its `source`. livespec-dev-tooling's own entry is
rendered from this tree and is proven equal to it by the derivation test. The
entrance looks an inventory up by the repository its authenticated pull-request
read names, never by a candidate-supplied path, and refuses a repository the
release carries no inventory for.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling.checks._ci_matrix_parse import parse_ci_jobs
from livespec_dev_tooling.incident_ci_policy import CiTarget
from livespec_dev_tooling.incident_gate_inventory import timing_classes
from livespec_dev_tooling.incident_strict_json import strict_json

__all__: list[str] = [
    "SELF_REPOSITORY",
    "InventorySource",
    "InventoryUndeclaredError",
    "decode_inventory",
    "load_inventory",
    "load_repository_inventory",
    "render_inventory",
]
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-z5cjph
SELF_REPOSITORY = "thewoolleyman/livespec-dev-tooling"
_DIR = Path(__file__).parent / "data/incident-ci-inventory"
_PATH = Path(__file__).parent / "data/incident-ci-inventory.json"
_TEXT = re.compile(r"[a-z][a-z0-9-]*")
_REPOSITORY = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+")
_COMMIT = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, kw_only=True)
class InventorySource:
    """The adopter repository and default-branch commit an inventory was rendered from."""

    repository: str
    commit: str


class InventoryUndeclaredError(Exception):
    """The release carries no incident CI inventory for the repository; nothing may run."""


def render_inventory(
    *, workflow: str, inventory: str, source: InventorySource | None = None
) -> str:
    """Derive every actual normal member through the shared workflow parser.

    The output depends only on the derived target set and on each member's
    `incident-timing` class, read from the `check-targets.txt` text in
    `inventory` through the SAME reader the expedited local hooks use
    (livespec-dev-tooling-oqpw6t), so one annotation classifies a gate on both
    expedited paths. A member the inventory does not classify is unclassified.
    A workflow edit that leaves every job's contributed check targets unchanged
    renders the same bytes, so the packaged inventory never tracks unrelated
    workflow bytes. An adopter's inventory names the `source` it was rendered
    from; this repository's own inventory carries none, because it is rendered
    from the tree it ships in.
    """
    timing = timing_classes(inventory=inventory)
    jobs = parse_ci_jobs(source=workflow)
    # The coverage producer/consumer pair is wired only where both members exist,
    # so an adopter whose workflow has no per-file coverage job still renders.
    paired = {"check-coverage", "check-per-file-coverage"} <= {
        name for job in jobs for name in job.contributed_check_slugs
    }
    targets: list[CiTarget] = []
    for job in jobs:
        for name in sorted(job.contributed_check_slugs):
            consumer = paired and name == "check-coverage"
            producer = paired and name == "check-per-file-coverage"
            targets.append(
                CiTarget(
                    name=name,
                    classification=timing.get(name, "unclassified"),
                    batch=job.name,
                    needs=("check-per-file-coverage",) if consumer else (),
                    produces=("coverage-data",) if producer else (),
                    consumes=("coverage-data",) if consumer else (),
                )
            )
    document: dict[str, Any] = dict(schema=1, targets=[asdict(target) for target in targets])
    if source is not None:
        document["source"] = asdict(source)
    return (
        json.dumps(
            document,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def decode_inventory(*, text: str) -> tuple[CiTarget, ...]:
    """Refuse incomplete, duplicate, ambiguous or malformed released inventory."""
    return _decode(text=text)[0]


def _decode(*, text: str) -> tuple[tuple[CiTarget, ...], InventorySource | None]:
    value = strict_json(text=text, limit=65536)
    data = cast("dict[str, Any]", value) if isinstance(value, dict) else {}
    source = _source(value=data.get("source"))
    if (
        set(data) - {"source"} != {"schema", "targets"}
        or ("source" in data and source is None)
        or type(data["schema"]) is not int
        or data["schema"] != 1
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
            or row["classification"]
            not in {"fast", "slow", "not-applicable", "unclassified", "spec", "coverage"}
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
    return tuple(targets), source


def _source(*, value: object) -> InventorySource | None:
    row = cast("dict[str, Any]", value) if isinstance(value, dict) else {}
    if (
        set(row) != {"repository", "commit"}
        or not isinstance(row["repository"], str)
        or not isinstance(row["commit"], str)
        or _REPOSITORY.fullmatch(row["repository"]) is None
        or _COMMIT.fullmatch(row["commit"]) is None
    ):
        return None
    return InventorySource(repository=row["repository"], commit=row["commit"])


def load_inventory() -> tuple[CiTarget, ...]:
    """Read only packaged bytes; callers cannot substitute a candidate inventory.

    Packaged-data integrity is the installed release's integrity, so the bytes
    pass through decode_inventory's strict validation and no hand-pinned digest.
    """
    return decode_inventory(text=_PATH.read_bytes().decode())


def load_repository_inventory(*, repository: str) -> tuple[CiTarget, ...]:
    """The released inventory for `repository`, or a named refusal when there is none.

    `repository` is the one the caller's authenticated pull-request read names.
    An adopter's inventory must name that same repository as its source, so a
    file placed under the wrong name cannot select another repository's members.
    """
    if _REPOSITORY.fullmatch(repository) is None or ".." in repository.split("/"):
        message = "invalid repository for a released incident CI inventory"
        raise ValueError(message)
    if repository == SELF_REPOSITORY:
        return load_inventory()
    path = _DIR / f"{repository}.json"
    if not path.is_file() or path.is_symlink():
        message = (
            f"incident-inventory-undeclared: {repository} has no incident CI inventory"
            " in this livespec-dev-tooling release"
        )
        raise InventoryUndeclaredError(message)
    targets, source = _decode(text=path.read_bytes().decode())
    if source is None or source.repository != repository:
        message = "released incident CI inventory does not name its repository as source"
        raise ValueError(message)
    return targets
