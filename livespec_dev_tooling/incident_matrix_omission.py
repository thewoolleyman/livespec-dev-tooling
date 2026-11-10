"""Decide whether one reusable-check-matrix leg is omitted by incident policy.

`.github/workflows/reusable-check-matrix.yml` runs this once per leg, from the
livespec-dev-tooling Actions checkout and never from the consumer's tree:

    python3 -m livespec_dev_tooling.incident_matrix_omission

It reads three environment values:

- `GITHUB_EVENT_NAME`, set by the runner (the caller's event);
- `INCIDENT_OMITTED`, the workflow's `incident-omitted` input: the caller's
  passed incident aggregate's `omitted` list, a JSON array of incident
  controller member names such as `["check-heading-coverage"]`;
- `MATRIX_CHECK`, this leg's slug from the `checks` input.

It writes `omit=true` or `omit=false` to `$GITHUB_OUTPUT` and exits 0, or it
exits 1 without writing anything when the input is malformed.

Three rules decide the answer:

- **Only a pull request can omit.** Any other event, a master push included,
  answers `omit=false` without reading the input, so a push runs every
  requested check whatever labels, markers or input it receives.
- **Only a coverage or spec member can be omitted.** `OMITTABLE_MEMBERS` is the
  allowlist: the members the incident controller defers for the
  `incident-policy:coverage` or `incident-policy:spec` reason. A listed name
  outside it is refused with a warning, and its leg runs its check.
- **The input is a JSON array of strings, or nothing.** A JSON string, object,
  number or any other value fails the leg before it can report an omission.
  Membership is exact string equality, never a substring test. An empty value
  is the absent output GitHub renders as `''`, and omits nothing.

A leg slug names its member in either form the matrix accepts: the module
slug (`heading_coverage`) or the canonical kebab slug
(`check-heading-coverage`).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

__all__: list[str] = ["OMITTABLE_MEMBERS", "LegDecision", "decide", "leg_member", "main"]

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

_PULL_REQUEST = "pull_request"
_MEMBER_PREFIX = "check-"


@dataclass(frozen=True, kw_only=True)
class LegDecision:
    """One leg's answer: the exit code, whether it is omitted, and what to print."""

    code: int
    omit: bool
    lines: tuple[str, ...]


def leg_member(*, check: str) -> str:
    """The incident controller member name a matrix leg slug denotes."""
    if check.startswith(_MEMBER_PREFIX):
        return check
    return _MEMBER_PREFIX + check.replace("_", "-")


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


def decide(*, event_name: str, raw: str, check: str) -> LegDecision:
    """Decide one leg. A non-pull_request event never reads `raw`."""
    if event_name != _PULL_REQUEST:
        return LegDecision(
            code=0,
            omit=False,
            lines=(
                f"incident-omission: {event_name or 'unknown'} event; {check} runs, "
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
                f"JSON array of strings ({raw[:200]!r}); no leg may be omitted",
            ),
        )
    refused = tuple(
        f"::warning::incident-omission-refused: {name} is not a coverage or spec member, "
        "so it is never omitted and runs wherever it is a leg"
        for name in sorted(set(names) - OMITTABLE_MEMBERS)
    )
    member = leg_member(check=check)
    omit = member in OMITTABLE_MEMBERS and member in names
    verdict = (
        f"incident-omission: {check} ({member}) is omitted-by-incident-policy"
        if omit
        else f"incident-omission: {check} runs"
    )
    return LegDecision(code=0, omit=omit, lines=(*refused, verdict))


def main(*, environ: Mapping[str, str] | None = None) -> int:
    """Decide this leg from the environment and publish `omit` to `$GITHUB_OUTPUT`."""
    env = os.environ if environ is None else environ
    decision = decide(
        event_name=env.get("GITHUB_EVENT_NAME", ""),
        raw=env.get("INCIDENT_OMITTED", ""),
        check=env.get("MATRIX_CHECK", ""),
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
