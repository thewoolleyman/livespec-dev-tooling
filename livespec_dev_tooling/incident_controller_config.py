"""Validation primitives for the protected controller configuration."""

from __future__ import annotations

import re

__all__: list[str] = ["valid_branch_name", "valid_freshness_bound"]

_BRANCH_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*")


def valid_branch_name(*, name: object) -> bool:
    """Accept one plain branch name, never a revision expression or lock path."""
    return (
        isinstance(name, str)
        and _BRANCH_NAME.fullmatch(name) is not None
        and ".." not in name
        and not any(part.endswith(".lock") for part in name.split("/"))
    )


def valid_freshness_bound(*, value: object) -> bool:
    """Accept a non-negative committed freshness bound, but never a boolean."""
    return type(value) is int and value >= 0
