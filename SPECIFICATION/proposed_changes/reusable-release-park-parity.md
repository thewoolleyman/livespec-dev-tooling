---
topic: reusable-release-park-parity
author: claude-fable-5
created_at: 2026-07-04T09:59:25Z
---

## Proposal: reusable-release-park.yml two-leg spec parity

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/spec.md

### Summary

Adds the `#### `reusable-release-park.yml`` subsection to §"Reusable workflow inventory" in SPECIFICATION/contracts.md, documenting the release-train park backstop at parity with the three pin-and-bump reusable-workflow subsections. Per the design-record-authority rule the contract describes the TWO-leg design from design.md §L0c — leg (a) a parked open `release-please--*` pull request older than the threshold, and leg (b) unreleased `feat`/`fix` commits on the default branch newer than the latest release tag beyond the threshold — both governed by the single `park_threshold_hours` input. Also sweeps three neighbouring statements the addition would falsify: the H2 intro's "three thin shim workflows" count is qualified to "pin-and-bump" and notes the extra release-park shim; the inventory intro notes three of the four workflows implement the pin-and-bump policy while the fourth is the independent read-only park backstop; and — added 2026-07-21 after an independent adversarial review found the original sweep incomplete — `spec.md`'s definition of the cross-repo coordination category, which claims that category's workflows "implement the pin-and-bump mechanism" and enumerates four functions omitting the park backstop. The first two sweeps are inside `contracts.md`; the third is the reason `SPECIFICATION/spec.md` is now a second target file.

### Motivation

Work-item livespec-dev-tooling-afd: a spec-parity propose-change adds the reusable-release-park.yml subsection to contracts.md. An independent Fable review found the shipped reusable-release-park.yml implements only ONE of the TWO detection legs its design record (livespec/plan/fleet-plugin-currency/research/design.md §L0c) specifies. Per the ratified design-record-authority rule, the CONTRACT must describe the two-leg DESIGN, and the missing implementation leg is filed as a tracked gap. This propose-change re-drafts the payload to the two-leg design and sweeps the drift the addition introduces.

### Proposed Changes

This proposal adds the missing `#### `reusable-release-park.yml`` subsection to §"Reusable workflow inventory" so the reusable-workflow surface is documented at parity with the three pin-and-bump subsections, and it sweeps two neighbouring statements that the addition would otherwise falsify. Per the ratified design-record-authority rule, the contract describes the TWO-leg DESIGN recorded in `livespec/plan/fleet-plugin-currency/research/design.md` §L0c — NOT the shipped workflow, which currently implements only leg (a). The missing leg-(b) implementation is filed as a tracked dev-tooling work-item and is not silently contracted away.

Three verbatim replace-targets in `SPECIFICATION/contracts.md` (each exists once in the live file; re-verify against origin/master before applying):

=== Replace-target A (REQUIRED — the subsection insertion) ===
Replace this verbatim closing paragraph of the `#### `reusable-pin-freshness.yml`` subsection:

FIND (verbatim):
```
The freshness workflow is the safety net for missed dispatches, releases that occurred before this surface was wired in, and any future class of dispatch failure that does not auto-recover.
```

REPLACE WITH:
```
The freshness workflow is the safety net for missed dispatches, releases that occurred before this surface was wired in, and any future class of dispatch failure that does not auto-recover.

#### `reusable-release-park.yml`

Periodic release-train park backstop invoked by each release-please repository's own `release-park.yml` shim on `on: schedule: cron: ...` (plus `workflow_dispatch`). It is NOT one of the three pin-and-bump coordination shims (§"Self-hosting"); it is an independent, read-only guard on the release train that FEEDS the pin-and-bump web, so it ships in this inventory without taking part in the pin-and-bump policy.

Inputs:
- `park_threshold_hours` (number, optional, default `24`) — the single staleness threshold, in hours, governing BOTH detection legs below; one input, not two.

Behavior: the workflow MUST fail the scheduled job loud — naming the offending artifact and its age — when EITHER of two independent staleness legs trips, both measured against the single `park_threshold_hours` input:

- **Leg (a) — a parked open release pull request.** The workflow queries the caller repository's OPEN pull requests for one authored by the fleet release-please App bot on a `release-please--*` head branch, and FAILS when such a pull request has been open for at least `park_threshold_hours`. The workflow MUST measure a pull request's age from its open time (the `createdAt` timestamp), NOT its last-update time: release-please force-updates its release branch (resetting the last-update time to ~now) on every new `feat`/`fix` landing on the default branch, so an update-time measure would reset on every push and a genuinely parked release pull request would never age past the threshold. The workflow MUST recognize the fleet release-please App bot under EITHER login spelling it presents — `app/livespec-pr-bot` (as `gh pr list --json author` returns it) and `livespec-pr-bot[bot]` (as the webhook `pull_request` payload spells the same identity) — so detection stays correct across GitHub output shapes.
- **Leg (b) — an unreleased backlog with no release pull request open.** The workflow MUST ALSO fail when the default branch carries `feat`/`fix` commits newer than the latest release tag by more than `park_threshold_hours` (the age measured from the oldest such unreleased `feat`/`fix` commit against the same threshold). This is the case where release-please has failed to open a release pull request at all, so leg (a) has nothing to detect; leg (b) is the ONLY guard against a release train that silently produced no release pull request. Both legs share the one `park_threshold_hours` input.

The workflow performs NO auto-merge and NO mutation and requires NO GitHub App secrets: it authenticates with the read-only `github.token` (permissions `contents: read`, `pull-requests: read`), and its ONLY surface is the scheduled job's pass/fail status — a red job IS the alarm. It is the INDEPENDENT backstop to the release-please auto-merge path (`auto-enable-merge.yml`): auto-merge lands release-please pull requests hands-off, and this guard fails loud if that path ever regresses and a release pull request sits unmerged, so a stalled release train can never sit silent.
```

