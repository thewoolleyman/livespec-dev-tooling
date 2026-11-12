---
topic: the-flake-retry-plugin-reads
author: claude-opus-5-5 (fleet-flaky-tests)
created_at: 2026-11-12T09:10:16Z
---

## Proposal: A git subcommand word in a test's closure does not name a repository path

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds sentences to the "Untouched-test retry" bullet of non-functional-requirements.md section "Testing approach". A single-segment string literal (no `/`, an empty `PurePosixPath` suffix, not beginning with `-`) that stands in the subcommand position of a git command MUST NOT name a repository path. That position is the element immediately after a git program word in an argv display, or the first element of a list a closure-defined wrapper forwards to that position. Every other literal names paths exactly as today: filesystem calls, pathlib methods and every other argv element included. An unresolvable call or forwarding keeps naming, because undeterminable means touched. The exclusion is the one measured non-path use, so it cannot turn a really touched test untouched anywhere else. Adds two scenarios: a git subcommand word does not touch, and the same word in a filesystem call still does. Their heading-coverage rows are directed. Fleet scope: every repository that loads this library's flake-retry plugin.

### Motivation

Work item livespec-dev-tooling-d4siza (plan fleet-flaky-tests, epic livespec-dev-tooling-zwveqp). On 2026-11-12 livespec-dev-tooling#4275 changed `config/incident-fleet-evidence.json`. In CI run 43172130930 the flaky test `tests/livespec_dev_tooling/checks/test_red_green_replay_suite_runner.py::test_interactive_collection_and_worker_startup_output_renews_the_stall_window` failed and was NOT retried in place, so a flake the retry exists to absorb turned the expedited-incident-response-flag plan's critical-path PR red. The plugin read the test as touched because three modules of its closure carry the literal `"config"` as a git subcommand word: directly in a subprocess argument list at `gate_outcome_telemetry.py:262`, and as an element of a list argument of the helper call `git_text(args=["config", "--get", "remote.origin.url"])` at `incident_hook_process.py:195` and `incident_trusted_origin.py:43`. Under today's ratified text that withholding CONFORMS. "The closure names a path either as one string literal ...", so the literal `"config"` names the directory `config/`, and a changed path touches a test when it "lies inside a directory the closure names". So the fix is a spec change, not a conformance fix: legacy-coordinator-agent held d4siza at spec-change tier on this linked topic (ruling of 2026-11-12 ~08:3xZ). Any short common word that is also a top-level directory or extensionless file name in a consuming repository is exposed the same way, for example `config`, `docs`, `scripts`, `tests` or `ansible`. This is the top-level-directory remnant of the defect that closed livespec-dev-tooling-brlrrw: that fix stopped a proper ancestor of a named path from touching a test, but a bare top-level directory name is itself a named directory. A pre-filing doctor pass (objective and subjective phases walked against `flake_retry_decisions.py`, `_flake_retry_closure.py` and `flake_retry_paths.py`) found the rule implementable from the AST and found no conflict with the pending proposal `the-flake-retry-plugin-decides`, which inserts at a different sentence of the same bullet. legacy-coordinator-agent's grade of the first draft (livespec-dev-tooling#4288, 2026-11-12) required the exclusion to be NARROW. A false untouched lets a test the change really touched be retried and pass, which the maintainer's line forbids ("a test the PR touched is never retried at any level"); a false touched costs only a missing retry. So this rule keeps today's default and removes only the git subcommand position, rather than listing the positions where a literal does name a path. Measured 2026-11-12, over every `.py` file of the ten fleet repositories (a superset of every test closure), with a name-based approximation of the wrapper resolution. 2655 single-segment literals stand in a git subcommand position: livespec-dev-tooling 1203, livespec-orchestrator-beads-fabro 748, livespec 433, livespec-driver-pi 181, livespec-driver-codex 34, livespec-overseer 24, livespec-driver-claude 20, livespec-orchestrator-git-jsonl 12, livespec-runtime 0 and livespec-console-beads-fabro 0. Every one of them changes from naming to not naming, and every one is a non-path use: each value is a git command listed by `git help -a`. Only 153 of them can change any retry verdict, because only they equal a top-level entry of their own repository. `config` accounts for 151, all in livespec-dev-tooling, including the three motivating sites. `archive` accounts for 2: one in livespec, at `["git", "archive", ...]`, and one in livespec-orchestrator-beads-fabro that the approximation over-counted. That wrapper builds `["git", "-C", str(clone), *argv]`, so under this rule its `archive` keeps naming `archive/`. No literal outside a git subcommand position changes. The motivating flake itself is root-fixed separately by livespec-dev-tooling#4283 (livespec-dev-tooling-mioydi, merged 6e09fa97f).

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Testing approach", in the bullet that begins "**Untouched-test retry.**", insert the following sentences immediately after the sentence that ends "whose base, its first operand, is repository-rooted.":

A string literal that carries no `/`, whose `PurePosixPath` suffix is empty and which does not begin with `-` MUST NOT name a repository path when it stands in the subcommand position of a git command, and every other string literal of the closure MUST name paths exactly as the rules above state. A git program word is a string literal whose final path component is `git`, such as `"git"` or `"/usr/bin/git"`. A literal stands in the subcommand position of a git command when, by its immediate syntax, either it is the element immediately after a git program word in a list or tuple display, or it is the first element of a list or tuple display passed as the argument for a parameter of a function that forwards that parameter to the subcommand position. A function forwards a parameter to the subcommand position when its body places the parameter as a starred element immediately after a git program word in a list or tuple display, or passes the parameter as the argument for a parameter of a function that forwards it so; a call counts only when it resolves to such a function through the closure's own definitions and imports. When a git option precedes the forwarded or listed words, as in `["git", "-C", "repo", "status"]` or a function that builds `["git", "-C", str(clone), *argv]`, no literal of that command stands in the subcommand position, so each still names paths as above. When the plugin cannot resolve a call to a function the closure defines, or cannot follow how a function forwards its parameter, the literals passed to that call MUST keep naming paths as above, because undeterminable means touched. Every other position, including the argument of a filesystem call such as `os.listdir("config")`, of a `shutil`, `glob` or `io` function, of a pathlib method, and any other element of an argument list such as `"config"` in `["cat", "config"]`, MUST keep naming paths exactly as today.

In SPECIFICATION/scenarios.md, insert the following two scenarios immediately after the scenario headed "## Scenario: a failing test that shares only an ancestor directory name with the change set is retried":

## Scenario: a failing test whose closure carries a top-level directory name only as a git subcommand is retried

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test whose closure carries the string literal `"config"` only as the first element of `git_text(args=["config", "--get", "remote.origin.url"])`, where `git_text` is a function the closure defines that passes `args` to `run_git`, which builds `["git", *args]`

And a change set whose only path is `config/incident-fleet-evidence.json`

When that test fails on its first attempt

Then the plugin MUST treat the test as untouched and re-run it on its own, exactly as for any untouched failing test

## Scenario: a failing test whose closure reads a top-level directory through a filesystem call is still touched

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test whose closure carries the string literal `"config"` as the argument of `os.listdir("config")`, and also as a git subcommand elsewhere

And a change set whose only path is `config/incident-fleet-evidence.json`

When that test fails

Then the session MUST fail on that first failure, and the plugin MUST NOT re-run the test

At revise, tests/heading-coverage.json MUST gain one row for each new scenario. Until its test lands, each row is a `"test": "TODO"` row whose reason names the integration tier and whose `work_item` is livespec-dev-tooling-d4siza, registered in tests/heading-coverage-debt.json through `just generate-heading-coverage-debt-register`.
