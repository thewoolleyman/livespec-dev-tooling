---
topic: dev-host-tmp-refills-about
author: claude-opus-5-5
created_at: 2026-11-12T00:31:14Z
---

## Proposal: The dev host runs its session-scratch and pytest legs every 2 hours, not only daily

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add a paragraph to §"Dev host disk retention": the same role installs a second timer that runs a scratch-only pass every scratch interval (a role variable, default 2 hours). The pass applies the session-scratch and pytest removals by the daily run's own rules and runs no other step. The daily timer's hold also holds the new timer.

### Motivation

Measured on vmi3006760 by the dev-host-disk-retention plan (livespec-dev-tooling-qgwxo4). The implementation item is livespec-dev-tooling-7tfa3x, which waits on this proposal; the filing screen's spec-change tier linked it to this topic. legacy-coordinator-agent accepted the change on 2026-11-12.

- /tmp, a 48G tmpfs, went from 52% used at 2026-11-11 14:08Z to about 80% (9.5 GiB free) at 23:27Z: about 13 GiB in 9 h. On 2026-11-11 it also reached 86% at 13:27Z.
- The daily run at 23:27Z removed 69 dead session scratch directories and 5 aged pytest directories, reclaiming about 18 GiB. Those two legs took about 40 s.
- The whole daily run took 19m27s. Its uv ownership walk (a 300 s budget) and its bulk-dump size walk (13m43s over 1.67M files) are why. Neither belongs in a pass that runs every 2 hours, so the frequent pass must be the scratch and pytest legs only.
- The section already says the retention runs 'at least daily'. It does not say a second, more frequent pass exists, what it may do, or that holding the daily timer also holds it. A hold that stopped only one of two timers would leave the dev-host-disk-retention tripwire (which stops the night's firing when a live session lacks a liveness carrier) half-applied.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Dev host disk retention", insert this paragraph directly after the paragraph that begins **Provisioned, not hand-installed.**:

> **Scratch between daily runs.** Because agent sessions can refill `/tmp` within hours, the same role MUST also install a second systemd timer that runs a scratch-only pass at least once per scratch interval, a role variable documented in the role's `HOST_VARS.md` with a default of 2 hours. The scratch-only pass MUST apply the session scratch removal and the pytest removal stated below, by exactly the same rules, liveness check and scratch retention period as the daily run, and MUST log what it removed and the free space of `/tmp` before and after. It MUST NOT run any other step of the daily run. The role variable that holds the daily timer stopped and disabled MUST hold the scratch-only timer stopped and disabled too, and releasing it MUST release both.
