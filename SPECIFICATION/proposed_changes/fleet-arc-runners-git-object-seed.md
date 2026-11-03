---
topic: fleet-arc-runners-git-object-seed
author: claude-opus-5-5:ci-cache-optimization
created_at: 2026-11-03T23:32:02Z
---

## Proposal: Git object seed tier for the runner pool

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a git object seed as a tier of §"Runner-pool build cache tiers". It is a SEEDED, per-repository copy of each routed repository's default-branch object store. The job container names it as a git alternate object directory, so `actions/checkout` fetches from the forge only the objects the seed lacks. Workflows do not change. A missing or unreadable seed leaves the job on a normal full fetch.

### Motivation

Plan ci-cache-optimization measured `Checkout` + `Post Checkout` at about 53 normalized k3s job-hours a week (research 002). Of that time, 56% is `Fetching the repository`, and it sits in a tail: 13 of 74 sampled fetches took over 10 s and carry half the fetch time, worst on full-history jobs (research 004). A node benchmark (research 005) compared three shapes. A redirected local mirror is no faster than the forge under load (6.8-7.1 s against 6.5-7.7 s on poweredge for a full-history fetch), because it still builds a full pack per job. A forge fetch with the default-branch objects present as an alternate took 0.5-1.1 s on every node. The job's own git sees the alternate through `GIT_ALTERNATE_OBJECT_DIRECTORIES`, and fetch negotiation honours it: 0 KB transferred against 34,960 KB without it. That is the only mechanism that meets the section's zero-workflow-change rule, because `actions/checkout` deletes the work tree and runs `git init` before it fetches, so no `info/alternates` file can be placed. The estimated saving is about 19 normalized job-hours a week, second only to lever 1. The section names no git tier today, so the carrier cannot be implemented until this clause exists.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Runner-pool build cache tiers", append to the **Tiers.** paragraph, after the action-archive sentences:

"The pool MUST provide a git object seed: a SEEDED tree holding, for each routed repository, the git objects reachable from that repository's default branch and its tags, and no others. The populator, the one trusted writer under **Trust by construction**, MUST build it only from the forge's default branch and tags of each routed repository, never from a pull-request ref, and MUST publish it as a generation. A generation MUST NOT be pruned while any work volume seeded from it can still be bound to a pod. The volume provisioner seeds it into each runner work volume exactly as it seeds a SEEDED dependency tree, under the one byte budget and one file budget above and under the reflink rule of **Storage placement**, at a per-repository path. For a job on a node that holds the tree, the pool MUST set `GIT_ALTERNATE_OBJECT_DIRECTORIES` in the job container to the seeded object directory of the job's own repository, from the pool's runner container hook and never from a workflow step. The pool MUST set it only when that directory exists in the job's work volume. A routed job whose seed is present MUST fetch from the forge only the objects its seed lacks. Its checkout MUST produce the same work tree and the same refs as a fetch without the seed. Because the seed's objects are then referenced by the job's repository and not copied into it, the seed MUST stay readable at the same path for the job's whole life. A seed that is missing, stale or unreadable MUST leave the job's checkout to fetch from the forge as it would without the tier (**Fail-soft and kill switch**), and the fleet kill switch MUST disable this tier with the others. Because a git alternate must be a local path, the host-served preference above does not apply to this tier, and a `runner-only` node runs it cold."

In the **Trust by construction.** paragraph nothing changes. The seed is a private reflink copy in the job's own volume, the shared generation is reachable from no job pod, and the tier is namespaced per repository by path, with the hook naming only the job's own repository's directory, so the per-repository namespacing rule already covers it with no carve-out.

In §"Runner-pool cache telemetry" **Per-job spans.**, the existing per-tier span rule then covers the new tier unchanged: one span per tier recording hit or miss, generation identity and age.

In SPECIFICATION/scenarios.md, add after §"Scenario: a routed job sets up its actions from the pool's action-archive cache, and falls back to a download when an archive is missing":

"## Scenario: a routed job's checkout fetches only the objects its git object seed lacks, and falls back to a full fetch when the seed is missing

Given the pool's git object seed holds the default-branch and tag objects of every routed repository

When a routed job whose repository's seed is present in its work volume runs `actions/checkout` with `fetch-depth: 0`

Then the job container MUST name that repository's seeded object directory in `GIT_ALTERNATE_OBJECT_DIRECTORIES`, set by the pool's runner container hook

And the checkout MUST transfer from the forge only objects absent from the seed, and MUST produce the same work tree and refs as a checkout without the seed

And a job whose seed is missing or unreadable MUST fetch from the forge as it would without the tier and run to its own outcome

And a routed job on a `runner-only` node MUST fetch from the forge and run to its own outcome

And under the fleet kill switch every job MUST fetch from the forge as it would without the tier"
