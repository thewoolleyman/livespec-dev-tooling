# livespec_dev_tooling/workflow_checks/

Workflow checks, each invocable as
`python -m livespec_dev_tooling.workflow_checks.<slug>` and exiting
non-zero on a violation. Per `SPECIFICATION/contracts.md` §"Shared check
inventory" → "Workflow checks", these are shared, project-agnostic checks
invoked by a specific workflow step rather than by the per-commit
`just check` aggregate. Two kinds are defined:

- **Revise-workflow checks**, invoked by the `/livespec:revise` pre-step.
  `no_stale_revise_branches` is the member; that pre-step is mandatory
  and load-bearing.
- **Release-workflow checks**, invoked by a consumer's release-gating
  step — a `pre-push` script, a release job, or any step running before
  a version number becomes final. `release_bump_classification` is the
  member; it has NO mandated caller, since adoption is per-consumer
  opt-in.

Living here (NOT under `checks/`) keeps them out of the canonical-set
derivation (`canonical_checks` walks `checks/*.py`) and out of the
wiring-completeness invariant. That placement is load-bearing, not a
filing preference: a module under `checks/` becomes a canonical slug, and
a canonical slug obliges EVERY consumer to wire it into `just check` AND
its CI matrix.

The `python -m livespec_dev_tooling.workflow_checks.<slug>` invocation set
IS an enumerated element of §"Semver discipline"'s semver-stable surface —
that enumeration is what sanctions consumer invocation — but enumeration
does not make these checks canonical.

Diagnostics flow through the vendored `structlog` (JSON to stderr) —
`print`/`sys.*.write` are banned here.
