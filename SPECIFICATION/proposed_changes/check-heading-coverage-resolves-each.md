---
topic: check-heading-coverage-resolves-each
author: claude-opus-5-5
created_at: 2026-11-08T04:22:52Z
---

## Proposal: A heading-coverage row must name a test that exists, and the check resolves every mapped test reference

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a "Mapped tests exist" requirement to §"Testing approach": `heading_coverage` resolves each test reference a non-TODO `tests/heading-coverage.json` row carries against the repository's tree, in every reference shape the fleet's registries use, and fails on a reference whose file is absent or whose named test the file does not define. A mapped file it cannot read or parse is reported as unresolved, distinct from an absent test, and also fails. Add one scenario exercising it. The release that first carries this direction follows the adoption order this repository already applies: it is tagged only after every consumer whose registry the direction would fail has repaired its rows.

### Motivation

Held work item livespec-dev-tooling-rglvm7, filed 2026-11-08 by plan spec-implementation-lockstep (livespec-orchestrator-beads-fabro epic bd-ib-ax3rds) on legacy-coordinator-agent's R301 ruling. Its spec-change tier record reads classification feature, verdict unstated, generalization target ## Testing approach, linked topic check-heading-coverage-resolves-each. The ratified text requires every scenario heading to have a coverage entry, and a TODO entry to converge mechanically, but says nothing about whether a non-TODO entry's test exists. So a row naming a deleted or renamed test reads as covered: a false green. Measured on origin default branches on 2026-11-08: livespec has 6 such references (for example `tests.bin.test_bootstrap.test_bootstrap_passes_on_current_version`, which `tests/bin/test_bootstrap.py` no longer defines), livespec-orchestrator-beads-fabro has 6, and livespec-overseer has 11. Nine other members have none. History: resolution landed in 29a49c05 (v1.52.13) for livespec-dev-tooling-8t0i and -r3ib. livespec-dev-tooling-jel7 reverted it on 2026-09-07 because it was armed ahead of adoption and reddened those same three consumers' pin bumps. The check's docstring says re-landing it behind adoption 'is tracked separately', yet no open item tracked it, so the rows -r3ib cited are still dangling two months later. The three consumer repairs are filed: livespec-qke72f, bd-ib-5a222e and overseer-lx5l7i. The reference shapes listed are the ones the fleet's registries actually use, taken from the same sweep: dolt-server maps shell test paths, livespec-console-beads-fabro maps Rust file::fn and src/lib.rs::tests::fn paths and a plural `tests` array, livespec-driver-pi maps a dotted id naming a hyphenated TypeScript test file, and homelab and livespec-orchestrator-beads-fabro use dotted modules followed by `::`. The direction is not a lever: per -jel7 it must not return as a flag, env var or severity knob, which is why the adoption order is stated as a release precondition rather than a setting.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, §"Testing approach", insert one new bullet immediately after the bullet that begins "- **Coverage gate.**":

> - **Mapped tests exist.** A non-`TODO` row of a repository's `tests/heading-coverage.json` MUST name a test that exists in that repository. `heading_coverage` MUST resolve every test reference a row carries against the repository's tree: a dotted Python id, a dotted module followed by `::` names, or a file path optionally followed by `::` names. A name after the file is a Python `def` or `class`, a Rust `fn` or `mod`, or a TypeScript test title, and a dotted id MAY name a test file whose stem spells `_` as `-`. A row MAY carry several references, as a `tests` array or separated by `,` or `;`. A reference whose file is absent, or whose named test that file does not define, MUST fail the check, naming the row's heading and the reference. A mapped file the check cannot read or parse MUST be reported as unresolved, distinct from an absent test, and MUST also fail. This direction MUST NOT be configurable by any flag, environment variable or severity setting. The first release that carries it MUST be tagged only after every consumer whose registry it would fail has repaired its rows, so no consumer's pin bump to that release fails `heading_coverage`.

In SPECIFICATION/scenarios.md, insert a new scenario immediately before the heading `## Scenario: a heading-coverage TODO reason asserting non-testability is rejected while one acknowledging an owed test passes`:

```markdown
## Scenario: a heading-coverage row naming a test that no longer exists fails, while one naming an existing test in any fleet reference shape passes

Given a non-`TODO` heading-coverage row whose test reference names a test file that is absent, or a test function, class, Rust `fn` or TypeScript test title that its file does not define

When `heading_coverage` evaluates the row

Then the check fails, naming the row's heading and the unresolved reference

But given rows whose references name existing tests as a dotted Python id, a dotted module followed by `::` names, a file path followed by `::` names, a `tests` array, and a `,`-separated list

Then the check passes each of those rows

And given a row whose mapped file exists but cannot be parsed

Then the check reports that reference as unresolved, distinct from an absent test, and fails
```

The new scenario adds one `## ` heading to scenarios.md. The revise that ratifies this proposal MUST add its `tests/heading-coverage.json` entry in the same change: a spec-first `TODO` whose `reason` acknowledges an owed integration-tier test, owned by livespec-dev-tooling-rglvm7, with its row in `tests/heading-coverage-debt.json`.
