---
topic: roll-distributed-sendmessage-onto-vps
author: distributed-send-message
created_at: 2026-11-14T04:48:48Z
---

## Proposal: vps converges the SendMessage policy from ansible/claude-messaging.yml

### Target specification files

- non-functional-requirements.md

### Summary

State that vps is an interactive Claude host converged by ansible/claude-messaging.yml.

### Motivation

Plan distributed-sendmessage child livespec-dev-tooling-2bwvf4. The dev host carries the coordinator and dispatcher seats. The role was applied there on 2026-11-14 through the committed playbook.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Interactive fleet seat profile", append after the "Seats message by SendMessage, never by pane typing." paragraph:

**Where the policy is converged.** The playbook `ansible/claude-messaging.yml` MUST apply `claude_distributed_sendmessage` to every member of the inventory group `interactive_claude_hosts`, and the dev host `vps` MUST be a member of that group.
