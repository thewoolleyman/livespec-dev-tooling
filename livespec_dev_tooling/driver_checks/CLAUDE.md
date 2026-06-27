# livespec_dev_tooling/driver_checks/

Structural checks specific to a per-agent-runtime Driver plugin bundle
(`livespec-driver-claude`, `livespec-driver-codex`), each invocable as
`python -m livespec_dev_tooling.driver_checks.<slug>` and exiting non-zero
on a violation. Only the two Driver repos wire these (via a curated,
literal check list); they are NOT fleet-universal invariants. Living here
(NOT under `checks/`) keeps them out of the canonical-set derivation
(`canonical_checks` walks `checks/*.py`) and out of the
wiring-completeness invariant, so the aggregate-enforced consumers are
never forced to wire a driver-only check. Diagnostics flow through the
vendored `structlog` (JSON to stderr) — `print`/`sys.*.write` are banned
here.
