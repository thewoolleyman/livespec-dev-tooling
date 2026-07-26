"""Exit attribution for the MEMBER leg of the central fleet-conformance sweep.

Extracted from `fleet_conformance.py` (the `_lanes` / `_contract_rows` precedent)
because adding the member-scoping branch inline crossed that module's 250-LLOC hard
ceiling and pushed `main()` past its return-count limit. The split is FORCED by those
gates rather than chosen, and it lands on a real seam: this module owns one question
— given a completed sweep, what exit status does THIS member's CI deserve — and
touches neither the sweep nor the GitHub seam.

Per the maintainer ruling of 2026-07-21, a non-conforming fleet member must fail ONLY
its own CI, never every other member's. Surfacing and BLOCKING are separable: a
member registered before its wiring lands SHOULD surface immediately and loudly
(register-first is deliberate), but it must not land as a hard merge-gate failure in a
repo that neither owns nor can fix it.

Two invariants this module must not break, both learned the expensive way:

- **Scope the EXIT, never the EVALUATION.** Every member is evaluated and reported by
  the caller before this module is consulted. Filtering the evaluation would make each
  repo blind to fleet state and would silently shrink what the central sweep's own
  per-repo runs cover.
- **`blind_rows` is NOT scoped.** A blind row means a lane that OWNS a row could not
  read its source — this check's own vacuity, not any member's violation — so it keeps
  failing in every context. Letting the member scoping swallow it would reopen exactly
  the hole the blind-row escalation closed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import structlog.stdlib

    from livespec_dev_tooling.fleet._lanes import MemberVerdict
    from livespec_dev_tooling.fleet.contract import Manifest

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

__all__: list[str] = ["RunTallies", "member_ci_exit_code", "own_failing_rows"]


def own_failing_rows(
    *, member_verdicts: tuple[MemberVerdict, ...], running_as: str
) -> tuple[str, ...]:
    """The running member's own failing rows, read off the per-member verdicts.

    Reuses the verdict substrate the release-dispatch filter already consumes rather
    than re-deriving attribution, so the exit status and the published verdict
    artifact can never disagree about who violated what.
    """
    for verdict in member_verdicts:
        if verdict.member == running_as:
            return verdict.failing_rows
    return ()


@dataclass(frozen=True, kw_only=True)
class RunTallies:
    """The three run-level counts the summary reports, carried as one value.

    Grouped rather than passed as three parameters because they always travel
    together and are always reported together — and because the caller's argument
    count is itself gated. `errors` is the FLEET-WIDE total, deliberately: it stays
    in the summary so a member run still reports fleet state even though only the
    running member's rows decide its exit.
    """

    errors: int
    blind_rows: int
    out_of_vantage_rows: int


def member_ci_exit_code(
    *,
    manifest: Manifest,
    member_verdicts: tuple[MemberVerdict, ...],
    running_as: str | None,
    tallies: RunTallies,
    log: structlog.stdlib.BoundLogger,
) -> int:
    """The exit status a member's own CI leg deserves: 0, 1 (precondition), or 4.

    `running_as` is the caller's already-resolved answer to "which member am I", so
    the resolution stays monkeypatchable at the CLI module and this function stays a
    pure decision over values.
    """
    if running_as is None:
        log.error(
            "member-ci run cannot resolve which member it is running as",
            hint=(
                "the origin remote is not a github.com URL; run inside a member "
                "checkout, or omit --member-ci to run the fleet-level sweep"
            ),
        )
        return 1
    if running_as not in manifest.member_names():
        # Not a quiet pass: scoping the exit to "this repo's findings" when this repo
        # has no manifest entry would scope it to NOTHING and report success while
        # enforcing nothing.
        log.error(
            "member-ci run is not a fleet manifest member",
            running_as=running_as,
            hint=(
                "register it in livespec .livespec-fleet-manifest.jsonc, or omit "
                "--member-ci: an unregistered repo has no findings of its own to "
                "scope to, so scoping would pass vacuously"
            ),
        )
        return 1
    owned = own_failing_rows(member_verdicts=member_verdicts, running_as=running_as)
    if owned or tallies.blind_rows:
        log.error(
            "fleet conformance FAILED for this member",
            member=running_as,
            own_failing_rows=list(owned),
            error_findings=tallies.errors,
            blind_rows=tallies.blind_rows,
            out_of_vantage_rows=tallies.out_of_vantage_rows,
        )
        return 4
    log.info(
        "fleet conformance passed for this member",
        member=running_as,
        own_failing_rows=[],
        error_findings=tallies.errors,
        blind_rows=tallies.blind_rows,
        out_of_vantage_rows=tallies.out_of_vantage_rows,
        hint=(
            "findings about OTHER members are reported above and are not this "
            "repo's to fix; the scheduled fleet sweep and the release fan-out "
            "preflight fail on them"
        ),
    )
    return 0
