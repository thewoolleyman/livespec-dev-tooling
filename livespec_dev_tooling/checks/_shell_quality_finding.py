"""The shell-quality finding record, shared by the check's two finding sources.

`shell_quality` assembles one verdict from two INDEPENDENT sources — the
ShellCheck substrate and the justfile recipe policy in
`_shell_quality_recipes` — and renders both through a single structlog stream,
so the record they share belongs to neither of them. Keeping it in the check
module would make the recipe module import its own consumer; keeping it in the
recipe module would put the shared rendering shape under a concern that is only
one of its two producers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = [
    "Finding",
]


@dataclass(frozen=True, kw_only=True)
class Finding:
    reason: str
    path: Path
    line: int
    recipe: str | None = None
    binary_name: str | None = None
    required_version: str | None = None
    remedy: str | None = None
    code: str | None = None
    severity: str | None = None
    construct: str | None = None
