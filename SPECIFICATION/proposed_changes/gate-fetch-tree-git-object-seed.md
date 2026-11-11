---
topic: gate-fetch-tree-git-object-seed
author: claude-opus-5-5
created_at: 2026-11-11T01:31:06Z
---

## Proposal: The git object seed covers every gated repository, and a runner-only node may seed its delegated gate Jobs' volumes

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Widen the git object seed from routed repositories to routed and gated repositories, and keep runner work volumes on routed seeds only. Let a delegated gate Job's volume receive a private copy of its own repository's seed, under the same budgets, reflink rule and pruning guard. On a runner-only node, place that gate-volume tree on the filesystem the gate volumes are provisioned under, and amend the four sentences that currently forbid it: Scope, Tiers' runner-only cold clause, Storage placement, and What a runner-only node's jobs get. Widen Trust by construction to gated repositories and gate Jobs.

### Motivation

Gate Jobs fetch cold. Production pod events at 2026-11-10 ~23:10Z put fetch-tree at 88 s on the M4 worker node, 19 s on hp-xubuntu, 4 s on gmktec-xubuntu and 3 s on poweredge-xubuntu. The pool already publishes a git object seed, but only for routed repositories and only into runner work volumes, and several sentences forbid any seeded tree on a runner-only node, where gate fetch-tree is slowest. hp-xubuntu's gate volumes are already seeded with a UV-only generation published beside their local-path root (504ddfb6, 2026-11-03), which the current text forbids, so this also ratifies that existing practice explicitly. legacy-coordinator-agent routed this proposal for livespec-dev-tooling-zbu7jf (plan ci-cache-optimization) after a tier judgement (2026-11-11T01:20:58Z) read the gate consumer as a spec change. The M4's measured 232 KiB/s inbound makes its publication slow, but each generation crosses that path once.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Runner-pool build cache tiers":

1. In **Scope.**, replace "together with a cold start in place of a seeded tree." with "together with a cold start in place of a seeded tree for its runner work volumes; its delegated gate Jobs' volumes MAY be seeded as **Storage placement** allows."

2. In **Tiers.**, replace "a SEEDED tree holding, for each routed repository, the git objects reachable from that repository's default branch and its tags, and no others" with "a SEEDED tree holding, for each routed repository and each repository that declares `delegated_gate = true`, the git objects reachable from that repository's default branch and its tags, and no others".

3. In **Tiers.**, replace "MUST build it only from the forge's default branch and tags of each routed repository" with "MUST build it only from the forge's default branch and tags of each such repository".

4. In **Tiers.**, after the sentence ending "under the one byte budget and one file budget above and under the reflink rule of **Storage placement**, at a per-repository path.", add: "A runner work volume MUST receive only the routed repositories' seeds. The pool MAY also give a delegated gate Job's volume a private copy of the gated repository's seed, and only that repository's, under the same budgets and the same reflink rule, for the gate's seeded tree fetch (contracts.md §\"Delegated pre-push gate\" **Seeded tree fetch.**). A generation MUST NOT be pruned while any gate volume holding a copy of it can still be bound to a pod."

5. In **Tiers.**, replace "Because a git alternate must be a local path, the host-served preference above does not apply to this tier, and a `runner-only` node runs it cold." with "Because a git alternate must be a local path, the host-served preference above does not apply to this tier, and a `runner-only` node's runner work volumes run it cold."

6. In **Trust by construction.**, replace "it MUST build only the default branch of each routed repository." with "it MUST build only the forge's default branch of each routed repository and of each repository that declares `delegated_gate = true`, never from the delegated gate's mirror. A delegated gate Job is a job for every rule of this paragraph."

7. In **Storage placement.**, after "a seeded warm tree MUST live on the tier that holds the work volumes it is seeded into (the `ci-workvols` role), because a seed that costs no data bytes is legal only within one filesystem.", add: "On a node with no `ci-workvols` tier, a seeded warm tree for delegated gate Jobs' volumes MUST instead live on the same filesystem as the directory those gate volumes are provisioned under; where that filesystem does not support reflink, the gate volume MUST get no seed (cold) rather than a byte copy."

In SPECIFICATION/non-functional-requirements.md §"Runner-pool node rebuild recipe", in **What a runner-only node's jobs get.**, replace "It MUST NOT seed a work volume from a warm tree, because the node carries no `ci-workvols` tier for a seed to live on." with "It MUST NOT seed a runner work volume from a warm tree, because the node carries no `ci-workvols` tier for a seed to live on. A delegated gate Job's volume on that node MAY be seeded from a warm tree placed as §\"Runner-pool build cache tiers\" **Storage placement** allows."

