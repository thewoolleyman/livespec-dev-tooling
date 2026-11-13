---
topic: the-flake-retry-closure-retries
author: claude-opus-5-5 (seat:fleet-flaky-tests)
created_at: 2026-11-13T11:32:22Z
---

## Proposal: The flake-retry closure attributes the request and path forms it now misses

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Amend the "Untouched-test retry" bullet of `SPECIFICATION/non-functional-requirements.md` §"Testing approach" so that the closure analysis MUST attribute to a test's closure every repository path the closure reaches through any of these forms: a test's own path read from pytest's `request` (`request.path`, `request.fspath`, `request.node.path`, `request.node.parent.path` and other `request.node` chains that name the test's own module or a directory containing it, and `request.module.__file__`); that same path read through `getattr(request, "path")`, through a name aliased to `request`, or through a parameter of a closure-defined helper or fixture, whatever its name, that the closure calls with `request`; `os.path.join` and `os.path.dirname`; an f-string; `Path.with_name`; and a fixture or helper defined in another test module and imported from it, judged in the module that defines it. A module-level name bound to a chain of string literals only is DETERMINATE and joins as those literal segments, so a test that joins it keeps its in-place retry for an unrelated change and is touched by a change at the joined path. The existing rule stays: a closure path the plugin cannot determine makes the test touched. Add one scenario for each of three cases, beside the existing flake-retry scenarios: a test path reached through getattr, an alias, a renamed helper parameter or another path form is touched by a change under it; a fixture imported from another test module is judged in its defining module; and a literal-only name chain keeps the test retryable for an unrelated change and touched for a change at its path. Carrying item: livespec-dev-tooling-k3lpwj.

### Motivation

Work item livespec-dev-tooling-k3lpwj (plan fleet-flaky-tests, epic livespec-dev-tooling-zwveqp) is held at the spec-change tier on this topic, and legacy-coordinator-agent ruled that it be filed. The item was filed on legacy-coordinator-agent's grades of livespec-dev-tooling#4413 (merged 2026-11-13 as 90fedaccf). Its probes showed that every form named in the Summary currently falls to the RETRIED side. A failing test whose code or data the change just touched is then re-run as if it were a flake. That is the unsafe direction: a false untouched lets a real regression pass on a re-run, while a false touched only costs one missing retry.

The ratified bullet does not cover these forms. It names three repository-rooted bases: a string literal, an expression derived from `__file__`, and a name the closure binds to one of those. It counts only `/` joins of consecutive string literals. It says nothing about pytest's `request` object, even though the plugin on master already reads `request.path`, `request.fspath` and `request.node.path` as the test's own path (`livespec_dev_tooling/_flake_retry_places.py`). That module's docstring records the gap: "`request` is recognised only by that name, never through `getattr` or an alias". The bullet's existing catch-all, "When the plugin cannot determine which paths a closure names, the test MUST be treated as touched", should cover these forms. It does not take effect, because the plugin does not see these forms as paths at all, so it never reaches the undeterminable branch. The rule therefore has to name the forms.

Since #4413 was rebased, master reads `_incident_fleet_sources.py:47`, `Path(__file__).resolve().parents[1] / CLAIMS_RELATIVE_PATH` with `CLAIMS_RELATIVE_PATH = Path("config") / "incident-fleet-evidence.json"`, as undeterminable. Every test that reaches it therefore loses its in-place retry. That is the safe direction, but it is wrong: the joined path is determinate. legacy-coordinator-agent folded the literal-only name-chain case into the item (2026-11-13, about 10:30Z) so that this retry is restored where the path is in fact known.

One finding came out of drafting the cross-module fixture rule. A `request` read inside a fixture that another test module defines and a test imports yields the IMPORTING test's path at run time, not the defining module's path. The defining module's `__file__` and its names do resolve in the defining module. So the proposed text judges the definition in its defining module but routes a `request` read there through the same bound as a `request` read in a `conftest.py`. Otherwise a change beside the importing test would be retried.

Compatibility with pending proposals. `a-cwd-or-rootpath-base-is-repository-rooted` (livespec-dev-tooling-wc23r2) replaces the bullet's "A base is repository-rooted when …" sentence. This proposal inserts its sentences after the following sentence and leaves that one untouched, so the two compose in either order. `the-flake-retry-plugin-reads` (livespec-dev-tooling-d4siza) inserts after a different sentence. `a-delegated-gate-job-rewrites` does not touch this bullet. The in-flight survey found no open pull request or `spec/*` branch that touches this bullet. Fleet scope: every repository that loads this library's flake-retry plugin gets the fix at its next pin bump.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, §"Testing approach", in the bullet that begins "**Untouched-test retry.**", make two edits.

**Edit 1.** In the sentence that begins "A path expression with any other base, such as a function parameter, …", replace "such as a function parameter," with "such as a function parameter that this bullet does not count as a test's request,". The rest of that sentence is unchanged.

**Edit 2.** Insert the following sentences directly after that sentence, which ends "…MUST NOT count as string literals of the closure for this rule.":

