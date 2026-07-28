"""Shared role-key gating for layout-dependent checks."""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import (  # noqa: E402
    Config,
    ConventionNotAdopted,
    LegacyAmbiguousEmpty,
    NotApplicable,
    PrefixRole,
    RoleAbsence,
    ScalarRole,
    SupersededBy,
    TreeRole,
    UnarmedUntil,
    assert_never,
    iter_py_files,
    role_absence,
    role_prefixes,
    role_trees,
)

__all__: list[str] = [
    "ensure_declared_paths_contain_python",
    "resolve_role_prefixes",
    "resolve_role_trees",
    "role_absence_exit_code",
]

_LEGACY_AMBIGUOUS_MESSAGE = " ".join(
    (
        "role key uses the AMBIGUOUS legacy empty spelling — it cannot say whether the",
        "concept does not apply here or applies and is switched off; migrate to one of",
        "not_applicable / superseded_by / unarmed_until / convention_not_adopted",
    )
)
_LEGACY_SPELLING = "legacy-ambiguous-empty"
_MIGRATION_REF = "livespec-dev-tooling-8o8e.1"
_BLESSED = (
    "not_applicable",
    "superseded_by",
    "unarmed_until",
    "convention_not_adopted",
)
_UNDECLARED_ROLE_KEY_MESSAGE = " ".join(
    (
        "role key undeclared — declare the real value, or declare it absent with one of",
        "not_applicable / superseded_by / unarmed_until / convention_not_adopted, each",
        "carrying its reason in the value rather than in a comment",
    )
)


def _announce_absence(
    *,
    absence: RoleAbsence,
    key: str,
    log: structlog.stdlib.BoundLogger,
    check_id: str,
) -> None:
    """Log one declared-absent role key at the severity its variant earns.

    THE one exhaustive match over `RoleAbsence`. Every consuming check reaches it
    through `resolve_role_*` or `role_absence_exit_code`, so a new variant breaks
    the type gate here rather than silently inheriting "pass quietly" at a dozen
    call sites.

    The severities are deliberately NOT uniform. `legacy-ambiguous-empty` is a WARN
    because Phase 1's entire purpose is to make a previously INVISIBLE state
    countable before Phase 2 migrates anyone. `unarmed_until` is a WARN because it
    is the one variant with an expiry — the concept applies here and is switched
    off pending named work, which is exactly the state that should stay visible.
    The other three are settled declarations and log at INFO.
    """
    match absence:
        case LegacyAmbiguousEmpty(key=legacy_key, repo=repo):
            log.warning(
                _LEGACY_AMBIGUOUS_MESSAGE,
                check_id=check_id,
                role=legacy_key,
                repo=repo,
                role_key_spelling=_LEGACY_SPELLING,
                migration=_MIGRATION_REF,
                blessed_spellings=list(_BLESSED),
            )
        case UnarmedUntil(ledger_id=ledger_id):
            log.warning(
                "role key declared UNARMED pending named work — the concept applies here",
                check_id=check_id,
                role=key,
                role_key_spelling="unarmed_until",
                ledger_id=ledger_id,
            )
        case NotApplicable(reason=reason):
            log.info(
                "role key declared NOT APPLICABLE — the concept does not exist for this repo",
                check_id=check_id,
                role=key,
                role_key_spelling="not_applicable",
                reason=reason,
            )
        case SupersededBy(reason=reason):
            log.info(
                "role key declared SUPERSEDED — the concept is satisfied by another mechanism",
                check_id=check_id,
                role=key,
                role_key_spelling="superseded_by",
                reason=reason,
            )
        case ConventionNotAdopted(reason=reason):
            log.info(
                "role key declared CONVENTION NOT ADOPTED — this repo declines the convention",
                check_id=check_id,
                role=key,
                role_key_spelling="convention_not_adopted",
                reason=reason,
            )
        case _:
            assert_never(absence)


def role_absence_exit_code(
    *,
    config: Config,
    role: TreeRole | PrefixRole | ScalarRole,
    key: str,
    log: structlog.stdlib.BoundLogger,
    check_id: str,
) -> int | None:
    """Return the early exit for an undeclared or declared-absent union role key.

    Key OMISSION stays a
    hard error via `declared_keys` — absence is already loud for role keys, and this
    union is about EMPTINESS. Every declared-absent variant returns 0 (Phase 1
    rejects nothing), but each announces itself at its own severity first.
    """
    if key not in config.declared_keys:
        log.error(_UNDECLARED_ROLE_KEY_MESSAGE, check_id=check_id, role=key)
        return 1
    absence = role_absence(role=role)
    if absence is None:
        return None
    _announce_absence(absence=absence, key=key, log=log, check_id=check_id)
    return 0


def resolve_role_trees(
    *,
    role: TreeRole,
    key: str,
    log: structlog.stdlib.BoundLogger,
    check_id: str,
) -> tuple[Path, ...]:
    """The declared trees, announcing the variant when the role is declared absent.

    For consumers that iterate a role key WITHOUT gating on it — `claude_md_coverage`
    walks `target_dirs` in a bare `for` loop with no gate at all, which is why a
    declared-empty value there walked zero directories and printed NOTHING. Routing
    them through here is what makes those silent skips observable.
    """
    absence = role_absence(role=role)
    if absence is not None:
        _announce_absence(absence=absence, key=key, log=log, check_id=check_id)
    return role_trees(role=role)


def resolve_role_prefixes(
    *,
    role: PrefixRole,
    key: str,
    log: structlog.stdlib.BoundLogger,
    check_id: str,
) -> tuple[str, ...]:
    """The declared source prefixes, announcing the variant when declared absent."""
    absence = role_absence(role=role)
    if absence is not None:
        _announce_absence(absence=absence, key=key, log=log, check_id=check_id)
    return role_prefixes(role=role)


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
