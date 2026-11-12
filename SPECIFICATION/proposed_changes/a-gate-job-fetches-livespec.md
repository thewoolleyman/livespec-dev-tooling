---
topic: a-gate-job-fetches-livespec
author: claude-opus-5-5 (gate-job-resources seat)
created_at: 2026-11-12T14:50:03Z
---

## Proposal: A gate Job reads livespec core and its public siblings from the in-cluster gate mirror

### Target specification files

- contracts.md
- scenarios.md

### Summary

In contracts.md §"Delegated pre-push gate", add a **Gate mirror reads.** bullet after **Cross-repository siblings.**:
- the gate Job fetches the pinned livespec core ref, and clones each PUBLIC cross-repository sibling, from the in-cluster gate mirror that already serves the tree under test;
- it falls back to the forge only when the mirror does not carry that ref or repository, or the mirror read fails;
- the mirror's converge keeps livespec core and the public siblings fetched into the mirror;
- the Job logs which source served each read.

The proposal also amends the anonymous-public-clone sentence of **Cross-repository siblings.** to match. A private sibling keeps its installation-token clone from the forge. Two scenarios are added.

### Motivation

Every gate Job makes up to four anonymous github.com calls: the core fetch, plus one per public sibling clone. All of them leave through the homelab's one NAT egress, across 12 gate slots.
- From about 13:20Z on 2026-11-12, GitHub answered a share of those anonymous fetches with 401. 7 of 11 gates failed fetch-livespec-core through 13:33Z, and pre-push gate pods failed fleet-wide from 14:14Z.
- GitHub's own notices of 2026-11-08 and 2026-11-09 describe new traffic controls on anonymous users and state that authenticated requests were unaffected. legacy-coordinator-agent infers the throttle may PERSIST, so a retry (topic a-gate-job-retries-a) is the stopgap, and removing the anonymous calls is the fix (coordinator ruling, livespec-dev-tooling-reuqym).

The mirror already exists and already sits on every gate Job's path: the tree under test is fetched from it. Serving core and the public siblings from it removes the anonymous forge calls from the common case. The forge stays as a fallback under **Forge reads.** (topic a-gate-job-retries-a), for a ref the mirror lacks or a mirror read that fails, so a stale or partial mirror degrades to today's behaviour instead of failing a gate.

PRIVATE siblings are deliberately OUT:
- their clone is already authenticated, which GitHub states the throttle does not affect;
- the gate mirror's daemon is unauthenticated and reachable cluster-wide, so serving private contents from it would widen who can read them.

FRESHNESS IS RELAXED, and stated rather than hidden. A sibling served from the mirror is at its default-branch head as the mirror last fetched it, not as the forge holds it at that instant. A pinned core ref is a tag or a branch, and a tag does not move.

### Proposed Changes

### contracts.md §"Delegated pre-push gate" — **Cross-repository siblings.**

Replace the sentence

> A public sibling is cloned anonymously.

with

> A public sibling is cloned as **Gate mirror reads.** below states.

### contracts.md §"Delegated pre-push gate" — new bullet

Insert immediately after the **Cross-repository siblings.** bullet:

> - **Gate mirror reads.** The gate Job MUST fetch the livespec core ref that the consumer's `.livespec.jsonc` `compat.pinned` names from the in-cluster gate mirror, the same mirror it fetches the tree under test from. It MUST clone each public cross-repository sibling from that mirror too. The Job MUST read either from the forge only when the mirror does not carry that ref or repository, or when the read from the mirror fails. A forge read made this way is governed by **Forge reads.**. A private sibling MUST NOT be served from the gate mirror: it is cloned from the forge with its installation token, as **Cross-repository siblings.** states. The gate mirror's converge MUST keep livespec core and every public repository that a delegating consumer's `cross_repo_targets` names fetched into the mirror, refreshing them on a schedule the converge declares. A sibling cloned from the mirror is at its default branch's head as of the mirror's last refresh. The Job MUST log, for each of these reads, whether the mirror or the forge served it.

### scenarios.md

Add these two scenarios immediately after `## Scenario: an opted-in push whose consumer names a private cross-repository sibling clones it with a read-only installation token`:

> ## Scenario: a delegated gate Job fetches its pinned livespec core ref from the gate mirror
>
> Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`
>
> And a gate mirror that carries the livespec core ref the consumer's `.livespec.jsonc` `compat.pinned` names
>
> When a git push of a tree that has no green token runs the pre-push gate
>
> Then the gate Job MUST fetch that ref from the gate mirror
>
> And the gate Job MUST make no read of that ref from the forge
>
> And the gate Job's log MUST name the gate mirror as the source of that ref

> ## Scenario: a delegated gate Job reads a pinned livespec core ref the gate mirror lacks from the forge
>
> Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`
>
> And a gate mirror that does not carry the livespec core ref the consumer's `.livespec.jsonc` `compat.pinned` names
>
> When a git push of a tree that has no green token runs the pre-push gate
>
> Then the gate Job MUST fetch that ref from the forge
>
> And the gate Job's log MUST name the forge as the source of that ref

### Co-edit owed at revise time

The revise commit adds one `tests/heading-coverage.json` row for each new scenario heading. Each row is either a real test or a `"test": "TODO"` row whose `reason` names the consumer tier and whose `work_item` is livespec-dev-tooling-reuqym. The commit regenerates `tests/heading-coverage-debt.json` with `just generate-heading-coverage-debt-register`.

### Ordering

This bullet cites **Forge reads.**, which topic a-gate-job-retries-a adds. Its --only-topic revise cut MUST follow that topic's ratification in the same stop-the-line slot.
