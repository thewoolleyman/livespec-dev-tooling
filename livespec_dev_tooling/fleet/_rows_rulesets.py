"""The ruleset half of a fleet member's effective required-check set.

The `branch-protection` assert row and its reconcile both read a member's
default-branch protection as classic protection's required checks UNION every
active ruleset's `required_status_checks` rule, per the fleet paragraph of the
`branch_protection_alignment` check contract in this repository's
SPECIFICATION/contracts.md (v149). This module reads that ruleset half through
the injected `FleetContext` runner and reuses the check's own parsing, so the
check and the fleet surface cannot disagree about what a ruleset holds.

A read that fails, or answers in a shape that is not the documented one, is
UNVERIFIED rather than empty: the row skips and the reconcile does not write.
"""

from __future__ import annotations

import json

from livespec_dev_tooling.checks._branch_protection_rulesets import (
    _non_app_bypass,
    _ruleset_status_rules,
    _RulesetRequirements,
)
from livespec_dev_tooling.fleet._context import FleetContext
from livespec_dev_tooling.fleet._gh_runner import InvocationNotPerformed, gh_answer

__all__: list[str] = ["member_ruleset_requirements", "ruleset_problems"]


def _stdout(*, ctx: FleetContext, args: list[str]) -> str | None:
    """The body of a `gh` read that ran and succeeded, or None."""
    result = gh_answer(outcome=ctx.run_gh(args=args, stdin=None))
    if isinstance(result, InvocationNotPerformed) or result.returncode != 0:
        return None
    return result.stdout


def _parsed(*, text: str) -> object:
    """`text` as JSON, or None when it does not parse (never evidence of emptiness)."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _bypass_verdict(*, ctx: FleetContext, base: str, ruleset_id: int) -> bool | None:
    """Whether a ruleset lists a non-App bypass actor; None when that is unverified."""
    body = _stdout(ctx=ctx, args=["api", f"{base}/rulesets/{ruleset_id}"])
    if body is None or _parsed(text=body) is None:
        return None
    return _non_app_bypass(stdout=body)


def member_ruleset_requirements(
    *, ctx: FleetContext, repo: str, ref: str
) -> _RulesetRequirements | str:
    """The required checks active rulesets hold on `ref`, or why that is unverified."""
    base = f"repos/{ctx.owner}/{repo}"
    rules = _stdout(
        ctx=ctx, args=["api", "--paginate", "--slurp", f"{base}/rules/branches/{ref}?per_page=100"]
    )
    held = None if rules is None else _ruleset_status_rules(pages=_parsed(text=rules))
    if held is None:
        return f"{repo}: the ruleset rules on {ref} are unreadable or malformed"
    non_app: list[int] = []
    for ruleset_id in sorted(held):
        verdict = _bypass_verdict(ctx=ctx, base=base, ruleset_id=ruleset_id)
        if verdict is None:
            return f"{repo}: ruleset {ruleset_id} has no readable bypass list"
        if verdict:
            non_app.append(ruleset_id)
    return _RulesetRequirements(
        contexts=frozenset(c for contexts, _ in held.values() for c in contexts),
        strict_ruleset_ids=tuple(i for i, (_, strict) in sorted(held.items()) if strict),
        non_app_bypass_ruleset_ids=tuple(non_app),
    )


def ruleset_problems(*, rulesets: _RulesetRequirements) -> list[str]:
    """The alignment problems a contributing ruleset carries, one per ruleset and rule."""
    strict = [
        f"ruleset {ruleset_id} requires a check on the default branch with strict enabled "
        "(strict must be OFF)"
        for ruleset_id in rulesets.strict_ruleset_ids
    ]
    bypass = [
        f"ruleset {ruleset_id} requires a check on the default branch but lets a non-App "
        "actor bypass it (only GitHub App bypass actors are allowed)"
        for ruleset_id in rulesets.non_app_bypass_ruleset_ids
    ]
    return strict + bypass
