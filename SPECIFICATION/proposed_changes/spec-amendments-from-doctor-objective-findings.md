---
topic: spec-amendments-from-doctor-objective-findings
author: claude-opus-4-7
created_at: 2026-05-25T17:25:13Z
---

## Proposal: drop-dangling-cross-file-reference-to-coordination-surface-bootstrap-procedure

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/non-functional-requirements.md

### Summary

`contracts.md` line 181 (in §"Self-hosting") references `non-functional-requirements.md §"Coordination-surface bootstrap procedure"` with the annotation "(which lands as a separate amendment in the same revise pass that lands this contract)". The companion amendment never landed in v002; the target section does not exist in the NFR file's H2 inventory today. The reference is a dangling cross-file `§"…"` citation that escapes the static-phase `doctor-anchor-reference-resolution` check (which is intentionally scoped to same-file Markdown link anchors per its docstring at `livespec/doctor/static/anchor_reference_resolution.py:17-20`).

### Motivation

Detected during a `/livespec:doctor` LLM-objective phase run on 2026-05-25. The reference rots silently because no static check covers cross-file `§"…"` prose citations; only an LLM-objective sweep notices. The related sibling propose-change `livespec/SPECIFICATION/proposed_changes/reference-discipline-invariant.md` (filed in the same investigation) would codify the rule that prevents future instances, but that fix runs through livespec's revise cycle independently; the dangling reference here needs disposition irrespective of when (or whether) the upstream invariant lands.

### Proposed Changes

Inline the bootstrap detail into `contracts.md` §"Self-hosting" and drop the cross-reference. Specifically, replace the current §"Self-hosting" paragraph (lines 177-181):

> ### Self-hosting
>
> The library is itself a sibling consumer of its own coordination automation surface. The library's own `.github/workflows/` MUST include the three consumer shims (`release-dispatch.yml`, `bump-pin-from-dispatch.yml`, `pin-freshness.yml`) and the repository MUST carry the `livespec-sibling` topic. The shims delegate to the reusable workflows at the library's own currently-pinned release tag; consequently the library pin-and-bumps itself when livespec releases.
>
> The self-hosting bootstrap (initial publication of the coordination workflows) is a one-time manual step performed by a human contributor; thereafter the system perpetuates via its own dispatches. The bootstrap is described in this library's `non-functional-requirements.md` §"Coordination-surface bootstrap procedure" (which lands as a separate amendment in the same revise pass that lands this contract).

with the revised content:

> ### Self-hosting
>
> The library is itself a sibling consumer of its own coordination automation surface. The library's own `.github/workflows/` MUST include the three consumer shims (`release-dispatch.yml`, `bump-pin-from-dispatch.yml`, `pin-freshness.yml`) and the repository MUST carry the `livespec-sibling` topic. The shims delegate to the reusable workflows at the library's own currently-pinned release tag; consequently the library pin-and-bumps itself when livespec releases.
>
> The self-hosting bootstrap is a one-time manual step: a human contributor authors the three consumer shims with their `uses:` lines pinned to a hand-chosen bootstrap tag (typically the first tag of this library that ships all three reusable workflows under `.github/workflows/`), tags the bootstrap release, and verifies that the first dispatch from a sibling release reaches this library and opens a bump-PR. Thereafter the system perpetuates via its own dispatches and the manual step is never repeated.

The revision removes the dangling §"Coordination-surface bootstrap procedure" reference and inlines a self-contained one-paragraph description of the bootstrap procedure. NO change required to `non-functional-requirements.md` — the section that was promised never landed and no other content references it.

This propose-change documents the SPEC change. Implementation work: none. The cross-reference was the only artifact pointing at the missing NFR section.


## Proposal: drop-stale-proposal-stage-language-in-contracts-migration-notes

### Target specification files

- SPECIFICATION/contracts.md

### Summary

`contracts.md` §"Migration notes" (lines 183-189) carries proposal-stage future-tense imperative phrasing ("The following content currently in `livespec/SPECIFICATION/contracts.md` MUST migrate here as part of this proposal's acceptance, and MUST be replaced by a cross-reference in livespec's spec…"). Since `contracts.md` is the ratified v002 contract, the migration the section prescribes either happened (text is anachronistic) or didn't (action items belong in a tracked work-item, not in the ongoing contract surface). Either way the section's wording is inappropriate for a ratified spec file.

### Motivation

Detected during the same `/livespec:doctor` LLM-objective phase run as the prior proposal. The pattern is not unique to this file — `livespec/SPECIFICATION/contracts.md:208` and `livespec/SPECIFICATION/non-functional-requirements.md:592` carry similar leftover proposal-stage language inside ratified content. Neither the existing `doctor-bcp14-keyword-wellformedness` nor the existing `doctor-anchor-reference-resolution` static checks cover this pattern; only an LLM-objective sweep notices.

The companion upstream propose-change `livespec/SPECIFICATION/proposed_changes/reference-discipline-invariant.md` codifies a related-but-distinct rule (no cross-spec references); a future propose-change MAY codify a complementary "no proposal-stage tense in ratified content" invariant, but that broader sweep is out of scope for THIS proposal, which targets only the specific stale section in dev-tooling.

### Proposed Changes

Delete §"Migration notes" (lines 183-189) entirely. The historical provenance the section records — that certain content was migrated from `livespec/SPECIFICATION/contracts.md` in v002 of this library's spec — already lives in `history/v002/contracts.md` as the canonical snapshot. The ongoing v002+ contract surface does not need to carry the historical-action note; that's exactly what `history/` is for.

Specifically, delete:

