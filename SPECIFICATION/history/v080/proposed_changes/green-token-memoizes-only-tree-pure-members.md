---
topic: green-token-memoizes-only-tree-pure-members
author: claude-opus-5-5
created_at: 2026-10-18T19:29:59Z
---

## Proposal: The green token memoizes only tree-pure members; world-reading members run on every push

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Narrows what the green token stands for. As the section is worded, a token match lets the pre-push gate skip both paths for a byte-identical clean tree. After this change the token memoizes only the members of the gate's check set whose verdict depends on the committed tree alone (tree-pure members). On a token match the gate still runs every world-reading member on the pushing host, and refuses the push if one fails. Purity is declared per check. A member with no declaration counts as world-reading, and this repository's own check aggregate refuses a member that carries no declaration. The change amends the "Verdict" and "Explicit local route" bullets of `SPECIFICATION/contracts.md` §"Delegated pre-push gate", adds a "Token memoization" bullet to the same section, and adds two scenarios to `SPECIFICATION/scenarios.md`.

### Motivation

Work-item `livespec-dev-tooling-aape` (child of plan `delegated-gate-fleet-rollout`, epic `livespec-dev-tooling-mvalxq`) records the defect. The green token keys a memoized verdict on the tree's hash, and that key is sound only for a check whose answer is a function of the tree. Several members of the check aggregate read state outside the tree, and their answer can change while the tree does not. Examples are a check that reads master's CI status, one that reads live branch-protection settings, ones that read the work-items ledger, one that reads the tooling installed on the host, and one that reads the agent memory store. Because the two bullets amended here let a token match skip the whole gate, the ordinary sequence of a green `just check` followed later by `git push` skips those members. A push can then land on a red master on the strength of an observation made arbitrarily long before. The ledger comment of 2026-09-08 measured a seven-week-old token on a live checkout.

The work-item's Definition of Done contradicts the "Explicit local route" bullet, which says the gate "skips both paths for that tree", and the "Verdict" bullet, which says a byte-identical tree "is not gated twice". So the spec change has to land before the item can be dispatched. Of the three fixes recorded on the item, this proposal states the one the item chose: each check declares its purity, and the set that always runs is derived from those declarations rather than kept as a separate hand-maintained list. A time limit on the token is deliberately not proposed. Master can turn red seconds after a token is written, so a time limit only caps how long a wrong verdict is reused.

The proposal states the invariant (what may be memoized, the safe default, the refusal of an undeclared member, and where a declaration lives) and leaves the module layout and the declaration's syntax to the implementer. The same defect exists in the livespec repository's own justfile and its `SPECIFICATION/contracts.md` §"Pre-commit step ordering". That is outside this spec target and is owed as a separate livespec work-item once this change ships in a livespec-dev-tooling release.

### Proposed Changes

Three edits to `SPECIFICATION/contracts.md` §"Delegated pre-push gate" and two new scenarios in `SPECIFICATION/scenarios.md`. Each replace-target below is quoted verbatim from the section as it stands.

**Edit 1 — the "Verdict" bullet.** Replace its final sentence:

> A green delegated verdict records the same green token — the per-worktree marker, keyed on the `HEAD` tree's hash, that the pre-push gate consults before either path — that a green local aggregate records, so a byte-identical tree is not gated twice while the worktree stays clean.

with:

> A green delegated verdict records the same green token — the per-worktree marker, keyed on the `HEAD` tree's hash, that the pre-push gate consults before either path — that a green local aggregate records, so the tree-pure members of a byte-identical tree's check set are not gated twice while the worktree stays clean. Its world-reading members are not memoized by that token and run again on the pushing host, as the "Token memoization" bullet below requires.

**Edit 2 — the "Explicit local route" bullet.** Replace the whole bullet:

> - **Explicit local route.** A green local `just check` that skips no member, run in the pushing worktree, records the green token, after which the pre-push gate skips both paths for that tree while the worktree is clean. An unavailable cluster therefore never prevents pushing a clean worktree whose tree has gone green locally.

