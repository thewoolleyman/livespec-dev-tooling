---
topic: roll-distributed-sendmessage-onto-gamingpc
author: distributed-send-message
created_at: 2026-11-14T04:48:48Z
---

## Proposal: gamingpc-xubuntu converges the SendMessage policy from ansible/claude-messaging.yml

### Target specification files

- non-functional-requirements.md

### Summary

Add gamingpc-xubuntu to interactive_claude_hosts.

### Motivation

Plan distributed-sendmessage child livespec-dev-tooling-nd4kmw. The maintainer runs interactive Claude sessions on gamingpc-xubuntu. The role was applied there on 2026-11-14.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Interactive fleet seat profile", in the "Where the policy is converged." paragraph, after the sentence naming `vps`, add: "`gamingpc-xubuntu` MUST also be a member of `interactive_claude_hosts`."
