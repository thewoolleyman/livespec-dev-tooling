---
topic: point-every-fleet-agents-md
author: distributed-send-message
created_at: 2026-11-14T04:48:49Z
---

## Proposal: Every fleet AGENTS.md points to the SendMessage protocol

### Target specification files

- non-functional-requirements.md

### Summary

Require this repository's AGENTS.md index to point to the protocol, and the protocol to be the link other fleet repositories use.

### Motivation

Plan distributed-sendmessage child livespec-dev-tooling-75add5. Agents that never read the protocol keep typing into panes. Pointers landed in the fleet's repositories on 2026-11-14.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Interactive fleet seat profile", append after the "Where the policy is converged." paragraph:

**The protocol is linked from agent guidance.** This repository's `AGENTS.md` progressive-guidance index MUST point to `.ai/distributed-sendmessage-protocol.md`. That file MUST be the canonical protocol the other fleet repositories' `AGENTS.md` link to, and a change to the rule MUST be made there.
