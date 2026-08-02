"""CLI end-to-end test harness — the single canonical implementation.

Per `livespec/SPECIFICATION/contracts.md` section "CLI end-to-end harness contract"
(requirement 6), the top-of-pyramid, user-surface end-to-end harness — driver,
structural skill discovery, per-skill fixtures loader, time-bomb coverage gate,
and step orchestrator — ships from `livespec-dev-tooling` and is consumed by
every plugin repo via the existing pin-bump dependency flow.

Consumers import the entry point as

    from livespec_dev_tooling.testing.cli_e2e import test_workflow_full_round_trip

and wire it into their own `tests/e2e-cli/` pytest collection (requirement 7).
See `cli_e2e` for the full module surface and the `LIVESPEC_E2E_HARNESS`
mock|real selector.
"""

__all__: list[str] = []
