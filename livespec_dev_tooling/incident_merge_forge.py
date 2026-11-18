"""incident_merge_forge — the forge-side preconditions of the incident-merge principal.

The `Incident-merge principal.` paragraph of SPECIFICATION/contracts.md
(inside its expedited incident execution contract, v246) lets an independently provisioned
principal merge one expedited repair outside the merge queue. Two of the facts
it must read at merge time live on the forge, and this module reads them
(livespec-dev-tooling-u3nbm3, slice B3):

- `has_incident_label` — whether the pull request carries the
  `expedited-incident-response` label. NECESSARY, NEVER SUFFICIENT: the
  incident authority chain is the sole authority for the merge.
- `required_checks_verdict` — whether EVERY context of the default branch's
  RULESET-required check set (read by the shared `checks._effective_required_checks`)
  concluded `success` on the exact head SHA. A ruleset bypass also skips `required_status_checks`,
  so this verification is the principal's own and is never left to the forge.

EVERY READ FITS THE MERGE APP'S GRANT (Contents read, Pull requests read and write, Checks
read, Commit statuses read, Metadata read). Measured live with the App's own token
(2026-11-18, livespec-dev-tooling-o6u7jm): the classic branch-protection read answers 403
(it needs Administration read) and the Actions runs read needs Actions read, so neither is
used. The required set is the repository's RULESETS alone (`rules/branches/<branch>`,
Metadata read); a context required only by classic protection is therefore not verified
here (master's classic protection lists no contexts). A merge-queue run is told apart by
its check suite's head branch (`gh-readonly-queue/...`), read from the Checks API.

A context is green only when every piece of evidence for it on that SHA says
`success`: its latest counted check run, and its latest commit status. A check
run counts only when its check suite ran on a branch that is not a merge queue's
(`gh-readonly-queue/`); a run that ran only in a merge queue, or whose suite's branch
cannot be shown, never counts. A failing, pending or absent context
is not green, and `NotGreen.contexts` names each one. An empty effective set is
not green either: a vacuous pass verifies nothing.

The forge is an injected `ForgeReader` (production: `budgeted_gh.gh_read`), so
no test touches the network or a credential.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from livespec_dev_tooling.checks._effective_required_checks import (
    EffectiveSetUnreadable,
    ForgeReader,
    read_ruleset_required_set,
)
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = [
    "INCIDENT_LABEL",
    "CheckState",
    "ForgeReader",
    "Green",
    "IncidentForgeReadError",
    "NotGreen",
    "OffendingCheck",
    "has_incident_label",
    "required_checks_verdict",
]

INCIDENT_LABEL = "expedited-incident-response"
_QUEUE_BRANCH_PREFIX = "gh-readonly-queue/"
# Paginated check-run pages outgrow the strict decoder's 64 KiB default; this
# still bounds a runaway answer.
_READ_LIMIT = 8 * 1024 * 1024

CheckState = Literal["failing", "pending", "absent", "merge-group-only", "event-unknown"]


class IncidentForgeReadError(Exception):
    """A forge read ended without an answer; the caller must refuse the merge."""

    def __init__(self, *, path: str, detail: str) -> None:
        super().__init__(f"{path}: {detail}")


@dataclass(frozen=True, kw_only=True)
class OffendingCheck:
    """One required context that is not green on the head, and why."""

    context: str
    state: CheckState


@dataclass(frozen=True, kw_only=True)
class Green:
    """Every context of the effective set concluded `success` on `head_sha`."""

    head_sha: str
    contexts: frozenset[str]


@dataclass(frozen=True, kw_only=True)
class NotGreen:
    """The head is not verified green; `contexts` names each offending context."""

    head_sha: str
    reason: str
    contexts: tuple[OffendingCheck, ...] = ()


def _pages(*, forge: ForgeReader, path: str) -> list[object]:
    answer = forge(args=["api", "--paginate", "--slurp", path])
    if answer.returncode != 0:
        raise IncidentForgeReadError(path=path, detail=answer.stderr.strip()[:200])
    try:
        parsed: object = strict_json(text=answer.stdout, limit=_READ_LIMIT)
    except IncidentJsonRefusalError as error:
        raise IncidentForgeReadError(path=path, detail="body was not strict JSON") from error
    if not isinstance(parsed, list):
        raise IncidentForgeReadError(path=path, detail="body was not a list of pages")
    return cast("list[object]", parsed)


def _members(*, pages: list[object], key: str, path: str) -> list[dict[str, object]]:
    """Every object listed under `key` across the pages; malformed is unreadable."""
    members: list[dict[str, object]] = []
    for page in pages:
        listed = cast("dict[str, object]", page).get(key) if isinstance(page, dict) else None
        if not isinstance(listed, list):
            raise IncidentForgeReadError(path=path, detail=f"a page carried no {key} list")
        for entry in cast("list[object]", listed):
            if not isinstance(entry, dict):
                raise IncidentForgeReadError(path=path, detail=f"a {key} entry was not an object")
            members.append(cast("dict[str, object]", entry))
    return members


def has_incident_label(*, forge: ForgeReader, repo: str, pr_number: int) -> bool:
    """Whether the pull request carries the `expedited-incident-response` label.

    Necessary, never sufficient. Raises `IncidentForgeReadError` when the pull
    request cannot be read, so "unread" is never reported as "unlabelled".
    """
    path = f"repos/{repo}/pulls/{pr_number}"
    answer = forge(args=["api", path])
    if answer.returncode != 0:
        raise IncidentForgeReadError(path=path, detail=answer.stderr.strip()[:200])
    try:
        parsed: object = strict_json(text=answer.stdout, limit=_READ_LIMIT)
    except IncidentJsonRefusalError as error:
        raise IncidentForgeReadError(path=path, detail="body was not strict JSON") from error
    labels = cast("dict[str, object]", parsed).get("labels") if isinstance(parsed, dict) else None
    if not isinstance(labels, list):
        raise IncidentForgeReadError(path=path, detail="body carried no labels list")
    return any(
        isinstance(label, dict) and cast("dict[str, object]", label).get("name") == INCIDENT_LABEL
        for label in cast("list[object]", labels)
    )


def _suite_branches(*, forge: ForgeReader, repo: str, head_sha: str) -> dict[object, object]:
    """Each check suite on the head, mapped to the branch it ran on (Checks read)."""
    path = f"repos/{repo}/commits/{head_sha}/check-suites?per_page=100"
    suites = _members(pages=_pages(forge=forge, path=path), key="check_suites", path=path)
    return {suite.get("id"): suite.get("head_branch") for suite in suites}


def _run_states(
    *, forge: ForgeReader, repo: str, head_sha: str
) -> tuple[dict[str, str], dict[str, CheckState]]:
    """Per name, the latest counted check run's state, and why an uncounted name is absent."""
    branches = _suite_branches(forge=forge, repo=repo, head_sha=head_sha)
    path = f"repos/{repo}/commits/{head_sha}/check-runs?per_page=100"
    runs = _members(pages=_pages(forge=forge, path=path), key="check_runs", path=path)
    latest: dict[str, tuple[int, str]] = {}
    uncounted: dict[str, CheckState] = {}
    for run in runs:
        name, run_id = run.get("name"), run.get("id")
        if not isinstance(name, str) or type(run_id) is not int or run.get("head_sha") != head_sha:
            continue
        suite = run.get("check_suite")
        suite_id = cast("dict[str, object]", suite).get("id") if isinstance(suite, dict) else None
        branch = branches.get(suite_id)
        if not isinstance(branch, str) or branch.startswith(_QUEUE_BRANCH_PREFIX):
            uncounted[name] = "event-unknown" if not isinstance(branch, str) else "merge-group-only"
            continue
        state = "pending" if run.get("status") != "completed" else str(run.get("conclusion"))
        if name not in latest or run_id > latest[name][0]:
            latest[name] = (run_id, state)
    return {name: state for name, (_, state) in latest.items()}, uncounted


