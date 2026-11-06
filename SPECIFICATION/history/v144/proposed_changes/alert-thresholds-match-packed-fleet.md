---
topic: alert-thresholds-match-packed-fleet
author: claude-opus-5-5
created_at: 2026-11-04T17:21:54Z
---

## Proposal: Retire the 15-minute node CPU-idle value trigger for a pool packed to capacity

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Remove 'a node whose CPU idle share stays at or below 10% for 15 minutes' from the triggers that §"Runner-pool node telemetry" requires. Per-node CPU stays on the board. Saturation becomes actionable only through the outcome triggers the pool already carries.

### Motivation

Plan address-honeycomb-alerts (epic bd-ib-xkwdap in livespec-orchestrator-beads-fabro) found that this trigger (`2K4wKhXN2SL`) sent more than 220 alert emails in the 7 days to 2026-11-04 and never pointed at an actionable condition. The pool is packed on purpose: the Dispatcher fills factory quota and ARC fills churn slots. Over the 72 h ending 2026-11-04 15:45Z, idle was at or below 10% in 28% (gmktec-xubuntu, hp-xubuntu) to 59% (poweredge-xubuntu) of 15-minute buckets. Stretches lasted up to 495 minutes, and the 12-hour rolling average idle reached 0.011 on poweredge-xubuntu. Any idle-share threshold short enough to be timely fires during normal operation. Over the same 7 days, the harm-shaped triggers that saturation would cause stayed quiet: factory pod Pending over 10 min, OOMKilled/CrashLoopBackOff, API-server readiness and the controllers. The datastore p99 trigger fired only on short spikes, and those are tracked as their own cause.

### Proposed Changes

In `non-functional-requirements.md` §"Runner-pool node telemetry", paragraph **Board and triggers.**, replace

"and value triggers for a node whose CPU idle share stays at or below 10% for 15 minutes, a node reporting MemoryPressure, and a node whose memory working set exceeds 90% of its capacity."

with

"and value triggers for a node reporting MemoryPressure and a node whose memory working set exceeds 90% of its capacity. The pool is packed to capacity by design, so a node's CPU idle share MUST be shown on the board and MUST NOT carry a value trigger. CPU saturation becomes actionable only through the outcome triggers of §\"Runner-pool workload and control-plane telemetry\": a pod Pending past its bound, an OOM-killed or crash-looping container, a failing readiness check, and datastore request latency."

The committed definition `ci-runner/observability/triggers/k8s-node-cpu-saturation.json` and its live Honeycomb trigger MUST be removed in the same change that lands this revision.

## Proposal: Widen the factory ResourceQuota trigger window from 15 minutes to 2 hours

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

A factory namespace's ResourceQuota fires only when it stays at or above 90 percent of hard for 2 hours, not 15 minutes. That keeps leak detection and stops alerts on the Dispatcher's normal full-quota operation.

### Motivation

Over the 72 h ending 2026-11-04 15:45Z, trigger `nBJML2UAgbm` sent more than 80 alert emails in 7 days. The factory's requests.cpu and limits.cpu ratios were at or above 0.9 in 20% of 15-minute buckets. That is the Dispatcher admitting to quota, as designed, and the factory Pending-pod trigger did not fire once. The longest stretch at or above 0.9 was 75 minutes (factory and factory-mi-homelab), and the longest at 1.0 was 75 minutes (factory-mi-homelab). A quota pinned for 2 hours is not normal: it means quota is held with no runs progressing, for example pods or cleanup pods leaking (cf. bd-ib-3i3j3k), or a wedged drain. That is the condition worth an alert, and a 2-hour window would have been quiet over this 72 h.

### Proposed Changes

In `non-functional-requirements.md` §"Runner-pool workload and control-plane telemetry", paragraph **Board and triggers.**, replace the bullet

"- a factory namespace's ResourceQuota usage of pods, CPU or memory stays at or above 90 percent of its hard value for 15 minutes;"

with

"- a factory namespace's ResourceQuota usage of pods, CPU or memory stays at or above 90 percent of its hard value for 2 hours. The window MUST stay longer than the longest full-quota stretch measured under normal admission, and the trigger's description MUST record that measurement, because the Dispatcher admits to quota by design and a shorter window fires on normal operation;"

The committed `ci-runner/observability/triggers/k8s-factory-quota-near-hard.json` MUST carry `query.time_range` 7200, with an evaluation frequency that Honeycomb accepts for that range, and the definitions test that asserts the specification windows MUST be updated in the same change.
