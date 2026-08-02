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

## Scenario: a blessed declared-absent spelling parses to a distinct variant carrying its reason

Given a consumer declares a union role key as one of the four declared-absent inline tables with a non-empty payload

When the configuration loader reads that block

Then the key MUST resolve to a variant distinguishable from every other declared-absent variant

And the payload MUST be retrievable from the parsed value rather than requiring a reader to consult the TOML comment

## Scenario: a declared-absent variant with an empty payload is rejected at load

Given a consumer declares a union role key with a blessed variant name but an empty or whitespace-only payload

When the loader reads that block

Then loading MUST fail with an error naming the key and every legal spelling

## Scenario: the legacy empty spelling on a union key is rejected at load

Given a consumer declares a union role key as a bare `[]` or `""`

When the loader reads that block

Then loading MUST fail with a `ConfigParseError` naming the key

And the diagnostic MUST name every legal spelling for that key

And the emptiness MUST NOT be reported as a sanctioned opt-out

## Scenario: an empty clean role key makes its consuming check stricter, not blinder

Given a consumer declares `io_trees` as a bare `[]`

When the catch-position and domain-raise checks run

Then they MUST inspect the consumer's full first-party universe

And the number of files inspected MUST be non-zero

And no file MUST be wholesale exempt by virtue of that empty declaration

## Scenario: an unarmed-until payload naming a closed work item is a conformance failure

Given a consumer declares a union role key as `unarmed_until` whose payload names a work item that is closed

When the conformance verifier runs

Then it MUST report a failure identifying the consumer, the key, and the item

And the failure MUST state that the declaration claims pending work that is already complete

## Scenario: a stale pin whose bump PR never opened escalates once the release ages past the settle window

Given a fleet member's pin is behind the source repository's latest release

And NO bump pull request for that latest release is open in that member

And the latest release's `published_at` is more than the settle window in the past

When the pin-currency row is evaluated in the release fan-out preflight

Then the row MUST report an error-severity finding

And the diagnostic MUST state that no bump pull request exists and MUST name the release's age

And the same condition evaluated in the per-PR CI job or the scheduled central sweep MUST be reported at warning severity with the identical diagnostic

## Scenario: a stale pin inside the settle window with no bump PR stays a warning

Given a fleet member's pin is behind the source repository's latest release

And NO bump pull request for that latest release is open in that member

And the latest release's `published_at` is within the settle window

When the pin-currency row is evaluated in any context, including the release fan-out preflight

Then the row MUST report the finding at warning severity

And the finding MUST NOT move any exit code and MUST NOT exclude the member from the release fan-out

## Scenario: an unparseable pin file is a finding, never a passing row

Given a fleet member carries a file at a path a known pin format claims

And the walk finds that file and cannot parse its contents

When the pin-currency row for that format is evaluated

Then the row MUST NOT report a passing outcome

And the row MUST report a finding naming the member and the unparseable file

And the finding MUST be distinguishable from that member carrying no pin of that format at all

And the finding MUST be error severity in the release fan-out preflight and warning severity in every other evaluating context

## Scenario: a healthy App installation budget yields a fresh exactly-scoped token

Given the GitHub App installation's REST core and GraphQL remaining budgets meet the caller's configured minima

And the caller requests a specific owner and repository set

When the caller invokes the `github-rate-budget-token` Action

Then the Action MUST probe the installation budget with a minimum-scope token

And it MUST mint a second token only after the healthy probe

And the output token MUST preserve exactly the requested owner and repository scope

And both tokens MUST retain normal end-of-job revocation

## Scenario: a deficient App installation budget waits for the later reset

Given either the REST core or GraphQL remaining budget is below its configured minimum

And the deficient resources advertise different reset times

When the caller invokes the `github-rate-budget-token` Action

Then the Action MUST wait until the later deficient reset plus the configured cushion and deterministic seed-derived jitter

And it MUST re-probe both budgets after waiting

And it MUST mint the downstream token only after both budgets meet their minima

## Scenario: an App installation budget does not recover inside the wait bound

Given a deficient App installation budget remains below its configured minima

And the next required wait would exceed the configured aggregate maximum

When the budget gate evaluates the next wait

Then the Action MUST fail with `rate-budget-not-restored`

And it MUST NOT mint a downstream token

## Scenario: an App budget probe cannot authenticate or reach GitHub

Given the budget probe receives a transport, authentication, or non-success HTTP failure

When three total fetch attempts have failed with the specified retry delays

Then the Action MUST fail with `probe-unusable`

And it MUST distinguish that failure from a healthy probe reporting exhausted quota

## Scenario: an App budget probe returns a malformed rate-limit payload

Given GitHub returns a successful response that lacks a required core or GraphQL remaining or reset field

When the budget gate validates the response

Then the Action MUST fail with `rate-budget-malformed`

And it MUST NOT wait or mint a downstream token from an indeterminate budget
