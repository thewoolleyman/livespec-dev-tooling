"""The expected job graph of a workflow, read from its source bytes at the merge revision.

An original incident run is collected against the jobs its workflow declares, so the
graph must come from the workflow at the merge, never from an operator's file or from
the jobs that happened to exist. The reader understands the block-style subset a
GitHub Actions workflow uses for job identity: `jobs`, each job's `name`, `needs` and
`strategy.matrix` dimensions. The package carries no YAML dependency, so anything the
reader cannot resolve with certainty (a reusable-workflow job, `include` / `exclude`,
a dynamic matrix, an expression in a name) refuses by name instead of omitting a job.
"""

from __future__ import annotations

import itertools
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling._incident_run_types import EvidenceRefusal, ExpectedJob

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from returns.pipeline import is_successful  # noqa: E402
from returns.result import safe  # noqa: E402

__all__: list[str] = ["derive_graph"]

_KEY = re.compile(r"""^(?P<key>"[^"]+"|'[^']+'|[\w.-]+):(?:\s+(?P<value>\S.*))?$""")
_MATRIX_REF = re.compile(r"\$\{\{\s*matrix\.([\w-]+)\s*\}\}")
_UNSUPPORTED_DIMENSIONS = frozenset({"include", "exclude"})


class _UnresolvableError(Exception):
    """The workflow cannot be resolved with certainty; the detail names what and why."""

    def __init__(self, *, subject: str, reason: str) -> None:
        super().__init__(f"{subject} {reason}")


@dataclass(frozen=True, kw_only=True)
class _Line:
    indent: int
    text: str


@dataclass(frozen=True, kw_only=True)
class _Entry:
    key: str
    value: str
    children: tuple[_Line, ...]


@dataclass(frozen=True, kw_only=True)
class _Job:
    job_id: str
    name: str | None
    needs: tuple[str, ...]
    dimensions: tuple[tuple[str, tuple[str, ...]], ...]


def _strip_comment(*, text: str) -> str:
    """Drop a trailing ` #` comment that sits outside quotes."""
    quote = ""
    for index, character in enumerate(text):
        if quote:
            quote = "" if character == quote else quote
        elif character in "\"'":
            quote = character
        elif character == "#" and (index == 0 or text[index - 1] in " \t"):
            return text[:index]
    return text


def _lines(*, source: str) -> tuple[_Line, ...]:
    stripped = [_strip_comment(text=raw).rstrip() for raw in source.splitlines()]
    return tuple(
        _Line(indent=len(text) - len(text.lstrip(" ")), text=text.strip())
        for text in stripped
        if text.strip()
    )


def _scalar(*, value: str) -> str:
    text = value.strip()
    quoted = len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'"  # noqa: PLR2004
    return text[1:-1] if quoted else text


def _entries(*, lines: tuple[_Line, ...]) -> tuple[_Entry, ...]:
    """The mapping entries at a block's own indent, each with the lines nested under it."""
    indent = lines[0].indent if lines else 0
    rows: list[tuple[_Line, list[_Line]]] = []
    for line in lines:
        attaches = line.indent > indent or line.text.startswith("- ")
        if rows and attaches:
            rows[-1][1].append(line)
        else:
            rows.append((line, []))
    entries: list[_Entry] = []
    for head, children in rows:
        matched = _KEY.match(head.text)
        if matched is None:
            raise _UnresolvableError(subject=head.text, reason="is not a mapping entry")
        value = matched.group("value") or ""
        entries.append(
            _Entry(key=_scalar(value=matched.group("key")), value=value, children=tuple(children))
        )
    return tuple(entries)


def _listing(*, entry: _Entry) -> tuple[str, ...]:
    """A scalar, a one-line flow list or a block list of scalars."""
    value = entry.value
    if value and entry.children:
        raise _UnresolvableError(subject=entry.key, reason="has nested lines after an inline value")
    if value.startswith("["):
        if not value.endswith("]"):
            raise _UnresolvableError(
                subject=entry.key, reason="flow list is not closed on its line"
            )
        return tuple(_scalar(value=part) for part in value[1:-1].split(",") if part.strip())
    if value:
        return (_scalar(value=value),)
    items = [line.text for line in entry.children]
    if not all(item.startswith("- ") and ":" not in item for item in items):
        raise _UnresolvableError(subject=entry.key, reason="is not a list of scalars")
    return tuple(_scalar(value=item.removeprefix("- ")) for item in items)


