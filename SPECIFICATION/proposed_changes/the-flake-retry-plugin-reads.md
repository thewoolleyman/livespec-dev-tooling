---
topic: the-flake-retry-plugin-reads
author: claude-opus-5-5 (fleet-flaky-tests)
created_at: 2026-11-12T08:40:11Z
---

## Proposal: A single-segment string literal names a repository directory only in a path position

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds sentences to the "Untouched-test retry" bullet of non-functional-requirements.md section "Testing approach". A string literal that is a single path segment (no `/` and an empty `PurePosixPath` suffix, so `config`, `.github` and `Dockerfile` are single segments while `x.sh` is not) MUST NOT name a repository path unless it stands in a path position. The positions are: the base or a segment of a path expression, a pathlib constructor or `joinpath` argument, an `os.path.join` argument, the path argument of `open`, or a `cwd` keyword value, judged from the literal's immediate syntax. A literal bound by assignment to a name in such a position counts as standing there. Standing in a path position is necessary, not sufficient: the existing join, base and proper-ancestor rules still decide what the literal names. A literal that is an element of a list, tuple or set display, or an argument of any other resolvable call, such as the git subcommand `"config"`, does not stand in a path position. An argument of a call whose callee the plugin cannot resolve is treated as standing in one, because undeterminable means touched. Literals carrying a `/` or a non-empty suffix and the dotted-module-name rule are unchanged. Adds one scenario to scenarios.md, and its heading-coverage row is directed. Fleet scope: every repository that loads this library's flake-retry plugin.

### Motivation

Work item livespec-dev-tooling-d4siza (plan fleet-flaky-tests, epic livespec-dev-tooling-zwveqp). On 2026-11-12 livespec-dev-tooling#4275 changed `config/incident-fleet-evidence.json`. In CI run 43172130930 the flaky test `tests/livespec_dev_tooling/checks/test_red_green_replay_suite_runner.py::test_interactive_collection_and_worker_startup_output_renews_the_stall_window` failed and was NOT retried in place, so a flake the retry exists to absorb turned the expedited-incident-response-flag plan's critical-path PR red. The plugin read the test as touched because three modules of its closure carry the literal `"config"` as a git subcommand word: directly in a subprocess argument list at `gate_outcome_telemetry.py:262`, and as an element of a list argument of the helper call `git_text(args=["config", "--get", "remote.origin.url"])` at `incident_hook_process.py:195` and `incident_trusted_origin.py:43`. Under today's ratified text that withholding CONFORMS. "The closure names a path either as one string literal ...", so the literal `"config"` names the directory `config/`, and a changed path touches a test when it "lies inside a directory the closure names". So the fix is a spec change, not a conformance fix: legacy-coordinator-agent held d4siza at spec-change tier on this linked topic (ruling of 2026-11-12 ~08:3xZ). Any short common word that is also a top-level directory or extensionless file name in a consuming repository is exposed the same way, for example `config`, `docs`, `scripts`, `tests` or `ansible`. This is the top-level-directory remnant of the defect that closed livespec-dev-tooling-brlrrw: that fix stopped a proper ancestor of a named path from touching a test, but a bare top-level directory name is itself a named directory. A pre-filing doctor pass (objective and subjective phases walked against `flake_retry_decisions.py`, `_flake_retry_closure.py` and `flake_retry_paths.py`) found the rule implementable from the AST. It found no conflict with the pending proposal `the-flake-retry-plugin-decides`, which inserts at a different sentence of the same bullet. Its wording findings are folded in. The motivating flake itself is root-fixed separately by livespec-dev-tooling#4283 (livespec-dev-tooling-mioydi).

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Testing approach", in the bullet that begins "**Untouched-test retry.**", insert the following sentences immediately after the sentence that ends "whose base, its first operand, is repository-rooted.":

A string literal is a single path segment when it carries no `/` and its `PurePosixPath` suffix is empty, so `config`, `.github` and `Dockerfile` are single segments and `x.sh` is not. A single-segment string literal MUST NOT name a repository path, file or directory, unless it stands in a path position of the closure. A literal stands in a path position when, by its immediate syntax, it is the base or a segment of a path expression; an argument of a constructor of any `pathlib` class, under any import spelling, or of a `joinpath` call; an argument of `os.path.join`; the path argument of `open`; or the value of a `cwd` keyword argument. A literal bound by assignment, anywhere in the closure, to a name that stands in a path position stands in that position too. Standing in a path position is necessary and not sufficient: the literal then names only what the rules above allow, so a segment still names only the whole join of its path expression, a segment of a path expression whose base is not repository-rooted still names nothing, and a proper ancestor of a named path still does not by itself touch a test. A literal that is an element of a list, tuple or set display, or an argument of any call whose callee the plugin resolves to something other than a listed callable, does not stand in a path position, for example the git subcommand `"config"` in `git_text(args=["config", "--get", "remote.origin.url"])` or in `["git", "config", "--get"]`. A literal that is an argument of a call whose callee the plugin cannot resolve, for example a name bound to `os.path.join` through an expression the plugin cannot follow, MUST be treated as standing in a path position, because undeterminable means touched. This narrowing accepts that a single-segment literal passed as a path through any call not listed, such as `shutil.copytree`, `os.listdir`, `glob` or a subprocess argument list, no longer names a repository path. It does not change how a literal that carries a `/` or a non-empty suffix names a path, and it does not change the dotted-module-name rule.

In SPECIFICATION/scenarios.md, insert the following scenario immediately after the scenario headed "## Scenario: a failing test that shares only an ancestor directory name with the change set is retried":

## Scenario: a failing test whose closure carries a top-level directory name only as a command word is retried

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test whose closure carries the string literal `"config"` only as an element of a list argument of a call, `git_text(args=["config", "--get", "remote.origin.url"])`, where `git_text` is a function the closure defines, and in no path position

And a change set whose only path is `config/incident-fleet-evidence.json`

When that test fails on its first attempt

Then the plugin MUST treat the test as untouched and re-run it on its own, exactly as for any untouched failing test

At revise, tests/heading-coverage.json MUST gain a row for the new scenario. Until its test lands that row is a `"test": "TODO"` row whose reason names the integration tier and whose `work_item` is livespec-dev-tooling-d4siza, registered in tests/heading-coverage-debt.json through `just generate-heading-coverage-debt-register`.
