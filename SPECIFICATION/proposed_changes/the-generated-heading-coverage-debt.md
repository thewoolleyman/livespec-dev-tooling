---
topic: the-generated-heading-coverage-debt
author: claude-opus-5-5
created_at: 2026-11-13T13:37:58Z
---

## Proposal: The heading-coverage debt register is one file per row, so changes to different rows never textually conflict, and a drifted register is refused naming its rows

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

The debt register moves from the single file `tests/heading-coverage-debt.json` to the directory `tests/heading-coverage-debt/`, one file per row. The proposal states four things the ratified text leaves out:

- Changes to different rows never textually conflict under git's default merge, whatever the operation: inserting, removing or rewriting a row.
- Each row's file name is a stable, filesystem-safe encoding of its key, and no two different keys share a name.
- A register that differs from a fresh regeneration is refused, naming each extra, missing, misnamed or differing file by its key.
- A consuming repository adopts the new layout in the same bump commit that adopts the generator, keeping every `first_seen`. A check that still meets the old single file refuses it by name.

### Motivation

livespec-dev-tooling-mpv6bp was refused at dispatch on 2026-11-13 at 13:32:59Z: rc=5, spec-change tier, verdict PARTIAL at v210, linked topic the-generated-heading-coverage-debt. The ratified text, ## Testing approach, ### Scenario-tier coverage, states regeneration and first_seen preservation. It states no layout that merges without conflict, and no refusal that names the differing rows.

The cost is measured. On 2026-11-13 the v209 revise, livespec-dev-tooling#4438, went DIRTY on the register twice and was rebased by hand twice (e989974bc, 50755879f). The revise queue sat behind it, and legacy-coordinator-agent imposed a merge quiet on heading-coverage changes. Every revise inserts rows and every implementation removes them, and both land inside 30-minute delegated push gates.

A single-file layout was measured and rejected. plan/ci-runtime-and-cost/research/010-debt-register-merge-lab-2026-11-13.md records it, with the script and its raw output. Four single-file layouts were tested under `git merge-file`, which is the merge a rebase applies: the current pretty-printed array, and one row per line with one, two or three separator lines. Every one merged cleanly when rewriting two adjacent rows or inserting into different gaps. The current layout already does that. Every one CONFLICTED on these three cases:

- removing two adjacent rows;
- inserting a row beside a row the other branch removes;
- inserting two rows into the same gap.

Adjacent removals cannot be fixed by any single-file layout. Git's diff gives each deleted separator to the same side of both removed rows, so the two deletions always touch. Those are the conflict classes the revise queue actually hits.

The lab ran `git merge-file`, which does no rename detection. A real rebase does, and with many small, similar files it can pair one row's removal with another's insertion. That is why the clause names the check, not the merge, as the guarantee that the register is right after a rebase.

One file per row removes them, because changes to different rows touch different files. A custom merge driver cannot do this: GitHub's mergeability check and its server-side rebase-merge run no `.gitattributes` merge driver, so a pull request would still read DIRTY.

The register stays committed rather than derived at check time. first_seen is state the register carries forward, not a pure function of the tree.

The file-name encoding has to be stable, safe as a file name, and injective. A readable slug alone is not injective: two headings that differ only in punctuation slug alike. Percent-encoding the whole key would be injective, but long headings would exceed the 255-byte file-name limit. So the name is a truncated slug plus a key hash. The generator refuses to write a register in which two keys would share a name, which makes "no two keys share a file" a guarantee rather than a probability.

