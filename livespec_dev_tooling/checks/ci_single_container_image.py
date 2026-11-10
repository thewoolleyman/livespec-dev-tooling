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
reference. Two or more distinct references fail the check, naming each distinct
image and every line that declares it. One reference, or no container at all,
passes. A service container's `image:` and a step input named `image` are not job
`container:` images and contribute nothing. A repository with no
`.github/workflows/ci.yml` has no workflow to judge and passes.

FAIL-BY-DEFAULT: the spec says MUST fail, so there is no severity lever.

Output discipline: per spec, `print` and direct `sys.stderr.write` are banned in
this package; diagnostics flow through structlog (JSON to stderr) per the
vendor-path-aware import below.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []

CHECK_PURITY = "tree-pure"


_CI_WORKFLOW_PATH = Path(".github") / "workflows" / "ci.yml"
_CONTAINER_KEY = re.compile(r"^(?P<indent>[ \t]*)container:[ \t]*(?P<value>.*)$")
_IMAGE_KEY = re.compile(r"^[ \t]*image:[ \t]*(?P<value>.*)$")
_QUOTED = re.compile(r"""^(?P<quote>["'])(?P<body>.*?)(?P=quote)""")
_TRAILING_COMMENT = re.compile(r"[ \t]+#.*$")
# Two distinct references are the smallest set a delegated gate Job cannot resolve.
_MIN_CONFLICTING_IMAGES = 2
_HINT = (
    "A delegated gate Job runs in the one image it resolves from this workflow, and "
    "`render-gate-job.sh` refuses a workflow that declares several. Pin every job "
    "`container:` to the same image reference."
)


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


def _container_images(*, source: str) -> list[tuple[int, str]]:
    """Every job `container:` image in the workflow, as (1-based line, reference)."""
    lines = source.splitlines()
    declared: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = _CONTAINER_KEY.match(line)
        if match is None:
            continue
        scalar = _reference(raw=match.group("value"))
        if scalar:
            declared.append((index + 1, scalar))
            continue
        block = _block_image(lines=lines, start=index + 1, parent_indent=len(match.group("indent")))
        if block is not None:
            declared.append(block)
    return declared


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
    lines_by_image: dict[str, list[int]] = {}
    for lineno, image in _container_images(source=workflow.read_text(encoding="utf-8")):
        lines_by_image.setdefault(image, []).append(lineno)
    if len(lines_by_image) < _MIN_CONFLICTING_IMAGES:
        return 0
    for image, lines in sorted(lines_by_image.items()):
        log.error(
            "CI workflow declares more than one distinct job container image",
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
