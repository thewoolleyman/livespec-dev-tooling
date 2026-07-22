"""source_trees_scoped_to_consumer — guard against copied core path drift.

Every configured layout role must point at a path that exists in the
consumer repo, and only livespec core itself — the repo whose
`[project].name` is `livespec` — may scope roles to core's
`.claude-plugin/scripts/livespec` package tree.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import Config, load_config, load_project_name  # noqa: E402

__all__: list[str] = []


_CORE_PACKAGE_TREE = Path(".claude-plugin") / "scripts" / "livespec"
_CORE_PROJECT_NAME = "livespec"


class _DeclaredPath(NamedTuple):
    """One repo-root-relative path declared by a config role."""

    role: str
    path: Path


class _Finding(NamedTuple):
    """One scope drift finding."""

    role: str
    path: Path
    failure_mode: str


def _iter_role_paths(*, config: Config) -> tuple[_DeclaredPath, ...]:
    out: list[_DeclaredPath] = []
    for role, paths in (
        ("source_trees", config.source_trees),
        ("io_trees", config.io_trees),
        ("commands_trees", config.commands_trees),
        ("pure_trees", config.pure_trees),
        ("covered_trees", config.covered_trees),
        ("target_dirs", config.target_dirs),
    ):
        out.extend(_DeclaredPath(role=role, path=path) for path in paths)
    out.extend(
        _DeclaredPath(role="source_tree_prefixes", path=Path(prefix.rstrip("/")))
        for prefix in config.source_tree_prefixes
    )
    for pairing in config.mirror_pairings:
        out.append(_DeclaredPath(role="mirror_pairings.source_tree", path=pairing.source_tree))
        out.append(_DeclaredPath(role="mirror_pairings.test_tree", path=pairing.test_tree))
    return tuple(out)


def _has_foreign_package_drift(*, declared: Path, is_core_repo: bool) -> bool:
    if not declared.is_relative_to(_CORE_PACKAGE_TREE):
        return False
    return not is_core_repo


def _find_scope_drift(
    *, declared_paths: Iterable[_DeclaredPath], repo_root: Path
) -> tuple[_Finding, ...]:
    is_core_repo = load_project_name(repo_root=repo_root) == _CORE_PROJECT_NAME
    findings: list[_Finding] = []
    for declared in declared_paths:
        if not (repo_root / declared.path).exists():
            findings.append(
                _Finding(role=declared.role, path=declared.path, failure_mode="missing")
            )
        if _has_foreign_package_drift(declared=declared.path, is_core_repo=is_core_repo):
            findings.append(
                _Finding(
                    role=declared.role,
                    path=declared.path,
                    failure_mode="foreign_package",
                )
            )
    return tuple(findings)


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("source_trees_scoped_to_consumer")
    repo_root = Path.cwd()
    config = load_config(repo_root=repo_root)
    findings = _find_scope_drift(
        declared_paths=_iter_role_paths(config=config),
        repo_root=repo_root,
    )
    for finding in findings:
        log.error(
            "configured source-tree role is not scoped to this consumer",
            role=finding.role,
            path=finding.path.as_posix(),
            failure_mode=finding.failure_mode,
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
