---
topic: self-hosting-selfsourced-glob-drift
author: claude-opus-5
created_at: 2026-09-08T03:12:00Z
---

## Proposal: §"Self-hosting" enumerates the self-sourced `uses:` pins with a stale literal glob — name the format instead of restating its file set

### Target specification files

- SPECIFICATION/contracts.md

### Summary

§"Self-hosting" defines which of this library's own pins are SELF-SOURCED — the ones no incoming
dispatch can ever reconcile, and which the producer must therefore rewrite at release time. It
identifies the second of the two self-sourced formats by restating a literal file glob:

> (ii) this library's OWN `.github/workflows/*.yml` `uses:` refs into its own reusable workflows

That glob is a COPY of the `uses:` ref format's scan set, and the original has moved twice while
the copy has not. It should name the format and let the format's own bullet define the file set.

### Motivation

Filed as a follow-up from the v063 revise pass, with the ratification reviewer's explicit
agreement that it is a follow-up and NOT a ratification condition on that amendment.

**The copy is narrower than the original on two axes, one of them pre-existing.**

- **SUFFIX, pre-existing.** The `uses:` ref format has covered `*.yml` AND `*.yaml` since well
  before v063. §"Self-hosting" has only ever said `*.yml`. A self-referencing `uses:` line in a
  `.yaml` shim is a self-sourced pin that this section does not describe.
- **SUFFIX and DIRECTORY, introduced by v063.** The format now additionally covers `*.jinja`
  workflow TEMPLATES, and `.github/workflows/` at ANY DEPTH. A self-referencing `uses:` line in a
  workflow template — precisely the artifact class v063 was filed about, after measuring template
  pins in `livespec` that had never moved while their root counterparts were bumped repeatedly —
  is self-sourced by the same derivation and is outside this section's stated glob.

**Why a stale copy here is worse than a stale copy elsewhere.** This section exists because the
release fan-out DELIBERATELY excludes the publishing repository from its own dispatch matrix, so
no `sibling-released` event announcing this library's own release ever arrives here. It states the
consequence plainly:

> Without this rule the producer has NO release-driven path that tracks either the image it builds
> or the reusable workflows it publishes; the periodic freshness scan is then the only remaining
> catch — at worst a full cron cycle late, and never release-coupled.

A self-sourced pin this section fails to enumerate has no release-coupled reconciler at all. It is
the same "reproducible, and now silently rotting" failure v063's own motivation describes: the pin
is concrete, so nothing looks wrong, and the automation that would advance it cannot see it.

**Measured, and stated honestly: the drift is LATENT in this repository today, not live.**
Measured against this checkout on 2026-09-08: this repository carries exactly one
`.github/workflows/` directory (the root one), no `*.yaml` workflow files, and no `*.jinja`
workflow templates anywhere. Its self-referencing `uses:` lines are the four shims
(`pin-freshness.yml`, `bump-pin-from-dispatch.yml`, `release-park.yml`, `release-dispatch.yml`),
all `*.yml` at the root, all inside the stated glob — and all observed at `v1.58.5`, having just
been advanced by this library's own release self-bump. So no pin is rotting unreconciled right
now, and the producer-at-release-time path is demonstrably WORKING for the pins this glob names.
That is the point: the mechanism is healthy, and a self-sourced pin that falls outside the glob
would not be covered by it while looking exactly like the ones that are.

That is a reason to fix the wording cheaply, not a reason to defer it. The gap opens the moment
this library grows a workflow template or a `.yaml` shim — and this library is the fleet's TEMPLATE
PRODUCER, which makes acquiring a `templates/*/.github/workflows/*.jinja` tree an ordinary future
step rather than a hypothetical one. The defect would then present as silence: a self-sourced pin
that no dispatch reconciles, no release rewrites, and nothing reports.

### Proposed Changes

In §"Self-hosting", replace

> (ii) this library's OWN `.github/workflows/*.yml` `uses:` refs into its own reusable workflows —
> the consumer shims named above plus any other self-referencing `uses:` — whose source repo
> derives to this library from the `<repo>` segment.

with

> (ii) this library's OWN self-referencing `uses:` refs into its own reusable workflows, in the
> full scan set of the §"Pin autodiscovery rules" `uses:` ref format — every workflow file AND
> workflow template that format covers, not only the root `*.yml` shims — comprising the consumer
> shims named above plus any other `uses:` line whose source repo derives to this library from the
> `<repo>` segment. This section deliberately does NOT restate that format's file set: the format's
> own bullet is the single definition, and a copy here would drift from it.

### Rationale

- **It removes a duplicated definition rather than updating it**, so this section cannot drift
  again the next time the format's scan set changes. The failure being fixed is the copy, not the
  particular suffix it is stale on.
- **It changes no behaviour and widens no scan set.** Which pins are self-sourced is determined by
  source-repo derivation, which is unchanged; this section only ENUMERATES them, and the
  enumeration is being made to match what the walk already discovers.
- **It is consistent with how the same sentence already handles the OTHER self-sourced format**,
  which it identifies by reference — "(i) the fabro-sandbox docker image tag (§"Pin autodiscovery
  rules")" — rather than by restating that format's paths. Bullet (ii) is the odd one out.

### Non-goals of this proposal

- It does NOT change the producer-at-release-time reconciliation rule, its ordering constraint for
  the image tag, or the `chore(deps):` commit convention.
- It does NOT add any pin format, and does not alter which repositories are dispatch siblings.
- It does NOT depend on this library acquiring a workflow template; the wording is correct either
  way.
