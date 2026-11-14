---
topic: ship-the-claude-distributed-sendmessage
author: distributed-send-message
created_at: 2026-11-14T04:48:48Z
---

## Proposal: Interactive seats message by SendMessage, enforced by managed policy

### Target specification files

- non-functional-requirements.md
- scenarios.md

### Summary

Add to §"Interactive fleet seat profile" the rule that interactive Claude seats message each other with SendMessage across machines and never type into a Claude seat's pane, and the managed-policy role that enforces it. Add one scenario.

### Motivation

The maintainer ruled on 2026-11-14 that typing into a seat's pane interrupts their own interaction with it. Seats moved to hetzner-xubuntu also lost their message channel to the vps (hetzner-xubuntu-info hxi-wx53tb). Plan distributed-sendmessage (epic livespec-dev-tooling-rlwppp) shipped role claude_distributed_sendmessage in livespec-dev-tooling#4595 and proved it live. This records the rule the code enforces.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Interactive fleet seat profile", append after the "Observable in llm-spend." paragraph:

**Seats message by SendMessage, never by pane typing.** An interactive Claude Code session MUST address another Claude Code session with the `SendMessage` tool, on the same host or another, and MUST NOT type text into a terminal pane that hosts a Claude agent. This repository MUST carry one Ansible role, `claude_distributed_sendmessage`, that installs the following as root-owned Claude Code MANAGED policy on each interactive host it is applied to:

- `remoteControlAtStartup: true`, so every interactive session joins Remote Control and is listed and messageable from the other hosts;
- `crossSessionInbound: accept`, so a permission-mode difference between sender and receiver does not hold a message behind an approval dialog;
- a PreToolUse Bash hook, the pane-input guard;
- the rule itself, in the managed `CLAUDE.md`.

The pane-input guard MUST refuse `herdr pane send-text`, `herdr pane run` and `herdr agent prompt` whose target pane hosts a Claude agent. It MUST refuse literal-text `tmux send-keys` and `tmux paste-buffer` into any pane. It MUST fail closed when it cannot determine the target's occupant. Every refusal MUST name `SendMessage` and `ListAgents`. The guard MUST admit:

- key-only `send-keys`;
- input into the caller's own pane;
- input into a pane that hosts no agent;
- input into a pane hosting a non-Claude agent, which cannot receive SendMessage.

The role MUST run the guard's regression corpus against the staged copy before it replaces an installed guard. The protocol agents follow is `.ai/distributed-sendmessage-protocol.md`.

In SPECIFICATION/scenarios.md, append:

## Scenario: a seat that types a message into a Claude seat's pane is refused and pointed at SendMessage

- Given an interactive host on which the `claude_distributed_sendmessage` role is applied
- And a Claude Code session started on that host after the apply
- When that session runs `herdr pane send-text <pane> <text>` against a pane that hosts a Claude agent
- Then the pane-input guard refuses the command and the text is not typed
- And the refusal names `SendMessage` and `ListAgents`
- And `herdr pane send-keys <pane> esc` against the same pane is not refused
- And `herdr pane send-text` against a pane hosting a Codex agent is not refused
