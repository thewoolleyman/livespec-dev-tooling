---
topic: roll-distributed-sendmessage-onto-hetzner
author: distributed-send-message
created_at: 2026-11-14T04:48:49Z
---

## Proposal: hetzner-xubuntu converges the SendMessage policy from its own provisioning

### Target specification files

- non-functional-requirements.md

### Summary

State that hetzner-xubuntu takes the same role from hetzner-xubuntu-info's committed provisioning, not from this repository's inventory.

### Motivation

Plan distributed-sendmessage child livespec-dev-tooling-ajsrg3. hetzner-xubuntu is governed by hetzner-xubuntu-info, which consumes this repository's shared roles at an exact pin. It applied the role on 2026-11-14 (hetzner-xubuntu-info#128).

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Interactive fleet seat profile", at the end of the "Where the policy is converged." paragraph, add: "`hetzner-xubuntu` is an interactive host whose own repository, `hetzner-xubuntu-info`, MUST converge `claude_distributed_sendmessage` from its committed provisioning at its pin of this repository; it MUST NOT be added to this repository's inventory."
