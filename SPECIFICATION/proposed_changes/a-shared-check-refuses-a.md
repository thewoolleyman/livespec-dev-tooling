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

Add a canonical per-commit shared check, `no_unratified_scenario_numbers`. It fails when a pending proposed-change file carries a numbered scenario heading whose number is not already a scenario heading in the same spec tree's ratified `scenarios.md`. So a proposal names a new scenario without a number, and the revise assigns the number when it cuts the version. The check reads a new OPTIONAL role key, `proposed_changes_dirs`. A consumer that has not declared the key is unarmed, and the check says so on a loud line in its output on every run. Each consumer declares the key when it adopts the check; a consumer whose pending proposals still carry pre-assigned numbers declares it in the pull request that rewrites them.

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

The coordinator's ordering rule is adoption first, then arming. The check must not refuse the orchestrator's in-flight proposals that claim 347 to 358: their own revises, or that repository's adoption pull request, renumber them.

The key is OPTIONAL, on the coordinator's ruling (legacy-coordinator-agent, session 56ce1bcd, 2026-11-13). A REQUIRED key would fail every consumer that has not yet adopted the check at its next pin bump, which arms the check ahead of adoption. That is the failure shape in which one shared release turned five repositories red. Two conditions keep the optional form from staying silently unarmed. First, an undeclared key prints a loud UNARMED line on every run. Second, each consumer's adoption declares the key: the six unnumbered consumers in their bump pull requests, and the numbered ones in their adoption items, in the order livespec-orchestrator-git-jsonl, livespec-console-beads-fabro, livespec-orchestrator-beads-fabro. Making the key required once every fleet consumer has declared it is a separate follow-up, not part of this proposal.

A numbered heading whose number the ratified `scenarios.md` already carries stays legal. Without that exemption, a proposal that edits a ratified numbered scenario would be refused for quoting the heading it edits.

### Proposed Changes

Six edits (1, 2, 3, 5, 6 and 7), plus the revise's co-edit of `tests/heading-coverage.json` (4).

**1. `SPECIFICATION/contracts.md` §"Shared check inventory".** In the **Shared** bullet's list of style gates, insert `no_unratified_scenario_numbers` after `heading_coverage`, so the list reads `(`claude_md_coverage`, `comment_line_anchors`, `file_lloc`, `heading_coverage`, `no_unratified_scenario_numbers`, `vendor_manifest`, `no_direct_tool_invocation`, `commit_pairs_source_and_test`)`.

Then add this H3 section after `### `no_ambient_environment_loops` check` and before `## Consumer configuration schema`:

> ### `no_unratified_scenario_numbers` check
>
> This is a canonical per-commit check. It lives under `livespec_dev_tooling/checks/`, and every consumer wires it into its `just check` aggregate and its CI matrix per this section.
>
> **A pending proposal names a new scenario without a number. The revise assigns the number.** A scenario number written into a proposal before its revise is a reservation that nothing serializes, so two proposals in flight together can claim the same number. The revise is the one serialized point, so it is where a number is assigned. A consumer whose `scenarios.md` numbers its scenarios gives a new scenario the next free number when its revise cuts the version. Until then the proposal writes the scenario as `Scenario: <description>`.
>
> Invocation: `python -m livespec_dev_tooling.checks.no_unratified_scenario_numbers`. The check reads the role key `proposed_changes_dirs` (§"Role keys"). It inspects every `.md` file directly inside each declared directory. For each directory, the RATIFIED `scenarios.md` is the file of that name in the directory's parent, the spec root the directory belongs to. A spec root with no `scenarios.md` ratifies no scenario number.
>
> A line of an inspected file is a NUMBERED SCENARIO HEADING when, after one optional leading unified-diff marker (`+`, `-` or a space) and then any run of blockquote markers (`>`) and whitespace are removed, it begins with one to six `#` characters, whitespace, the word `Scenario`, whitespace and a run of decimal digits. Those digits are its number. The prefix rule exists because proposals carry new text as quoted paragraphs and as fenced unified diffs, and a heading inside either is still the heading the revise would write.
>
> The check MUST fail, exiting `4`, on every numbered scenario heading in an inspected file whose number is not the number of a numbered scenario heading in the ratified `scenarios.md`. It MUST name, for each finding, the file, the line number and the heading text. It MUST NOT fail on a numbered scenario heading whose number the ratified `scenarios.md` already carries: a proposal that edits a ratified scenario quotes that scenario's heading. It MUST NOT fail on a scenario number that appears outside a heading, such as a prose reference to `Scenario 239`. It MUST NOT inspect `history/`, so an archived proposal is never re-judged. It MUST exit `0` when no finding remains.
>
> **Arming follows adoption.** The check is armed for a consumer only once that consumer declares `proposed_changes_dirs`. While the key is undeclared, the check MUST inspect no proposal, MUST exit `0`, and MUST print exactly one line, on standard error, `no_unratified_scenario_numbers UNARMED: <repo> declares no proposed_changes_dirs`, on every run. `<repo>` is the `<owner>/<name>` parsed from the consumer's `origin` remote URL, or the repository root directory's name when there is no `origin` or its URL does not parse. That line is how an unarmed consumer stays visible instead of silently passing.
>
> **A declared key that inspects nothing is a configuration error.** A declared empty array MUST make the check exit `3`, naming the key. A declared path whose spec root, the path's parent directory, does not exist MUST make the check exit `3`, naming that path, so a mistyped path cannot silently disarm the check. A declared directory that exists and holds no `.md` file has no pending proposal, and the check passes it. A consumer whose pending proposals still carry pre-assigned scenario numbers MUST NOT declare the key before those headings are rewritten. Its adoption pull request MUST, in one change, rewrite each pending proposal's unratified numbered scenario heading to the unnumbered form and declare the key. A proposal whose own revise lands first is renumbered by that revise, which leaves the adoption pull request less to rewrite. A consumer whose pending proposals carry no unratified numbered scenario heading declares the key in the pull request that adopts the release carrying this check.

