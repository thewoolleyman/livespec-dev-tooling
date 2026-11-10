"""Decide whether one reusable-check-matrix leg is omitted by incident policy.

`.github/workflows/reusable-check-matrix.yml` runs this once per leg, from a
checkout of the LATEST RELEASE of livespec-dev-tooling, never from the
consumer's tree and never from unreleased master:

    python3 -m livespec_dev_tooling.incident_matrix_omission

It reads these environment values:

- `GITHUB_EVENT_NAME`, `GITHUB_EVENT_PATH`, `GITHUB_REPOSITORY` and
  `GITHUB_WORKSPACE`, set by the runner for the caller's event;
- `CALLER_WORKFLOW_REF`, the caller's `github.workflow_ref`
  (`owner/repo/.github/workflows/<file>@<ref>`): in a reusable workflow the
  `github` context belongs to the CALLER, so this names the workflow that
  called the matrix;
- `GH_TOKEN`, the caller's token: `gh` uses it for the one read of that
  workflow file, made through the sanctioned `budgeted_gh.gh_read`;
- `INCIDENT_OMITTED`, the workflow's `incident-omitted` input: the caller's
  passed incident aggregate's `omitted` list, a JSON array of incident
  controller member names such as `["check-heading-coverage"]`;
- `INCIDENT_CI_RESULT`, the workflow's `incident-ci-result` input;
- `MATRIX_CHECK`, this leg's module slug from the `checks` input.

It writes `omit=true` or `omit=false` to `$GITHUB_OUTPUT` and exits 0, or it
exits 1 without writing anything when the input is malformed.

The rules, in order:

- **Only a pull request can omit.** Any other event (`push`,
  `pull_request_target`, `merge_group`, ...) answers `omit=false` without
  reading the input.
- **The input is a JSON array of strings, or nothing.** Anything else fails
  the leg before it can report an omission. Membership is exact equality.
- **Only an omittable member can be omitted** (`OMITTABLE_MEMBERS`): a coverage
  or spec member the incident controller defers that has a run-check module.
  `check-coverage` is deferred by the controller but is a `just` target with no
  module, so no matrix leg can be it; it is ignored. Any other listed name is
  refused with a warning.
- **Only a leg run-check can run can be omitted.** run-check runs
  `livespec_dev_tooling.checks.<slug>` verbatim, so a slug that is not a module
  name (`check-heading-coverage`) is refused and runs, and fails, as before.
- **Only an authorized incident can omit.** The caller's `incident-ci` result
  must be `success`; the event payload's pull request must carry the
  `expedited-incident-response` label and come from this repository, not a
  fork; and the CALLING workflow must pass the call-site rule of
  `incident_matrix_call_site`. That workflow is read at the pull request's
  BASE commit, the trusted revision: it holds only merged code, which passed
  review and the workflow-edit gates, while the head and the merge commit
  carry the PR author's edits. The copy GitHub actually ran (the merge commit,
  checked out in `GITHUB_WORKSPACE`) must be byte-identical to it, so a pull
  request that edits its calling workflow omits nothing. Otherwise the
  omission is refused with a warning and the leg runs its check.

An omitted leg prints a `::notice` annotation, so the check run shows the
omission beside its `success`. Every caller-supplied value is JSON-quoted
before it is printed, so no input can inject a workflow command.

`--check-callers [PATH ...]` runs the call-site rule over workflow files
(default: `.github/workflows/*.yml` and `*.yaml`) and exits 1 on a finding.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling import budgeted_gh
from livespec_dev_tooling import incident_matrix_call_site as call_site

__all__: list[str] = [
    "CONTROLLER_ONLY_MEMBERS",
    "INCIDENT_LABEL",
    "OMITTABLE_MEMBERS",
    "IncidentAuthority",
    "LegDecision",
    "decide",
    "leg_member",
    "main",
]

OMITTABLE_MEMBERS: frozenset[str] = frozenset(
    {
        "check-per-file-coverage",
        "check-check-coverage-incremental",
        "check-heading-coverage",
        "check-heading-coverage-debt-register",
        "check-no-todo-registry",
    }
)
# Deferred by the incident controller but no run-check module: never a matrix leg.
CONTROLLER_ONLY_MEMBERS: frozenset[str] = frozenset({"check-coverage"})
INCIDENT_LABEL = "expedited-incident-response"

_q = call_site.quoted
_PULL_REQUEST = "pull_request"
_MODULE_SLUG = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True, kw_only=True)
class LegDecision:
    """One leg's answer: the exit code, whether it is omitted, and what to print."""

    code: int
    omit: bool
    lines: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class IncidentAuthority:
    """What the leg can see of the incident: payload, result and the calling workflow.

    `caller` is the calling workflow's path, `base_text` its text at the pull
    request's base commit, and `running_text` the copy GitHub ran.
    """

    payload: Mapping[str, Any] | None
    repository: str
    incident_ci_result: str
    caller: str | None
    base_text: str | None
    running_text: str | None


def leg_member(*, check: str) -> str | None:
    """The member a module slug denotes, or None when run-check cannot run it."""
    if _MODULE_SLUG.fullmatch(check) is None:
        return None
    return "check-" + check.replace("_", "-")


