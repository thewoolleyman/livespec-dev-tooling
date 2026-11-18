"""The default branch's EFFECTIVE required-check set, read through an injected reader.

The `branch_protection_alignment` check contract in SPECIFICATION/contracts.md
(v149) defines the set: classic protection's required contexts UNION every
active ruleset's `required_status_checks` rule on the default branch, every page
read. The check grades that set (`effective_contexts` is the union it aligns),
and the incident-merge principal (`livespec_dev_tooling.incident_merge_forge`)
verifies every member of the SAME set green on a pull request's exact head. One
definition serves both, so the two can never disagree about which checks are
required.

The reader is injected: a callable taking the `gh` argument tail and answering a
`budgeted_gh.GhRead`, so production passes `budgeted_gh.gh_read` and a test
passes a dict-backed fake. Nothing here spawns `gh`. Unlike the check's own
fetchers, every failure here is UNREADABLE: a caller verifying a merge has no
graceful skip, and a set this run did not see whole is never reported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, cast

from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.checks._branch_protection_api import (
    _NOT_PROTECTED_MARKER,
    _STATUS_CHECKS_NOT_ENABLED_MARKER,
)
from livespec_dev_tooling.checks._branch_protection_rulesets import (
    _parse_pages,
    _ruleset_status_rules,
)

__all__: list[str] = [
    "EffectiveRequiredSet",
    "EffectiveSetUnreadable",
    "ForgeReader",
    "effective_contexts",
    "read_effective_required_set",
]


class ForgeReader(Protocol):
    """One forge read: the `gh` argument tail in, a `GhRead` out."""

    def __call__(self, *, args: list[str]) -> GhRead: ...


@dataclass(frozen=True, kw_only=True)
class EffectiveRequiredSet:
    """The effective set as read whole, with the branch it was read on."""

    branch: str
    contexts: frozenset[str]


@dataclass(frozen=True, kw_only=True)
class EffectiveSetUnreadable:
    """The set could not be read whole; `detail` names why."""

    detail: str


def effective_contexts(*, classic: frozenset[str], ruleset: frozenset[str]) -> frozenset[str]:
    """The effective required-check set: the classic contexts UNION the ruleset ones."""
    return classic | ruleset


def _json_object(*, stdout: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None


def _default_branch(*, reader: ForgeReader, repo: str) -> str | EffectiveSetUnreadable:
    answer = reader(args=["api", f"repos/{repo}"])
    body = _json_object(stdout=answer.stdout) if answer.returncode == 0 else None
    branch = body.get("default_branch") if body is not None else None
    if not isinstance(branch, str) or not branch:
        return EffectiveSetUnreadable(detail=f"the default branch of {repo} could not be read")
    return branch


def _classic(*, reader: ForgeReader, repo: str, branch: str) -> frozenset[str] | str:
    """The classic contribution, or a string naming why it is unreadable."""
    path = f"repos/{repo}/branches/{branch}/protection/required_status_checks"
    answer = reader(args=["api", path])
    if answer.returncode != 0:
        combined = f"{answer.stdout}\n{answer.stderr}"
        # The same two answers, in the same order, the check keys on.
        if _NOT_PROTECTED_MARKER in combined:
            return f"the default branch {branch} has no branch protection"
        if _STATUS_CHECKS_NOT_ENABLED_MARKER in combined:
            return frozenset()
        return f"classic required checks unreadable: {answer.stderr.strip()[:200]}"
    body = _json_object(stdout=answer.stdout)
    listed = body.get("contexts") if body is not None else None
    if not isinstance(listed, list):
        return "classic required checks payload carried no contexts list"
    return frozenset(c for c in cast("list[object]", listed) if isinstance(c, str))


def _ruleset(*, reader: ForgeReader, repo: str, branch: str) -> frozenset[str] | str:
    """The active-ruleset contribution, or a string naming why it is unreadable."""
    path = f"repos/{repo}/rules/branches/{branch}?per_page=100"
    answer = reader(args=["api", "--paginate", "--slurp", path])
    if answer.returncode != 0:
        return f"ruleset rules unreadable: {answer.stderr.strip()[:200]}"
    held = _ruleset_status_rules(pages=_parse_pages(stdout=answer.stdout))
    if held is None:
        return "ruleset rules payload was not a list of rule pages"
    return frozenset(c for contexts, _strict in held.values() for c in contexts)


def read_effective_required_set(
    *, reader: ForgeReader, repo: str
) -> EffectiveRequiredSet | EffectiveSetUnreadable:
    """Read the default branch's effective required-check set whole, or say why not.

    An unprotected default branch is unreadable here rather than an empty set:
    the check fails such a branch (`protection_absent`), so no set it grades
    exists to verify against.
    """
    branch = _default_branch(reader=reader, repo=repo)
    if isinstance(branch, EffectiveSetUnreadable):
        return branch
    classic = _classic(reader=reader, repo=repo, branch=branch)
    if isinstance(classic, str):
        return EffectiveSetUnreadable(detail=classic)
    ruleset = _ruleset(reader=reader, repo=repo, branch=branch)
    if isinstance(ruleset, str):
        return EffectiveSetUnreadable(detail=ruleset)
    return EffectiveRequiredSet(
        branch=branch, contexts=effective_contexts(classic=classic, ruleset=ruleset)
    )
