---
topic: a-test-loop-statement-over
author: claude-opus-5-5 (fleet-flaky-tests)
created_at: 2026-11-08T23:59:28Z
---

## Proposal: A test file must not loop over os.environ, so its coverage is the same on every host

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an "Environment-independent test coverage" bullet to §"Testing approach": a test file MUST NOT contain a for statement over os.environ, whose body's coverage depends on the host, and filters ambient variables in a single expression statement instead. Add a contract section for the shared check no_ambient_environment_loops at the end of §"Shared check inventory": what it walks and reads, its findings, no exemption, its wiring consequence, and its release order. List it among the test-infrastructure gates, and add one scenario exercising it on two hosts.

### Motivation

Held work item livespec-dev-tooling-dpkz32, filed 2026-11-08 by plan fleet-flaky-tests (epic livespec-dev-tooling-zwveqp) at legacy-coordinator-agent's request. Its spec-change tier record reads classification feature, verdict unstated, generalization target ## Shared check inventory, linked topic a-test-loop-statement-over, spec v161. The ratified Coverage gate holds every first-party file to 100% line and branch coverage, and says nothing about coverage that depends on the host environment.

Measured by sandbox-commit-gate-ceiling on livespec-dev-tooling-jd4qle. On the same tree, 53b2106167c9, check-per-file-coverage read tests/livespec_dev_tooling/test_pre_commit_delegate.py as 249 statements with 0 missed in the factory sandbox, and as 249 with 1 missed (line 511) in PR CI run 42535463884. Line 511 is a monkeypatch.delenv inside a for statement over the ambient GIT_* variables. The factory gate passed and CI failed, which costs a full factory run each time. A single expression statement does not have the flaw: coverage counts it under its first line, and that line runs whatever the environment holds.

Sweep of the local primary checkouts on 2026-11-08, an AST walk of tests/ for for statements whose iterable reads environ:
- livespec-dev-tooling has 5: tests/consumer/test_green_token_purity_memoization.py:408, tests/livespec_dev_tooling/checks/test_local_memory_drift_audit.py:51, tests/livespec_dev_tooling/test_green_token.py:105, tests/livespec_dev_tooling/test_incident_hook_entry_edges.py:54 and tests/livespec_dev_tooling/test_tdd_commit.py:122.
- livespec-orchestrator-beads-fabro has 3: tests/bin/test_bootstrap_unattended_marker_forwarding.py:182, tests/conftest.py:578 and tests/integration/test_incident_provenance_receipts.py:349.
- livespec-overseer has 1: tests/test_check_coverage_reuse_token.py:40.
- Twenty-three other clones have none.

Why there is no exemption: legacy-coordinator-agent ruled that an unconditioned coverage pragma is an agent-writable carve-out from a coverage gate, which the jd4qle rider forbids, and the rewrite is always available. Why a static check rather than a fixture that resets GIT_* first: the fixture fixes only the variables it names, and its own loop has the same flaw. Why the import-alias and same-scope binding forms are covered: copying the environment first is the obvious way to dodge a name-only rule, and it keeps the host dependence. Why adoption comes first: a module under checks/ is a canonical slug, which obliges every consumer to wire it, and a check armed before the repositories it judges have adopted the shape turned five repositories red in 46c5dab, reverted in f4247110.

An independent sonnet doctor pass on the first draft (2026-11-09 00:01:15Z, no blockers) shaped this text: a contract section beside the codex_hook_reconcilable precedent, the alias coverage, "single expression statement" in place of "one line", and a negated MAY restated as MUST.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, §"Testing approach", insert one new bullet immediately after the bullet that begins "- **Coverage gate.**":

> - **Environment-independent test coverage.** A Python file under the repository's test tree MUST NOT contain a `for` or `async for` statement whose iterable reads `os.environ`. Such a loop runs its body only when the host process carries a matching variable, so the file's coverage would depend on the host. A test that filters or removes ambient variables MUST do it in a single expression statement, such as a comprehension, whose coverage is the same in every environment. The shared check `no_ambient_environment_loops` (§"`no_ambient_environment_loops` check" in contracts.md) enforces this.

