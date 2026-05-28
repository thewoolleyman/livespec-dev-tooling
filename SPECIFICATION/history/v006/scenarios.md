# livespec-dev-tooling — scenarios

This file holds acceptance scenarios in Gherkin form. Each Gherkin keyword line is preceded and followed by a blank line so that every step renders as its own Markdown paragraph under GitHub-Flavored Markdown.

## Scenario: livespec consumes the package via uv git source

Given livespec's `pyproject.toml` declares `livespec-dev-tooling` under `[dependency-groups].dev` with `[tool.uv.sources]` pinning a `git = "https://github.com/thewoolleyman/livespec-dev-tooling.git"` and `tag = "vX.Y.Z"`

And livespec's `justfile` references each shared check as `uv run python -m livespec_dev_tooling.checks.<slug>`

When a contributor runs `just check` in the livespec repo

Then every check resolves to the package-provided module

And the run completes with exit code `0` on a clean working tree

## Scenario: every livespec-impl-* plugin consumes the package via `python -m`

Given a `livespec-impl-*` plugin's `pyproject.toml` declares `livespec-dev-tooling` under `[dependency-groups].dev` via `[tool.uv.sources]`

And the plugin's `justfile` invokes shared checks as `uv run python -m livespec_dev_tooling.checks.<slug>`

When a contributor runs `just check` in the plugin repo

Then each shared check runs against the plugin's working tree

And no plugin-local copy of any shared check is required

## Scenario: a CI workflow consumes the reusable check-matrix

Given a consumer's `.github/workflows/ci.yml` declares `jobs.check-suite.uses: thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-check-matrix.yml@vX.Y.Z`

And the workflow input `checks` lists the slugs the consumer wants to run

When the workflow runs on `pull_request`, `push` to master, or `merge_group`

Then each matrix entry executes the named check via the `run-check` composite Action

And the matrix's pass/fail status is reported to GitHub as a required status check

## Scenario: a livespec contract change ships an additive surface bump

Given livespec releases a new version that adds a new spec rule covered by a new shared check

And this library's `compat` block in `.livespec.jsonc` still pins the previous livespec release

When a contributor opens a bump-pin pull request against this library declaring the new pinned livespec tag

Then the PR adds the new check module under `livespec_dev_tooling/checks/<new-slug>.py` with a paired test

And the PR bumps `pyproject.toml`'s `version` field with a `feat:` Conventional Commit

And `release-please` opens a corresponding release PR on merge that cuts the next MINOR version

## Scenario: a breaking change to an existing check's CLI ships as a MAJOR bump

Given an existing check module's argv contract is changing in a backwards-incompatible way (e.g., a new required positional argument)

When a contributor opens the change as a `feat!:` Conventional Commit (or includes a `BREAKING CHANGE:` footer)

Then `release-please` opens a release PR that cuts the next MAJOR version

And the release notes call out the breaking change so every consumer's bump-pin PR addresses the new argv contract explicitly

## Scenario: self-application catches a regression before release

Given this library's `master` branch is green and a contributor opens a PR that mutates a shared check's logic

And the mutation introduces a subtle regression detectable only when the check runs against this library's own source tree

When CI runs `just check` against the PR's working tree

Then the self-application failure surfaces the regression at PR time

And the PR cannot merge until the regression is fixed and the check is green against this library's own source

## Scenario: a check attempts forbidden network I/O

Given a contributor writes a new check that reaches out to a remote HTTP endpoint

When CI runs the `no-network-io` gate (the gate that asserts every check stays within the local filesystem + project-local subprocess envelope; sketch only — the gate may itself be tested by a sandboxed firewall fixture or by AST inspection)

Then the gate fails the build

And the PR cannot merge until the network call is removed per `constraints.md` §"No network I/O"