Adoption order follows CLAUDE.md, "Ordering — confirm the reader before you write": the refusal must not reach a consumer whose register is still a single file. Since the-bump-pin-reconcile-inserts (livespec-dev-tooling#4524), the bump commit that `reusable-bump-pin-from-dispatch.yml` makes already reconciles the consumer's canonical wiring. The regeneration rides in that same commit.

FLEET SCOPE: the ten repositories that track a register, measured 2026-11-13. They are livespec-dev-tooling, livespec, livespec-orchestrator-beads-fabro, livespec-overseer, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec-runtime, livespec-console-beads-fabro and livespec-orchestrator-git-jsonl. The generator and the check ship from livespec-dev-tooling, so each consumer adopts through its pin bump with no code of its own.

Carrier: livespec-dev-tooling-mpv6bp (plan ci-runtime-and-cost, epic livespec-dev-tooling-ib3oe3). Its Definition of Done is re-worded to this text after ratification. legacy-coordinator-agent ruled option (b) on 2026-11-13 and approves mpv6bp once this ratifies.

### Proposed Changes

Edits to SPECIFICATION/non-functional-requirements.md, `## Testing approach`, `### Scenario-tier coverage`:

1. In the bullet that begins "Every `TODO` row MUST appear in the repository's heading-coverage debt register", replace the parenthesis "(`tests/heading-coverage-debt.json`, keyed by `(spec_root, spec_file, heading)` with the owning `work_item` and `first_seen` date)" with "(the directory `tests/heading-coverage-debt/`, one file per row keyed by `(spec_root, spec_file, heading)` with the owning `work_item` and `first_seen` date, laid out as the next two bullets state)". Nothing else in that bullet changes.

2. Directly after that bullet, insert these two bullets:

- The register MUST hold one file per row in `tests/heading-coverage-debt/` and nothing else. An absent `tests/heading-coverage-debt/` and an empty one are the same empty register, because git tracks no empty directory: the generator MUST write no placeholder for it, and the check MUST treat the two alike. Each file is a JSON object carrying the row's `spec_root`, `spec_file`, `heading`, `work_item` and `first_seen`. Its name is a function of the key alone: `<slug>--<hash>.json`. `<slug>` is `<spec_file>-<heading>` lower-cased, with every run of characters outside `[a-z0-9]` replaced by one `-`, leading and trailing `-` stripped, and truncated to 80 characters. `<hash>` is the first 16 lower-case hex digits of the SHA-256 of the UTF-8 JSON array `[spec_root, spec_file, heading]`, serialized with no whitespace and no ASCII escaping. The generator MUST refuse to write a register in which two different keys would share a file name, naming both keys, so no two keys ever map to one file. Because each row is its own file, two branches from one base that each change a different row — inserting, removing or rewriting it, including rows adjacent in sort order — and each regenerate the register MUST rebase onto one another with no textual conflict in `tests/heading-coverage-debt/` under git's default merge, with no custom merge driver configured. After that rebase the directory MUST equal a fresh mechanical regeneration of the rebased tree, with every surviving row's `first_seen` unchanged. Two branches that change the SAME row, including one that removes a row the other rewrites, MAY conflict on its file. Git's rename detection MAY also pair one row's removal with another row's insertion and carry the other branch's edit onto the wrong file without a conflict. A clean rebase is therefore never itself evidence that the register is right: the debt-register check below MUST refuse any such mis-merge as a misnamed or differing file. Either outcome MUST be resolved by regenerating the register on the rebased tree, never by hand-editing a file.
- A committed register that differs from a fresh mechanical regeneration of the same tree MUST be refused by the heading-coverage debt-register check. Each file that parses as a JSON object carrying the five fields is judged by the key its content names, and each finding is reported once, in this order of precedence. The refusal MUST name, by its `(spec_root, spec_file, heading)` key:
  - each misnamed file, whose name is not its own key's encoding, reported only as misnamed and never also as extra or missing;
  - each extra file, whose key regeneration would not write;
  - each missing file, a key regeneration would write that no file in the directory carries;
  - each differing file, whose key regeneration writes with a different field, together with the field that differs.
  Every other entry in the directory, including a file that is not valid JSON, a JSON value missing a field, and a name not ending in `.json`, MUST be named by its path. That is the same verdict a hand edit earns, because the register is generated, never authored. The adoption order below means the check does not meet a register still in the old layout. Should it meet one, a `tests/heading-coverage-debt.json` with no `tests/heading-coverage-debt/` beside it, it MUST refuse, naming the legacy single-file register. Every comparison with `HEAD` that the ratified clauses make, including `first_seen` preservation and the rule that the register only shrinks, MUST read the single-file layout when that is what `HEAD` holds, so the converting commit keeps every surviving row's `first_seen`. The bump commit that `reusable-bump-pin-from-dispatch.yml` makes to adopt a livespec-dev-tooling release carrying this layout MUST regenerate that repository's register, and remove its `tests/heading-coverage-debt.json`, in that same commit. In livespec-dev-tooling, which ships the generator and the check and so has no such bump, the change that introduces this layout MUST regenerate its own register in that same change.

Edits to SPECIFICATION/scenarios.md. No existing `## ` heading changes.

3. In "## Scenario: a new heading-coverage TODO row absent from the debt register fails the authoring-time armed tier", replace "that is not present in the repository's `tests/heading-coverage-debt.json` register" with "that is not present in the repository's `tests/heading-coverage-debt/` register".

4. In "## Scenario: resolving a heading-coverage TODO to a real test requires removing its debt-register entry", replace "When the staged change also removes that row from `tests/heading-coverage-debt.json`" with "When the staged change also removes that row's file from `tests/heading-coverage-debt/`".

5. In "## Scenario: the heading-coverage debt register regenerates from the live registry and matches byte-for-byte", make two replacements:
   - Replace "Then the generated `tests/heading-coverage-debt.json` matches the expected register byte-for-byte" with "Then the generated `tests/heading-coverage-debt/` directory matches the expected register file for file, byte-for-byte".
   - Replace "And regenerating it a second time MUST produce an identical file, never a hand-authored drift" with "And regenerating it a second time MUST produce an identical directory, never a hand-authored drift".

6. Directly after "## Scenario: the heading-coverage debt register regenerates from the live registry and matches byte-for-byte", insert these four scenarios:

## Scenario: two branches that change different heading-coverage debt-register rows rebase without a textual conflict

Given two branches from one base, each of which changes a different `test: "TODO"` heading-coverage row and regenerates `tests/heading-coverage-debt/`

And the two changes are any pair of: inserting a row, removing a row, or rewriting a row, including two rows adjacent in the register's sort order

When the second branch is rebased onto the first under git's default merge with no custom merge driver configured

Then the rebase MUST complete with no textual conflict in `tests/heading-coverage-debt/`

And the rebased register MUST equal a fresh mechanical regeneration of the rebased tree, with every surviving row's `first_seen` unchanged

But when the two branches change the same row, the rebase MAY stop on a conflict in that row's file, and regenerating the register on the rebased tree MUST resolve it

## Scenario: two different heading-coverage debt keys never share a register file name

Given two keys that differ only in punctuation, so their slugs are equal

When the debt register is generated

Then each key MUST be written to its own file, whose name is its slug followed by its own key hash

And a key whose slug is longer than 80 characters MUST be written to a file whose slug part is that slug's first 80 characters, followed by the key's own hash

And when two different keys would encode to the same file name, the generator MUST refuse to write the register, naming both keys

## Scenario: a debt register that differs from its regeneration is refused naming each differing row

Given a committed `tests/heading-coverage-debt/` that has one extra file, lacks one file that regeneration would write, holds one file whose name is not its key's encoding, and holds one file whose `work_item` differs from regeneration

When the heading-coverage debt-register check runs

Then it MUST refuse, naming the extra, missing and misnamed files by their keys and the differing file by its key and the field `work_item`

And the misnamed file MUST be named only as misnamed, never also as an extra or a missing file

And when the directory also holds a file that is not valid JSON and a file not ending in `.json`, the refusal MUST name each of them by its path

And when the repository holds only the legacy single file `tests/heading-coverage-debt.json`, the check MUST refuse, naming the legacy single-file register

## Scenario: a repository adopting the per-row heading-coverage debt register converts it in one commit and keeps every first_seen

Given a repository whose committed register is the single file `tests/heading-coverage-debt.json` holding rows with past `first_seen` dates

When the commit that adopts this layout regenerates the register, through the bump commit that `reusable-bump-pin-from-dispatch.yml` makes or, in livespec-dev-tooling, the change that introduces the layout

Then that one commit MUST add `tests/heading-coverage-debt/` with one file per row and remove `tests/heading-coverage-debt.json`

And every row's file MUST carry the `first_seen` its row held in the single file at `HEAD`

And the heading-coverage debt-register check MUST pass on that commit

Heading-coverage rider, for the revise commit (not `resulting_files[]`):

- Add a `tests/heading-coverage.json` row for each of the four new scenario headings.
- Each row carries `"test": "TODO"`, `"work_item": "livespec-dev-tooling-mpv6bp"`, and a reason naming the consumer tier (`tests.consumer`, this repository's `scenario_tiers`) and mpv6bp as the owner.
- Then run `just generate-heading-coverage-debt-register` and stage what it writes.
- The register is still the single file at the time this revise lands, because mpv6bp changes the layout.
