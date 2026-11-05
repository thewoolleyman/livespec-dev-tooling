---
topic: agent-session-guard-refuses-foreground-full-suite-pytest
author: claude-opus-5-5
created_at: 2026-11-05T00:07:07Z
---

## Proposal: Agent-session guard refuses a foreground full-suite pytest on a delegating host

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a bullet to contracts.md §"Agent-session gate-command guard". When the session's host can delegate gates, the guard refuses an agent session's foreground full-suite pytest and names the gate-start form, so a seat cannot bypass §"Delegated gate-runner runs" by running the suite directly. Targeted pytest runs, runs already under gate-start, runs in a repository that does not delegate, and runs on a host that cannot delegate (such as a factory sandbox) are not refused. Two scenarios state the behaviour.

### Motivation

Plan dev-host-test-gate-load (epic livespec-dev-tooling-6vuiwe) measured it in A6 window 3 (research note 008). From 22:25Z to 22:45Z on 2026-11-04, pytest-xdist workers started directly in a livespec-dev-tooling worktree ran at 4.2 to 6.6 cores on the dev host. Window 2 (note 007) showed the same shape at 2.6 to 3.0 cores. §"Delegated gate-runner runs" routes a full suite to a gate Job only when it starts through gate-start. The guard refuses only foreground hook-running git commands and bare-backgrounded gate commands. So a foreground pytest bypasses both, and that keeps the plan's assertion 6 (routine test and gate load under one core on the dev host) unmet. legacy-coordinator-agent ruled on 2026-11-05 that a carrier is filed for it (livespec-dev-tooling-4pchid). This proposal is the clause that carrier implements.

### Proposed Changes

In SPECIFICATION/contracts.md §"Agent-session gate-command guard", insert after the **Background gate commands.** bullet:

- **Foreground full-suite pytest.** The guard MUST refuse a `Bash` tool call that runs a full-suite pytest in the foreground when two things hold. First, the repository the command targets has `delegated_gate = true`. Second, the session's user can read the gates kubeconfig on that host, the same host eligibility §"Delegated pre-push gate" decides. A pytest invocation is `pytest`, `python -m pytest` or `uv run pytest`, with or without a `mise exec --` prefix. It is full-suite when it names no test file, directory or node id, or when it passes `-n` or `--numprocesses`. The repository it targets is decided as for a git command: a `cd <path> &&` or `-C <path>` prefix names that path, and any other command targets the session's working directory. The refusal MUST carry its own `check_id`, distinct from the other refusals of this guard. It MUST name the one-call detached form `just gate-start -- <command>`, which runs that command as a gate Job under §"Delegated gate-runner runs". The guard MUST NOT refuse a pytest that names explicit test files, directories or node ids and does not pass `-n` or `--numprocesses`. It MUST NOT refuse a pytest in a repository without `delegated_gate = true`, or on a host whose user cannot read the gates kubeconfig, such as a factory sandbox.

In the **What is not refused.** bullet of the same section, add the targeted pytest, the undelegated repository and the ineligible host above to the list of commands the guard MUST NOT refuse.

In SPECIFICATION/scenarios.md, add after §"Scenario: an agent session's commit in a repository with no installed commit hook is not refused":

## Scenario: an agent session's foreground full-suite pytest on a delegating host is refused and names the gate-start form

Given a repository with `delegated_gate = true`
And an agent session whose user can read the gates kubeconfig
When the session runs `uv run pytest -n 8` in the foreground in that repository
Then the guard MUST refuse the tool call with its full-suite pytest `check_id`
And the refusal MUST name `just gate-start -- uv run pytest -n 8`

## Scenario: an agent session's targeted pytest or a factory sandbox's full suite is not refused

Given a repository with `delegated_gate = true`
When an agent session on a host whose user can read the gates kubeconfig runs `uv run pytest tests/test_one.py` in the foreground
Then the guard MUST NOT refuse the tool call
And when an agent session on a host whose user cannot read the gates kubeconfig runs `uv run pytest -n 8` in the foreground
Then the guard MUST NOT refuse that tool call either

The revise that accepts this proposal MUST add the two new `## Scenario:` headings to tests/heading-coverage.json in the same commit.