def _status_states(*, forge: ForgeReader, repo: str, head_sha: str) -> dict[str, str]:
    """Per context, the latest commit status state on the head (the combined view)."""
    path = f"repos/{repo}/commits/{head_sha}/status?per_page=100"
    statuses = _members(pages=_pages(forge=forge, path=path), key="statuses", path=path)
    return {
        str(status.get("context")): str(status.get("state"))
        for status in statuses
        if isinstance(status.get("context"), str)
    }


def _offending(
    *,
    context: str,
    runs: dict[str, str],
    uncounted: dict[str, CheckState],
    statuses: dict[str, str],
) -> OffendingCheck | None:
    evidence = [state for state in (runs.get(context), statuses.get(context)) if state is not None]
    if not evidence:
        return OffendingCheck(context=context, state=uncounted.get(context, "absent"))
    if all(state == "success" for state in evidence):
        return None
    pending = any(state == "pending" for state in evidence)
    return OffendingCheck(context=context, state="pending" if pending else "failing")


def required_checks_verdict(*, forge: ForgeReader, repo: str, head_sha: str) -> Green | NotGreen:
    """Whether every effective required context concluded `success` on `head_sha`.

    Never raises for a forge failure: a set or an answer this run did not read
    whole is `NotGreen` with the reason, and the principal refuses on it.
    """
    effective = read_ruleset_required_set(reader=forge, repo=repo)
    if isinstance(effective, EffectiveSetUnreadable):
        return NotGreen(head_sha=head_sha, reason=effective.detail)
    if not effective.contexts:
        return NotGreen(
            head_sha=head_sha,
            reason=f"the ruleset required-check set of {effective.branch} is empty",
        )
    try:
        runs, uncounted = _run_states(forge=forge, repo=repo, head_sha=head_sha)
        statuses = _status_states(forge=forge, repo=repo, head_sha=head_sha)
    except IncidentForgeReadError as error:
        return NotGreen(head_sha=head_sha, reason=f"check results unreadable: {error}")
    offending = tuple(
        found
        for context in sorted(effective.contexts)
        if (found := _offending(context=context, runs=runs, uncounted=uncounted, statuses=statuses))
        is not None
    )
    if offending:
        names = ", ".join(f"{o.context} ({o.state})" for o in offending)
        return NotGreen(
            head_sha=head_sha,
            reason=f"required checks not green on {head_sha}: {names}",
            contexts=offending,
        )
    return Green(head_sha=head_sha, contexts=effective.contexts)
