"""Read job-level container-image declarations from a GitHub Actions workflow.

The CI conformance check and delegated-gate renderer share this dependency-free
reader so the image the gate runs cannot drift from the images CI declares.
"""

from __future__ import annotations

import re

__all__: list[str] = ["container_images"]

_CONTAINER_KEY = re.compile(r"^(?P<indent>[ \t]*)container:[ \t]*(?P<value>.*)$")
_IMAGE_KEY = re.compile(r"^[ \t]*image:[ \t]*(?P<value>.*)$")
_QUOTED = re.compile(r"""^(?P<quote>["'])(?P<body>.*?)(?P=quote)""")
_TRAILING_COMMENT = re.compile(r"[ \t]+#.*$")


def _reference(*, raw: str) -> str:
    """The image reference a YAML scalar names, without quotes or a trailing comment."""
    quoted = _QUOTED.match(raw)
    if quoted is not None:
        return quoted.group("body")
    return _TRAILING_COMMENT.sub("", raw).strip()


def _indent_of(*, line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _block_image(*, lines: list[str], start: int, parent_indent: int) -> tuple[int, str] | None:
    """The direct-child `image:` in the `container:` block opened above `start`."""
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


def container_images(*, source: str) -> list[tuple[int, str]]:
    """Every nonempty job `container:` image, as a (1-based line, reference) pair."""
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
        if block is not None and block[1]:
            declared.append(block)
    return declared