def _map(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _unauthorized(*, authority: IncidentAuthority) -> str | None:
    """Why this pull request may not omit, or None when an incident authorizes it."""
    if authority.incident_ci_result != "success":
        return f"the caller's incident-ci result is {_q(value=authority.incident_ci_result)}"
    pull_request = _map(value=_map(value=authority.payload).get("pull_request"))
    labels = pull_request.get("labels")
    items = cast("list[object]", labels) if isinstance(labels, list) else []
    if INCIDENT_LABEL not in [_map(value=x).get("name") for x in items]:
        return f"the pull request does not carry the {INCIDENT_LABEL} label"
    head = _map(value=_map(value=pull_request.get("head")).get("repo")).get("full_name")
    base = _map(value=_map(value=pull_request.get("base")).get("repo")).get("full_name")
    if not (head == base == authority.repository and authority.repository):
        return f"the pull request's head repository is not {_q(value=authority.repository)}"
    return call_site.call_site_reason(
        caller=authority.caller, base_text=authority.base_text, running_text=authority.running_text
    )


def _parse(*, raw: str) -> tuple[str, ...] | None:
    """The input's names, or None when it is not a JSON array of strings."""
    if not raw.strip():
        return ()
    try:
        value: object = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    if not isinstance(value, list):
        return None
    items = cast("list[Any]", value)
    if not all(isinstance(item, str) for item in items):
        return None
    return tuple(cast("list[str]", items))


def _refusals(*, names: tuple[str, ...], check: str, member: str | None) -> tuple[str, ...]:
    refused = tuple(
        f"::warning::incident-omission-refused: {_q(value=name)} is not a coverage or spec "
        "member, so it is never omitted and runs wherever it is a leg"
        for name in sorted(set(names) - OMITTABLE_MEMBERS - CONTROLLER_ONLY_MEMBERS)
    )
    if names and member is None:
        refused += (
            f"::warning::incident-omission-refused-leg: {_q(value=check)} is not a module slug "
            "run-check can run, so it is never omitted",
        )
    return refused


def decide(*, event_name: str, raw: str, check: str, authority: IncidentAuthority) -> LegDecision:
    """Decide one leg. A non-pull_request event never reads `raw`."""
    if event_name != _PULL_REQUEST:
        return LegDecision(
            code=0,
            omit=False,
            lines=(
                f"incident-omission: {_q(value=event_name)} event; {_q(value=check)} runs, "
                "and the incident-omitted input is not read",
            ),
        )
    names = _parse(raw=raw)
    if names is None:
        return LegDecision(
            code=1,
            omit=False,
            lines=(
                "::error::incident-omitted-malformed: the incident-omitted input is not a "
                f"JSON array of strings ({_q(value=raw[:200])}); no leg may be omitted",
            ),
        )
    member = leg_member(check=check)
    lines = _refusals(names=names, check=check, member=member)
    requested = member in OMITTABLE_MEMBERS and member in names
    reason = _unauthorized(authority=authority) if requested else None
    if reason is not None:
        lines += (f"::warning::incident-omission-unauthorized: {reason}; {_q(value=check)} runs",)
    if not requested or reason is not None:
        return LegDecision(
            code=0,
            omit=False,
            lines=(*lines, f"incident-omission: {_q(value=check)} runs"),
        )
    notice = (
        f"::notice title=omitted-by-incident-policy::{_q(value=check)} ({member}) was not "
        "executed; the caller's passed incident CI aggregate defers it for this pull request"
    )
    return LegDecision(code=0, omit=True, lines=(*lines, notice))


def _read_payload(*, path: str) -> Mapping[str, Any] | None:
    try:
        value: object = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    return _map(value=value)


def _read_text(*, path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _authority(
    *, env: Mapping[str, str], read: Callable[..., budgeted_gh.GhRead]
) -> IncidentAuthority:
    """The incident as this leg can verify it, reading the calling workflow at the base."""
    payload = _read_payload(path=env.get("GITHUB_EVENT_PATH", ""))
    repository = env.get("GITHUB_REPOSITORY", "")
    caller = call_site.caller_path(
        workflow_ref=env.get("CALLER_WORKFLOW_REF", ""), repository=repository
    )
    base = _map(value=_map(value=_map(value=payload).get("pull_request")).get("base"))
    workspace = env.get("GITHUB_WORKSPACE", "")
    return IncidentAuthority(
        payload=payload,
        repository=repository,
        incident_ci_result=env.get("INCIDENT_CI_RESULT", ""),
        caller=caller,
        base_text=call_site.fetch_at(
            repository=repository,
            path=caller or "",
            sha=str(base.get("sha", "")),
            read=read,
        ),
        running_text=_read_text(path=Path(workspace) / caller) if caller and workspace else None,
    )


def main(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    read: Callable[..., budgeted_gh.GhRead] | None = None,
) -> int:
    """Decide this leg from the environment, or check call sites with `--check-callers`."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--check-callers"]:
        directory = Path.cwd() / ".github" / "workflows"
        named = [Path(p) for p in args[1:]]
        files = named or sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])
        findings = call_site.check_callers(paths=files)
        _ = sys.stderr.write("".join(f + "\n" for f in findings))
        return 1 if findings else 0
    env = os.environ if environ is None else environ
    decision = decide(
        event_name=env.get("GITHUB_EVENT_NAME", ""),
        raw=env.get("INCIDENT_OMITTED", ""),
        check=env.get("MATRIX_CHECK", ""),
        authority=_authority(env=env, read=read or budgeted_gh.gh_read),
    )
    stream = sys.stdout if decision.code == 0 else sys.stderr
    _ = stream.write("".join(line + "\n" for line in decision.lines))
    output = env.get("GITHUB_OUTPUT", "")
    if decision.code == 0 and output:
        with Path(output).open("a", encoding="utf-8") as handle:
            _ = handle.write(f"omit={'true' if decision.omit else 'false'}\n")
    return decision.code


if __name__ == "__main__":
    raise SystemExit(main())
