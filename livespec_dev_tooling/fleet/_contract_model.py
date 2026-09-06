"""Shared fleet obligation row model and vantage constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from livespec_dev_tooling.fleet._context import FleetContext, FleetMember, RowOutcome

__all__: list[str] = [
    "ADMIN_VANTAGE",
    "CENTRAL_APP_VANTAGE",
    "CENTRAL_VANTAGE",
    "ObligationRow",
    "RowFn",
]


# The VANTAGE a row's assert needs — i.e. which credential class can answer
# it. This is a property of the OBLIGATION, not of any particular run, which
# is why it is declared on the row rather than hardcoded as a row-id list in
# a runner: adding a scoped row is then a one-field decision at the table,
# and every lane re-partitions itself automatically.
#
# `central` — readable under whatever GitHub credential the central lane
# runs with (repo contents, topics, repo objects): the fleet App
# installation token in the automated contexts (per-PR CI, the scheduled
# fleet-conformance.yml, the release fan-out preflight) and the operator's
# own credential in a local `check-fleet-conformance` run, so these rows
# enforce in BOTH.
#
# `central-app` — needs the fleet GitHub App installation token ITSELF:
# `GET /installation/repositories` (the app-installation row's one read)
# answers only under an installation token, never under an operator PAT or
# oauth credential. Exactly the automated central contexts hold one, so the
# row enforces there; a local central sweep reports it out-of-vantage
# naming those contexts. This completes the vantage model
# (livespec-dev-tooling-29qo): with it, blind_rows is structurally 0 in
# every healthy context, which is what made blind escalatable to error.
#
# `admin` — needs GitHub ADMIN scope on each member (the Actions-secrets
# list and the branch-protection endpoints). The App token deliberately
# lacks admin scope (least privilege, livespec
# non-functional-requirements.md section "GitHub App auth model"), so these rows
# can only be answered by an operator's own admin `gh` credentials. They
# are enforced in the world-gate lane, which runs in the operator's own
# deliberate `just check` and in NEITHER local hook gate (it reads nine
# other repositories' live admin state, so a sibling's unrepaired state
# would refuse unrelated commits here) — see `fleet_conformance_admin.py`.
CENTRAL_VANTAGE = "central"
CENTRAL_APP_VANTAGE = "central-app"
ADMIN_VANTAGE = "admin"


class RowFn(Protocol):
    """One obligation-row operation (assert or reconcile) over a member."""

    def __call__(self, *, ctx: FleetContext, member: FleetMember) -> RowOutcome: ...


@dataclass(frozen=True, kw_only=True)
class ObligationRow:
    """One per-class obligation: assert logic plus its reconcile reference.

    `reconcile` is None where the fix is not machine-applicable from
    this vantage point; `manual_hint` then tells the operator what to
    do (the hint never gates anything the check itself gates — the
    no-circular-gating rule).

    `vantage` names the credential class that can answer the row, so a
    lane runs the rows it can actually evaluate and reports the rest as
    out-of-vantage (naming the owning lane) rather than as blind.
    """

    row_id: str
    obligation_type: str
    applies_to: frozenset[str]
    assert_member: RowFn
    reconcile: RowFn | None = None
    manual_hint: str = ""
    vantage: str = CENTRAL_VANTAGE