**2. `SPECIFICATION/contracts.md` §"Role keys".** Add this bullet to the role-key inventory after the `target_dirs` bullet:

> - **`proposed_changes_dirs`** — array of strings. Repo-root-relative paths of the consumer's pending proposed-change directories, one per spec tree, such as `SPECIFICATION/proposed_changes/`. **Consumers:** `no_unratified_scenario_numbers`. OPTIONAL. An undeclared key leaves that check unarmed, and the check prints its UNARMED line, per that check's §"Arming follows adoption". A declared key MUST be a non-empty array of paths whose spec roots exist, per that check's "A declared key that inspects nothing is a configuration error" (exit `3`). It is not a member of `UNION_ROLE_KEYS` or `REQUIRED_ROLE_KEYS`, and it takes no declared-absent spelling; see Proposed Change 5.

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
> ## Scenario: a consumer that has not declared proposed_changes_dirs is unarmed and says so, until its adoption pull request declares the key
>
> Given a consumer that does not declare `proposed_changes_dirs`
>
> And a pending proposal in its `SPECIFICATION/proposed_changes/` quotes an unratified `## Scenario 358 — <title>`
>
> When the consumer runs `python -m livespec_dev_tooling.checks.no_unratified_scenario_numbers`
>
> Then the check exits `0` and inspects no proposal
>
> And its output carries the line `no_unratified_scenario_numbers UNARMED: <repo> declares no proposed_changes_dirs`
>
> When the consumer's adoption pull request rewrites that heading to `## Scenario: <title>` and declares `proposed_changes_dirs` with its `SPECIFICATION/proposed_changes/` directory
>
> Then the check exits `0`, inspects every pending proposal, and prints no UNARMED line
>
> ## Scenario: a consumer that declares proposed_changes_dirs empty or names a missing spec root fails as a configuration error
>
> Given a consumer that declares `proposed_changes_dirs = []`
>
> When the consumer runs `python -m livespec_dev_tooling.checks.no_unratified_scenario_numbers`
>
> Then the check exits `3` and names `proposed_changes_dirs`
>
> When the consumer instead declares `proposed_changes_dirs = ["SPECIFICATON/proposed_changes/"]` and no `SPECIFICATON/` directory exists
>
> Then the check exits `3` and names that path

**4. `tests/heading-coverage.json` (the revise's co-edit).** Add one entry per new scenario heading, with `test` set to `TODO`, `work_item` set to `livespec-dev-tooling-kw5tox`, and a reason that names the owed test's tier. Example reason: "Spec-first: a real test at the integration tier or above is owed that runs the shared check as a subprocess against a fixture consumer tree in this state. livespec-dev-tooling-kw5tox owns it."

**5. `SPECIFICATION/contracts.md` §"Role keys" and §"Clean role keys retain `[]`" (the exception this key needs).** At the end of §"Role keys"' paragraph that begins "**UNDECLARED** — the key is absent from the block — is a hard ERROR", add:

> Exception: `proposed_changes_dirs` is an OPTIONAL gating key under the adoption-first ordering rule. Its UNDECLARED state is UNARMED (exit `0` plus that check's one UNARMED line), not an ERROR, and it is not a member of `UNION_ROLE_KEYS` or `REQUIRED_ROLE_KEYS`.

At the end of §"Clean role keys retain `[]`"'s paragraph that begins "**The partition criterion is explicit", add:

> The one exception is `proposed_changes_dirs`: its declared value is its check's scan universe, but it is OPTIONAL, so it is neither a UNION nor a CLEAN key. An empty declaration of it is a configuration error (exit `3`), and an undeclared one is UNARMED, per §"Role keys".

**6. `SPECIFICATION/contracts.md` §"Fleet surface — central conformance and reconcile" (closing the de-arming hole).** An undeclared key is indistinguishable from a deleted one, so add this paragraph after the paragraph that begins "**Vendored-tree pin fidelity":

> **Scenario-number arming (the `proposed-changes-dirs-armed` obligation row).** Until `proposed_changes_dirs` becomes a required key, the assert-mode row MUST list every manifest member whose `pyproject.toml` does not declare `proposed_changes_dirs` as `unarmed`, at warning severity, naming the member. This repository MUST keep a committed adoption list of the members that have declared the key. A member gets onto it in the same change that records its adoption. A member that is on the adoption list and no longer declares the key MUST be an ERROR finding naming the member, because removing the declaration de-arms the check. When this proposal is ratified, the follow-up that makes `proposed_changes_dirs` required, once every member has declared it, MUST be filed as a named work item and cited in the revision record.

**7. `SPECIFICATION/contracts.md` §"`no_unratified_scenario_numbers` check" (rollout), appended to the H3 section of Proposed Change 1:**

> **Rollout.** livespec-dev-tooling declares `proposed_changes_dirs` in the same pull request that ships the check, so this repository is armed from the release that carries it. Every consumer's bump to that release wires `check-no-unratified-scenario-numbers` into its aggregate and CI matrix. Wired with the key undeclared, the check is UNARMED and green, so the bump never reddens a consumer that has not adopted it. livespec core consumes this package like any other consumer. Its `scenarios.md` carries no scenario heading, so its bump pull request wires the check and declares the key in the same change. Each consumer whose ratified scenarios carry no numbers declares the key in its bump pull request. Each consumer whose ratified scenarios carry numbers declares it in its own adoption pull request, after rewriting its pending numbered headings.