"A test's own path is also a repository-rooted base. It is pytest's `request.path`, `request.fspath` or `request.node.path`; `request.module.__file__`; or `request.node.parent.path` or any other chain of `parent` steps from `request.node` whose `path` or `fspath` names the test's own module or a directory that contains it. The closure MUST attribute a repository path reached through such a base in each of these forms, exactly as if `request` were written by name. The first form is `getattr` with a string-literal attribute name, such as `getattr(request, "path")`. The second is a name the closure binds by assignment to `request`, or to another name that counts as `request`. The third is a parameter of a function or fixture the closure defines, whatever that parameter is named, when a call in the closure passes `request`, or a name that counts as `request`, in that parameter's position or by its keyword. An example is `def data_dir(req): return req.path.parent / "data"` called as `data_dir(request)`. A `getattr` on something that counts as `request` whose attribute name is not a string literal makes the closure's paths undeterminable. A path expression MUST also join a repository-rooted base to its string-literal parts through each of these forms, exactly as the `/` operator does: `os.path.join(...)`; `os.path.dirname(...)`, which steps to the parent the way `.parent` does; an f-string whose leading replacement field is a repository-rooted base, its following literal text split at `/` into segments; and `Path.with_name(...)` with a string-literal argument, which names the sibling path. A fixture or helper that the test's closure takes from another test module, by import or as that module's fixture, is judged in the module that defines it, so `__file__` and every name it binds resolve there and not in the module that uses it. A `request` read in any module other than the test's own file is the exception. That includes a `conftest.py`, a helper module, and another test module that defines a fixture or helper the test takes from it. There the test path is the path of the test that reaches it, not the path of the module that reads it. The plugin MUST attribute to the closure each repository path such an expression can name for that test. It MAY do so by naming whole a directory that every such test lies under, such as a `conftest.py`'s own directory. When it cannot bound that path, the closure's paths are undeterminable. A module-level name bound only to a string literal, or only to a chain of string literals joined by `/`, `Path(...)` or `os.path.join(...)`, is determinate. This holds whether the closure defines the name in the module that uses it or imports it from another in-repository module. For example, `CLAIMS_RELATIVE_PATH = Path("config") / "incident-fleet-evidence.json"`. Wherever a path expression joins such a name after a repository-rooted base, its literal segments MUST count as consecutive string-literal segments of that expression. So `Path(__file__).resolve().parents[1] / CLAIMS_RELATIVE_PATH` names `config/incident-fleet-evidence.json` exactly, under the same rules as if those segments were written in place: it MUST NOT be read as undeterminable, and it MUST NOT be read as naming the repository root."

The bullet's existing sentence "When the plugin cannot determine which paths a closure names, the test MUST be treated as touched." MUST stay as it is. Every undeterminable case above falls under it. The rest of the bullet is unchanged.

In `SPECIFICATION/scenarios.md`, add the following three scenarios, in this order, directly before `## Scenario: a change set that touches the build or the plugin disables every retry`. They then sit with the other flake-retry scenarios, after any flake-retry scenario that an earlier revise placed at that position.

"## Scenario: a failing test whose closure reaches a changed path through getattr, an alias of request or another path form fails at once

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set that contains `tests/widgets/data/sample.json` and no module of the test's closure

And a failing test in `tests/widgets/test_render.py` whose closure names `tests/widgets/data/` only through one of these expressions: `getattr(request, "path").parent / "data"`; `req.path.parent / "data"` after `req = request`; a helper `def data_dir(req): return req.path.parent / "data"` called as `data_dir(request)`; `request.node.parent.path.parent / "data"`; `os.path.join(os.path.dirname(request.module.__file__), "data")`; `f"{Path(__file__).parent}/data"`; or `Path(__file__).with_name("data")`

When that test fails, whichever one of those expressions its closure uses

Then the plugin MUST treat the test as touched

And the session MUST fail on that first failure, and the plugin MUST NOT re-run the test"

"## Scenario: a fixture imported from another test module is judged in the module that defines it

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a fixture `shared_data` defined in `tests/b/test_source.py` as `Path(__file__).parent / "data"`, which `tests/a/test_user.py` imports and a failing test there uses

And a change set that contains `tests/b/data/x.json` and no module of the test's closure

When that test fails

Then the plugin MUST treat the test as touched, and the session MUST fail on that first failure with no re-run

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a fixture `own_data` defined in `tests/b/test_source.py` as `request.path.parent / "data"`, which `tests/a/test_user.py` imports and a failing test there uses

And a change set that contains `tests/a/data/x.json` and no module of the test's closure

When that test fails

Then the plugin MUST treat the test as touched, because a `request` read in the defining module yields the importing test's path, and the session MUST fail on that first failure with no re-run"

"## Scenario: a module-level name bound to string literals only keeps a joined closure path determinate

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test whose closure names a path only as `Path(__file__).resolve().parents[1] / CLAIMS_RELATIVE_PATH`, in a module one directory below the repository root, such as `livespec_dev_tooling/_incident_fleet_sources.py`, so that `parents[1]` is the repository root, and where the closure binds `CLAIMS_RELATIVE_PATH = Path("config") / "incident-fleet-evidence.json"` at module level

And a change set whose only path is `docs/unrelated.md`

When that test fails on its first attempt

Then the plugin MUST treat the test as untouched and re-run it on its own, exactly as for any untouched failing test

And when the change set's only path is `config/incident-fleet-evidence.json` instead, the session MUST fail on that first failure, and the plugin MUST NOT re-run the test"

The revise that accepts this proposal MUST add one `tests/heading-coverage.json` entry for EACH of the three new scenario headings in the revise commit. Each is a TODO row whose `reason` names the integration tier and names livespec-dev-tooling-k3lpwj as the work item that owes the test. Each carries the explicit key `"work_item": "livespec-dev-tooling-k3lpwj"`. The revise MUST also regenerate the heading-coverage debt register (`just generate-heading-coverage-debt-register`) and stage `tests/heading-coverage-debt.json`.
