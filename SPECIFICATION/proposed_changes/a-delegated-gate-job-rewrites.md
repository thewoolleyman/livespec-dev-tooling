---
topic: a-delegated-gate-job-rewrites
author: claude-opus-5-5 (seat:fleet-flaky-tests)
created_at: 2026-11-13T01:32:29Z
---

## Proposal: A delegated gate Job's dependency-cache rewrite leaves the repository's tracked files unmodified as git reads them

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Require that a gate Job routing a repository's locked artifacts through a host-served cache leaves every tracked file unmodified as git compares the Job's working tree with its index and with `HEAD`. A lockfile rewrite the cache needs is preferably made outside the tree. Otherwise it is kept out of git's working-tree comparison by a mechanism that leaves the hidden files' index and `HEAD` contents equal to the pushed tree's. Add two scenarios. In the first, a delegated gate Job that routes locked artifacts through the pool's cache still retries an untouched failing test. In the second, such a Job still reports a pushed lockfile change.

### Motivation

Delegated gate run 20261112T233120Z-805597 (Job gate-livespec-orchestrator-beads-fabro-j7cjs, tree 4b02c3cc), measured 2026-11-12/13, pushed one `.md` file from a clean worktree. Its log reports ":: gate: 1 uv.lock file(s): 952 locked artifacts through http://pypi-proxy.ci-warm-cache.svc.cluster.local:8081". Later it reports "FLAKE-RETRY-WITHHELD … a non-version-only pyproject.toml or uv.lock change".

The cause is in `ci-runner/k3s/phase2/gates/gate-job-template.yaml`. Its `rewrite_lock_through_pypi_proxy` rewrites every `uv.lock` IN PLACE, from `files.pythonhosted.org` to the proxy, before the checks run. The ratified "Untouched-test retry" bullet (§"Testing approach") defines the change set to include unstaged working-tree differences. The pod-local rewrite therefore enters the change set. The flake-retry plugin then correctly withholds every retry for the whole session.

§"Runner-pool build cache tiers" requires the caching to be pool infrastructure that a routed repository needs no changes to benefit from. It does not say the cache must leave the repository's tree as pushed, and that gap is what this proposal closes.

Result: no delegated gate on that template retries any flake in place while the proxy answers. That is every delegated gate, in every repository the template serves. The same hazard applies to any lockfile a gate cache rewrites, not only `uv.lock`, so the rule is stated for every lockfile.

Work item livespec-dev-tooling-o4hkgh carries the fix, and its launch is held on this topic. Owner: plan fleet-flaky-tests (epic livespec-dev-tooling-zwveqp).

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, §"Runner-pool build cache tiers", **Tiers.** paragraph, insert the following sentence directly after the sentence that says a host-served realization MUST be preferred over a seeded tree (the sentence ending "…a seed whose measured bytes or duration exceed their budgets."):

"A gate Job that routes a repository's locked artifacts (its `uv.lock`, `Cargo.lock`, `package-lock.json` or any other lockfile) through a host-served cache MUST leave every file the repository tracks unmodified as git compares the Job's working tree with its index and with `HEAD`; a lockfile rewrite the cache needs MUST be made outside the tree, which is the preferred route, or else MUST be kept out of git's working-tree comparison by a mechanism that leaves the index and `HEAD` contents of every file it hides equal to the pushed tree's, so that every check reading the run's change set sees the same change set in the Job as on the pushing host."

In `SPECIFICATION/scenarios.md`, add the following scenario directly after `## Scenario: a failing test that copies a repository directory into a temporary root is still touched`, so it sits with the flake-retry scenarios and before `## Scenario: a change set that touches the build or the plugin disables every retry`:

"## Scenario: a delegated gate Job that routes locked artifacts through the pool's cache still retries an untouched failing test

Given a pushed tree that changes neither `pyproject.toml` nor any `uv.lock`

When a delegated gate Job routes that tree's locked artifacts through the pool's host-served PyPI cache and runs the repository's tests

Then the change set every check reads in the Job (the diff against the merge base, with staged, unstaged and untracked changes) MUST equal the pushed tree's change set

And a failing test the change does not touch MUST be re-run on its own, as the Untouched-test retry bullet requires"

Add a second scenario directly after that one:

"## Scenario: a delegated gate Job that routes locked artifacts through the pool's cache still reports a pushed lockfile change

Given a pushed tree that changes `uv.lock`

When a delegated gate Job routes that tree's locked artifacts through the pool's host-served PyPI cache

Then the Job's change set MUST still list `uv.lock`

And the `uv.lock` contents that change set compares MUST be the pushed tree's own bytes, so the cache rewrite neither hides nor fakes a lockfile change"

The revise that accepts this proposal MUST add one `tests/heading-coverage.json` entry for EACH of the two new scenario headings in the revise commit. Each is a TODO row whose `reason` names the integration tier and livespec-dev-tooling-o4hkgh as the work item that owes the test, and each carries the explicit key `"work_item": "livespec-dev-tooling-o4hkgh"`. The revise MUST also regenerate the debt register (`just generate-heading-coverage-debt-register`) and stage `tests/heading-coverage-debt.json`.