with:

> - **Explicit local route.** A green local `just check` that skips no member, run in the pushing worktree, records the green token. While the worktree is clean and its `HEAD` tree is the tree the token names, the pre-push gate takes neither path: it submits no gate Job and does not run the local fall-through, and runs only the world-reading members that the "Token memoization" bullet below requires. An unavailable cluster therefore never prevents pushing a clean worktree whose tree has gone green locally, and a world-reading member that fails still refuses that push.

**Edit 3 — a new bullet.** Insert the following bullet immediately after the "Explicit local route" bullet and before the "Credential use" bullet:

> - **Token memoization.** The green token MUST memoize only the members whose verdict depends on the committed tree alone. Such a member is *tree-pure*: the same tree always yields its same verdict. A member whose verdict can change while the tree does not is *world-reading*, because it reads state outside the tree. Examples of such state are a remote service's status, live repository settings, the work-items ledger, other clones or worktrees, the tooling installed on the host, and the commits around the tree. Each member of a gate's check set carries its own purity declaration. A check this repository ships declares its own purity, so the declaration reaches every consuming repository with the library. A member that exists only in one repository is declared by that repository. A member with no purity declaration MUST be treated as world-reading. When the token matches, the pre-push gate MUST run, on the pushing host, every world-reading member of the check set its local fall-through runs. It MUST NOT run that set's tree-pure members, and it MUST refuse the push when any member it runs fails. It MUST also print the name of each member it ran and the number of members it skipped because the token matched, so that a memoized push never reads as fully gated. This repository's own check aggregate MUST fail, naming the member, when one of its members carries no purity declaration. Without that refusal an undeclared member would quietly fall back to the world-reading default, and the saving the token exists for would shrink without anyone noticing. This bullet binds the pre-push gate of every repository that records the green token, whether or not it delegates.

**Edit 4 — two new scenarios.** Insert the following two scenarios into `SPECIFICATION/scenarios.md` immediately after the scenario `## Scenario: an opted-in push is refused when no verdict arrives` (that is, before `## Scenario: a second controller cannot reserve the Docker engine install guard while a run is unfinished`), so they sit with the other delegated-gate scenarios:

> ## Scenario: a push of a tree holding a green token still runs the members that read state outside the tree
>
> Given a consuming repository's worktree with no uncommitted changes whose `HEAD` tree is the tree its green token names
>
> And the check set the pre-push gate's local fall-through runs holds a tree-pure member, a world-reading member, and a member that carries no purity declaration
>
> And the world-reading member fails for that tree
>
> When a git push of that tree runs the pre-push gate
>
> Then the world-reading member and the member that carries no purity declaration MUST run on the pushing host
>
> And the tree-pure member MUST NOT run
>
> And a gate Job MUST NOT be submitted to the `gates` namespace
>
> And the push MUST be refused
>
> ## Scenario: a check aggregate member with no purity declaration fails the aggregate
>
> Given a member of livespec-dev-tooling's check aggregate that carries no purity declaration
>
> When livespec-dev-tooling's full `just check` aggregate runs
>
> Then the aggregate MUST exit non-zero
>
> And its output MUST name that member

**Ratification mechanics (for the revise payload, not spec text).** This proposal adds no `## ` heading to `contracts.md`; the "Token memoization" bullet sits inside the existing §"Delegated pre-push gate". It adds exactly two `## ` headings to `scenarios.md`:

- `## Scenario: a push of a tree holding a green token still runs the members that read state outside the tree`
- `## Scenario: a check aggregate member with no purity declaration fails the aggregate`

The revise payload MUST carry, as `../tests/heading-coverage.json` in `resulting_files[]`, one `TODO` row for each, with `spec_root` `SPECIFICATION`, `spec_file` `scenarios.md`, `work_item` `livespec-dev-tooling-aape`, and a `reason` naming the integration tier (for example: "A real test at the integration tier or above is owed for this heading; livespec-dev-tooling-aape owns it."). The heading-coverage debt register MUST be regenerated, never hand-edited.
