"""Driver-plugin checks invocable via `python -m livespec_dev_tooling.driver_checks.<slug>`.

These are structural checks specific to a per-agent-runtime Driver plugin
bundle (`livespec-driver-claude`, `livespec-driver-codex`). Only the two
Driver repos wire them; they are NOT fleet-universal invariants. They live
here (NOT under `livespec_dev_tooling/checks/`) so the canonical-set
derivation (`canonical_checks` walks `checks/*.py`) auto-excludes them — a
driver-specific check must not be forced onto the aggregate-enforced
consumers (livespec core, the orchestrator plugins, livespec-runtime) via
`check-aggregate-completeness`. Each Driver repo's `just check` invokes the
relevant slug directly through a curated, literal check list.

`plugin_structure` is the first such check (relocated out of `checks/` in
livespec-2exa, after its move INTO `checks/` made it a canonical slug that
crashed/false-failed every aggregate-enforced consumer).
"""

__all__: list[str] = []