In SPECIFICATION/scenarios.md, add after "## Scenario: a routed job's checkout fetches only the objects its git object seed lacks, and falls back to a full fetch when the seed is missing":

## Scenario: the git object seed covers every gated repository, and a runner-only node seeds only its gate volumes

Given a repository that declares `delegated_gate = true` and is not routed to the runner pool

When the populator publishes a git object seed generation

Then the generation MUST hold that repository's default-branch and tag objects and no object reachable only from a pull-request ref

And on a `runner-only` node, when the pool seeds a delegated gate Job's volume, that volume MUST receive a reflink copy of its own repository's seed only, while a runner work volume on that node MUST receive no seed

And a generation MUST NOT be pruned while a gate volume holding a copy of it can still be bound to a pod

## Proposal: A delegated gate Job's tree fetch MAY read its volume's git object seed copy as an alternate, and refetches cold on any seed fault

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a **Seeded tree fetch.** bullet after **Verdict.** in contracts.md §"Delegated pre-push gate". The gate Job MAY name its volume's private seed copy as an alternate. The fetch keeps no depth limit and must end with the same tree, base, refs and reachable history as an unseeded fetch. A connectivity check runs before the recipe. Any seed fault (missing or unreadable copy, a fetch failing with the alternate named, a failed connectivity check) discards the fresh repository and refetches with no alternate, never failing the gate. The copy stays readable for the Job's whole life. The kill switch disables it. A scenario states these.

### Motivation

This is the consumer half of livespec-dev-tooling-zbu7jf; the companion proposal supplies the seed. The binding condition from legacy-coordinator-agent is that a stale, partial or corrupt seed yields the same verdict as a cold fetch. That is made testable here as identical recipe inputs (same tree, base, refs and history) plus a cold refetch on any detected fault. The depth ban stays because history readers such as the revert exemption's merge-base --is-ancestor against an arbitrarily old commit (docs/server-side-revert-exemption.md) need full history. An older generation only supplies fewer objects, so it is not treated as a fault.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", add this bullet after **Verdict.**:

- **Seeded tree fetch.** When the gate Job's volume holds a private copy of the node's git object seed for the gated repository (non-functional-requirements.md §"Runner-pool build cache tiers"), the Job's fetch of the tree under test and its base MAY name that copy as a git alternate of the fresh repository it fetches into. The alternate MAY only add objects. The fetch MUST NOT use a depth limit, and the fresh repository MUST end with the same tree, base commit, refs and reachable history that the same fetch with no alternate produces, so that every ancestry and merge-base query the recipe makes answers identically. Before the recipe runs, the Job MUST check the connectivity of the fetched tree and base (for example `git fsck --connectivity-only`). The fault cases are: a copy that is missing or unreadable, a fetch that fails while the alternate is named, or a failed connectivity check. In any of them, the Job MUST discard the fresh repository, fetch again from the gate mirror with no alternate, and continue. A seed fault MUST NOT by itself produce a red verdict or a no-verdict outcome. The Job MUST keep the copy readable for its whole life. An older generation is not a fault, because it only supplies fewer objects. Under the fleet kill switch (non-functional-requirements.md §"Runner-pool build cache tiers"), the fetch MUST name no alternate. This bullet binds every delegated gate Job that fetches a tree from the gate mirror, including the Jobs of §"Delegated pre-commit aggregate" and §"Delegated gate-runner runs".

In SPECIFICATION/scenarios.md, add after "## Scenario: a routed job's checkout fetches only the objects its git object seed lacks, and falls back to a full fetch when the seed is missing":

## Scenario: a delegated gate Job's tree fetch reads its volume's git object seed copy as an alternate, and refetches cold on any seed fault

Given a delegated gate Job whose volume holds a private copy of the gated repository's git object seed

When the gate Job fetches the tree under test and its base into a fresh repository

Then the fetch MAY name the copy as its git alternate, and then MUST transfer from the gate mirror only objects absent from the copy

And the fetch MUST NOT use a depth limit, and the fresh repository MUST end with the same tree, base commit, refs and reachable history as the same fetch with no alternate

And when the copy is missing or unreadable, the fetch fails with the alternate named, or the connectivity check of the fetched tree and base fails, the Job MUST discard the fresh repository, fetch again with no alternate, and report the verdict that fetch yields

And under the fleet kill switch the fetch MUST name no alternate
