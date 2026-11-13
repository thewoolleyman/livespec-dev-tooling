---
topic: the-generated-heading-coverage-debt
author: claude-opus-5-5
created_at: 2026-11-13T13:37:58Z
---

## Proposal: The generated heading-coverage debt register merges without textual conflict and a drifted copy is refused naming its rows

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

State two properties of the generated heading-coverage debt register that the ratified text leaves out. First, its on-disk layout merges with no textual conflict under git's default merge when two branches change different rows, including rows adjacent in sort order. Second, a committed register that differs from a fresh regeneration is refused, and the refusal names the differing rows.

### Motivation

livespec-dev-tooling-mpv6bp was refused at dispatch on 2026-11-13 at 13:32:59Z (rc=5, spec-change tier, verdict PARTIAL at v210, linked topic the-generated-heading-coverage-debt). The judgement: ## Testing approach, Scenario-tier coverage, states regeneration and first_seen preservation, but it states no register layout that rebases without a textual conflict under git's default merge. It also does not visibly state that a refusal names the differing rows. This proposal adds exactly those two properties.

The cost is measured. On 2026-11-13 the v209 revise, livespec-dev-tooling#4438, went DIRTY on tests/heading-coverage{,-debt}.json after master's 5a9f33e66 and was rebased by hand (e989974bc). During that push's 30-minute gate, master's 6d391ffb6 made it DIRTY again, this time on the debt register ALONE (heading-coverage.json auto-merged). It was rebased by hand a second time (50755879f). The revise queue sat behind that one PR, and the coordinator imposed a merge quiet on heading-coverage changes. The cause is the layout. The register is a sorted, pretty-printed JSON array of about 229 rows, 7 lines each, written by `json.dumps(rows, indent=2)`. Two changes to rows adjacent in sort order overlap in git's merge context, so a file the spec already calls GENERATED still merges as hand-authored text.

The clause states the property rather than the bytes, because the generator owns the layout. It does name the one remedy that cannot satisfy it: GitHub's mergeability check and its server-side rebase-merge do not run custom .gitattributes merge drivers. A regenerate-on-merge driver would fix only local rebases, and the PR would still read DIRTY. The path is fixed by the existing clause, so this is a layout change inside the file and needs no new path. first_seen is state the register carries forward, which is why the file is still committed rather than derived at check time.

The refusal half closes a gap the current check does not cover. heading_coverage_debt_register refuses unregistered, stale, grown and schema-incomplete rows, and first_seen moved later. Nothing refuses a register whose rows or bytes differ from what the generator would write. Once the layout carries merge-relevant structure, that comparison is the guard that keeps a hand-resolved conflict from landing. Naming the differing rows tells the author what to regenerate.

Fleet scope: the generator ships from livespec-dev-tooling (livespec_dev_tooling/heading_coverage_debt.py). The fix lands once and reaches each of the ten repositories that track a register through its pin bump plus one regeneration.

Carrier: livespec-dev-tooling-mpv6bp (plan ci-runtime-and-cost, epic livespec-dev-tooling-ib3oe3). legacy-coordinator-agent approves it once this ratifies.

### Proposed Changes

Two edits, landed together in one revise.

1. `SPECIFICATION/non-functional-requirements.md`, `## Testing approach`, `### Scenario-tier coverage`: insert the two bullets below directly after the existing bullet that ends "The register MUST be generated mechanically, never authored by hand." No existing bullet is reworded.

- The register's committed layout MUST merge as data rather than as entangled text. When two branches from one base each change a different register row — adding, removing or rewriting it, including two rows adjacent in the register's sort order — and each regenerates the register, the second branch MUST rebase onto the first with no textual conflict in `tests/heading-coverage-debt.json` under git's default merge with no custom merge driver configured. After that rebase the file MUST equal a fresh mechanical regeneration of the rebased tree, with every surviving row's `first_seen` unchanged. The generator chooses the layout. One layout that satisfies this puts each row on its own line in the stable sort order, separates adjacent rows with a line that no row change rewrites, and gives no row a separator or trailing comma that its neighbour's change must also rewrite. The path stays `tests/heading-coverage-debt.json` and the file stays valid JSON carrying the same rows. A remedy that only a local merge driver or a post-merge regeneration applies does NOT satisfy this clause, because the forge's mergeability check and its server-side rebase-merge run neither.
- A committed register that differs from a fresh mechanical regeneration of the same tree MUST be refused by the heading-coverage debt-register check. The refusal MUST name each differing row by its `(spec_root, spec_file, heading)` key together with the field that differs, and a row present on only one side MUST be named with the side that carries it. When every row agrees and only the bytes differ, the refusal MUST say the register is not in the generated layout. That is the same verdict a hand edit earns, because the register is generated, never authored.

2. `SPECIFICATION/scenarios.md`: add the scenario below directly after `## Scenario: the heading-coverage debt register regenerates from the live registry and matches byte-for-byte`.

## Scenario: two branches that change adjacent heading-coverage debt-register rows rebase without a textual conflict

Given two branches from one base, each of which changes a different `test: "TODO"` heading-coverage row whose register entries are adjacent in the register's sort order, and each of which regenerates `tests/heading-coverage-debt.json`

When the second branch is rebased onto the first under git's default merge with no custom merge driver configured

Then the rebase MUST complete with no textual conflict in `tests/heading-coverage-debt.json`

And the rebased register MUST equal a fresh mechanical regeneration of the rebased tree, with every surviving row's `first_seen` unchanged

And when a register that differs from that regeneration is committed instead, the heading-coverage debt-register check MUST refuse it, naming each differing row by its `(spec_root, spec_file, heading)` key

Heading-coverage rider, for the revise commit (not `resulting_files[]`): add a `tests/heading-coverage.json` row for the new scenario heading with `"test": "TODO"`, `"work_item": "livespec-dev-tooling-mpv6bp"`, and a `reason` that reads "A real test at the integration tier or above is owed for this heading: two real git branches rebased under the default merge, plus the check's refusal of a drifted register. livespec-dev-tooling-mpv6bp owns it." Then regenerate `tests/heading-coverage-debt.json` with `just generate-heading-coverage-debt-register` and stage it.

