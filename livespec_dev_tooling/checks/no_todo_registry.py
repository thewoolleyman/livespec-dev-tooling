"""no_todo_registry — `tests/heading-coverage.json` TODO entries, gated by OWNERSHIP.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-no-todo-registry` row), a `test: "TODO"`
entry is an authoring placeholder rather than real coverage.

ENTRY SCHEMA — the `work_item` field. A heading-coverage entry
using `test: "TODO"` MUST also carry a non-empty string
`work_item` naming the covering-test work-item that owns
replacing it, stamped beside `reason`. Per livespec core's
`SPECIFICATION/spec.md` (the heading-coverage co-edit rule) the
revise flow files that item and stamps the returned id; where a
project has no configured orchestrator the author supplies an
id from the project's own tracker. "An unowned TODO entry is
never valid." An entry whose `work_item` is absent, empty,
whitespace-only, or not a string is UNOWNED.

The TODO scan ALWAYS runs (no skip carve-out, no exemption list,
no per-repo opt-in). A self-documenting severity lever selects
between two tiers:

- PER-COMMIT tier (lever unset or empty): every TODO entry is
  logged at WARNING level and the check exits 0, so authoring
  placeholders surface without blocking `just check`. Ownership
  does NOT change this tier's verdict.
- RELEASE tier (`LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST`
  set to a non-empty value; CI sets it for the release context):
  per `SPECIFICATION/non-functional-requirements.md`
  § "Release-gate targets", the tier rejects an UNOWNED TODO
  and, where the configured tracker makes liveness mechanically
  checkable, one whose named `work_item` is closed or
  nonexistent. An owned live TODO does not block an unrelated
  release.

The release tier is therefore strictly NARROWER than the
per-commit tier's finding set — unowned is a subset of any — so
narrowing it can only stop reddening repos, never start.

LIVENESS IS BEST-EFFORT AND ABSENT BY DEFAULT. No tracker is
configured for this repo family, and a release runs on hosted CI
that cannot reach a loopback ledger, so `_probe_work_item_liveness`
reports `None` (UNVERIFIED) rather than inventing a verdict. An
UNVERIFIED entry PASSES, but emits a `liveness_unverified`
diagnostic — an unreachable tracker is not a passing liveness
check, and the two must never be indistinguishable. Liveness is
deliberately confined to the release tier: a per-commit verdict
depending on mutable external state could flip master red with no
commit, which `.ai/ci-gate-discipline.md` treats as a real broken
state rather than a notification.

The check loads the JSON file (strict JSON, not JSONC) and
walks the array. If the file is missing or contains no TODO
entries, the check exits 0.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_COVERAGE_PATH = Path("tests") / "heading-coverage.json"
_FAIL_ENV_VAR = "LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST"


def _is_owned(*, entry: dict[str, object]) -> bool:
    """Return whether `entry` names a work-item that owns replacing its TODO.

    Absent, non-string, empty, and whitespace-only values are all UNOWNED —
    the ratified rule admits only a non-empty id.
    """
    work_item = entry.get("work_item")
    return isinstance(work_item, str) and bool(work_item.strip())


def _probe_work_item_liveness(*, work_item: str) -> bool | None:
    """Best-effort liveness probe for `work_item`; `None` means UNVERIFIED.

    ABSENT BY DEFAULT, and that is the shipped production behavior rather
    than a placeholder: this repo family configures no tracker at all, and
    the release gate runs on hosted CI that cannot reach a loopback ledger.
    Returning `None` keeps the check honest — it reports that liveness was
    not established instead of asserting a work-item is live.

    A consumer that configures a reachable tracker replaces this seam; the
    ratified rule only asks for liveness "where the configured tracker
    makes liveness mechanically checkable".
    """
    del work_item  # No tracker is configured; nothing to query.
    return None


def _warn_every_todo(*, offenders: list[dict[str, object]]) -> None:
    """PER-COMMIT tier: warn on every TODO entry regardless of ownership.

    Deliberately identical to the pre-ownership behavior, and that identity
    is load-bearing: it is what makes the release-tier narrowing a strict
    loosening that reddens no repository.
    """
    emit = structlog.get_logger("no_todo_registry")
    for entry in offenders:
        emit.warning(
            'heading-coverage.json entry has `test: "TODO"`',
            heading=entry.get("heading"),
            spec_root=entry.get("spec_root"),
            fail_env_var=_FAIL_ENV_VAR,
            failing=False,
        )


def _release_tier_failures(*, offenders: list[dict[str, object]]) -> int:
    """RELEASE tier: count entries that must block the release.

    Rejects an UNOWNED entry, and an owned one whose work-item is checkably
    closed or nonexistent. An owned entry whose liveness cannot be
    established PASSES, but emits a `liveness_unverified` diagnostic so it
    is never indistinguishable from a verified one.
    """
    emit = structlog.get_logger("no_todo_registry")
    failing = 0
    for entry in offenders:
        if not _is_owned(entry=entry):
            failing += 1
            emit.error(
                'heading-coverage.json entry has `test: "TODO"` with no owning `work_item`',
                heading=entry.get("heading"),
                spec_root=entry.get("spec_root"),
                fail_env_var=_FAIL_ENV_VAR,
                failing=True,
            )
            continue
        work_item = cast("str", entry.get("work_item")).strip()
        live = _probe_work_item_liveness(work_item=work_item)
        if live is None:
            emit.warning(
                "owned TODO entry accepted; work-item liveness UNVERIFIED "
                "(no reachable tracker configured)",
                heading=entry.get("heading"),
                spec_root=entry.get("spec_root"),
                work_item=work_item,
                liveness_unverified=True,
                failing=False,
            )
        elif not live:
            failing += 1
            emit.error(
                'heading-coverage.json entry has `test: "TODO"` owned by a '
                "closed or nonexistent work-item",
                heading=entry.get("heading"),
                spec_root=entry.get("spec_root"),
                work_item=work_item,
                fail_env_var=_FAIL_ENV_VAR,
                failing=True,
            )
    return failing


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    cwd = Path.cwd()
    coverage_path = cwd / _COVERAGE_PATH
    if not coverage_path.is_file():
        return 0
    text = coverage_path.read_text(encoding="utf-8")
    parsed = json.loads(text)
    offenders: list[dict[str, object]] = []
    if isinstance(parsed, list):
        # The `cast` is the single typed parse boundary: `json.loads` yields
        # `Any`, the `isinstance` guard narrows to `list`, and the cast gives
        # the elements a typed `object` shape so the per-element
        # `isinstance(entry, dict)` filter stays a load-bearing runtime guard.
        # The compound condition (single `if`, inline cast evaluated only
        # after the isinstance short-circuit) preserves the original branch
        # shape — no new branch, so coverage stays 100%.
        entries = cast("list[object]", parsed)
        for entry in entries:
            if isinstance(entry, dict) and cast("dict[str, object]", entry).get("test") == "TODO":
                offenders.append(cast("dict[str, object]", entry))
    if not offenders:
        return 0
    if not bool(os.environ.get(_FAIL_ENV_VAR)):
        _warn_every_todo(offenders=offenders)
        return 0
    return 1 if _release_tier_failures(offenders=offenders) else 0


if __name__ == "__main__":
    raise SystemExit(main())
