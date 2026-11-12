---
topic: a-consumer-verifies-its-own-dev-tooling-imports-are-declared
author: claude-opus-5-5
created_at: 2026-11-12T02:03:57Z
---

## Proposal: The shipped package carries cross_repo_public_api, and a consumer verifies its own imports against it

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Amend the `cross_repo_public_api` bullet of §"Consumer configuration schema". livespec-dev-tooling MUST ship its own `cross_repo_public_api` declaration as package data whose entries equal its pyproject.toml array, and a consuming repository MAY verify, from its own tree and against its INSTALLED build, that every `livespec_dev_tooling` function it reaches is declared or already public under the repo-local consumption oracle. The bullet's "COMPLETENESS IS NOT VERIFIED LOCALLY" sentence is rewritten: the declaring repository still cannot see a sibling's import, but the consuming repository can, so completeness is now verified from the consumer's side as well as by the central-vantage row.

### Motivation

On 2026-11-12 the krc2yd purity slice of livespec-orchestrator-git-jsonl (commits 32f4360 / 4a64604, 01:12:34Z) added `from livespec_dev_tooling.green_token import main` to tests/integration/test_pre_push_delegated_gate.py. Nothing in that consumer flagged it. The central-vantage row cross-repo-public-api-declared then failed check-fleet-conformance on every livespec-dev-tooling pull request (#4223, #4234, #4235, #4236) until a stop-the-line declaration landed in this repository. The maintainer approved (2026-11-12, relayed by legacy-coordinator-agent) that a repository importing dev-tooling code checks in its own CI that each import is declared public, fleet-wide, and done mechanically like a lint. The declaration cannot be read from a consumer today: livespec-dev-tooling 1.197.0 as installed in livespec-orchestrator-git-jsonl's .venv carries no pyproject.toml and no data file holding the array. Carrier work item: livespec-dev-tooling-vobfwi.

### Proposed Changes

In SPECIFICATION/contracts.md §"Consumer configuration schema", in the `cross_repo_public_api` bullet:

1. After the sentence that begins "The consumer's own declaration of the names OTHER governed repos consume.", insert: "livespec-dev-tooling MUST ship its own declaration as package data inside the installed `livespec_dev_tooling` package, and the entries of that data MUST equal the `[tool.livespec_dev_tooling] cross_repo_public_api` array of the pyproject.toml the package was built from. A build whose package data and pyproject.toml disagree MUST fail this repository's own check aggregate, naming each entry present in one and absent from the other. The package data exists so that a consuming repository can read the declaration of the build it has INSTALLED; it MUST NOT be read from livespec-dev-tooling's default branch."

2. In the sentence that ends "declaration-presence for this key is the central-vantage conformance row's obligation, not a local one.", replace "not a local one" with "which a consuming repository MAY additionally verify for the names it reaches, as the last sentences of this bullet state".

3. After the sentence that begins "**TIGHTENING-ONLY**" and ends "exists to remove.", insert: "A consuming repository's check of its own imports (below) reads this key ONLY as what it already is, the declaring repository's statement of the names its siblings consume, exactly as the central-vantage row reads it. That reading MUST NOT widen or narrow `public_api_result_typed`'s scope in any repository, and it is not the exemption, allowlist or scan-universe reading this paragraph forbids."

4. Replace the sentence that begins "COMPLETENESS IS NOT VERIFIED LOCALLY:" through the end of the bullet with: "COMPLETENESS IS NOT VERIFIED BY THE DECLARING REPOSITORY: its own check cannot tell whether the declared set OMITS a name a sibling consumes, so a green run in the declaring repository does NOT mean its declared surface is complete. Completeness is instead verified from two other vantages. The CONSUMING repository MAY verify it for the names it reaches, through the commit-hook check `dev_tooling_imports_declared` (§"Shared check inventory", commit-hook checks), against the declaration shipped with the livespec-dev-tooling build it has installed. The central-vantage row remains the fleet-wide obligation under the split-enforcement clause of §"ROP composition" and MUST NOT be withdrawn because a consumer runs the commit-hook check. A name is satisfied when it is declared in the installed build's shipped data or is already public under the repo-local consumption oracle; the consumer-side check MUST use the same oracle the central-vantage row uses, so the two vantages cannot disagree about what is public."

## Proposal: A commit-hook check refuses a livespec_dev_tooling import that the installed build does not declare

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add `dev_tooling_imports_declared` to the commit-hook checks of §"Shared check inventory": a static check, run from a consumer's `check-pre-commit` ahead of its aggregate and from its `just check` aggregate, that reports every `livespec_dev_tooling` function the consumer's tree reaches which the installed build neither declares in its shipped `cross_repo_public_api` nor makes public under the repo-local consumption oracle. It decides from source alone, reports in warn mode unless `LIVESPEC_FAIL_IF_UNDECLARED_DEV_TOOLING_IMPORTS` is set, and is deliberately NOT a canonical slug until a fleet-wide measurement records zero offenders. Three scenarios state the behaviour.

### Motivation

The consumer is where the import is written, so the consumer is where it can be refused in seconds at commit time, before the central-vantage row fails every pull request of the declaring repository. The maintainer asked for it to be mechanical, like a lint: no model, no network, no execution. Ruff's banned-api rule (TID251) is a ban list, not an allowlist, so it cannot express "only declared names". The placement in `workflow_checks/` rather than `checks/` is load-bearing: §"Shared check inventory" records that a module under `checks/` becomes a canonical slug that obliges every consumer to wire it into `just check` and its CI matrix, so shipping it there would arm it fleet-wide on the next release, before any consumer has been measured. That is the arming-ahead-of-adoption failure this repository reverted in f4247110.

### Proposed Changes

1. In SPECIFICATION/contracts.md §"Shared check inventory", in the **Commit-hook checks** sub-bullet of **Workflow checks**, add a second member after `staged_precheck`:

"`dev_tooling_imports_declared` is a member: invoked as `python -m livespec_dev_tooling.workflow_checks.dev_tooling_imports_declared` from the consuming repository's root. It MUST parse the consumer's first-party Python tree and collect every `livespec_dev_tooling` function the tree reaches, whether named in a `from livespec_dev_tooling... import` statement or reached as an attribute of an imported `livespec_dev_tooling` module. For each, it MUST decide whether the function is declared in the `cross_repo_public_api` package data shipped with the consumer's INSTALLED livespec-dev-tooling build, or is public under the repo-local consumption oracle the central-vantage row uses, evaluated against that installed build's source. It MUST decide by parsing source files alone: it MUST NOT import a consumer module, execute consumer code, or make a network call. For every reached function that is neither declared nor public, it MUST print the import site as repository-relative file and line, together with the missing declaration as its `file` and `function`. When `LIVESPEC_FAIL_IF_UNDECLARED_DEV_TOOLING_IMPORTS` is unset or empty, it MUST print each such offender as a warning and exit 0. When the variable is set non-empty, it MUST exit non-zero if any offender exists. When there is no offender, it MUST print no offender and exit 0 in either mode. A consumer that wires it SHOULD run it both from its `check-pre-commit` recipe ahead of the pre-commit aggregate and as a member of its `just check` aggregate. This repository's own `check-pre-commit` and `just check` MUST run it."

2. In the same section, after the paragraph that begins "**The placement is load-bearing, not a filing preference**", add: "`dev_tooling_imports_declared` MUST NOT be moved under `livespec_dev_tooling/checks/`, and so MUST NOT become a canonical slug, until a run of it against every governed repository at that repository's installed livespec-dev-tooling build has been recorded with zero offenders in every repository. That recorded measurement is the precondition for arming it fleet-wide, because promotion to a canonical slug obliges every consumer to wire it at once."

3. In SPECIFICATION/scenarios.md, add three scenarios:

```gherkin
## Scenario: a consumer's commit-hook check reports a livespec_dev_tooling function its installed build does not declare

Given a consuming repository whose test file imports a function from livespec_dev_tooling
And the consumer's installed livespec-dev-tooling build neither declares that function in its shipped cross_repo_public_api nor makes it public under the repo-local consumption oracle
And LIVESPEC_FAIL_IF_UNDECLARED_DEV_TOOLING_IMPORTS is set

When the consumer runs `python -m livespec_dev_tooling.workflow_checks.dev_tooling_imports_declared`

Then the check MUST exit non-zero
And its output MUST name the import's file and line
And its output MUST name the missing declaration's file and function

## Scenario: a consumer whose every livespec_dev_tooling function is declared or locally public passes the commit-hook check

Given a consuming repository that reaches one livespec_dev_tooling function declared in its installed build's shipped cross_repo_public_api
And reaches a second livespec_dev_tooling function that is public under the repo-local consumption oracle and not declared
And LIVESPEC_FAIL_IF_UNDECLARED_DEV_TOOLING_IMPORTS is set

When the consumer runs `python -m livespec_dev_tooling.workflow_checks.dev_tooling_imports_declared`

Then the check MUST exit 0
And its output MUST name no offender

## Scenario: a declaration present only on livespec-dev-tooling's default branch does not satisfy the commit-hook check

Given a consuming repository that imports a livespec_dev_tooling function
And that function is declared in cross_repo_public_api on livespec-dev-tooling's default branch but not in the consumer's installed release
And LIVESPEC_FAIL_IF_UNDECLARED_DEV_TOOLING_IMPORTS is set

When the consumer runs `python -m livespec_dev_tooling.workflow_checks.dev_tooling_imports_declared`

Then the check MUST exit non-zero
And its output MUST name that import as undeclared
```

The revise that accepts this proposal MUST add one `tests/heading-coverage.json` entry per new `## Scenario` heading in the same commit, each a spec-first TODO row naming the integration tier and `"work_item": "livespec-dev-tooling-vobfwi"`, and MUST regenerate `tests/heading-coverage-debt.json`.
