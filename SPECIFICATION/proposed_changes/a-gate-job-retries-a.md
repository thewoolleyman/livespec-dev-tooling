---
topic: a-gate-job-retries-a
author: claude-opus-5-5 (gate-job-resources seat)
created_at: 2026-11-12T14:39:56Z
---

## Proposal: A gate Job retries a transiently refused forge read and fails a missing ref at once

### Target specification files

- contracts.md
- scenarios.md

### Summary

Add a **Forge reads.** bullet to contracts.md §"Delegated pre-push gate", directly after **Cross-repository siblings.**. It names the gate Job's two forge reads: the fetch of the pinned livespec core ref and each sibling clone. A transient refusal (401/403/429/5xx or transport) MUST be retried with a bounded number of attempts, a bounded total wait and growing waits. An anonymous 401 counts as transient even when an absent or private repository caused it. A ref reported not found in a readable repository, or a repository reported not found to a credentialed read, MUST fail at once, with a FATAL line naming it. Every attempt MUST be logged with its number and failure class. The retry MUST NOT add a credential. Two scenarios are added to scenarios.md. The bullet states no counts and says nothing about how the retry is packaged.

### Motivation

From about 13:20Z on 2026-11-12, github.com intermittently answered anonymous shallow fetches from the homelab NAT egress with HTTP 401. In a pod with no askPass, git reports this as `could not read Username`.
- 7 of 11 gates failed `fetch-livespec-core` through 13:33Z.
- From 14:14Z, pre-push gate pods failed fleet-wide: `Init:Error`, then `context deadline exceeded`.

The spec says nothing about how the gate Job treats a forge read that fails. The implementation (livespec-dev-tooling-yjcyay) therefore cannot be judged against a stated rule. Its filing judgement (14:35:44Z) classified it as spec-change/PARTIAL under this topic. The coordinator rules that silence is not a statement.

This proposal states the BEHAVIOUR only:
- what is retried, and that the retry is bounded;
- what is never retried;
- what is logged;
- that no credential is added (coordinator ruling: no new credential anywhere).

It does not state counts or how the retry is packaged. A credential helper, where a container already holds a token, belongs to topic self-hosted-ci-git-fetches. The in-cluster mirror for the tokenless reads belongs to livespec-dev-tooling-reuqym's topic. Both are compatible with this bullet: the mirror changes WHERE a read goes, and this bullet governs how a forge read is retried whenever one is made.

### Proposed Changes

### contracts.md §"Delegated pre-push gate"

Insert this bullet immediately after the **Cross-repository siblings.** bullet:

> - **Forge reads.** The gate Job reads from the forge in two ways: it fetches the livespec core ref that the consumer's `.livespec.jsonc` `compat.pinned` names, and it clones each cross-repository sibling. When the forge refuses one of these reads transiently, the Job MUST retry that read before letting it fail the gate. A transient refusal is an HTTP 401, 403, 429 or 5xx answer, or a transport failure. An HTTP 401 to an ANONYMOUS read counts as transient even when its cause is a repository that does not exist or is private: the forge gives an anonymous reader the same answer in every one of those cases. A 403 can be permanent, because the read lacks the rights, and it is still retried only within the same bound. The retry MUST be bounded both in its number of attempts and in its total wait, and the wait between attempts MUST grow. A read that still fails once the bound is spent MUST fail the gate exactly as the same read would without the retry. Two not-found reports MUST NOT be retried: a ref the forge reports not found in a repository the read can see, and a repository the forge reports not found to a read that presents a credential. In either case the Job MUST fail that read at once with a `FATAL` line naming the missing ref or repository. The Job MUST log every attempt with its attempt number and the class of its failure. The retry MUST NOT add a credential: an anonymous read stays anonymous on every attempt, and a private sibling's clone presents the same installation token on every attempt.

### scenarios.md

Add these two scenarios immediately after `## Scenario: an opted-in push whose consumer names a private cross-repository sibling clones it with a read-only installation token`:

> ## Scenario: a delegated gate Job retries a forge read the forge refuses transiently
>
> Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`
>
> And a forge that answers the gate Job's first fetch of the pinned livespec core ref with HTTP 401 and a later fetch with that ref
>
> When a git push of a tree that has no green token runs the pre-push gate
>
> Then the gate Job MUST fetch the livespec core ref again after a wait
>
> And the gate Job MUST run the consumer's recipe
>
> And the gate Job's log MUST name each fetch attempt with its attempt number and the class of its failure

> ## Scenario: a delegated gate Job fails a forge read of a missing ref at once
>
> Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`
>
> And whose `.livespec.jsonc` `compat.pinned` names a livespec core ref that does not exist in the livespec core repository, which the gate Job's anonymous read can see
>
> When a git push of a tree that has no green token runs the pre-push gate
>
> Then the gate Job MUST fetch that ref exactly once
>
> And the gate Job MUST report a `FATAL` line naming that ref
>
> And the gate Job MUST NOT run the consumer's recipe

### Co-edit owed at revise time

The revise commit adds one `tests/heading-coverage.json` row for each new scenario heading. Each row is either a real test or a `"test": "TODO"` row whose `reason` names the consumer tier and whose `work_item` is livespec-dev-tooling-yjcyay. The commit regenerates `tests/heading-coverage-debt.json` with `just generate-heading-coverage-debt-register`.
