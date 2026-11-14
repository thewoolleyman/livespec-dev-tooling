---
topic: sendmessage-is-guidance-not-a-block
author: distributed-send-message
created_at: 2026-11-14T20:05:22Z
---

## Proposal: SendMessage is guidance, never a block on pane typing

### Target specification files

- non-functional-requirements.md
- scenarios.md

### Summary

Turn the v218 rule that seats MUST NOT type into a Claude pane, enforced by a managed pane-input guard, into guidance: seats SHOULD prefer SendMessage, and nothing this repository installs may refuse pane input.

### Motivation

Maintainer ruling 2026-11-14: "DO NOT PREVENT SESSIONS FROM TYPING INTO PANES. IT IS NECESSARY SOMETIMES. JUST GIVE EXPLICIT AND ABUNDANT GUIDANCE TO USE SENDMESSAGE." The guard blocked necessary input, such as typing /remote-control into a seat whose Remote Control had dropped. livespec-dev-tooling#4707 stops the role wiring the guard and removes it from hosts.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Interactive fleet seat profile":

1. In the **Scope.** paragraph, replace the quoted clause name "Seats message by SendMessage, never by pane typing." with "Seats prefer SendMessage; pane typing stays allowed." and "The messaging rule" with "The messaging guidance".

2. Replace the whole "**Seats message by SendMessage, never by pane typing.**" clause, including its bullet list and the two following pane-input-guard paragraphs (the refusal list, fail-closed, the tmux retired-transport rule, the admit list, the guard's fail-open on internal error and the regression-corpus requirement), with:

**Seats prefer SendMessage; pane typing stays allowed.** An interactive Claude Code session SHOULD address another Claude Code session with the `SendMessage` tool, on the same host or another, because text typed into a terminal pane lands in the input line the maintainer may be typing into. Typing into another session's pane MUST remain available: no hook or policy this repository installs may refuse it, because it is sometimes necessary, for example to run a slash command, answer a picker, reach a session `SendMessage` cannot reach, or reach a non-Claude seat. This repository MUST carry one Ansible role, `claude_distributed_sendmessage`, that installs the following as root-owned Claude Code MANAGED policy on each interactive host it is applied to:

- `remoteControlAtStartup: true`, so every interactive session signed in to claude.ai joins Remote Control and is listed and messageable from the other hosts;
- `crossSessionInbound: accept`, so a permission-mode difference between sender and receiver does not hold a message behind an approval dialog;
- the guidance itself, in the managed `CLAUDE.md`: prefer `SendMessage`, and type into a pane only when that is necessary.

The role MUST NOT install a PreToolUse hook, or any other policy, that refuses input into a pane. It MUST remove the retired pane-input guard, `/usr/local/lib/claude-code/pane-input-guard.py`, from a host that carries it. The protocol agents follow is `.ai/distributed-sendmessage-protocol.md`.

Leave "**Where the policy is converged.**" and "**The protocol is linked from agent guidance.**" unchanged.

In SPECIFICATION/scenarios.md, replace the scenario "## Scenario: a seat that types a message into a Claude seat's pane is refused and pointed at SendMessage" with:

## Scenario: a seat may type into a Claude seat's pane and is guided to prefer SendMessage

Given an interactive host on which the `claude_distributed_sendmessage` role is applied

And a Claude Code session started on that host after the apply

When that session runs `herdr pane send-text <pane> <text>` against a pane that hosts a Claude agent

Then no hook installed by the role refuses the command

And the managed `CLAUDE.md` that session loaded tells it to prefer `SendMessage` and to type into a pane only when that is necessary
