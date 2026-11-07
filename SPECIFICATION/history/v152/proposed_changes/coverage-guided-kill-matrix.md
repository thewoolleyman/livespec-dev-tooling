---
topic: coverage-guided-kill-matrix
author: claude-opus-5-5
created_at: 2026-11-07T17:23:32Z
---

## Proposal: Rule-26 kill matrix: coverage-guided test selection

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Revise two bullets of contracts.md section 'Rule-26 mutation kill matrix' and add one scenario. The Mutants-and-attribution bullet changes from running every test against every mutant to COVERAGE-GUIDED selection: each mutant is run against the tests whose per-test coverage executes its mutated location. A test that does not execute that location is recorded as not killing the mutant, without being run against it. A test whose coverage cannot be measured is run against every mutant. The Report-format bullet gains the test-selection method, so a reader can tell how the matrix was built.

### Motivation

Plan fleet-mutation-testing-rule-26 (epic livespec-dev-tooling-oi2two) must produce a real kill-matrix report for every fleet repository (plan assertions A1 and A4). The shipped engine (livespec-dev-tooling-wou75w, closed 2026-11-07) runs one pytest process per test per mutant, and that cannot finish at fleet scale: about 5,500 livespec-dev-tooling tests times 1,000+ mutants at about 0.5 s each is roughly a month, and livespec-orchestrator-beads-fabro's 11.7k tests are worse. The maintainer ruled on 2026-11-07, attended, recorded as a scope event on the epic, that the matrix is coverage-guided. A test that never executes a line cannot observe a mutation of that line, so restricting each mutant to the tests that cover it keeps the kill matrix, the surviving mutants and the redundancy candidates, at a small fraction of the cost. The fallback for unmeasurable coverage keeps the rule conservative: a test is never assumed unable to kill a mutant without evidence. The selection method is reported so the artefact states how it was built.

### Proposed Changes

In `SPECIFICATION/contracts.md` section 'Rule-26 mutation kill matrix', replace the **Mutants and attribution.** bullet with:

- **Mutants and attribution.** The engine MUST generate mutants of the adopting repository's first-party code. For every generated mutant, it MUST run each test whose per-test coverage executes that mutant's mutated location, and it MUST record the identity of every such test that killed the mutant. A test whose per-test coverage does not execute a mutant's mutated location MUST be recorded as not killing that mutant, without being run against it. A test whose per-test coverage the engine cannot measure MUST be run against every generated mutant. A run that generates zero mutants MUST exit non-zero with a finding naming the empty mutant set, and MUST NOT write a report that reads as a clean result. On the Python path the engine MUST use the fleet-pinned mutmut. Other ecosystems MAY use a language-appropriate engine, such as cargo-mutants for Rust, provided they produce the report format below.

In the same section, in the **Report format.** bullet, replace 'It MUST carry: the engine and its version;' with 'It MUST carry: the engine and its version; the test-selection method used to pair tests with mutants;' and leave the rest of the bullet unchanged.

Add the following scenario to the end of `SPECIFICATION/scenarios.md`:

## Scenario: a coverage-guided kill-matrix run skips tests that do not execute a mutant

Given a Python package with functions F and G, where test T1 executes only F and test T2 executes only G

When `just mutation-kill-matrix` runs over that package

Then each mutant of F MUST be run against T1 and MUST NOT be run against T2

And each mutant of G MUST be run against T2 and MUST NOT be run against T1

And the report MUST name the test-selection method it used
