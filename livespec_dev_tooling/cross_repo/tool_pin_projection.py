"""Project a released ShellCheck pin into a fleet consumer's mise config.

The fleet bump action is executable TOOLING from a support checkout that can be
newer than the release it is fanning out. Pin DATA therefore comes from the
exact released tag's `.mise.toml`, passed here separately from the consumer
file. The pure `project_shellcheck_pin` core scopes both reads to `[tools]`,
requires one exact semver in the release, and preserves an existing consumer
pin's indentation and comment.

`main()` is the composite Action's I/O boundary. It reads the two paths from
environment variables, writes only the consumer file on success, and emits a
GitHub Actions error annotation on a refused projection.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402

from livespec_dev_tooling.cross_repo.fabro_image_pin_rewrite import (  # noqa: E402
    tag_version_component,
)

__all__: list[str] = ["ToolPinProjectionRefused", "project_shellcheck_pin"]

_ProjectionRefusal = Literal[
    "released-shellcheck-pin-missing",
    "consumer-tools-table-missing",
    "consumer-shellcheck-pin-ambiguous",
]


@dataclass(frozen=True, kw_only=True)
class ToolPinProjectionRefused:
    """A fail-closed tool-pin projection and its operator-relevant reason."""

    reason: _ProjectionRefusal


_RELEASED_PIN_RE = re.compile(r'^\s*shellcheck\s*=\s*"([^"]+)"\s*(?:#.*)?$')
_CONSUMER_PIN_RE = re.compile(r"^(\s*)shellcheck\s*=.*?(\s*(?:#.*)?)$")


def _tools_bounds(*, lines: list[str]) -> tuple[int, int] | None:
    header = next((index for index, line in enumerate(lines) if line.strip() == "[tools]"), None)
    if header is None:
        return None
    end = next(
        (
            index
            for index, line in enumerate(lines[header + 1 :], start=header + 1)
            if line.lstrip().startswith("[")
        ),
        len(lines),
    )
    return header, end


def _without_newline(*, line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _released_version(*, text: str) -> str | None:
    lines = text.splitlines(keepends=True)
    bounds = _tools_bounds(lines=lines)
    if bounds is None:
        return None
    header, end = bounds
    matches: list[str] = []
    for line in lines[header + 1 : end]:
        body, _newline = _without_newline(line=line)
        match = _RELEASED_PIN_RE.fullmatch(body)
        if match is not None:
            candidate = match.group(1)
            if tag_version_component(tag=f"v{candidate}") == f"v{candidate}":
                matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def project_shellcheck_pin(
    *, released_mise_text: str, consumer_mise_text: str
) -> Result[str, ToolPinProjectionRefused]:
    """Return consumer mise text carrying the exact released ShellCheck pin.

    The release must declare exactly one quoted `X.Y.Z` ShellCheck value in its
    `[tools]` table. The consumer must have a `[tools]` table and at most one
    ShellCheck entry. All refusal shapes leave the consumer text untouched.
    """
    version = _released_version(text=released_mise_text)
    if version is None:
        return Failure(ToolPinProjectionRefused(reason="released-shellcheck-pin-missing"))

    lines = consumer_mise_text.splitlines(keepends=True)
    bounds = _tools_bounds(lines=lines)
    if bounds is None:
        return Failure(ToolPinProjectionRefused(reason="consumer-tools-table-missing"))
    header, end = bounds
    matches: list[tuple[int, re.Match[str], str]] = []
    for index in range(header + 1, end):
        body, newline = _without_newline(line=lines[index])
        match = _CONSUMER_PIN_RE.fullmatch(body)
        if match is not None:
            matches.append((index, match, newline))
    if len(matches) > 1:
        return Failure(ToolPinProjectionRefused(reason="consumer-shellcheck-pin-ambiguous"))
    if matches:
        index, match, newline = matches[0]
        lines[index] = f'{match.group(1)}shellcheck = "{version}"{match.group(2)}{newline}'
        return Success("".join(lines))

    newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
    insertion_index = end
    if end > header + 1 and lines[end - 1].strip() == "":
        insertion_index = end - 1
    if insertion_index > 0 and not lines[insertion_index - 1].endswith(("\n", "\r")):
        lines[insertion_index - 1] += newline
    lines.insert(insertion_index, f'shellcheck = "{version}"{newline}')
    return Success("".join(lines))


def main() -> int:
    """I/O boundary for the composite Action's tag-matched projection step."""
    released_path = Path(os.environ["RELEASED_MISE_FILE"])
    consumer_path = Path(os.environ["CONSUMER_MISE_FILE"])
    projected = project_shellcheck_pin(
        released_mise_text=released_path.read_text(encoding="utf-8"),
        consumer_mise_text=consumer_path.read_text(encoding="utf-8"),
    )
    if isinstance(projected, Failure):
        _ = sys.stderr.write(
            f"::error::cannot project released shellcheck pin: {projected.failure().reason}\n"
        )
        return 1
    _ = consumer_path.write_text(projected.unwrap(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
