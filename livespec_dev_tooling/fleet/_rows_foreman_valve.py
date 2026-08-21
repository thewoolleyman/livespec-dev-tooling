"""Foreman-valve-disposition declaration row — ARMED 2026-08-21.

Every governed fleet member must DECLARE `foreman_valve_disposition` in its
`.livespec.jsonc`. The row does NOT mandate which value: a repo may
deliberately choose `report-only`, and this check passes it. What the row
forbids is arriving at `report-only` SILENTLY.

WHY SILENCE IS THE DEFECT. `overseer/foreman_valve_policy.effective_valve_
disposition` fail-closes to `report-only` when the key is absent. Under
`report-only` a foreman SURFACES every human valve and blocked session and
ACTS ON NONE of them, so work sits until a person happens to look. The
fail-closed default is correct as a default; what is wrong is that nothing
distinguishes a repo that CHOSE it from a repo that never chose at all.

THE MEASUREMENT THIS ROW COMES FROM, 2026-08-21: 5 of 14 governed repos
declared the key. The other 9 had been surfacing valves and acting on none of
them for weeks. A live foreman seat reported its own disposition as
`configured: null, source: default` while a picker it had surfaced sat over two
hours before clearing. None of those 9 had chosen `report-only` — they had
never been asked.

WHY IT DRIFTED, and it is not neglect. The fleet-wide autonomy-lever rollout
(`livespec-jvdvx4`, child `.15`) armed every safe `spec_governance` and
`dispatcher` lever on every governed repo and CLOSED. This key lives in the
`livespec-overseer` namespace, so it was OUT OF THAT SWEEP'S SCOPE BY
CONSTRUCTION and no carrier ever covered it. It was then set ad hoc, repo by
repo, whenever an individual foreman happened to ask its maintainer — five
repos across four separate dates. A sweep scoped by namespace leaves every
other namespace unattended, and nothing noticed for a week.

THIS ROW IS REGISTERED IN `OBLIGATION_ROWS` as `foreman-valve-declared`, at
`ALL_CLASSES`: every governed member runs foreman seats, and every one of them
should have chosen.

ARMED AT BIRTH, DELIBERATELY, AND THE PRECONDITION WAS MEASURED FIRST. The
sibling `_rows_decision_authority` row shipped DISARMED and was armed only once
its offender count hit zero, because `plan/rop-railway-enforcement/` records a
check armed ahead of adoption turning five repos red and being reverted. That
ordering is respected here rather than skipped: the fan-out landed FIRST, and
all 14 governed members were re-measured on their own `origin/master` — not a
working tree — as carrying the key before this row was registered. Arming at
birth is safe only because the offender count was already zero; if you are
adding a row of your own, measure before you arm rather than copying this.

AN UNRECOGNIZED VALUE IS A FINDING, NOT A PASS. The resolver treats a value it
does not recognize exactly like omission: it falls back to `report-only` and
sets a `warning` field nobody reads. So a presence-only test would report a
repo compliant while it ran on the very default this row exists to prevent.
`declared_valve_disposition` returns the raw declared string and the caller
judges it, so a typo names itself in the finding.

CAN'T-READ IS NOT ABSENT. An unreadable or unparseable `.livespec.jsonc` SKIPS
rather than finding. A member whose config cannot be fetched has not been shown
to be non-compliant, and reporting it as an offender would be a finding the
member cannot act on.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "CONFIG_KEY",
    "CONFIG_PATH",
    "CONFIG_SECTION",
    "RECOGNIZED_DISPOSITIONS",
    "assert_foreman_valve_declared",
    "declared_valve_disposition",
    "parsed_config",
]

CONFIG_PATH = ".livespec.jsonc"

# Mirrors `overseer/foreman_valve_policy.py`. Kept as literals rather than
# imported: this package does not depend on the overseer package, and a silent
# divergence would make the row assert something the resolver does not read.
# If the resolver's key or values change, this row must be updated with it —
# that coupling is real and is better stated here than hidden behind an import
# that does not exist.
CONFIG_SECTION = "livespec-overseer"
CONFIG_KEY = "foreman_valve_disposition"
RECOGNIZED_DISPOSITIONS: tuple[str, ...] = ("report-only", "consensus")


def parsed_config(*, config_text: str) -> dict[str, Any] | None:
    """The parsed `.livespec.jsonc` object, or `None` when it is not parseable.

    Returns `None` rather than raising so the caller can SKIP an unparseable
    config instead of reporting an offender. `jsoncomment` surfaces malformed
    input as `ValueError` (`json.JSONDecodeError` derives from it); the catch is
    narrow deliberately, since a broad one is banned outside `io/` here and
    would also swallow defects in this module.
    """
    try:
        loaded = jsoncomment.loads(config_text)
    except ValueError:
        return None
    if not isinstance(loaded, dict):
        return None
    return cast(dict[str, Any], loaded)


def declared_valve_disposition(*, config_text: str) -> str | None:
    """The raw declared disposition, or `None` when absent or unparseable.

    Returns the value UNJUDGED so the caller can name an unrecognized one in
    its finding. Resolves `<section>.<key>` first and the bare top-level `<key>`
    second, which is the precedence the resolver itself applies.

    `None` is deliberately ambiguous between "absent" and "unparseable" — the
    two have different outcomes, so `assert_foreman_valve_declared` separates
    them by calling `parsed_config` first rather than inferring from this.
    """
    config = parsed_config(config_text=config_text)
    if config is None:
        return None
    return _declared_from(config=config)


def _declared_from(*, config: dict[str, Any]) -> str | None:
    section = config.get(CONFIG_SECTION)
    if isinstance(section, dict) and CONFIG_KEY in section:
        nested = cast(dict[str, Any], section).get(CONFIG_KEY)
        return nested if isinstance(nested, str) else None
    value = config.get(CONFIG_KEY)
    return value if isinstance(value, str) else None


def assert_foreman_valve_declared(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member's `.livespec.jsonc` declares `foreman_valve_disposition`.

    Passes on EITHER recognized value — the obligation is to have chosen, not
    to have chosen a particular way. Skips a member whose config is unreadable
    or unparseable (can't-read is not absent). A finding names the member, and
    an unrecognized value names itself.
    """
    config_text = ctx.file_text(repo=member.repo, path=CONFIG_PATH)
    if config_text is None:
        return RowSkip(reason=f"{member.repo}: {CONFIG_PATH} unreadable or absent")
    config = parsed_config(config_text=config_text)
    if config is None:
        return RowSkip(reason=f"{member.repo}: {CONFIG_PATH} is not parseable jsonc")
    declared = _declared_from(config=config)
    if declared is None:
        return RowFinding(
            message=(
                f"{member.repo}: {CONFIG_PATH} declares no "
                f"{CONFIG_SECTION}.{CONFIG_KEY} — the resolver fail-closes to "
                f"'report-only', so this repo's foreman surfaces every human valve "
                f"and acts on none, without having chosen to"
            )
        )
    if declared not in RECOGNIZED_DISPOSITIONS:
        return RowFinding(
            message=(
                f"{member.repo}: {CONFIG_PATH} declares {CONFIG_KEY} "
                f"'{declared}', which the resolver does not recognize — it falls "
                f"back to 'report-only' exactly as if the key were absent "
                f"(expected one of {', '.join(RECOGNIZED_DISPOSITIONS)})"
            )
        )
    return RowPass()