def _dimensions(*, strategy: _Entry | None) -> tuple[tuple[str, tuple[str, ...]], ...]:
    matrices = (
        [entry for entry in _entries(lines=strategy.children) if entry.key == "matrix"]
        if strategy
        else []
    )
    if not matrices:
        return ()
    if matrices[0].value:
        raise _UnresolvableError(subject="matrix", reason="is not spelled out as dimensions")
    dimensions: list[tuple[str, tuple[str, ...]]] = []
    for entry in _entries(lines=matrices[0].children):
        values = _listing(entry=entry)
        if entry.key in _UNSUPPORTED_DIMENSIONS or not values or any("${{" in v for v in values):
            raise _UnresolvableError(
                subject=entry.key, reason="matrix dimension cannot be expanded"
            )
        dimensions.append((entry.key, values))
    return tuple(dimensions)


def _job(*, entry: _Entry) -> _Job:
    fields = {item.key: item for item in _entries(lines=entry.children)}
    if "uses" in fields:
        raise _UnresolvableError(subject=entry.key, reason="job calls a reusable workflow")
    name = fields.get("name")
    needs = fields.get("needs")
    return _Job(
        job_id=entry.key,
        name=_scalar(value=name.value) if name else None,
        needs=_listing(entry=needs) if needs else (),
        dimensions=_dimensions(strategy=fields.get("strategy")),
    )


def _leg_name(*, job: _Job, leg: dict[str, str]) -> str:
    if job.name is None:
        return f"{job.job_id} ({', '.join(leg.values())})" if leg else job.job_id
    resolved = _MATRIX_REF.sub(lambda found: leg.get(found.group(1), found.group(0)), job.name)
    if "${{" in resolved:
        raise _UnresolvableError(
            subject=job.job_id, reason=f"job name {job.name} is not resolvable"
        )
    return resolved


def _legs(*, job: _Job) -> tuple[dict[str, str], ...]:
    keys = [key for key, _values in job.dimensions]
    product = itertools.product(*(values for _key, values in job.dimensions))
    return tuple(dict(zip(keys, combination, strict=True)) for combination in product)


@safe
def _graph(*, source: bytes) -> tuple[ExpectedJob, ...]:
    block = _lines(source=source.decode("utf-8"))
    top = [index for index, line in enumerate(block) if line == _Line(indent=0, text="jobs:")]
    if not top:
        if any(line.indent == 0 and line.text == "jobs: {}" for line in block):
            return ()
        raise _UnresolvableError(subject="workflow", reason="has no block-style jobs section")
    section = tuple(itertools.takewhile(lambda line: line.indent > 0, block[top[0] + 1 :]))
    jobs = [_job(entry=entry) for entry in _entries(lines=section)]
    names = {
        job.job_id: [_leg_name(job=job, leg=leg) for leg in _legs(job=job) or ({},)] for job in jobs
    }
    flat = [name for legs in names.values() for name in legs]
    if len(set(flat)) != len(flat):
        raise _UnresolvableError(subject="jobs", reason="resolve to the same name")
    unknown = sorted({need for job in jobs for need in job.needs} - names.keys())
    if unknown:
        raise _UnresolvableError(subject="needs", reason="name no job: " + ", ".join(unknown))
    return tuple(
        ExpectedJob(name=name, needs=tuple(n for need in job.needs for n in names[need]))
        for job in jobs
        for name in names[job.job_id]
    )


def derive_graph(*, source: bytes) -> tuple[ExpectedJob, ...] | EvidenceRefusal:
    """Every job the workflow declares, matrix legs expanded, or a refusal naming why not."""
    result = _graph(source=source)
    if is_successful(result):
        return result.unwrap()
    return EvidenceRefusal(
        code="incident-original-run-graph-unsupported", detail=str(result.failure())
    )
