"""Refuse a Rule-26 mutation kill matrix reachable from ``just check``."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []

CHECK_PURITY = "tree-pure"

_JUSTFILE = Path("justfile")
_AGGREGATE = "check"
_FORBIDDEN_RECIPE = "mutation-kill-matrix"
_HEADER = re.compile(
    r"""^(?!@?[A-Za-z0-9_-]+[ \t]*:=)@?(?P<name>[A-Za-z0-9_-]+)
(?=[ \t:])[^\n]*?:(?!=)(?P<dependencies>.*)$""".replace("\n", "")
)
_RECIPE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


def _recipe_graph(*, justfile_text: str) -> dict[str, set[str]]:
    """Return the aggregate's declared dependency and target-array edges."""
    graph: dict[str, set[str]] = {}
    current_recipe: str | None = None
    in_check_targets = False
    for raw_line in justfile_text.splitlines():
        header = _HEADER.match(raw_line)
        if header is not None:
            current_recipe = cast(str, header["name"])
            graph.setdefault(current_recipe, set()).update(
                _RECIPE_NAME.findall(cast(str, header["dependencies"]).split("#", maxsplit=1)[0])
            )
            in_check_targets = False
            continue
        if current_recipe != _AGGREGATE:
            continue
        line = raw_line.strip().split("#", maxsplit=1)[0].strip()
        if line == "targets=(":
            in_check_targets = True
            continue
        if line == ")":
            in_check_targets = False
            continue
        if in_check_targets and _RECIPE_NAME.fullmatch(line) is not None:
            graph[_AGGREGATE].add(line)
    return graph


def _is_reachable(*, graph: dict[str, set[str]], target: str) -> bool:
    """Whether ``target`` is a transitive dependency of the ``check`` recipe."""
    visited = {_AGGREGATE}
    pending = list(graph.get(_AGGREGATE, set()))
    while pending:
        recipe = pending.pop()
        if recipe == target:
            return True
        visited.add(recipe)
        pending.extend(graph.get(recipe, set()).difference(visited))
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
    return structlog.get_logger("rule_26_keep_out")


def main() -> int:
    """Fail only when the on-demand mutation recipe is reachable from ``check``."""
    justfile = Path.cwd() / _JUSTFILE
    if not justfile.is_file():
        return 0
    graph = _recipe_graph(justfile_text=justfile.read_text(encoding="utf-8"))
    if not _is_reachable(graph=graph, target=_FORBIDDEN_RECIPE):
        return 0
    _configure_logger().error(
        "Rule-26 keep-out violation: mutation-kill-matrix is reachable from just check aggregate",
        aggregate="just check",
        recipe=_FORBIDDEN_RECIPE,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