> ### Migration notes
>
> The following content currently in `livespec/SPECIFICATION/contracts.md` MUST migrate here as part of this proposal's acceptance, and MUST be replaced by a cross-reference in livespec's spec:
>
> - The "auto-merge bot architecture deferred; v1 MAY rely on manual bump-pin PRs" half-sentence at livespec contracts.md §"Cross-repo coordination — pin-and-bump" — superseded by this section's full automation contract.
> - The reusable-workflow inventory specifics from livespec contracts.md §"Shared code sync — livespec-dev-tooling" — the consumption-shape sentence stays in livespec, the workflow inventory is now this library's surface.
> - The specific surface enumeration in livespec contracts.md §"Shared code sync — livespec-dev-tooling" — the semver-stable surface PRINCIPLE stays in livespec, the specific list of covered surface elements is now extended below in §"Semver coverage extension".

NO change required to §"Semver coverage extension" (the section §"Migration notes" forwards to). That section stands on its own as a substantive contract extension. The deletion is a pure removal of historical-action prose that has no ongoing contractual meaning.

This propose-change documents the SPEC change. Implementation work: none. The deletion is pure prose removal in the spec file; no code or check references the deleted section.


## Proposal: replace-external-epic-phase-references-with-self-contained-activity-descriptions

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/non-functional-requirements.md

### Summary

Seven `Phase G.2` / `Phase G.4` / `Phase G.6` references in the spec name epic phases of `livespec epic li-fgqgnk` — an external work-item-tracking identifier whose content is defined in livespec's impl-plaintext JSONL store, not in this spec tree. A reader of this spec cannot interpret "Phase G.4 completes the move" without external lookup, which violates the standalone-readability goal that the companion upstream propose-change `livespec/SPECIFICATION/proposed_changes/reference-discipline-invariant.md` codifies.

### Motivation

Detected during the same `/livespec:doctor` LLM-objective phase run as the prior two proposals. The references appear at: `spec.md:43`, `contracts.md:30`, `constraints.md:42`, `non-functional-requirements.md:20,27,66,74`. Each citation uses the phase identifier as a temporal qualifier ("once Phase G.4 completes the move", "at Phase G.2 of livespec epic li-fgqgnk", etc.) rather than describing the underlying activity inline.

The upstream propose-change codifies the rule but its acceptance does not retroactively rewrite this spec's existing prose; the rewrite is what THIS proposal does. The two propose-changes are independent: this one stands even if the upstream invariant doesn't land, because standalone-readability is a property worth restoring regardless of whether it's codified as a rule.

### Proposed Changes

Replace each phase reference with an inline description of the underlying activity. The mapping:

- "Phase G.2" → "library bootstrap" (the initial publication of the library with the tool-backed `just check` subset wired up).
- "Phase G.4" → "shared-check migration from livespec-core" (the migration of structural checks from `livespec/dev-tooling/checks/` into `livespec_dev_tooling/checks/`).
- "Phase G.6" → "post-release cross-repo coordination handoff" (the moment the library begins pin-and-bumping itself via its own coordination automation surface).

Per-file edits:

1. `spec.md:43` — Replace "if a second sibling library appears, a follow-up cycle (tracked at livespec work-item `li-huxsg3`) extracts the shared scaffold into a `templates/library/` copier template" with "if a second sibling library appears, a follow-up cycle extracts the shared scaffold into a `templates/library/` copier template" — dropping the work-item ID per the same standalone-readability rationale.

2. `contracts.md:30` — Replace "until livespec epic `li-fgqgnk` Phase G.4 completes the move" with "until the shared structural checks complete migration from livespec-core".

3. `constraints.md:42` — Replace "at Phase G.2 of livespec epic `li-fgqgnk`, `just check` runs only the tool-backed subset (ruff, pyright, pytest); structural checks come online in Phase G.4 as each migrates from livespec." with "at library-bootstrap time, `just check` runs only the tool-backed subset (ruff, pyright, pytest); structural checks come online as each migrates from livespec-core."

4. `non-functional-requirements.md:20` — Replace "The Red → Green commit pair is enforced by the `check-red-green-replay` gate at commit-msg time (once Phase G.4 migrates the gate from livespec)." with "The Red → Green commit pair is enforced by the `check-red-green-replay` gate at commit-msg time (once the gate migrates from livespec-core)."

5. `non-functional-requirements.md:27` — Replace "Architecture contracts MUST be declared in `pyproject.toml` `[tool.importlinter]` once the package gains multi-layer structure in Phase G.4 (parse / validate / io / commands)." with "Architecture contracts MUST be declared in `pyproject.toml` `[tool.importlinter]` once the package gains multi-layer structure (parse / validate / io / commands)."

6. `non-functional-requirements.md:66` — Replace "Once Phase G.4 migrates `assert_never_exhaustiveness.py`, the gate enforces this mechanically." with "Once `assert_never_exhaustiveness.py` migrates from livespec-core, the gate enforces this mechanically."

7. `non-functional-requirements.md:74` — Replace "Once Phase G.4 migrates `no_direct_tool_invocation.py`, the gate enforces this mechanically." with "Once `no_direct_tool_invocation.py` migrates from livespec-core, the gate enforces this mechanically."

Each replacement preserves the temporal-qualifier intent (the spec acknowledges that some shared checks are not yet local) while making the spec readable standalone — no reader needs to look up the meaning of "Phase G.4" to understand "the gate migrates from livespec-core". The phase identifiers remain implicit in the impl-plaintext work-item store as the authoritative tracking, accessible to anyone who needs to know the schedule; they no longer pollute the spec.

This propose-change documents the SPEC change. Implementation work: none. The edits are pure prose substitutions; no code references the phase identifiers.
