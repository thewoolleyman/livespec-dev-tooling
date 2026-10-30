"""Judge a held revert's fix-forward claim: who may claim, and whether it still holds.

Per `SPECIFICATION/contracts.md` section "Master-health reconciler" (work-item
`livespec-dev-tooling-joqff6`, child of plan `red-master-self-healing`).

A CLAIM HOLDS THE REVERT, AND EVERYTHING ELSE RELEASES IT. "Release" means only
that the hold is dropped: after it the revert is judged exactly as an unclaimed
one, so it merges only once its OWN CI is green. This module therefore answers a
single question — does a valid claim still hold this revert? — and the caller
turns "no" into the ordinary unclaimed path. It never merges anything.

THE CLAIMANT SET IS CLOSED. A claim is a comment on the revert pull request with
a `Fix-Forward: #<number>` line, and it counts only when posted by the
maintainer's forge login, or by the login that opened the culprit pull request
AND carrying a non-blank `Claimed-By:` line naming the owning session. Any other
comment is ignored and the revert proceeds as though unclaimed. The line
convention is mechanical on purpose: no decision here reads prose, and no LLM
reaches it.

THE CLOCK IS DATA. "Now" is `ReconcileState.observed_at` and every transition
carries its own epoch-seconds timestamp, so the same recording always yields the
same verdict. Any forward transition restarts the step clock, so the clock is the
NEWEST timestamp the claim and its fix have recorded, and the stall duration
applied is the one for the step the fix is currently waiting in.

IT FAILS CLOSED. A missing or malformed hard cap or stall duration, an unrecorded
"now", or a red episode that did not record when it went red cannot show that a
claim is still inside its limits, so the claim does not hold. The fleet default
for the cap is provisioned into committed configuration; there is deliberately no
number here to fall back on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from livespec_dev_tooling.cross_repo.master_health_episode import red_since
from livespec_dev_tooling.cross_repo.master_health_state import (
    CI_FAILURE,
    CI_SUCCESS,
    FIX_CLOSED,
    FIX_MERGED,
    FixForwardClaim,
    FixPullRequest,
    ReconcileConfig,
    ReconcileState,
    RevertPullRequest,
)

__all__: list[str] = [
    "HoldVerdict",
    "claimed_fix_numbers",
    "hold_verdict",
    "valid_claims",
]

# Both patterns are anchored to a whole line and use horizontal whitespace only,
# so a `Claimed-By:` with nothing after it can never borrow the next line's text.
_FIX_LINE = re.compile(r"^Fix-Forward:[ \t]*#(\d+)[ \t]*\r?$", re.MULTILINE)
_CLAIMED_BY_LINE = re.compile(r"^Claimed-By:[ \t]*\S.*$", re.MULTILINE)

_SECONDS_PER_MINUTE = 60


@dataclass(frozen=True, kw_only=True)
class HoldVerdict:
    """Whether a valid claim still holds the revert, and why.

    `claimed` is `True` when at least one VALID claim is in force, whether or not
    it still holds: the caller words an escalation differently when a hold was
    just dropped (for example by the hard cap) than when nothing was ever
    claimed.
    """

    claimed: bool
    holds: bool
    reason: str


@dataclass(frozen=True, kw_only=True)
class _Limits:
    """The committed limits, converted to seconds."""

    hard_cap: int
    claim_to_fix_pr: int
    ci_in_flight: int
    fix_to_merge: int
    merged_to_green: int


def claimed_fix_numbers(*, body: str) -> tuple[int, ...]:
    """The fix pull request numbers a comment body names, in order of appearance."""
    return tuple(int(number) for number in _FIX_LINE.findall(body))


def _is_claimant(
    *, claim: FixForwardClaim, revert: RevertPullRequest, config: ReconcileConfig
) -> bool:
    """Whether `claim` was posted by someone inside the ratified claimant set.

    Logins are compared case-insensitively because the forge treats them so.
    """
    author = claim.author.casefold()
    if config.maintainer_login is not None and author == config.maintainer_login.casefold():
        return True
    return (
        revert.culprit_opened_by is not None
        and author == revert.culprit_opened_by.casefold()
        and _CLAIMED_BY_LINE.search(claim.body) is not None
    )


def valid_claims(
    *, revert: RevertPullRequest, config: ReconcileConfig
) -> tuple[FixForwardClaim, ...]:
    """The comments that are claims at all: a claimant inside the set, naming a fix."""
    return tuple(
        claim
        for claim in revert.claims
        if _is_claimant(claim=claim, revert=revert, config=config)
        and claimed_fix_numbers(body=claim.body)
    )


def _limits(*, config: ReconcileConfig) -> _Limits | None:
    """The committed limits in seconds, or `None` when ANY of them is missing."""
    cap = config.hard_cap_minutes
    claim = config.stall_claim_to_fix_pr_minutes
    ci = config.stall_ci_in_flight_minutes
    merge = config.stall_fix_to_merge_minutes
    green = config.stall_merged_to_green_minutes
    if cap is None or claim is None or ci is None or merge is None or green is None:
        return None
    return _Limits(
        hard_cap=cap * _SECONDS_PER_MINUTE,
        claim_to_fix_pr=claim * _SECONDS_PER_MINUTE,
        ci_in_flight=ci * _SECONDS_PER_MINUTE,
        fix_to_merge=merge * _SECONDS_PER_MINUTE,
        merged_to_green=green * _SECONDS_PER_MINUTE,
    )


def _thrash_reason(*, fix: FixPullRequest) -> str | None:
    """Why the fix is thrashing, or `None` when it is not.

    Only DECIDED commits are compared: a cancelled or pending run says nothing
    about the failing set, and a newer push routinely cancels the older run.
    """
    if fix.state == FIX_MERGED and fix.master_ci_conclusion == CI_FAILURE:
        return "the fix merged while master stays red"
    previous: tuple[str, ...] | None = None
    for commit in fix.commits:
        if commit.ci_conclusion not in (CI_SUCCESS, CI_FAILURE):
            continue
        failing = set(commit.failing_checks)
        if len(failing) != len(commit.failing_checks):
            return "the same check failed repeatedly"
        if previous is not None and failing:
            before = set(previous)
            if failing - before:
                return "a new check started failing"
            if len(failing) >= len(before):
                return "a new commit did not reduce the failing checks"
        previous = commit.failing_checks
    return None


def _waiting_limit(*, fix: FixPullRequest, limits: _Limits) -> int:
    """The stall duration of the step the fix is currently waiting in.

    A merged fix waits on `master` CI to start and then on it to finish (the
    in-flight duration); an open fix whose latest commit has a decided result, or
    whose auto-merge is armed, waits on a human or the merge queue (the
    fix-to-merge duration); anything else is waiting on CI.
    """
    if fix.state == FIX_MERGED:
        return (
            limits.ci_in_flight if fix.master_ci_started_at is not None else limits.merged_to_green
        )
    if fix.auto_merge_armed_at is not None:
        return limits.fix_to_merge
    if fix.commits and fix.commits[-1].ci_conclusion in (CI_SUCCESS, CI_FAILURE):
        return limits.fix_to_merge
    return limits.ci_in_flight


def _last_transition(*, fix: FixPullRequest | None, claimed_at: int) -> int:
    """The newest recorded forward transition: the instant the step clock restarted."""
    if fix is None:
        return claimed_at
    stamps = [claimed_at, fix.opened_at]
    for commit in fix.commits:
        stamps.append(commit.pushed_at)
        stamps.extend(
            stamp for stamp in (commit.ci_started_at, commit.ci_finished_at) if stamp is not None
        )
    stamps.extend(
        stamp
        for stamp in (fix.auto_merge_armed_at, fix.merged_at, fix.master_ci_started_at)
        if stamp is not None
    )
    return max(stamps)


def _fix_release_reason(*, fix: FixPullRequest | None) -> str | None:
    """Why the recorded fix pull request no longer holds the revert, or `None`."""
    if fix is None:
        return None
    if fix.state == FIX_CLOSED:
        return "the claimed fix pull request was closed without merging"
    thrash = _thrash_reason(fix=fix)
    return None if thrash is None else f"the fix is thrashing: {thrash}"


def _release_reason(
    *,
    claims: tuple[FixForwardClaim, ...],
    revert: RevertPullRequest,
    state: ReconcileState,
    config: ReconcileConfig,
) -> str | None:
    """Why the valid `claims` no longer hold `revert`, or `None` when they still do.

    The order is the safety argument: the fail-closed answer first, then the hard
    cap (which outranks any progress), then the contest and thrash rules, and only
    a fix that survives all of them is measured against its stall duration.
    """
    limits = _limits(config=config)
    now = state.observed_at
    since = red_since(state=state)
    if limits is None or now is None or since is None:
        return (
            "the hard cap, a stall duration or a timestamp is missing or malformed, so "
            "the reconciler fails closed to revert-by-default"
        )
    if now - since > limits.hard_cap:
        return "master has been red past the hard cap"
    numbers = sorted(
        {number for claim in claims for number in claimed_fix_numbers(body=claim.body)}
    )
    if len(numbers) > 1:
        return "more than one fix pull request is claimed"
    fix = next((found for found in revert.fix_pull_requests if found.number == numbers[0]), None)
    reason = _fix_release_reason(fix=fix)
    if reason is not None:
        return reason
    claimed_at = min(
        claim.posted_at for claim in claims if numbers[0] in claimed_fix_numbers(body=claim.body)
    )
    limit = limits.claim_to_fix_pr if fix is None else _waiting_limit(fix=fix, limits=limits)
    if now - _last_transition(fix=fix, claimed_at=claimed_at) > limit:
        return "no forward transition occurred within the current step's stall duration"
    return None


def hold_verdict(
    *, revert: RevertPullRequest, state: ReconcileState, config: ReconcileConfig
) -> HoldVerdict:
    """Whether a valid fix-forward claim still holds `revert`.

    `state` is the gating-projected window, which is where "how long has master
    been red" is read from.
    """
    claims = valid_claims(revert=revert, config=config)
    if not claims:
        return HoldVerdict(
            claimed=False, holds=False, reason="no valid fix-forward claim is in force"
        )
    reason = _release_reason(claims=claims, revert=revert, state=state, config=config)
    if reason is not None:
        return HoldVerdict(claimed=True, holds=False, reason=reason)
    return HoldVerdict(claimed=True, holds=True, reason="the fix is making forward progress")
