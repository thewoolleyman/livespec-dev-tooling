"""Decide whether one reusable-check-matrix leg is omitted by incident policy.

`.github/workflows/reusable-check-matrix.yml` runs this once per leg, from a
checkout of the LATEST RELEASE of livespec-dev-tooling, never from the
consumer's tree and never from unreleased master:

    python3 -m livespec_dev_tooling.incident_matrix_omission

It reads these environment values:

- `GITHUB_EVENT_NAME`, `GITHUB_EVENT_PATH`, `GITHUB_REPOSITORY` and
  `GITHUB_WORKSPACE`, set by the runner for the caller's event;
- `INCIDENT_OMITTED`, the workflow's `incident-omitted` input: the caller's
  passed incident aggregate's `omitted` list, a JSON array of incident
  controller member names such as `["check-heading-coverage"]`;
- `INCIDENT_CI_RESULT`, the workflow's `incident-ci-result` input: the
  caller's `incident-ci` job result;
- `MATRIX_CHECK`, this leg's module slug from the `checks` input.

It writes `omit=true` or `omit=false` to `$GITHUB_OUTPUT` and exits 0, or it
exits 1 without writing anything when the input is malformed.

The rules, in order:

- **Only a pull request can omit.** Any other event (`push`,
  `pull_request_target`, `merge_group`, ...) answers `omit=false` without
  reading the input.
- **The input is a JSON array of strings, or nothing.** Anything else fails
  the leg before it can report an omission. Membership is exact equality.
- **Only a coverage or spec member can be omitted** (`OMITTABLE_MEMBERS`). A
  listed name outside it is refused with a warning.
- **Only a leg run-check can run can be omitted.** run-check runs
  `livespec_dev_tooling.checks.<slug>` verbatim, so a slug that is not a module
  name (`check-heading-coverage`) is refused and runs, and fails, as before.
- **Only an authorized incident can omit.** The caller's `incident-ci` result
  must be `success`; the event payload's pull request must carry the
  `expedited-incident-response` label and come from this repository, not a
  fork; and the caller's workflows must wire both inputs only from the
  `incident-ci` job's guarded output (`caller_wiring_findings`). Otherwise the
  omission is refused with a warning and the leg runs its check.

An omitted leg prints a `::notice` annotation, so the check run shows the
omission beside its `success`. Every caller-supplied value is JSON-quoted
before it is printed, so no input can inject a workflow command.

`--check-callers [PATH ...]` runs the wiring rule over workflow files (default:
`.github/workflows/*.yml` and `*.yaml`) and exits 1 on a finding.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

__all__: list[str] = [
    "GUARDED_OMITTED",
    "GUARDED_RESULT",
    "INCIDENT_LABEL",
    "OMITTABLE_MEMBERS",
    "IncidentAuthority",
    "LegDecision",
    "caller_wiring_findings",
    "decide",
    "leg_member",
    "main",
]

OMITTABLE_MEMBERS: frozenset[str] = frozenset(
    {
        "check-coverage",
        "check-per-file-coverage",
        "check-check-coverage-incremental",
        "check-heading-coverage",
        "check-heading-coverage-debt-register",
        "check-no-todo-registry",
    }
)
INCIDENT_LABEL = "expedited-incident-response"
GUARDED_OMITTED = (
    "${{ needs.incident-ci.result == 'success' && needs.incident-ci.outputs.omitted || '[]' }}"
)
GUARDED_RESULT = "${{ needs.incident-ci.result }}"
_WIRED = {"incident-omitted": GUARDED_OMITTED, "incident-ci-result": GUARDED_RESULT}

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
    """What the leg can see of the incident: payload, repository, result and wiring."""

    payload: Mapping[str, Any] | None
    repository: str
    incident_ci_result: str
    workflows: tuple[tuple[str, str], ...]


def _q(*, value: str) -> str:
    """A caller value as one inert JSON string: no newline, no bare `%`."""
    return json.dumps(value).replace("%", "%25")


def leg_member(*, check: str) -> str | None:
    """The member a module slug denotes, or None when run-check cannot run it."""
    if _MODULE_SLUG.fullmatch(check) is None:
        return None
    return "check-" + check.replace("_", "-")


def _wirings(*, workflows: Sequence[tuple[str, str]]) -> list[tuple[str, str, str, str]]:
    """Every non-comment line naming an incident input: (where, key, value, line)."""
    found: list[tuple[str, str, str, str]] = []
    for source, text in workflows:
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            for key in _WIRED:
                if stripped.startswith("#") or f"{key}:" not in stripped:
                    continue
                value = stripped.removeprefix(f"{key}:").strip()
                if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                found.append((f"{source}:{number}", key, value, stripped))
    return found


def caller_wiring_findings(*, workflows: Sequence[tuple[str, str]]) -> list[str]:
    """Each line that wires an incident input from anything but `incident-ci`'s guarded output."""
    return [
        f"{where}: {key} is not wired from the incident-ci job's guarded output "
        f"{_WIRED[key]}: {_q(value=line)}"
        for where, key, value, line in _wirings(workflows=workflows)
        if value not in ("", _WIRED[key])
    ]


