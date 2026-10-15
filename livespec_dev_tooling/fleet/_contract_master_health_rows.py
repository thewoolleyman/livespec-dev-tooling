"""The red-master self-healing slice of the central obligation table.

Spliced into `OBLIGATION_ROWS` at the position its row occupies, the same way
`_contract_declaration_rows` and `_contract_github_state_rows` are, and for the
same recorded reason: `_contract_rows.py` has TWICE reached its 250-LLOC hard
ceiling and silently closed the fleet's one obligation table to new rows
(`livespec-dev-tooling-oitd` at 246, `livespec-dev-tooling-lptplj` at 262). It
sat at 235 when this slice was authored, so an inline row here would have left
room for roughly one more — which is the state both of those work-items record
as the failure.

The slice is named for a CONCERN rather than for one row: plan
`red-master-self-healing` (epic `livespec-dev-tooling-zcp5vb`) has a sibling
child E1 — the "master red longer than N minutes with no revert pull request in
flight" detector — whose row belongs beside this one.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._contract_classes import ALL_CLASSES
from livespec_dev_tooling.fleet._contract_model import ObligationRow
from livespec_dev_tooling.fleet._reconcile_shims import reconcile_shim_workflows
from livespec_dev_tooling.fleet._rows_files import assert_master_health_workflow

__all__: list[str] = [
    "MASTER_HEALTH_ROWS",
]


MASTER_HEALTH_ROWS: tuple[ObligationRow, ...] = (
    # ALL_CLASSES because a red master stops ANY member's factory through the
    # green-master dispatch gate, so no class can opt out — and with a
    # `reconcile`, because charter item 6 makes `wire-fleet-member` the ONLY
    # path by which the shim reaches a repository. A `manual_hint` here would
    # invite exactly the hand-configuration that item forbids.
    #
    # ARMED AT BIRTH, and the arming is sound for a reason the sibling rows in
    # `_contract_rows` could not use. Their precondition was a pre-measured
    # offender count of ZERO; this obligation's offender count is EVERY member
    # until the release carrying the reconciler is pinned and wired, so there is
    # no zero to wait for. What makes it landable anyway is that the row is
    # MACHINE-FIXABLE end to end — one `wire-fleet-member` run per member
    # resolves it — and that the repository rolling it out is the one whose
    # dispatch it gates. What `plan/rop-railway-enforcement/` records as
    # forbidden is arming a check whose offenders CANNOT satisfy it (46c5dab
    # reddened five repos and was reverted in f4247110); these can, through the
    # ordinary wire run, with no change of shape asked of them.
    ObligationRow(
        row_id="workflow-master-health-reconcile",
        obligation_type="committed-file",
        applies_to=ALL_CLASSES,
        assert_member=assert_master_health_workflow,
        reconcile=reconcile_shim_workflows,
    ),
)
