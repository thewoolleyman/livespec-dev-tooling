"""Lane capacity: refuse a declared gate request that no committed gates-cq lane admits.

contracts.md "Delegated pre-push gate", Declared gate resources, Lane
capacity (v192). Kueue admits a Job in ONE flavor covering both cpu and
memory, so a request larger than every flavor would only end without a
verdict at the admission bound. The comparison runs only for a repository
that declares `gate_cpu` or `gate_memory`, against that Job's EFFECTIVE
request: each declared value, and the renderer's own default for the key it
does not declare. A repository declaring neither is never compared and its
queue file is never read.

The queue file and the renderer come from the same source the gate client
renders from: this repository's in-tree copies when it carries the renderer,
otherwise the copies packaged with `livespec_dev_tooling`. The file is parsed
with the vendored `livespec_yaml`, a private name that cannot shadow a
consumer's own `yaml`.
"""

from __future__ import annotations

import importlib
import re
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

__all__: list[str] = [
    "GATES_QUEUE_PACKAGED",
    "RENDERER_PACKAGED",
    "Lane",
    "committed_lanes",
    "lane_capacity_refusal",
    "largest_lane",
    "quantity",
]

_YAML = importlib.import_module("livespec_yaml")
_LOAD_ALL = cast("Callable[[str], Iterable[object]]", _YAML.safe_load_all)
_YAML_ERROR = cast("type[Exception]", _YAML.YAMLError)

_GATES_QUEUE_IN_REPO = Path("ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml")
_RENDERER_IN_REPO = Path("ci-runner/k3s/phase2/gates/render-gate-job.sh")
GATES_QUEUE_PACKAGED = Path(__file__).resolve().parent / "gates" / "cluster-queue-gates.yaml"
RENDERER_PACKAGED = Path(__file__).resolve().parent / "gates" / "render-gate-job.sh"
_GATES_CQ = "gates-cq"
_COMPARED_KEYS = ("gate_cpu", "gate_memory")
# The renderer's defaults line, `cpu="5"; memory="6Gi"; parallelism="4"; ...`:
# the default has ONE owner, so the comparison reads it rather than restating it.
_DEFAULTS_LINE = re.compile(r'^cpu="([^"]*)"; memory="([^"]*)";', re.MULTILINE)
_QUANTITY = re.compile(r"^([0-9]+(?:\.[0-9]+)?)([A-Za-z]{0,2})$")
_SCALE = {
    "": Fraction(1),
    "m": Fraction(1, 1000),
    "k": Fraction(10**3),
    "M": Fraction(10**6),
    "G": Fraction(10**9),
    "T": Fraction(10**12),
    "Ki": Fraction(2**10),
    "Mi": Fraction(2**20),
    "Gi": Fraction(2**30),
    "Ti": Fraction(2**40),
}


@dataclass(frozen=True, kw_only=True)
class Lane:
    """One committed gates-cq flavor: its name and nominal quotas, by value and as committed."""

    name: str
    cpu: Fraction
    memory: Fraction
    cpu_text: str
    memory_text: str


def quantity(*, value: object) -> Fraction | None:
    """A Kubernetes resource quantity read by value, or None when it is not one."""
    match = _QUANTITY.match(str(value).strip())
    if match is None or match.group(2) not in _SCALE:
        return None
    return Fraction(match.group(1)) * _SCALE[match.group(2)]


def committed_lanes(*, queue: Path) -> tuple[Lane, ...]:
    """Every gates-cq flavor in `queue` with a readable cpu and memory quota, in file order."""
    text = _read(path=queue)
    if text is None:
        return ()
    try:
        documents = list(_LOAD_ALL(text))
    except _YAML_ERROR:
        return ()
    return tuple(
        lane
        for document in documents
        if _mapping(value=document).get("kind") == "ClusterQueue"
        and _mapping(value=_mapping(value=document).get("metadata")).get("name") == _GATES_CQ
        for group in _items(
            value=_mapping(value=_mapping(value=document).get("spec")).get("resourceGroups")
        )
        for flavor in _items(value=_mapping(value=group).get("flavors"))
        for lane in _lane(flavor=_mapping(value=flavor))
    )


def largest_lane(*, lanes: tuple[Lane, ...]) -> Lane:
    """The greatest cpu quota, then the greater memory quota, then the first in the file."""
    return max(enumerate(lanes), key=lambda pair: (pair[1].cpu, pair[1].memory, -pair[0]))[1]


def lane_capacity_refusal(*, repo_root: Path, declared: tuple[tuple[str, str], ...]) -> str | None:
    """Why no gates-cq lane admits this declaration; None when one does or no comparison is owed."""
    values = dict(declared)
    compared = ", ".join(f"{key} = {values[key]}" for key in _COMPARED_KEYS if key in values)
    if not compared:
        return None
    in_tree = (repo_root / _RENDERER_IN_REPO).is_file()
    queue = repo_root / _GATES_QUEUE_IN_REPO if in_tree else GATES_QUEUE_PACKAGED
    renderer = repo_root / _RENDERER_IN_REPO if in_tree else RENDERER_PACKAGED
    lanes = committed_lanes(queue=queue)
    if not lanes:
        return (
            f"the gate client cannot read or parse the gates-cq lanes of {queue} "
            f"to compare {compared}"
        )
    defaults = _renderer_defaults(renderer=renderer)
    cpu = quantity(value=values.get("gate_cpu", defaults[0]))
    memory = quantity(value=values.get("gate_memory", defaults[1]))
    if cpu is None or memory is None:
        return (
            f"the gate client cannot read the default gate Job request of {renderer} "
            f"to compare {compared}"
        )
    if any(lane.cpu >= cpu and lane.memory >= memory for lane in lanes):
        return None
    largest = largest_lane(lanes=lanes)
    return (
        f"no committed gates-cq lane in {queue} admits the declared {compared} "
        f"({repo_root}/pyproject.toml), so Kueue could never admit its gate Job; the largest "
        f"lane is {largest.name} with {largest.cpu_text} CPU and {largest.memory_text} memory"
    )


def _renderer_defaults(*, renderer: Path) -> tuple[str, str]:
    """The renderer's own default cpu and memory, or two empty strings when unreadable."""
    match = _DEFAULTS_LINE.search(_read(path=renderer) or "")
    return (match.group(1), match.group(2)) if match else ("", "")


def _read(*, path: Path) -> str | None:
    """The file's text, or None when it is absent or unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _lane(*, flavor: dict[str, object]) -> tuple[Lane, ...]:
    """The flavor as a lane, or nothing when either quota is missing or unreadable."""
    quotas = {
        _mapping(value=resource).get("name"): _mapping(value=resource).get("nominalQuota")
        for resource in _items(value=flavor.get("resources"))
    }
    cpu, memory = quantity(value=quotas.get("cpu")), quantity(value=quotas.get("memory"))
    if cpu is None or memory is None:
        return ()
    return (
        Lane(
            name=str(flavor.get("name")),
            cpu=cpu,
            memory=memory,
            cpu_text=str(quotas.get("cpu")),
            memory_text=str(quotas.get("memory")),
        ),
    )


def _mapping(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _items(*, value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []
