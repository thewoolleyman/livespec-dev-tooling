# livespec_dev_tooling/fleet/

The fleet-membership contract surface (per
`livespec/SPECIFICATION/non-functional-requirements.md` §"Fleet
membership contract"). ONE shared contract definition — the per-class
obligation table in `contract.py`, each row referencing typed assert
logic AND (where machine-fixable) reconcile logic — consumed by BOTH
`python -m livespec_dev_tooling.fleet.fleet_conformance` (assert mode;
central vantage point over every manifest member) and `python -m
livespec_dev_tooling.fleet.wire_fleet_member` (idempotent reconcile
mode; operator-invoked, NOT CI). Manifest `adopters` are consumed by
`_adopter_lane.py` ONLY — the posture-gated `claude-plugin-currency`
leg the ADMIN world-gate lane (`fleet_conformance_admin`) owns; the
per-class obligation table never applies to adopters, and `profile`
has no sweep reader by design.

These are NOT canonical per-repo checks: nothing here lives under
`livespec_dev_tooling/checks/`, so the canonical-slug discovery does
not pick them up and sibling repos do not wire them. Row functions
return outcome values (`RowPass` / `RowFinding` / `RowSkip`) instead
of logging; the two CLI engines own all structlog output. All GitHub
access flows through the injected `GhRunner` seam on `FleetContext`
so tests run hermetically. Secret VALUES never appear in argv, logs,
or outcomes — `wire_fleet_member` pushes them env→stdin only.
