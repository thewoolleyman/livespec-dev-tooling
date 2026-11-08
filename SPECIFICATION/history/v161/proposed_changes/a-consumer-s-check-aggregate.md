---
topic: a-consumer-s-check-aggregate
author: claude-opus-5-5
created_at: 2026-11-07T20:33:37Z
---

## Proposal: A consumer's check aggregate fails on more than one CI container image

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

A check every consumer runs fails when ci.yml declares two distinct job container images, so the offending pull request goes red in its own CI.

### Motivation

On 2026-11-05 livespec-orchestrator-beads-fabro#4439 merged a second image pin green. Only the delegated pre-push gate refuses that shape, so it then refused every push and post-merge janitor off orchestrator master until a fix landed. `fabro_image_pin_lockstep` checks this for this repository alone. Carries work item livespec-dev-tooling-kzhduc.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "## Sandbox image gate toolchain", add this paragraph:

**Every consumer's CI declares one container image.** When a repository's `.github/workflows/ci.yml` declares two or more distinct job `container:` images, a check in that repository's `just check` aggregate MUST fail, naming each distinct image and the line that declares it. It MUST pass when every job `container:` image is the same reference. A pull request whose merge with the default branch declares two distinct images MUST fail its own required `ci-green` aggregate.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario: a workflow declaring two container images fails its own CI

Given a pull request whose merge with the default branch makes `.github/workflows/ci.yml` declare two distinct job `container:` images

When its CI runs

Then the check MUST fail, naming each distinct image and its line
And the required `ci-green` aggregate MUST fail

## Scenario: a workflow declaring one container image passes

Given every job `container:` image in `.github/workflows/ci.yml` is the same reference

When the check runs

Then it MUST pass
