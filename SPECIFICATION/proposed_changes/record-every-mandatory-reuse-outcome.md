---
topic: record-every-mandatory-reuse-outcome
author: claude-opus-5-5 (ci-runtime-and-cost)
created_at: 2026-11-12T13:27:33Z
---

## Proposal: The reuse-outcome detector delivers each maintainer notification to the dev host's ntfy topic and logs the receipt

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Appends two sentences to the paragraph "Reuse outcomes are recorded and fallbacks reach the maintainer." in non-functional-requirements.md. They state the channel the detector's maintainer notifications go through (the dev host's ntfy topic, the host's claude_ntfy_topic inventory value, already the channel of the dev-host capacity alert), and that delivery is confirmed by the message id the ntfy server returns, which the detector logs. A publish the server does not accept is logged as undelivered and retried on the next run. Adds one scenario to scenarios.md.

### Motivation

v161 ratified this topic (decision modify, 2026-11-08) for work item livespec-dev-tooling-akljpy, the recording-and-detection line of the check-coverage fallback post-mortem (plan ci-runtime-and-cost, research 006). On 2026-11-12 at 13:21:52Z the dispatcher refused akljpy at spec-change tier on this topic (verdict partial, generalization target "## Hooks and CI", spec v204, hold reason awaiting-rejudgement). The judgement found the five-outcome record, the 30-minute notification, the missing-outcome notification, the p90 step-change notification and the stale-detector notification all stated. It found two things unstated: that a notification's delivery is confirmed by a receipt the detector logs (the "delivered" part of the item and its throwaway-PR bullet), and the notification channel. The plan's own Definition of Done requires a fallback to be raised to the maintainer "with no step relying on a person noticing", so a notification nobody can show was delivered does not meet it. The item left the channel to its owner (coordinator direction 2026-11-06), and the owner decided the dev host's ntfy topic. It is the existing desktop push route, it is already the channel the spec names for the dev-host capacity alert ("Alert before full."), and it is not one of the cron-driven PR or issue comments that .ai/fleet-and-secrets.md section "Maintainer Signaling" rules out. ntfy answers each accepted publish with a message id, which is the receipt.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, append the following two sentences to the end of the paragraph that begins "**Reuse outcomes are recorded and fallbacks reach the maintainer.**":

The detector MUST publish every maintainer notification it raises to the dev host's ntfy topic, the host's `claude_ntfy_topic` inventory value, and MUST log, for each one, the message id the ntfy server returned for it as the notification's delivery receipt. A publish the ntfy server does not accept MUST be logged as undelivered and MUST be retried on the detector's next run until a receipt is logged.

In SPECIFICATION/scenarios.md, append the following scenario after "## Scenario: a stale detector reaches the maintainer":

## Scenario: a reuse detector notification is delivered to the dev host's ntfy topic with a logged receipt

Given a fleet CI run whose mandatory coverage consumer job recorded the outcome `missing_receipt`

When the scheduled detector raises the maintainer notification for that run

Then it MUST publish the notification to the dev host's ntfy topic

And it MUST log the message id the ntfy server returned for that notification
