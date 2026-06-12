# livespec_dev_tooling/agent_hooks/

Claude Code hook entry points (work-item livespec-dev-tooling-7us.2),
wired from a consuming repo's committed `.claude/settings.json` —
NOT part of the per-commit `just check` aggregate (the canonical-set
derivation walks `checks/*.py` only, so this directory is
auto-excluded, like `workflow_checks/`).

Local constraints:

- Every module is a hook PROTOCOL participant: hook-input JSON on
  stdin; exit `0` = allow, exit `2` = block (stderr is fed back to
  the agent). Any other exit is non-blocking by the Claude Code hook
  contract.
- **Fail-open is load-bearing.** A broken hook must never wedge a
  healthy agent: every error path (unparseable stdin, missing
  transcript, failed `git`/`gh` probe, internal crash) returns `0`.
  Blocking paths must be cheap (sub-second except the single `gh`
  call, which carries its own timeout) and must emit an actionable
  structured reason on stderr.
- Diagnostics flow through the vendored `structlog` (JSON to stderr);
  the blocking `reason` the agent reads IS the structured event. No
  `print`, no `sys.stderr.write`.
- Derived markers over sentinel files: derive in-flight state from
  git/gh evidence (uncommitted tracked changes, unpushed commits,
  unarmed PR), never from agent-maintained marker files.
