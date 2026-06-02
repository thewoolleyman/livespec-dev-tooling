# livespec_dev_tooling/workflow_checks/

Revise-workflow checks, each invocable as
`python -m livespec_dev_tooling.workflow_checks.<slug>` and exiting
non-zero on a violation. Per `SPECIFICATION/contracts.md` §"Shared check
inventory" → "Revise-workflow checks", these are shared, project-agnostic
checks invoked by a specific workflow step (the `/livespec:revise`
pre-step) rather than by the per-commit `just check` aggregate. Living
here (NOT under `checks/`) keeps them out of the canonical-set derivation
(`canonical_checks` walks `checks/*.py`) and out of the
wiring-completeness invariant. Diagnostics flow through the vendored
`structlog` (JSON to stderr) — `print`/`sys.*.write` are banned here.
