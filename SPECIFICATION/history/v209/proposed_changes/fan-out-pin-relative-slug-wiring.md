---
topic: fan-out-pin-relative-slug-wiring
author: claude-opus-5-5:ci-runtime-and-cost
created_at: 2026-11-10T11:15:29Z
---

## Proposal: fan-out preflight treats a post-pin canonical slug omission as staleness-class

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend contracts.md §"Pin-currency severity policy" so that, in the release fan-out preflight only, a `canonical-check-slugs-wired` finding whose every omitted slug is absent from the canonical check set of the livespec-dev-tooling release the member pins is a PIN-RELATIVE finding: it stays error-severity and is named in the exclusion summary, but it MUST NOT exclude the member from the dispatch matrix, because the sibling-released dispatch's bump-pin rewrite wires exactly those slugs. A finding that omits any slug already present in the pinned release's canonical check set, or that cannot resolve the pinned release's canonical check set, still excludes as today. The per-PR CI job and the scheduled central sweep keep their current severity for the row. Two scenarios are added and the existing non-pin exclusion scenario is narrowed to match.

### Motivation

livespec-dev-tooling-7url4a (plan ci-runtime-and-cost, epic livespec-dev-tooling-ib3oe3). The fan-out preflight excludes a member for any error finding other than the two pin-staleness classes, as v093 ratified. The `bump-pin-rewrite` composite that the sibling dispatch runs already performs the justfile and ci.yml canonical reconcile, so the dispatch itself wires any canonical slug that first shipped after the member's pin. Excluding the member for such a slug removes the only cure, which is the same reasoning v093 applied to staleness: the pin goes stale because the fan-out skips the member, and the fan-out skips the member because the pin is stale. Measured 2026-11-10 (rule G sweep): the v1.190.1 preflight (run 42732849823) and the v1.191.0 preflight (run 42759131006) each excluded the same three members, every exclusion on `canonical-check-slugs-wired`. livespec-orchestrator-git-jsonl (pin v1.187.0) omitted only `check-rule-26-keep-out`, first shipped in v1.188.0. livespec-runtime (pin v1.134.2) omitted `check-codex-hook-reconcilable`, `check-delegated-gate-check-suite` and `check-rule-26-keep-out`. livespec-console-beads-fabro (pin v1.171.0) omitted slugs older than its pin as well, which is genuine non-conformance and stays excluded under this proposal. contracts.md already makes individual canonical slugs pin-relative ("Once a consumer's library pin reaches the release that ships this module", at the `check-delegated-job-authority-skip` paragraph and its siblings); this proposal generalizes that rule to the fan-out filter. Implementation lives in `livespec_dev_tooling/fleet/dispatch_matrix_filter.py` (`_dispatch_matrix_partition`); per the revise reader-test discipline, the revise SHOULD run that module's tests against a drafted filter change before review.

### Proposed Changes

In SPECIFICATION/contracts.md §"Pin-currency severity policy", add the following bullet immediately after the bullet that begins "**BOTH CLASSES ESCALATE ONLY WHERE A PER-MEMBER REMEDY EXISTS.**":

> - **A canonical slug that shipped after the member's pin is a PIN-RELATIVE finding, and the fan-out preflight MUST NOT exclude for it.** In the release fan-out preflight, a `canonical-check-slugs-wired` finding whose EVERY omitted slug is absent from the canonical check set of the `livespec-dev-tooling` release the member pins is pin-relative. It MUST remain error-severity and MUST be named in the exclusion summary, with each omitted slug and the member's pinned release, but it MUST NOT exclude the member from the dispatch matrix. The sibling-released dispatch is its remedy: the bump-pin rewrite it runs reconciles the member's `just check` aggregate and its `ci.yml` canonical wiring against the release it bumps to, so excluding the member removes the cure exactly as excluding a stale pin would. The pinned release's canonical check set is the set §"Shared check inventory" derives from `livespec_dev_tooling/checks/<slug>.py`, read from that release's tagged tree; it MUST NOT be read from the latest release or inferred from the slug's name. A finding that omits ANY slug present in the pinned release's canonical check set is NOT pin-relative and MUST exclude the member, naming each such slug, because the member failed to wire a check it already had. When the member's pinned release, or its canonical check set, cannot be read or resolved, the finding MUST exclude the member exactly as a non-pin error finding does; an unread canonical check set is never evidence that a slug is post-pin. This rule changes only whether the finding excludes in the fan-out preflight: the per-PR CI job and the scheduled central sweep MUST report `canonical-check-slugs-wired` at the severity they report it today.

Replace the section's final paragraph with:

> An error finding for a member in the release's dispatch sibling set excludes that member from the dispatch matrix via the fan-out preflight's per-member filter (the reusable-release-dispatch.yml contract), EXCEPT a finding of either staleness class or a pin-relative `canonical-check-slugs-wired` finding, each of which MUST remain error-severity and be named in the exclusion summary but MUST NOT exclude the member. A member whose ONLY error findings are of those kinds MUST receive the dispatch. A can't-parse pin finding still excludes, because the bump rewrite cannot be applied to a pin file that does not parse. An excluding finding never halts dispatch to conformant members.

In SPECIFICATION/scenarios.md, replace the scenario `## Scenario: a member with an unparseable pin file or a non-pin error row is still excluded from the release dispatch` with:

> ## Scenario: a member with an unparseable pin file or a non-pin error row is still excluded from the release dispatch
>
> Given a fleet member with an error-severity can't-parse pin finding, or an error-severity finding on a row other than a pin-currency row that is not a pin-relative `canonical-check-slugs-wired` finding
>
> When the release fan-out filters its dispatch matrix
>
> Then the member MUST be excluded from the dispatch with an annotation naming it and the failing rows

and add the following two scenarios immediately after it:

> ## Scenario: a member that omits only canonical slugs newer than its pin still receives the release dispatch
>
> Given a fleet member that pins `livespec-dev-tooling` release v1.187.0
>
> And whose only error-severity finding in the fan-out preflight is a `canonical-check-slugs-wired` finding omitting `check-rule-26-keep-out`
>
> And `check-rule-26-keep-out` is absent from the canonical check set of the v1.187.0 tagged tree
>
> When the release fan-out filters its dispatch matrix
>
> Then the member MUST receive the sibling-released dispatch
>
> And the run summary MUST name the member as not excluded, with `check-rule-26-keep-out` and the pinned release v1.187.0
>
> And when the same member is evaluated by the per-PR CI job or the scheduled central sweep, the `canonical-check-slugs-wired` finding MUST be reported at the severity those contexts report it today
>
> ## Scenario: a canonical slug omission the fan-out cannot prove post-pin still excludes the member
>
> Given a fleet member whose fan-out preflight reports a `canonical-check-slugs-wired` finding
>
> And either one omitted slug is present in the canonical check set of the release the member pins, or that release or its canonical check set cannot be read
>
> When the release fan-out filters its dispatch matrix
>
> Then the member MUST be excluded from the dispatch
>
> And the exclusion annotation MUST name the member, and MUST name each omitted slug that the pinned release's canonical check set carries or state that the pinned release's canonical check set could not be read

The revise that accepts this proposal MUST add `tests/heading-coverage.json` rows for the two new scenario headings, owned by livespec-dev-tooling-7url4a, and MUST keep the existing row for the replaced scenario heading, whose text is unchanged.