=== Replace-target B (RECOMMENDED — inventory-intro drift sweep) ===
Replace the `### Reusable workflow inventory` intro paragraph:

FIND (verbatim):
```
The library MUST ship the following reusable workflows under `.github/workflows/`, each with a `workflow_call` trigger and the inputs/outputs declared below. Each workflow's path is the semver-stable identifier consumers reference via `uses:`.
```

REPLACE WITH:
```
The library MUST ship the following reusable workflows under `.github/workflows/`, each with a `workflow_call` trigger and the inputs/outputs declared below. Each workflow's path is the semver-stable identifier consumers reference via `uses:`. Three of the four implement the pin-and-bump policy; the fourth, `reusable-release-park.yml`, is the independent read-only release-train park backstop that guards the release train FEEDING that policy (it participates in no pin rewrite).
```

=== Replace-target C (REQUIRED — H2-intro drift sweep, falsified "three thin shim workflows" count) ===
The §"Cross-repo coordination automation surface" intro (immediately under the H2) states the per-repo footprint "is three thin shim workflows". Adding `release-park.yml` makes that a fourth per-repo shim for release-please members, so the unqualified count is falsified. Replace:

FIND (verbatim):
```
Per the DRY discipline, every consumer's per-repo coordination footprint is three thin shim workflows that delegate to the reusable workflows defined here; no coordination logic is duplicated across consumers.
```

REPLACE WITH:
```
Per the DRY discipline, every consumer's per-repo pin-and-bump coordination footprint is three thin shim workflows that delegate to the reusable workflows defined here; no coordination logic is duplicated across consumers. Release-please members additionally carry the independent `release-park.yml` shim — the read-only release-train park backstop that participates in no pin rewrite — per §"Reusable workflow inventory".
```

#### 4. `SPECIFICATION/spec.md` — the category definition this addition falsifies

**Added 2026-07-21** after an independent adversarial review found the original
sweep incomplete. The three sweeps above stay inside `contracts.md`, but the
statement that DEFINES the cross-repo coordination category lives in `spec.md`,
and this addition falsifies it in the same stroke.

`spec.md` says the coordination category "ships reusable workflows that
implement the pin-and-bump mechanism", then enumerates four functions — none of
which is the park backstop. Once `reusable-release-park.yml` joins that
category's "full inventory" (the very inventory `spec.md` points at), the
definition contradicts the contract text this proposal adds, which states in so
many words that the fourth workflow "participates in no pin rewrite". Sweeping
`contracts.md` alone would leave the spec asserting the category is
pin-and-bump-only while its own inventory says otherwise.

FIND (verbatim):
```
The **cross-repo coordination category** ships reusable workflows that implement the pin-and-bump mechanism declared in `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump" — release-dispatch fan-out, autodiscovery-driven bump-pin pull requests, vendored-library re-bump, and periodic pin-freshness sweeps.
```

REPLACE WITH:
```
The **cross-repo coordination category** ships reusable workflows that implement the pin-and-bump mechanism declared in `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump" — release-dispatch fan-out, autodiscovery-driven bump-pin pull requests, vendored-library re-bump, and periodic pin-freshness sweeps — plus the independent read-only release-train park backstop (`reusable-release-park.yml`), which guards the release train FEEDING that mechanism and participates in no pin rewrite.
```

The wording deliberately mirrors the inventory intro's own phrasing in sweep 2
("guards the release train FEEDING that policy … participates in no pin
rewrite"), so the two statements read as one rule rather than two overlapping
ones.

Heading-coverage co-edit: NOT required. The change adds only a `####` (H4) subsection and edits prose; it changes NO `## ` (H2) heading set, and `tests/heading-coverage.json` tracks only H2 headings. So no `../tests/heading-coverage.json` entry is added to `resulting_files[]`. Sweep 4 edits a `spec.md` paragraph and likewise changes no H2.

