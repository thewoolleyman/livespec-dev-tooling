"""Workflow parsing for the layered container-image check."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = ["ContainerImage", "aggregate_targets", "container_images"]

_CONTAINER_KEY = re.compile(r"^(?P<indent>[ \t]*)container:[ \t]*(?P<value>.*)$")
_IMAGE_KEY = re.compile(r"^[ \t]*image:[ \t]*(?P<value>.*)$")
_QUOTED = re.compile(r"""^(?P<quote>["'])(?P<body>.*?)(?P=quote)""")
_TRAILING_COMMENT = re.compile(r"[ \t]+#.*$")
_JOB_KEY = re.compile(r"^[ \t]{2}(?P<name>[^ \t:#][^:]*):[ \t]*(?:#.*)?$")
_CHECK_RECIPE = re.compile(r"^check(?:[ \t]+[^:]*)?:[ \t]*(?P<dependencies>.*)$")
_RECIPE_HEADER = re.compile(r"^[^ \t#:][^:]*:[ \t]*(?:#.*)?$")


@dataclass(frozen=True, kw_only=True)
class ContainerImage:
    """A job container image plus the job's source span."""

    image: str
    line: int
    job_start: int
    job_end: int


def _reference(*, raw: str) -> str:
    quoted = _QUOTED.match(raw)
    if quoted is not None:
        return quoted.group("body")
    return _TRAILING_COMMENT.sub("", raw).strip()


def _indent_of(*, line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _block_image(*, lines: list[str], start: int, parent_indent: int) -> tuple[int, str] | None:
    """Find the direct-child ``image:`` key of a ``container:`` block."""
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
    """Find the half-open span of the job containing ``index``."""
    job_start = next(
        (
            candidate
            for candidate in range(index, -1, -1)
            if _JOB_KEY.match(lines[candidate]) is not None
        ),
        None,
    )
    if job_start is None:
        return None
    job_end = next(
        (
            candidate
            for candidate in range(job_start + 1, len(lines))
            if _JOB_KEY.match(lines[candidate])
        ),
        len(lines),
    )
    return job_start, job_end


def container_images(*, source: str) -> list[ContainerImage]:
    """Return each job-level container image with its source and job spans."""
    lines = source.splitlines()
    declared: list[ContainerImage] = []
    for index, line in enumerate(lines):
        match = _CONTAINER_KEY.match(line)
        if match is None:
            continue
        job = _job_span(lines=lines, index=index)
        if job is None:
            continue
        scalar = _reference(raw=match.group("value"))
        if scalar:
            declared.append(
                ContainerImage(image=scalar, line=index + 1, job_start=job[0], job_end=job[1])
            )
            continue
        block = _block_image(lines=lines, start=index + 1, parent_indent=len(match.group("indent")))
        if block is not None:
            line_number, image = block
            declared.append(
                ContainerImage(image=image, line=line_number, job_start=job[0], job_end=job[1])
            )
    return declared


def _check_recipe_targets(*, source: str) -> list[str]:
    """Return the dependencies and body targets in the ``check`` recipe."""
    entries: list[str] = []
    in_check_recipe = False
    for line in source.splitlines():
        if match := _CHECK_RECIPE.match(line):
            in_check_recipe = True
            entries.extend(match.group("dependencies").split())
            continue
        if _RECIPE_HEADER.match(line):
            in_check_recipe = False
        if in_check_recipe:
            entries.append(line.strip())
    return entries


def aggregate_targets(*, repo_root: Path) -> set[str]:
    """Return the ``check`` aggregate itself plus its enumerable members."""
    try:
        entries = (repo_root / "check-targets.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        try:
            entries = _check_recipe_targets(
                source=(repo_root / "justfile").read_text(encoding="utf-8")
            )
        except OSError:
            return set()
    targets = {entry.split("#", maxsplit=1)[0].strip() for entry in entries}
    return {"check"} | {target for target in targets if target}
