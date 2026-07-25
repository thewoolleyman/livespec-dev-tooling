"""Shared role-key gating for layout-dependent checks."""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import Config, iter_py_files  # noqa: E402

__all__: list[str] = [
    "ensure_declared_paths_contain_python",
    "role_key_gate_exit_code",
    "role_key_paths_exit_code",
    "source_trees_exit_code",
]

_UNDECLARED_ROLE_KEY_MESSAGE = " ".join(
    (
        "role key undeclared — declare the real tree, or declare it explicitly",
        "empty with a comment giving the reason",
    )
)


def role_key_gate_exit_code(
    *,
    config: Config,
    key: str,
    value_is_empty: bool,
    log: structlog.stdlib.BoundLogger,
    check_id: str,
) -> int | None:
    """Return the early exit for an undeclared or declared-empty role key."""
    if key not in config.declared_keys:
        log.error(
            _UNDECLARED_ROLE_KEY_MESSAGE,
            check_id=check_id,
            role=key,
        )
        return 1
    if value_is_empty:
        log.info(
            "role key declared empty — sanctioned opt-out",
            check_id=check_id,
            role=key,
        )
        return 0
    return None


def ensure_declared_paths_contain_python(
    *,
    repo_root: Path,
    key: str,
    paths: tuple[Path, ...],
    log: structlog.stdlib.BoundLogger,
    check_id: str,
) -> bool:
    """Return False after logging when declared paths contain no `.py` files."""
    for path in paths:
        if any(iter_py_files(root=repo_root / path)):
            return True
    log.error(
        "declared role key resolves to no Python files",
        check_id=check_id,
        role=key,
        paths=[path.as_posix() for path in paths],
    )
    return False


def role_key_paths_exit_code(
    *,
    config: Config,
    key: str,
    paths: tuple[Path, ...],
    repo_root: Path,
    log: structlog.stdlib.BoundLogger,
    check_id: str,
) -> int | None:
    """Return the early exit for a role key and its declared Python paths."""
    gate_exit = role_key_gate_exit_code(
        config=config,
        key=key,
        value_is_empty=not paths,
        log=log,
        check_id=check_id,
    )
    if gate_exit is not None:
        return gate_exit
    if not ensure_declared_paths_contain_python(
        repo_root=repo_root,
        key=key,
        paths=paths,
        log=log,
        check_id=check_id,
    ):
        return 1
    return None


def source_trees_exit_code(
    *,
    config: Config,
    repo_root: Path,
    log: structlog.stdlib.BoundLogger,
    check_id: str,
) -> int | None:
    """Return the early exit for a `source_trees` role-key gate."""
    return role_key_paths_exit_code(
        config=config,
        key="source_trees",
        paths=config.source_trees,
        repo_root=repo_root,
        log=log,
        check_id=check_id,
    )
