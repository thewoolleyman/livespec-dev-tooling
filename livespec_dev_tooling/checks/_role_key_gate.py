"""Shared role-key gating for layout-dependent checks."""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._work_item_liveness import (  # noqa: E402
    NONEXISTENT,
    UNREACHABLE,
    bd_status_reader,
    resolve_liveness,
    resolved_status,
)
from livespec_dev_tooling.config import (  # noqa: E402
    Config,
    ConventionNotAdopted,
    NotApplicable,
    PrefixRole,
    RoleAbsence,
    ScalarRole,
    SupersededBy,
    TreeRole,
    UnarmedUntil,
    Undeclared,
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

# Phase 4 deleted the legacy variant, so this announces the OTHER absence a
# role can carry: nobody wrote the key. It is defensive rather than routine —
# `role_absence_exit_code` tests `declared_keys` FIRST and hard-errors there, so
# this arm is reached only if a consumer reads a role off a bare `Config()`
# without going through the gate. It logs at ERROR for the same reason that path
# does: an undeclared key is a configuration defect, never an opt-out.
_UNDECLARED_BASELINE_MESSAGE = " ".join(
    (
        "role key was never declared — this is the parse-time baseline, not a",
        "sanctioned absence; declare the real value, or declare it absent with one of",
        "not_applicable / superseded_by / unarmed_until / convention_not_adopted",
    )
)
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

# The ratified wording, not a paraphrase. `SPECIFICATION/scenarios.md` §"Scenario:
# an unarmed-until payload naming a closed work item is a conformance failure"
# requires the report to identify the consumer, the key and the item, AND to state
# that the declaration claims pending work that is already complete. The last
# clause is the one a reader acts on, so it is spelled out rather than implied by
# the status field alone.
_UNARMED_UNTIL_CLOSED_MESSAGE = " ".join(
    (
        "role key declared UNARMED pending named work whose work-item is CLOSED —",
        "the declaration claims pending work that is already complete, so the key is",
        "switched off with nothing left to wait for; re-arm it, or re-point the",
        "payload at the work that is genuinely still open",
    )
)
# The honest-degradation SKIP. `SPECIFICATION/spec.md` §"Non-goals" admits exactly
# one way to proceed without an answer, and it is a skip CARRYING ITS REASON —
# never a silent pass, never a hard-failed offline build. `liveness_unverified`
# is what keeps this from rendering like the verified-open case below.
_UNARMED_UNTIL_UNVERIFIED_MESSAGE = " ".join(
    (
        "role key declared UNARMED pending named work — the concept applies here.",
        "Work-item liveness UNVERIFIED: this repository's configured work-item store",
        "did not resolve the id, so whether the deferral is still owed is UNKNOWN",
        "rather than confirmed",
    )
)


def _announce_unarmed_until(
    *,
    ledger_id: str,
    key: str,
    log: structlog.stdlib.BoundLogger,
    check_id: str,
) -> None:
    """Announce one `unarmed_until` declaration at the severity its payload EARNS.

    This is the arm that used to make the docstring's promise false. The variant
    was called "the one variant with an expiry", but nothing in this library
    resolved the id against any tracker, so a declaration could name work that
    closed years ago and the key stayed switched off, silently, forever. The
    expiry now exists.

    Resolution goes through `checks/_work_item_liveness`, the ONE shared mechanism
    `SPECIFICATION/spec.md` §"Non-goals" requires for the work-item-liveness
    exception — a gate hand-rolling its own lookup is non-conforming there even
    when its behaviour is otherwise correct. `bd_status_reader` is read off this
    MODULE at call time so a test can substitute a deterministic double; no unit
    test needs a reachable tracker, and no test's verdict depends on the host it
    runs on.

    Three outcomes, deliberately distinguishable, because verified-live,
    verified-dead and UNVERIFIED are three different facts and a skip that renders
    like a pass is the defect this closes.

    AN ID THIS REPO'S OWN STORE DOES NOT HOLD IS UNVERIFIED, NOT DEAD, and the
    asymmetry is ratified rather than cautious: `SPECIFICATION/contracts.md`
    §"Role keys" requires a verifier of this property to resolve identifiers
    ACROSS trackers, "since a consumer MAY legitimately cite a work item held in
    another repository's tracker; a verifier that resolves only within the
    declaring repo would reject valid declarations". Measured across the fleet on
    2026-07-28, THREE of the four live payloads cite an id in a tenant the
    declaring repo does not own, so convicting on absence-from-the-local-tenant
    would put three conformant repos in false breach. This is the one place this
    gate reads the shared resolver more narrowly than `checks/no_todo_registry`
    does, and the narrowing is that clause.

    The verdict is ANNOUNCED, not enforced by exit code: `role_absence_exit_code`
    returns 0 for every declared-absent variant, and ERROR naming the id and its
    status is the "red or warning per the consuming gate's own contract" the
    exception admits.

    THE `unwrap()` BELOW CANNOT FAIL, and the guard above it is why: reaching
    the `elif` means `status` is neither UNREACHABLE nor NONEXISTENT, which
    means the store ANSWERED and holds the id — so `resolve_liveness` is on
    its success track by construction. Should that invariant ever break, an
    unwrap that raises is the right outcome: it is a bug in this function, and
    bugs raise here rather than degrading into a verdict nobody measured.
    """
    repo = Path.cwd()
    snapshot = bd_status_reader(repo=repo)
    status = resolved_status(work_item=ledger_id, snapshot=snapshot)
    live = resolve_liveness(work_item=ledger_id, snapshot=snapshot)
    fields: dict[str, object] = {
        "check_id": check_id,
        "role": key,
        "role_key_spelling": "unarmed_until",
        "ledger_id": ledger_id,
        "consumer": repo.as_posix(),
        "resolved_status": status,
    }
    if status in (UNREACHABLE, NONEXISTENT):
        log.warning(_UNARMED_UNTIL_UNVERIFIED_MESSAGE, **fields, liveness_unverified=True)
    elif not unsafe_perform_io(live.unwrap()):
        log.error(_UNARMED_UNTIL_CLOSED_MESSAGE, **fields)
    else:
        log.warning(
            "role key declared UNARMED pending named work — the concept applies here",
            **fields,
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
    countable before Phase 2 migrates anyone. `unarmed_until` is the one variant
    with an expiry — the concept applies here and is switched off pending named
    work, which is exactly the state that should stay visible — so it is the one
    variant whose severity is not fixed here at all: `_announce_unarmed_until`
    resolves its payload and picks WARN or ERROR from what the store answers. The
    other three are settled declarations and log at INFO.
    """
    match absence:
        case Undeclared(key=undeclared_key):
            log.error(
                _UNDECLARED_BASELINE_MESSAGE,
                check_id=check_id,
                role=undeclared_key,
                role_key_spelling="undeclared",
                blessed_spellings=list(_BLESSED),
            )
        case UnarmedUntil(ledger_id=ledger_id):
            _announce_unarmed_until(ledger_id=ledger_id, key=key, log=log, check_id=check_id)
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
