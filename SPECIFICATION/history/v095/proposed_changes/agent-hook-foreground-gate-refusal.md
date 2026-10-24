---
topic: agent-hook-foreground-gate-refusal
author: claude-opus-5-5
created_at: 2026-10-24T19:10:43Z
---

## Proposal: Agent-session gate-command guard: refuse a foreground hook-running git commit or push and name the detached form

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a new section, `## Agent-session gate-command guard`, to `SPECIFICATION/contracts.md`, immediately before `## Composite Actions wire contract`, plus three scenarios in `SPECIFICATION/scenarios.md`. The section makes the PreToolUse guard this repository ships (`livespec_dev_tooling.agent_hooks.pretooluse_background_guard`) refuse a FOREGROUND `git commit` or `git push` whose repository hooks run gates when an agent session issues it. The refusal names the one-call detached form through the detached gate runner. The section keeps the guard's existing refusal of a bare-backgrounded gate command, names the exemptions, and fixes the fail-open direction of a guard crash. It is the ratified rule work-item `livespec-dev-tooling-zlhnib` implements.

### Motivation

Measured on the shared VPS on 2026-10-24: a seat's canary commit sat more than 21 minutes in the commit-msg `check-red-green-replay` hook. The harness moved the foreground call to the background at its 20-minute ceiling, where such calls have been killed with no verdict. A kill leaves no exit code, which reads like a hook refusal (`.ai/gate-runtime-vs-harness-patience.md`). The detached gate runner (`just gate-start` / `just gate-wait`) already removes that failure. The PreToolUse guard already refuses a BARE-BACKGROUNDED gate command and names the runner. It does nothing about the FOREGROUND call, which is the case that loses verdicts. Coordinator gitops-fleet-capacity-monitoring commissioned a read-only investigation. On 2026-10-24 ~19:1xZ, under the maintainer's standing mandate to move gate load and verdict risk off the host, it decided the mechanism: option (a), the guard refuses and names the detached form. It recorded on zlhnib why the alternatives fail. An `updatedInput` rewrite is invisible to the agent, has to quote arbitrary heredoc commit messages through `bash -c`, changes the cwd semantics of just recipes, and is still judged in its original form by sibling guards. A git hook cannot detach itself, because git waits on the hook's exit status, so the commit would land unjudged. A PATH `git` wrapper shadows git for every caller, which is the same hazard as the `bd` shadowing rule. A timeout only moves the silent kill earlier. No H2 of this specification governs agent hooks or detaching today. §"Hooks and CI" covers the lefthook ordering only, so zlhnib's Definition of Done cannot reference a governing clause until this lands. This proposal ALIGNS with the pending in-tree proposal `detached-gate-runner`, which specifies the runner this guard points agents at. The guard's refusal names that runner's `gate-start` / `gate-wait` recipes and adds no requirement on the runner.

### Proposed Changes

Insert the following section into `SPECIFICATION/contracts.md` immediately before the line `## Composite Actions wire contract`:

> ## Agent-session gate-command guard
>
> This repository ships a Claude Code `PreToolUse` hook, `python -m livespec_dev_tooling.agent_hooks.pretooluse_background_guard`, which a consuming repository registers for the `Bash` tool. It exists because a gate command run from an agent session can outlast the harness's tool-call ceiling. When the harness kills such a call, it leaves no exit code, no output and no verdict, and that is indistinguishable from a refusal. The guard keeps every gate command that an agent session issues on the detached gate runner, where a run that does not finish reports `DIED_WITHOUT_VERDICT` and can never read as a pass. The guard decides where a gate command runs. It MUST NOT change which gates run or what they verify.
>
> - **Foreground hook-running git commands.** The guard MUST refuse a `Bash` tool call that runs `git commit` or `git push` in the foreground when the repository that command targets has the corresponding git hook installed: `pre-commit` or `commit-msg` for a commit, `pre-push` for a push. A command prefixed by `mise exec --`, or carrying `git -C <path>`, targets the repository it names. The refusal MUST carry its own `check_id`, distinct from the background-gate refusal below. It MUST name the one-call detached form that replaces the command: `run_id=$(mise exec -- just gate-start -- <the same command>) && mise exec -- just gate-wait "$run_id"`.
> - **Background gate commands.** The guard MUST continue to refuse a gate command — `just check*`, `git commit`, `git push`, `gh pr ...` — that the tool call backgrounds bare (the tool's background mode, or a trailing `&`), and MUST continue to name the same detached form.
> - **What is not refused.** The guard MUST NOT refuse: a command already dispatched through `gate-start`; a `gate-wait`, `gate-status` or `gate-list` call; `git push --dry-run` or `git push -n`; a `git commit` or `git push` carrying `-h` or `--help`; a push whose only refspecs delete remote branches; or a commit or push whose target repository has no installed hook of the corresponding kind. When the guard cannot establish whether the target repository's hook is installed, it MUST refuse.
> - **Fail-open on a guard fault.** When the guard itself fails with an internal error, the tool call MUST proceed as it would without the guard, which is the foreground behaviour that existed before this guard. The guard MUST report the fault on its own stderr. A guard fault MUST NOT be reported as a verdict of the gate the command runs.
> - **Scope.** The guard governs agent sessions of the harness that runs Claude Code `PreToolUse` hooks. It cannot tell a maintainer's `Bash` call inside such a session from the agent's, so it refuses both. Commands run outside an agent session — a terminal, CI, a Fabro sandbox's own hooks — are not governed. Codex sessions are not covered by this hook.

Append the following scenarios to `SPECIFICATION/scenarios.md`:

> ## Scenario: an agent session's foreground commit in a hooked repository is refused and names the detached form
>
> Given a repository whose `.git/hooks/pre-commit` is installed
>
> And an agent session whose `PreToolUse` hooks include the gate-command guard
>
> When the session issues a `Bash` tool call running `mise exec -- git commit -m "<message>"` in the foreground
>
> Then the guard MUST refuse the tool call with its foreground-gate `check_id`
>
> And the refusal MUST name `run_id=$(mise exec -- just gate-start -- mise exec -- git commit -m "<message>") && mise exec -- just gate-wait "$run_id"`
>
> ## Scenario: an agent session's commit dispatched through the detached gate runner is not refused
>
> Given a repository whose `.git/hooks/pre-commit` is installed
>
> And an agent session whose `PreToolUse` hooks include the gate-command guard
>
> When the session issues a `Bash` tool call running `mise exec -- just gate-start -- mise exec -- git commit -m "<message>"`
>
> Then the guard MUST NOT refuse the tool call
>
> ## Scenario: an agent session's dry-run push is not refused
>
> Given a repository whose `.git/hooks/pre-push` is installed
>
> And an agent session whose `PreToolUse` hooks include the gate-command guard
>
> When the session issues a `Bash` tool call running `git push --dry-run origin HEAD` in the foreground
>
> Then the guard MUST NOT refuse the tool call

Co-edit `tests/heading-coverage.json` in the revise pass: add one entry for the new `contracts.md` heading `## Agent-session gate-command guard` and one per new `scenarios.md` heading. The Background gate commands bullet is already proven by `tests/livespec_dev_tooling/agent_hooks/test_pretooluse_background_guard.py`. The section heading and the three scenarios are spec-first: their rows MUST be `TODO` entries whose `reason` names work-item `livespec-dev-tooling-zlhnib` as the implementing item, and the debt register is regenerated, never hand-edited.
