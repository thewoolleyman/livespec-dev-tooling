---
topic: retire-auto-update-branches-ref
author: retire-auto-update-branches-ref
created_at: 2026-06-22T20:41:56Z
---

## Proposal: retire-auto-update-branches-ref

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The App-token-over-GITHUB_TOKEN rationale in §"GitHub App auth model" cites auto-update-branches.yml as one of the precedents. That workflow is being retired family-wide (it auto-merged master into behind PRs via update-branch, injecting merge commits; its role is replaced by strict=false branch protection + auto-merge + post-merge CI). Reword the rationale so it no longer references the retired workflow while keeping the App-token rationale intact, citing auto-enable-merge.yml and the bump-pin shim workflows as the surviving precedents.

### Motivation

Retire all spec references to the now-removed auto-update-branches.yml workflow so contracts.md reflects the current coordination surface.

### Proposed Changes

In §"GitHub App auth model", change the sentence:

  The rationale for App-token over `GITHUB_TOKEN` mirrors the existing `auto-update-branches.yml` and `auto-enable-merge.yml` choices in livespec: pushes authored by `GITHUB_TOKEN` do not trigger downstream CI workflows (GitHub's workflow-recursion ceiling), which would leave bump PRs permanently `BLOCKED` with no CI re-runs against the updated head SHA.

to:

  The rationale for App-token over `GITHUB_TOKEN` mirrors the existing `auto-enable-merge.yml` and bump-pin shim workflow choices in livespec: pushes authored by `GITHUB_TOKEN` do not trigger downstream CI workflows (GitHub's workflow-recursion ceiling), which would leave bump PRs permanently `BLOCKED` with no CI re-runs against the updated head SHA.

This drops the reference to the retired `auto-update-branches.yml` workflow while preserving the App-token rationale and pointing at the surviving precedents (the `auto-enable-merge.yml` workflow and the bump-pin shim workflows, which both mint and use the App installation token for the same downstream-CI-triggering reason). No `## ` heading changes.
