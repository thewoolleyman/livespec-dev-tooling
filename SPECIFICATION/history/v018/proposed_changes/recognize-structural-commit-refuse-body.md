---
topic: recognize-structural-commit-refuse-body
author: thewoolleyman
created_at: 2026-06-25T21:44:56Z
---

## Proposal: recognize-structural-commit-refuse-body

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Update the §"`primary_checkout_commit_refuse_hook_installed` check" canonical-fingerprint description so it records BOTH recognized primary-detection mechanisms: the structural `git rev-parse --git-common-dir` mechanism (refuse when git-dir == git-common-dir; the current canonical body, armed on install) AND the legacy `git rev-parse --show-toplevel` mechanism (refuse when toplevel == livespec.primaryPath). The check now accepts EITHER, so a fleet repo still on the legacy body keeps passing the shared check until it re-bootstraps to the structural body.

### Motivation

M2 baseline machinery (livespec-zs22.7.3, Conformance Pattern concern #1 Worktree-discipline) switches the canonical commit-refuse hook body to structural primary detection with an explicit livespec.sandboxExempt marker, retiring the livespec.primaryPath fail-open arming step. The verifier's fingerprint was broadened to accept both detection mechanisms for a green fleet migration; the contract description must record both rather than naming only `git rev-parse --show-toplevel`.

### Proposed Changes

In §"`primary_checkout_commit_refuse_hook_installed` check":

1. In the second paragraph (the port description), change the worktree-no-op clause from "The hook is a no-op at secondary worktrees (whose `git rev-parse --show-toplevel` returns the worktree's own path, not the primary's)." to: "The hook is a no-op at secondary worktrees: the current canonical body detects the primary STRUCTURALLY (refuse when `git rev-parse --git-dir` equals `git rev-parse --git-common-dir`; a worktree's git-dir differs), so it is armed on install with no `livespec.primaryPath` arming step to miss; the legacy body detected the primary by comparing `git rev-parse --show-toplevel` to `livespec.primaryPath`. Both detection mechanisms are recognized during the fleet migration."

2. In the tolerant-fingerprint bullet list, replace the second bullet "- an invocation of `git rev-parse --show-toplevel` (the at-primary detection), AND" with: "- a primary-detection invocation that is EITHER `git rev-parse --git-common-dir` (the structural mechanism, current canonical body) OR `git rev-parse --show-toplevel` (the legacy mechanism), AND". Update the introductory sentence to say the check verifies the marker, the exit-1 branch, and at least one of the two detection invocations.

No `## ` heading changes (this is an edit within the existing H3 §"`primary_checkout_commit_refuse_hook_installed` check").
