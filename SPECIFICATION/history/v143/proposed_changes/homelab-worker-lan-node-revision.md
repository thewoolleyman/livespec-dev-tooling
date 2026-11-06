---
proposal: homelab-worker-lan-node.md
decision: modify
revised_at: 2026-11-06T02:27:41Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepts the proposal's three changes and modifies them: the worker's home-LAN address is a static address declared per host and outside the DHCP pool, because a VM bridged over Wi-Fi is seen by the router under its host's MAC (MAC NAT) and cannot be reserved (measured 2026-11-05 from poweredge: the M4 Max and its VM share one MAC); and two scenarios carry the new behaviour (bridged-network prerequisite refusal; the declared address as node IP), per the behaviour-needs-a-scenario split.

## Modifications

Change 2 (Home-LAN node) now requires a static home-LAN address declared in the host's declaration (the maintainer declares it outside the DHCP pool, which the task cannot observe), set by the task on the VM's bridged interface, and refuses a host declaring none. Added three scenarios: 'a missing bridged-network prerequisite stops the start task before the VM starts', 'the worker's node IP is its declared home-LAN address' and 'a host declaring no home-LAN address is refused before the VM starts'. Change 3 kept as the reviewed tailnet-policy sentence.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-06T02:26:50Z
verdict: NO BLOCKERS
proposal_stem: homelab-worker-lan-node
content_digest: 1e6aa9f7a62de450376efc79eed97672efde1dc350687b5f58c33e7f47a5519d
