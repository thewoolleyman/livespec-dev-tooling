# livespec_dev_tooling/agent_hooks/

Claude Code hook entry points (work-item livespec-dev-tooling-7us.2),
wired from a consuming repo's committed `.claude/settings.json` —
NOT part of the per-commit `just check` aggregate (the canonical-set
derivation walks `checks/*.py` only, so this directory is
auto-excluded, like `workflow_checks/`).

Local constraints:

- Every module is a hook PROTOCOL participant: hook-input JSON on
  stdin, and a verdict back out. **The channel is per EVENT, and the
  wrong one is silently invalid rather than merely unidiomatic.**
  `PreToolUse` (`pretooluse_background_guard`) still speaks the
  exit-code protocol: exit `0` = allow, exit `2` = deny with stderr
  fed back to the agent, any other exit non-blocking.
  `Stop` / `SubagentStop` (`subagent_stop_guard`) does NOT: its
  evaluator PARSES stdout as a response object, so the verdict travels
  as JSON on stdout (`{"continue": true, ...}` to allow;
  `decision`/`reason` plus `hookSpecificOutput.additionalContext` to
  block) and the exit code is uniformly `0`. Emitting the exit-code
  form there produces `hook returned invalid stop hook JSON output` on
  EVERY invocation, allow and block alike, which is exactly the defect
  `livespec-dev-tooling-4s2sey` fixed — a guard rejected as malformed
  guards nothing.
- **Fail-open is load-bearing.** A broken hook must never wedge a
  healthy agent: every error path (unparseable stdin, missing
  transcript, failed `git`/`gh` probe, internal crash) resolves to the
  ALLOW verdict in that hook's own protocol — exit `0` for the
  exit-code form, the allow RESPONSE OBJECT for the stdout-JSON form.
  A bare exit `0` is NOT fail-open on a Stop-family hook: the empty
  stdout is itself invalid. Blocking paths must be cheap (sub-second
  except the single `gh` call, which carries its own timeout) and must
  hand the agent an actionable reason.
- Diagnostics flow through the vendored `structlog` (JSON to stderr).
  No `print`, no `sys.stderr.write`. On the exit-code hooks the
  blocking `reason` the agent reads IS that structured event; on the
  stdout-JSON hooks the agent-facing text rides the response instead,
  and stderr is an operator record only. A hook listed in
  `supervisor_entry_files` may write its response with a direct
  `sys.stdout.write` — that stdout is a protocol channel, and it must
  carry the response object and NOTHING else.
- Derived markers over sentinel files: derive in-flight state from
  git/gh evidence (uncommitted tracked changes, unpushed commits,
  unarmed PR), never from agent-maintained marker files.
