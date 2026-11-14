---
topic: sandbox-image-gate-one-version-flavors
author: claude-opus-5-5:ci-runtime-and-cost
created_at: 2026-11-11T18:16:36Z
---

## Proposal: One image version per consumer workflow; a layered flavor only off the gate path; one shared image reader

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Amend §"Sandbox image gate toolchain" so a consumer's ci.yml names one image repository and one release version. A flavor layered on the gate flavor (python-rust-fuzz atop python-rust) is allowed only for jobs that run no `just check` aggregate target. The delegated gate runs in the gate flavor, and the gate and the shared check resolve images through one YAML reader. Adds three scenarios.

### Motivation

Measured 2026-11-11 (plan ci-runtime-and-cost, epic livespec-dev-tooling-ib3oe3). The current clause says a consumer's ci.yml MUST declare only one container image. livespec-dev-tooling-kzhduc implements it (livespec-dev-tooling#4191). Run against each fleet member's default-branch ci.yml, that check passes seven members and FAILS livespec-console-beads-fabro, which declares python-rust-v1.197.0 on five jobs and python-rust-fuzz-v1.197.0 on its check-fuzz job. The second flavor is harmless to the gate: console's delegated gate runs `just check`, whose 26 targets do not include check-fuzz. check-fuzz runs only in CI's own check-fuzz job, so the gate replays CI on python-rust alone. What the gate must not tolerate is two VERSIONS (the 2026-11-05 incident, livespec-orchestrator-beads-fabro#4439, python-v1.174.0 beside python-v1.175.0), or a non-gate flavor carrying a gate-replayed target. Separately, render-gate-job.sh resolves images with `grep -A1` after `container:`, so it misses console's fuzz image (written below two comment lines) while the YAML-reading check sees it. The gate and the check disagree today, and the clause should require one shared reader (livespec-dev-tooling-op67ed). legacy-coordinator-agent ruled 2026-11-11 18:27Z and 18:37Z that this changes what the check asserts, so it is ratification and comes before the check's Red/Green.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Sandbox image gate toolchain", replace the paragraph that begins "**Every consumer's CI declares one container image.**" in full.

Current text:

**Every consumer's CI declares one container image.** A delegated gate Job runs in the one image it resolves from the consumer's `.github/workflows/ci.yml`, so that file MUST declare only one. When a repository's `.github/workflows/ci.yml` declares two or more distinct job `container:` images, a check in that repository's `just check` aggregate MUST fail, naming each distinct image and the line that declares it. It MUST pass when every job `container:` image is the same reference. A pull request whose merge with the default branch declares two distinct images MUST fail its own required all-green aggregate job. The check MUST be exposed as a shared check consumers run through their pinned livespec-dev-tooling, with no copy of its logic in the consumer.

Replacement text:

**Every consumer's CI declares one container image version.** A delegated gate Job runs in the one image it resolves from the consumer's `.github/workflows/ci.yml`. Every job `container:` image in that file MUST name one image repository and one release version, the `v<semver>` suffix of its tag. The flavor is the part of the tag before that suffix. Flavors MAY differ only where one flavor, the gate flavor, is a dash-separated prefix of every other flavor named (for example `python-rust` and `python-rust-fuzz`), and a job whose image is not the gate flavor MUST NOT run any target of the repository's `just check` aggregate. The delegated gate MUST run in the gate flavor's image. When a repository's `.github/workflows/ci.yml` names two or more image repositories, two or more versions, a set of flavors with no gate flavor, or a non-gate-flavor job that runs a `just check` aggregate target, a check in that repository's `just check` aggregate MUST fail, naming each distinct image and the line that declares it. It MUST pass otherwise. The delegated gate and that check MUST resolve a workflow's job container images through one shared reader of the workflow's YAML, so an `image:` key written below comment lines inside a `container:` block is counted by both. A pull request whose merge with the default branch declares a set the check fails MUST fail its own required all-green aggregate job. The check MUST be exposed as a shared check consumers run through their pinned livespec-dev-tooling, with no copy of its logic in the consumer.

In SPECIFICATION/scenarios.md, append these three scenarios at the end of the file:

## Scenario: a workflow whose layered fuzz flavor runs no aggregate target passes and its gate runs in the base flavor

Given a consumer whose `.github/workflows/ci.yml` gives five jobs the container image `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-v1.197.0`

And gives one more job, whose only recipe is `just check-fuzz`, the container image `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-fuzz-v1.197.0`, written below two comment lines inside its `container:` block

And `check-fuzz` is not a target of that consumer's `just check` aggregate

When the consumer's single-container-image check runs, and the delegated gate renders that consumer's gate Job

Then the check MUST pass

And the gate Job MUST run in `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-v1.197.0`

## Scenario: a workflow naming two image versions fails the single-container-image check

Given a consumer whose `.github/workflows/ci.yml` gives one job `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v1.174.0` and every other job `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v1.175.0`

When the consumer's single-container-image check runs

Then it MUST fail, naming both images and each line that declares them

## Scenario: an image written below comment lines inside a container block is counted by the gate and the check alike

Given a consumer whose `.github/workflows/ci.yml` gives one job `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-v1.197.0` and gives another job `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v1.197.0`, written below comment lines inside its `container:` block

When the consumer's single-container-image check runs, and the delegated gate renders that consumer's gate Job

Then the check MUST fail, naming both images

And the delegated gate MUST refuse to render the Job, naming both images

At revise time, tests/heading-coverage.json gains one entry per new scenario heading (see the repository's revise co-edit discipline). The implementation owners are livespec-dev-tooling-kzhduc's version-rule follow-up (the check) and livespec-dev-tooling-op67ed (the gate's shared reader).
