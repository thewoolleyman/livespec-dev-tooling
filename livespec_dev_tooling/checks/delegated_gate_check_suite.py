"""Refuse a delegated gate suite whose pre-push slot runs a pre-commit aggregate.

The declared ``gate_check_suite`` is shared by the delegated pre-commit and
pre-push gates. The pre-commit route replaces only the final member, so that
member remains the pre-push slot in the declared suite. A pre-commit recipe
there would silently leave delegated pushes without the intended pre-push
aggregate.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import (  # noqa: E402  — vendor-path-aware import after sys.path insert.
    ConfigParseError,
    load_delegated_gate,
    load_gate_check_suite,
)

__all__: list[str] = []

CHECK_PURITY = "tree-pure"


_CHECK_ID = "delegated_gate_check_suite"
_FAIL_EXIT = 4
_PRE_COMMIT_RECIPES = frozenset({"check-pre-commit", "check-pre-commit-gated-tree"})
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=\S+")


def _recipe(*, entry: str) -> str | None:
    """Return an entry's first non-assignment token, if it has one."""
    for token in entry.split():
        if _ASSIGNMENT.fullmatch(token) is None:
            return token
    return None


def _configure_logger() -> structlog.stdlib.BoundLogger:
    """Configure the check's structured stderr logger."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(_CHECK_ID)


def main() -> int:
    """Refuse only the two pre-commit aggregates in a delegated final suite slot."""
    log = _configure_logger()
    try:
        delegated_gate = load_delegated_gate(repo_root=Path.cwd())
        gate_check_suite = load_gate_check_suite(repo_root=Path.cwd())
    except ConfigParseError:
        return 0
    if delegated_gate is not True or not gate_check_suite:
        return 0
    final_entry = gate_check_suite[-1]
    recipe = _recipe(entry=final_entry)
    if recipe not in _PRE_COMMIT_RECIPES:
        return 0
    log.error(
        " ".join(
            (
                "pyproject.toml gate_check_suite final entry is a pre-commit aggregate;",
                "the expected final pre-push recipe is check-pre-push",
            )
        ),
        check_id=_CHECK_ID,
        status="fail",
        path="pyproject.toml",
        key="gate_check_suite",
        final_entry=final_entry,
        recipe=recipe,
        expected_final_recipe="check-pre-push",
    )
    return _FAIL_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
