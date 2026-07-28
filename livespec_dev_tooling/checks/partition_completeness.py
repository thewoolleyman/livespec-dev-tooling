"""partition_completeness — Phase-0 first-party file role partition check.

PR4 of the `fleet-check-coverage` thread adds a meta-check over the
git-derived first-party Python universe. Every first-party `.py` file
must be claimed by exactly one configured role, or the repo receives a
Phase-0 warning naming the file. During Phase 0 this check NEVER fails:
it emits structured warnings for the fleet worklist and exits 0. A later
phase can promote these diagnostics to hard failures once consumers have
closed their gaps.

Role model:

- Specific semantic roles (`io_trees`, `commands_trees`,
  `supervisor_entry_files`, `dataclasses_tree`, `pure_trees`) are
  counted directly.
- Broad applicability roles (`source_trees`, `covered_trees`,
  `target_dirs`, `mirror_pairings`, `source_tree_prefixes`) are a
  fallback only when no specific role claims the file. Multiple broad
  matches collapse to one fallback claim, so a repo that declares both
  `source_trees = ["pkg"]` and `target_dirs = ["pkg"]` does not receive
  duplicate noise.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`. Passing repos are silent.
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

from livespec_dev_tooling.config import (  # noqa: E402
    Config,
    load_config,
    resolve_check_universe,
    role_path,
    role_prefixes,
    role_trees,
)

__all__: list[str] = []


class _Claim(NamedTuple):
    """One effective semantic ownership claim for a first-party Python file."""

    role: str
    scope: str


def _claim_label(*, claim: _Claim) -> str:
    return f"{claim.role}:{claim.scope}"


def _tree_claims(*, rel: Path, role: str, trees: Iterable[Path]) -> tuple[_Claim, ...]:
    return tuple(
        _Claim(role=role, scope=tree.as_posix()) for tree in trees if rel.is_relative_to(tree)
    )


def _specific_claims(*, rel: Path, config: Config) -> tuple[_Claim, ...]:
    claims: list[_Claim] = []
    claims.extend(_tree_claims(rel=rel, role="io_trees", trees=config.io_trees))
    claims.extend(_tree_claims(rel=rel, role="commands_trees", trees=config.commands_trees))
    if rel in config.supervisor_entry_files:
        claims.append(_Claim(role="supervisor_entry_files", scope=rel.as_posix()))
    dataclasses_tree = role_path(role=config.dataclasses_tree)
    if dataclasses_tree is not None and rel.is_relative_to(dataclasses_tree):
        claims.append(_Claim(role="dataclasses_tree", scope=dataclasses_tree.as_posix()))
    claims.extend(
        _tree_claims(rel=rel, role="pure_trees", trees=role_trees(role=config.pure_trees))
    )
    return tuple(claims)


def _broad_claims(*, rel: Path, config: Config) -> tuple[_Claim, ...]:
    claims: list[_Claim] = []
    claims.extend(_tree_claims(rel=rel, role="source_trees", trees=config.source_trees))
    claims.extend(_tree_claims(rel=rel, role="covered_trees", trees=config.covered_trees))
    claims.extend(
        _tree_claims(rel=rel, role="target_dirs", trees=role_trees(role=config.target_dirs))
    )
    for pairing in config.mirror_pairings:
        if rel.is_relative_to(pairing.source_tree):
            claims.append(_Claim(role="mirror_pairings", scope=pairing.source_tree.as_posix()))
    rel_posix = rel.as_posix()
    for prefix in role_prefixes(role=config.source_tree_prefixes):
        if rel_posix.startswith(prefix):
            claims.append(_Claim(role="source_tree_prefixes", scope=prefix))
    return tuple(claims)


def _effective_claims(*, rel: Path, config: Config) -> tuple[_Claim, ...]:
    specific = _specific_claims(rel=rel, config=config)
    if specific:
        return specific
    broad = _broad_claims(rel=rel, config=config)
    if not broad:
        return ()
    scopes = ",".join(_claim_label(claim=claim) for claim in broad)
    return (_Claim(role="broad_roles", scope=scopes),)


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("partition_completeness")


def main() -> int:
    log = _configure_logger()
    root, universe = resolve_check_universe()
    config = load_config(repo_root=root)
    for rel in universe:
        claims = _effective_claims(rel=rel, config=config)
        if not claims:
            log.warning(
                "first-party Python file has no declared semantic role — "
                "newly git-derived coverage; Phase-0 WARN "
                "(hard-fails once this repo is flipped to the hard gate in Phase 2)",
                file=rel.as_posix(),
                partition_status="unclaimed",
                phase="0-warn",
                newly_covered=True,
            )
        elif len(claims) > 1:
            log.warning(
                "first-party Python file has multiple declared semantic roles — "
                "newly git-derived coverage; Phase-0 WARN "
                "(hard-fails once this repo is flipped to the hard gate in Phase 2)",
                file=rel.as_posix(),
                partition_status="multiple_claims",
                claims=[_claim_label(claim=claim) for claim in claims],
                phase="0-warn",
                newly_covered=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
