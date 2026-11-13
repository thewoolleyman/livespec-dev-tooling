---
topic: a-shared-check-refuses-a
author: claude-opus-5-5
created_at: 2026-11-13T00:55:16Z
---

## Proposal: A shared check refuses a pending proposal that pre-assigns a scenario number

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add a canonical per-commit shared check, `no_unratified_scenario_numbers`. It fails when a pending proposed-change file carries a numbered scenario heading whose number is not already a scenario heading in the same spec tree's ratified `scenarios.md`. So a proposal names a new scenario without a number, and the revise assigns the number when it cuts the version. The check gates on a new UNION role key, `proposed_changes_dirs`. A consumer whose pending proposals still carry pre-assigned numbers declares that key `{ unarmed_until = "<ledger-id>" }`, naming its own open adoption item, until that item's pull request has rewritten them.

### Motivation

Implementation item livespec-dev-tooling-kw5tox, filed on legacy-coordinator-agent's request (session 56ce1bcd, 2026-11-13). The coordinator accepted option (a) for it: proposals carry no scenario number and the revise assigns one at cut time. The item's filing tier is spec-change, unstated against ## Shared check inventory, so it is held for this topic.

Measured cause (the coordinator's grader, over livespec-orchestrator-beads-fabro origin/master and 18 open chore(spec) pull requests, 2026-11-13 ~01:1xZ):

- Scenario 358 is claimed twice: by a pending proposal on master and by orchestrator #5061.
- Scenarios 353, 354 and 355 are each claimed twice among the proposals on master.
- Every number from 345 to 362 is claimed.

A scenario number assigned when a proposal is written is a reservation that nothing serializes. Every revise therefore has to renumber; orchestrator #5105 renumbered 353 to 359. The revise-version queue avoids this because it is order-based and assigns no numbers ahead of time. Scenario numbers can follow the same rule: the number is assigned at the one serialized point, the revise's cut.

The rejected alternative is a check that refuses a number already claimed on the default branch or by another pending proposal. It would have to read every other open pull request from the forge, so it would not be hermetic. Two pull requests opened at the same time would both pass it, and the first to merge would still force the second to renumber.

Fleet scope, counted 2026-11-13 in each primary checkout's `SPECIFICATION/scenarios.md`:

- Six consumers already ratify only the unnumbered `## Scenario: <description>` form, so they pass from the start: livespec-dev-tooling (407 headings), livespec-overseer (552), livespec-runtime (56), livespec-driver-codex (40), livespec-driver-claude (26) and livespec-driver-pi (21).
- Three number their scenarios: livespec-orchestrator-beads-fabro (331 numbered, plus 14 unnumbered), livespec-console-beads-fabro (34) and livespec-orchestrator-git-jsonl (6).
- livespec core's `scenarios.md` has no scenario headings.

The coordinator's ordering rule is adoption first, then arming. The check must not refuse the orchestrator's in-flight proposals that claim 347 to 358: their own revises, or that repository's adoption pull request, renumber them. `unarmed_until` is the existing sanctioned spelling for exactly that: a requirement deliberately switched off pending named, still-open work.

A numbered heading whose number the ratified `scenarios.md` already carries stays legal. Without that exemption, a proposal that edits a ratified numbered scenario would be refused for quoting the heading it edits.

### Proposed Changes

Three edits, plus the revise's co-edit of `tests/heading-coverage.json`.

**1. `SPECIFICATION/contracts.md` §"Shared check inventory".** In the **Shared** bullet's list of style gates, insert `no_unratified_scenario_numbers` after `heading_coverage`, so the list reads `(`claude_md_coverage`, `comment_line_anchors`, `file_lloc`, `heading_coverage`, `no_unratified_scenario_numbers`, `vendor_manifest`, `no_direct_tool_invocation`, `commit_pairs_source_and_test`)`.

Then add this H3 section after `### `no_ambient_environment_loops` check` and before `## Consumer configuration schema`:

> ### `no_unratified_scenario_numbers` check
>
> This is a canonical per-commit check. It lives under `livespec_dev_tooling/checks/`, and every consumer wires it into its `just check` aggregate and its CI matrix per this section.
>
> **A pending proposal names a new scenario without a number. The revise assigns the number.** A scenario number written into a proposal before its revise is a reservation that nothing serializes, so two proposals in flight together can claim the same number. The revise is the one serialized point, so it is where a number is assigned. A consumer whose `scenarios.md` numbers its scenarios gives a new scenario the next free number when its revise cuts the version. Until then the proposal writes the scenario as `Scenario: <description>`.
>
> Invocation: `python -m livespec_dev_tooling.checks.no_unratified_scenario_numbers`. The check gates on the role key `proposed_changes_dirs` (§"Role keys"). It inspects every `.md` file directly inside each declared directory. For each directory, the RATIFIED `scenarios.md` is the file of that name in the directory's parent, the spec root the directory belongs to. A spec root with no `scenarios.md` ratifies no scenario number.
>
> A line of an inspected file is a NUMBERED SCENARIO HEADING when, after one optional leading unified-diff marker (`+`, `-` or a space) and then any run of blockquote markers (`>`) and whitespace are removed, it begins with one to six `#` characters, whitespace, the word `Scenario`, whitespace and a run of decimal digits. Those digits are its number. The prefix rule exists because proposals carry new text as quoted paragraphs and as fenced unified diffs, and a heading inside either is still the heading the revise would write.
>
> The check MUST fail, exiting `4`, on every numbered scenario heading in an inspected file whose number is not the number of a numbered scenario heading in the ratified `scenarios.md`. It MUST name, for each finding, the file, the line number and the heading text. It MUST NOT fail on a numbered scenario heading whose number the ratified `scenarios.md` already carries: a proposal that edits a ratified scenario quotes that scenario's heading. It MUST NOT fail on a scenario number that appears outside a heading, such as a prose reference to `Scenario 239`. It MUST NOT inspect `history/`, so an archived proposal is never re-judged. It MUST exit `0` when no finding remains.
>
> **Arming follows adoption.** A consumer whose pending proposals still carry pre-assigned scenario numbers MUST declare `proposed_changes_dirs = { unarmed_until = "<ledger-id>" }`, naming its own open work item for adopting this check. That item's pull request MUST, in one change, rewrite each pending proposal's unratified numbered scenario heading to the unnumbered form and declare the key populated. A proposal whose own revise lands first is renumbered by that revise, which leaves the adoption pull request less to rewrite. A consumer whose pending proposals carry no unratified numbered scenario heading declares the key populated in the pull request that adopts the release carrying this check.

**2. `SPECIFICATION/contracts.md` §"Role keys".** Add this bullet to the role-key inventory after the `target_dirs` bullet:

> - **`proposed_changes_dirs`** — array of strings. Repo-root-relative paths of the consumer's pending proposed-change directories, one per spec tree, such as `SPECIFICATION/proposed_changes/`. **Consumers:** `no_unratified_scenario_numbers`. It is that check's GATING key. MUST be declared as either a populated array or exactly one of the four declared-absent spellings per §"Declared-absent spellings for the union role keys". `unarmed_until` is the spelling for a consumer whose pending proposals still carry pre-assigned scenario numbers, per that check's §"Arming follows adoption". `not_applicable` is the spelling for a consumer with no spec tree.

In §"Declared-absent spellings for the union role keys", extend the UNION-key enumeration so the sentence reads: The **UNION keys** — `pure_trees`, `target_dirs`, `source_tree_prefixes`, `dataclasses_tree`, `neutral_hook_body_path`, `proposed_changes_dirs` — are those whose declared value IS a consuming check's scan universe.

**3. `SPECIFICATION/scenarios.md`.** Append these scenarios:

> ## Scenario: a pending proposal that pre-assigns an unratified scenario number fails the shared check
>
> Given a consumer that declares `proposed_changes_dirs` populated with its `SPECIFICATION/proposed_changes/` directory
>
> And the ratified `SPECIFICATION/scenarios.md` carries numbered scenario headings up to `Scenario 344`
>
> And a pending proposal in that directory quotes a new heading `## Scenario 358 — <title>`
>
> When the consumer runs `python -m livespec_dev_tooling.checks.no_unratified_scenario_numbers`
>
> Then the check exits `4`
>
> And its finding names the proposal file, the line number and the heading text
>
> ## Scenario: a pending proposal that quotes a ratified numbered scenario or writes a new one unnumbered passes the shared check
>
> Given a consumer that declares `proposed_changes_dirs` populated
>
> And the ratified `scenarios.md` carries `## Scenario 207 — <title>`
>
> And a pending proposal quotes `## Scenario 207 — <amended title>`, refers to `Scenario 239` in prose, and adds `## Scenario: <description>`
>
> When the consumer runs `python -m livespec_dev_tooling.checks.no_unratified_scenario_numbers`
>
> Then the check exits `0`
>
> ## Scenario: a consumer whose pending proposals still carry pre-assigned numbers stays unarmed until its adoption item rewrites them
>
> Given a consumer that declares `proposed_changes_dirs = { unarmed_until = "<ledger-id>" }` naming its own open adoption item
>
> And a pending proposal in its `SPECIFICATION/proposed_changes/` quotes an unratified `## Scenario 358 — <title>`
>
> When the consumer runs `python -m livespec_dev_tooling.checks.no_unratified_scenario_numbers`
>
> Then the check exits `0` and inspects no proposal
>
> When the adoption item's pull request rewrites that heading to `## Scenario: <title>` and declares `proposed_changes_dirs` populated
>
> Then the check exits `0` and inspects every pending proposal

**4. `tests/heading-coverage.json` (the revise's co-edit).** Add one entry per new scenario heading, with `test` set to `TODO` and a reason stating that a real test is owed, citing `livespec-dev-tooling-kw5tox` as its `work_item`. Example reason: "Spec-first: a real test is owed that runs the shared check against a fixture consumer tree in this state. livespec-dev-tooling-kw5tox owns it."
