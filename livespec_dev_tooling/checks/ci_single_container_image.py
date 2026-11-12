"""ci_single_container_image — a consumer's CI workflow declares ONE container image.

A delegated gate Job runs in the one image
`ci-runner/k3s/phase2/gates/render-gate-job.sh` resolves from the consumer's
`.github/workflows/ci.yml`, and that script refuses a workflow declaring several
("declares 2 distinct container images ... Refusing to guess"). Nothing in a pull
request's own CI checked for the shape, so a job written against a superseded
image merged green on 2026-11-05 (livespec-orchestrator-beads-fabro#4439) and then
refused every push and post-merge janitor off that repository's master until a
single pin was restored. This check is the same single-image rule, run by every
consumer in its `just check` aggregate, so the failure shows in the offending
pull request's CI instead of in other sessions' pushes.

It reads each job's `container:` declaration, in either YAML shape (the
`container: <image>` scalar, or a block whose `image:` key is its first-level
child, wherever it sits among the block's keys), and groups the lines by image
reference. Every reference must name one image repository and one release
version; the check fails otherwise, naming each image and every line that
declares it. Flavors may differ only as a layering: one flavor, the gate flavor,
must be a dash-separated prefix of every other flavor named, and a job on any
other flavor must run no target of the repository's `just check` aggregate (the
bare `just check` included). No gate flavor, or a non-gate job running an
aggregate target, fails. A service container's `image:` and a step input named
`image` are not job `container:` images and contribute nothing. A repository
with no `.github/workflows/ci.yml` has no workflow to judge and passes.

FAIL-BY-DEFAULT: the spec says MUST fail, so there is no severity lever.

Output discipline: per spec, `print` and direct `sys.stderr.write` are banned in
this package; diagnostics flow through structlog (JSON to stderr) per the
vendor-path-aware import below.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.cross_repo.fabro_image_pin_rewrite import (  # noqa: E402
    tag_version_component,
)

__all__: list[str] = []

CHECK_PURITY = "tree-pure"


_CI_WORKFLOW_PATH = Path(".github") / "workflows" / "ci.yml"
_CONTAINER_KEY = re.compile(r"^(?P<indent>[ \t]*)container:[ \t]*(?P<value>.*)$")
_IMAGE_KEY = re.compile(r"^[ \t]*image:[ \t]*(?P<value>.*)$")
_QUOTED = re.compile(r"""^(?P<quote>["'])(?P<body>.*?)(?P=quote)""")
_TRAILING_COMMENT = re.compile(r"[ \t]+#.*$")
_JOB_KEY = re.compile(r"^[ \t]{2}(?P<name>[^ \t:#][^:]*):[ \t]*(?:#.*)?$")
_JUST_TARGET = re.compile(r"\bjust[ \t]+(?P<target>check(?:-[a-z0-9-]+)?)\b")
_TARGET = re.compile(r"^check(?:-[a-z0-9-]+)?$")
_HINT = (
    "Every job must name one image repository and release version. Layered flavors are "
    "allowed only off the gate path, beneath a dash-separated gate-flavor prefix."
)


@dataclass(frozen=True, kw_only=True)
class _Image:
    """A job container image plus the job's source span."""

    image: str
    line: int
    job_start: int
    job_end: int


def _reference(*, raw: str) -> str:
    """The image reference a YAML scalar names, without quotes or a trailing comment."""
    quoted = _QUOTED.match(raw)
    if quoted is not None:
        return quoted.group("body")
    return _TRAILING_COMMENT.sub("", raw).strip()


def _indent_of(*, line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _block_image(*, lines: list[str], start: int, parent_indent: int) -> tuple[int, str] | None:
    """The `image:` that is a direct child of the `container:` block opened above `start`."""
    child_indent: int | None = None
    for offset, line in enumerate(lines[start:], start=start):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = _indent_of(line=line)
        if indent <= parent_indent:
            return None
        if child_indent is None:
            child_indent = indent
        match = _IMAGE_KEY.match(line)
        if indent == child_indent and match is not None:
            return offset + 1, _reference(raw=match.group("value"))
    return None


def _job_span(*, lines: list[str], index: int) -> tuple[int, int] | None:
    """The half-open span of the job that contains line ``index``."""
    job_start: int | None = None
    for candidate in range(index, -1, -1):
        if _JOB_KEY.match(lines[candidate]) is not None:
            job_start = candidate
            break
    if job_start is None:
        return None
    for job_end in range(job_start + 1, len(lines)):
        if _JOB_KEY.match(lines[job_end]) is not None:
            return job_start, job_end
    return job_start, len(lines)


def _container_images(*, source: str) -> list[_Image]:
    """Every job `container:` image in the workflow, with its job's source span."""
    lines = source.splitlines()
    declared: list[_Image] = []
    for index, line in enumerate(lines):
        match = _CONTAINER_KEY.match(line)
        if match is None:
            continue
        scalar = _reference(raw=match.group("value"))
        job = _job_span(lines=lines, index=index)
        if job is None:
            continue
        if scalar:
            declared.append(_Image(image=scalar, line=index + 1, job_start=job[0], job_end=job[1]))
            continue
        block = _block_image(lines=lines, start=index + 1, parent_indent=len(match.group("indent")))
        if block is not None:
            lineno, image = block
            declared.append(_Image(image=image, line=lineno, job_start=job[0], job_end=job[1]))
    return declared


def _aggregate_targets(*, repo_root: Path) -> set[str]:
    """The ``check`` aggregate itself plus its enumerable member targets."""
    inventory = repo_root / "check-targets.txt"
    try:
        source = inventory.read_text(encoding="utf-8")
    except OSError:
        try:
            source = (repo_root / "justfile").read_text(encoding="utf-8")
        except OSError:
            return set()
    entries = {line.split("#", maxsplit=1)[0].strip() for line in source.splitlines()}
    return {"check"} | {entry for entry in entries if _TARGET.fullmatch(entry)}


def _image_parts(*, image: str) -> tuple[str, str, str] | None:
    """The image repository, layer flavor, and release version a pin names."""
    repository, separator, tag = image.rpartition(":")
    version = tag_version_component(tag=tag) if separator else None
    if version is None:
        return None
    anchor = f"-{version}"
    if not tag.endswith(anchor):
        return None
    flavor = tag.removesuffix(anchor)
    if not flavor:
        return None
    return repository, flavor, version


def _has_gate_flavor(*, flavors: set[str]) -> str | None:
    """The flavor that is a dash-separated prefix of all declared flavors."""
    for candidate in sorted(flavors, key=len):
        if all(flavor == candidate or flavor.startswith(f"{candidate}-") for flavor in flavors):
            return candidate
    return None


def _runs_aggregate_target(*, lines: list[str], image: _Image, aggregate: set[str]) -> bool:
    """Whether this image's job runs any declared aggregate target."""
    for line in lines[image.job_start : image.job_end]:
        for matched in _JUST_TARGET.finditer(line):
            if matched.group("target") in aggregate:
                return True
    return False


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("ci_single_container_image")


def main() -> int:
    log = _configure_logger()
    workflow = Path.cwd() / _CI_WORKFLOW_PATH
    if not workflow.is_file():
        log.info(
            "no CI workflow to judge",
            check_id="ci-single-container-image",
            path=str(_CI_WORKFLOW_PATH),
        )
        return 0
    source = workflow.read_text(encoding="utf-8")
    images = _container_images(source=source)
    if not images:
        return 0
    lines_by_image: dict[str, list[int]] = {}
    for image in images:
        lines_by_image.setdefault(image.image, []).append(image.line)
    parts = {image.image: _image_parts(image=image.image) for image in images}
    valid_parts = [part for part in parts.values() if part is not None]
    repositories = {part[0] for part in valid_parts}
    versions = {part[2] for part in valid_parts}
    flavors = {part[1] for part in valid_parts}
    gate_flavor = _has_gate_flavor(flavors=flavors)
    aggregate = _aggregate_targets(repo_root=Path.cwd())
    non_gate_runs_aggregate = False
    if gate_flavor is not None:
        for image in images:
            part = parts[image.image]
            if part is not None and part[1] != gate_flavor:
                non_gate_runs_aggregate = _runs_aggregate_target(
                    lines=source.splitlines(), image=image, aggregate=aggregate
                )
            if non_gate_runs_aggregate:
                break
    invalid = (
        any(part is None for part in parts.values())
        or len(repositories) > 1
        or len(versions) > 1
        or gate_flavor is None
        or non_gate_runs_aggregate
    )
    if not invalid:
        return 0
    for image, lines in sorted(lines_by_image.items()):
        log.error(
            "CI workflow violates the single-container-image gate rule",
            check_id="ci-single-container-image",
            path=str(_CI_WORKFLOW_PATH),
            image=image,
            lines=lines,
            distinct_images=len(lines_by_image),
            hint=_HINT,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