In SPECIFICATION/contracts.md, §"Shared check inventory":

1. In the **Shared** bullet's list of test-infrastructure gates, insert `no_ambient_environment_loops` immediately after `per_file_coverage`.
2. Insert the following subsection at the end of the section, immediately before the heading `## Consumer configuration schema`:

```markdown
### `no_ambient_environment_loops` check

Invocation: `python -m livespec_dev_tooling.checks.no_ambient_environment_loops`, wired as the `check-no-ambient-environment-loops` recipe. Exit `0` on pass, exit `4` with structured stderr findings on fail.

The check walks every `.py` file under the consumer's `tests_tree_prefix` (default `"tests/"`) and MUST fail on each `for` or `async for` statement whose iterable reads `os.environ`. That covers a read written directly, through an import alias (`import os as o`, `from os import environ`), or through a name bound in the same function or module scope from `os.environ`, `os.environ.copy()` or `dict(os.environ)`. Other indirection is out of scope. Each finding MUST name the file, the statement's line, and a single-expression rewrite. The check MUST read source statically and perform no network I/O, so its verdict is the same in the factory sandbox, on a developer host and in CI. It does not distinguish a loop whose body always runs, because the rewrite is always available. No coverage pragma, marker, flag, environment variable or severity setting is an exemption, and the check MUST ignore all of them.

This is a canonical per-commit check under `livespec_dev_tooling/checks/`. Once a consumer's library pin reaches the release that ships this module, that consumer's `check-aggregate-completeness` and the fleet-conformance row `canonical-check-slugs-wired` MUST report the slug as unwired until the consumer either wires `check-no-ambient-environment-loops` or declares a reasoned waiver under §"Shared check inventory" **Canonical-check waivers**. Release order: the first release that ships the module MUST be tagged only after every consumer whose tree it would fail has rewritten its loops, so no consumer's pin bump to that release fails the check itself.
```

The `tests_tree_prefix` role key's **Consumers** clause is NOT edited by the revise. Those clauses are derived from code, and `tests/spec/test_role_key_consumer_inventory.py` fails on any clause that names a check the code does not yet contain. The implementation of livespec-dev-tooling-dpkz32 adds `no_ambient_environment_loops` to that clause in the same change that adds the module.

In SPECIFICATION/scenarios.md, insert a new scenario immediately before the heading `## Scenario: the whole-suite coverage run prints its thirty slowest test phases`:

```markdown
## Scenario: a test loop over os.environ fails the ambient-environment check on every host, while a single-expression rewrite passes

Given a Python file under the declared `tests_tree_prefix` containing `for name in [n for n in os.environ if n.startswith("GIT_")]:` with `monkeypatch.delenv(name)` on the next line

When `no_ambient_environment_loops` runs, on a host whose environment carries a `GIT_` variable and on a host whose environment carries none

Then the check fails on both hosts, naming the file, the loop's line and a single-expression rewrite

And a `# pragma: no cover` comment on the loop's body line does not change that verdict

And the same loop written over a name bound from `dict(os.environ)` also fails

But given the same filtering written as one expression statement, such as `_ = [monkeypatch.delenv(n) for n in os.environ if n.startswith("GIT_")]`

Then the check passes that file on both hosts
```

The new scenario adds one `## ` heading to scenarios.md, and the new contracts.md subsection adds none. The revise that ratifies this proposal MUST add the scenario's `tests/heading-coverage.json` entry in the same change: a spec-first `TODO` whose `reason` acknowledges an owed integration-tier test, with `"work_item": "livespec-dev-tooling-dpkz32"`. Its row goes in `tests/heading-coverage-debt.json`, regenerated with `just generate-heading-coverage-debt-register`.