def _map(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _unauthorized(*, authority: IncidentAuthority) -> str | None:
    """Why this pull request may not omit, or None when an incident authorizes it."""
    if authority.incident_ci_result != "success":
        return f"the caller's incident-ci result is {_q(value=authority.incident_ci_result)}"
    pull_request = _map(value=_map(value=authority.payload).get("pull_request"))
    labels = pull_request.get("labels")
    items = cast("list[object]", labels) if isinstance(labels, list) else []
    names = [_map(value=x).get("name") for x in items]
    if INCIDENT_LABEL not in names:
        return f"the pull request does not carry the {INCIDENT_LABEL} label"
    head = _map(value=_map(value=pull_request.get("head")).get("repo")).get("full_name")
    base = _map(value=_map(value=pull_request.get("base")).get("repo")).get("full_name")
    if not (head == base == authority.repository and authority.repository):
        return f"the pull request's head repository is not {_q(value=authority.repository)}"
    wired = any(
        (key, value) == ("incident-omitted", GUARDED_OMITTED)
        for _where, key, value, _line in _wirings(workflows=authority.workflows)
    )
    if caller_wiring_findings(workflows=authority.workflows) or not wired:
        return "the caller's workflows do not wire incident-omitted only from incident-ci"
    return None


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
        for name in sorted(set(names) - OMITTABLE_MEMBERS)
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
            code=0, omit=False, lines=(*lines, f"incident-omission: {_q(value=check)} runs")
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


def _workflows(*, root: Path, paths: Sequence[str] = ()) -> tuple[tuple[str, str], ...]:
    """(path, text) of the named files, or of every workflow under `root`."""
    directory = root / ".github" / "workflows"
    files = [Path(p) for p in paths] or [*directory.glob("*.yml"), *directory.glob("*.yaml")]
    return tuple((str(f), f.read_text(encoding="utf-8")) for f in sorted(files) if f.is_file())


def main(*, argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    """Decide this leg from the environment, or check caller wiring with `--check-callers`."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--check-callers"]:
        findings = caller_wiring_findings(workflows=_workflows(root=Path.cwd(), paths=args[1:]))
        _ = sys.stderr.write("".join(f + "\n" for f in findings))
        return 1 if findings else 0
    env = os.environ if environ is None else environ
    workspace = env.get("GITHUB_WORKSPACE", "")
    authority = IncidentAuthority(
        payload=_read_payload(path=env.get("GITHUB_EVENT_PATH", "")),
        repository=env.get("GITHUB_REPOSITORY", ""),
        incident_ci_result=env.get("INCIDENT_CI_RESULT", ""),
        workflows=_workflows(root=Path(workspace)) if workspace else (),
    )
    decision = decide(
        event_name=env.get("GITHUB_EVENT_NAME", ""),
        raw=env.get("INCIDENT_OMITTED", ""),
        check=env.get("MATRIX_CHECK", ""),
        authority=authority,
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
