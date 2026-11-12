---
topic: the-flake-retry-plugin-decides
author: claude-opus-5-5 (ci-runtime-and-cost)
created_at: 2026-11-12T05:25:07Z
---

## Proposal: The flake-retry plugin parses each module once per session and decides retry once per test file

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds two sentences to the "Untouched-test retry" bullet of non-functional-requirements.md section "Testing approach". In one pytest session the flake-retry plugin MUST read and parse each test module, each conftest.py and each in-repository imported module at most once, however many test items it collects from them, and every item collected from one test file MUST receive the same retry decision. In a consumer's CI job whose change set names none of the whole-session disabling paths, the plugin's per-session work MUST NOT delay the job's first test result by more than 300 seconds after pytest starts collecting. Adds one scenario to scenarios.md. The bullet has no H2 of its own, so the only new heading is the scenario's.

### Motivation

Plan ci-runtime-and-cost (epic livespec-dev-tooling-ib3oe3) measured on 2026-11-05 (research 005) that the plugin re-derives each test's closure per collected item, re-reading and re-parsing the same modules thousands of times. Each of livespec-orchestrator-beads-fabro's four k3s coverage shards then spends about 300 s or more between its ":: coverage-shard N/4" log line and its first test result, about 20 runner-minutes per pull-request CI run. Work item livespec-dev-tooling-5y3luz fixes it. On 2026-11-12 the dispatcher refused it at spec-change tier on this linked topic (verdict partial, spec v199, orchestrator v0.320.0). The judgement found that the "Untouched-test retry" clause already implies one decision per test file, because a closure is built from the test file, its conftest chain and its import chain. It found nothing about reading or parsing each module at most once per session, and nothing bounding the shard's time to first result. This proposal states both, so the item's Definition of Done grades against ratified text. The touched/untouched rule is unchanged: a per-file decision MUST still follow it item for item.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Testing approach", in the bullet that begins "**Untouched-test retry.**", insert the following two sentences immediately after the sentence that ends "When the plugin cannot determine which paths a closure names, the test MUST be treated as touched.":

In one pytest session the plugin MUST read and parse each test module, each `conftest.py` and each in-repository imported module at most once, however many test items the session collects from them, and every test item collected from the same test file MUST receive the same retry decision, decided by the rule above. In a consumer's CI job whose change set names none of `pyproject.toml`, `uv.lock`, `justfile`, any `conftest.py` or the plugin itself, the plugin's per-session work MUST NOT delay the job's first test result by more than 300 seconds after pytest begins collection.

In SPECIFICATION/scenarios.md, append the following scenario:

## Scenario: the flake-retry plugin parses each module once and gives every item of one test file the same retry decision

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a test file that yields 200 parametrized test items and imports one in-repository module, `helpers.py`

And a run whose change set is computable and touches no module of that test file's closure

When the session collects and runs those items

Then the plugin MUST read and parse the test file, each `conftest.py` on its directory chain and `helpers.py` at most once each

And every one of the 200 items MUST be marked for retry

And when the change set is changed to modify `helpers.py`, every one of the 200 items MUST be treated as touched and MUST NOT be marked for retry

The revise that accepts this proposal MUST add a tests/heading-coverage.json row for the new scenario heading, a spec-first TODO row whose reason names the integration tier or above and whose work_item is livespec-dev-tooling-5y3luz, and MUST register it in tests/heading-coverage-debt.json.
