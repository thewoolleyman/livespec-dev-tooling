---
topic: runner-supervisor-rate-limit-control
author: gpt-5.6
created_at: 2026-08-14T00:43:50Z
---

## Proposal: Rate-aware JIT runner supervisor control

### Target specification files

- non-functional-requirements.md
- scenarios.md

### Summary

Make the fleet JIT runner supervisor pace installation-token/JIT-config requests and recover from GitHub throttling without retry storms, while preserving an auditable record of pressure and recovery.

### Motivation

Restarting the supervisor after the fleet capacity increase fanned out hundreds of GitHub App installation-token and JIT-config requests concurrently. GitHub applied secondary and installation API limits, and repeated restart retries repeated the burst instead of allowing the shared installation to recover.

### Proposed Changes

Add a `## JIT runner supervisor GitHub request discipline` non-functional requirement. A supervisor that mints JIT runners MUST maintain one durable, supervisor-wide request-control state spanning restarts and MUST admit token/JIT-config mint attempts through a bounded-concurrency, paced queue; startup, reconciliation, and recovery MUST use that same queue and MUST NOT fan out one request per desired slot. The configuration MUST make the concurrency limit and minimum inter-request spacing explicit and validate them as positive bounded values.

The controller MUST classify successful responses, primary exhaustion, secondary throttling (including HTTP 429 or GitHub's secondary-limit response), explicit `Retry-After`, reset-time guidance, transport failures, authentication/authorization failures, and malformed rate-limit guidance. On a rate-limit or throttle response it MUST open a shared cooldown/circuit-breaker for new mint work, honor a valid `Retry-After` or reset time as the lower bound, and schedule retryable work with capped exponential backoff plus independently sampled jitter. A single affected request MUST NOT cause every queued worker to retry at the same instant. It MUST NOT retry credential/permission failures as throttles, and it MUST stop after a configured finite retry budget with an actionable terminal failure rather than looping or repeatedly restarting the supervisor.

The supervisor MUST persist an append-only or equivalently queryable operational record containing request admission time, queue depth, in-flight count, response classification, attempt number, chosen delay and its reason, shared cooldown boundaries, terminal failures, and recovery/resumption events. It MUST preserve already-registered healthy runners during cooldown, leave queued demand pending, and resume paced admission only when the shared cooldown expires and a probe or next permitted request indicates recovery. Add integration-tier scenarios covering startup demand that exceeds the pace, a secondary-limit response that pauses all mint admission and resumes without a storm, and retry-budget exhaustion that records a terminal actionable failure.
