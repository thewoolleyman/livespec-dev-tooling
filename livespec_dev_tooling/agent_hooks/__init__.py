"""Agent-runtime hook scripts invocable via `python -m livespec_dev_tooling.agent_hooks.<slug>`.

Per work-item livespec-dev-tooling-7us.2 (mechanical prevention of
premature sub-agent turn-ends), these are Claude Code hook entry
points wired from a consuming repo's committed `.claude/settings.json`
hooks table — NOT members of the per-commit `just check` aggregate.
They live here (NOT under `livespec_dev_tooling/checks/`) so the
canonical-set derivation (`canonical_checks` walks `checks/*.py`)
auto-excludes them and they are NOT subject to the
wiring-completeness invariant, exactly like `workflow_checks/`.

- `subagent_stop_guard` — `SubagentStop` hook: blocks a sub-agent's
  turn-end (exit 2, reason on stderr) while derived in-flight markers
  exist in a worktree that sub-agent created (uncommitted tracked
  changes, unpushed commits, or a pushed branch whose PR is missing
  or not auto-merge-armed). Fail-open everywhere.
- `pretooluse_background_guard` — `PreToolUse` hook (matcher `Bash`):
  denies Bash calls that combine `run_in_background` with a gate
  command (`just check*`, `git commit`, `git push`, `gh pr`). Gates
  must run FOREGROUND with a raised timeout; a sub-agent that
  backgrounds a gate and ends its turn is terminated mid-dispatch.
"""

__all__: list[str] = []
