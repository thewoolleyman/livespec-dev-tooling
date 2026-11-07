"""Reading the ruleset half of the default branch's effective required-check set.

Split from `_branch_protection_api.py`, which the ruleset reads pushed past the
250-line hard LLOC ceiling. Like that module it TALKS TO THE FORGE and decides
nothing: `branch_protection_alignment` owns what each answer costs.

The effective required-check set is classic protection's contexts UNION every
active ruleset's `required_status_checks` rule on the default branch, per
the `branch_protection_alignment` check contract in this repository's
SPECIFICATION/contracts.md (v149). Every forge read goes through
`budgeted_gh.gh_read`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from livespec_dev_tooling.budgeted_gh import gh_read
from livespec_dev_tooling.checks._branch_protection_api import _RequiredContexts

__all__: list[str] = [
    "_RulesetRequirements",
    "_RulesetsUnreadable",
    "_fetch_ruleset_requirements",
    "_ruleset_status_rules",
]

# A ruleset bypass actor of this type is a GitHub App identity — the only bypass
# the contract admits on a ruleset that holds a required check.
_APP_ACTOR_TYPE = "Integration"


@dataclass(frozen=True, kw_only=True)
class _RulesetRequirements:
    """The required checks active repository rulesets hold on the default branch.

    `contexts` is the ruleset contribution to the effective required-check set.
    `strict_ruleset_ids` names each contributing ruleset whose rule turns strict
    on; `non_app_bypass_ruleset_ids` names each contributing ruleset that lists
    a bypass actor other than a GitHub App. Both are verdict inputs, not
    verdicts: the check decides what they cost.
    """

    contexts: frozenset[str]
    strict_ruleset_ids: tuple[int, ...]
    non_app_bypass_ruleset_ids: tuple[int, ...]


@dataclass(frozen=True, kw_only=True)
class _RulesetsUnreadable:
    """The ruleset contribution could not be read; never an empty contribution."""

    detail: str


def _ruleset_status_rules(*, pages: object) -> dict[int, tuple[frozenset[str], bool]] | None:
    """Per contributing ruleset, its required contexts and its strict flag; None if malformed.

    `pages` is the `--paginate --slurp` answer of `rules/branches/{branch}`: a
    list of pages, each a list of rule objects carrying `type` and `ruleset_id`.
    Only `required_status_checks` rules contribute. Anything that is not that
    shape is None, which the caller reports as unreadable rather than as a
    ruleset holding nothing.
    """
    if not isinstance(pages, list):
        return None
    held: dict[int, tuple[frozenset[str], bool]] = {}
    for page in cast("list[object]", pages):
        if not isinstance(page, list):
            return None
        for raw in cast("list[object]", page):
            rule = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
            ruleset_id = rule.get("ruleset_id")
            if rule.get("type") != "required_status_checks":
                continue
            parameters = rule.get("parameters")
            if type(ruleset_id) is not int or not isinstance(parameters, dict):
                return None
            params = cast("dict[str, object]", parameters)
            entries = params.get("required_status_checks")
            listed = cast("list[object]", entries) if isinstance(entries, list) else []
            contexts = {
                cast("dict[str, object]", e).get("context") for e in listed if isinstance(e, dict)
            }
            prior, prior_strict = held.get(ruleset_id, (frozenset(), False))
            held[ruleset_id] = (
                prior | {c for c in contexts if isinstance(c, str)},
                prior_strict or bool(params.get("strict_required_status_checks_policy")),
            )
    return held


def _non_app_bypass(*, stdout: str) -> bool | None:
    """Whether a ruleset body lists a non-App bypass actor; None when it lists none at all."""
    parsed = json.loads(stdout)
    body = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}
    actors = body.get("bypass_actors")
    if not isinstance(actors, list):
        return None
    return any(
        not isinstance(actor, dict)
        or cast("dict[str, object]", actor).get("actor_type") != _APP_ACTOR_TYPE
        for actor in cast("list[object]", actors)
    )


def _fetch_ruleset_requirements(
    *, protection: _RequiredContexts
) -> _RulesetRequirements | _RulesetsUnreadable:
    """Read the active ruleset contribution to the default branch's required checks.

    Issued only after the classic read succeeded, so the admin scope both reads
    need is proven: every failure here is UNREADABLE, never the graceful skip
    and never an empty contribution (the `branch_protection_alignment` check
    contract in SPECIFICATION/contracts.md, v149). The rules endpoint returns
    only rules whose ruleset enforcement is active, and every page is read.
    """
    base = f"repos/{protection.owner_repo}"
    rules_path = f"{base}/rules/branches/{protection.branch}?per_page=100"
    completed = gh_read(args=["api", "--paginate", "--slurp", rules_path])
    if completed.returncode != 0:
        return _RulesetsUnreadable(detail=f"rules read failed: {completed.stderr.strip()[:200]}")
    held = _ruleset_status_rules(pages=json.loads(completed.stdout))
    if held is None:
        return _RulesetsUnreadable(detail="rules payload was not a list of rule pages")
    non_app: list[int] = []
    for ruleset_id in sorted(held):
        body = gh_read(args=["api", f"{base}/rulesets/{ruleset_id}"])
        verdict = _non_app_bypass(stdout=body.stdout) if body.returncode == 0 else None
        if verdict is None:
            return _RulesetsUnreadable(detail=f"ruleset {ruleset_id} has no readable bypass list")
        if verdict:
            non_app.append(ruleset_id)
    return _RulesetRequirements(
        contexts=frozenset(c for contexts, _ in held.values() for c in contexts),
        strict_ruleset_ids=tuple(i for i, (_, strict) in sorted(held.items()) if strict),
        non_app_bypass_ruleset_ids=tuple(non_app),
    )
