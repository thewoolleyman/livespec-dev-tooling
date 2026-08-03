---
topic: github-hosted-ci-posture
author: codex-gpt-5
created_at: 2026-08-03T01:14:41Z
---

## Proposal: Hosted CI and fail-closed parked live gate

### Target specification files

- constraints.md
- contracts.md
- scenarios.md

### Summary

Align dev-tooling's CI and codex-acp coordination contract with the fleet's GitHub-hosted-only posture while keeping the live golden-master safety gate fail-closed.

### Motivation

The maintainer disabled the overloaded host-local runner pool. Normal fleet CI already resolves CI_RUNNER_LABELS to ubuntu-latest, but the live codex-acp golden-master requires privileged host capabilities and cannot honestly move to a stock hosted runner. The safe temporary state is hosted CI plus a parked bump, never a fabricated green gate.

### Proposed Changes

In constraints.md, the CI matrix shape MUST state that dev-tooling's own merge-gating CI and reusable check workflows execute on GitHub-hosted runners in the current fleet posture and MUST NOT require the shared factory host's self-hosted labels. In contracts.md section codex-acp factory gate, the live factory proof MUST remain a prerequisite for auto-merge. While the host-only receiver workflow is administratively disabled, a freshness scan MAY open or find a codex-acp bump PR and MAY emit its repository_dispatch event, but no component may synthesize the missing success callback, enable auto-merge, or treat absence as green; the PR MUST remain parked on the last verified version until the live gate is explicitly restored or a later spec revision defines an equivalent proof. Update the existing CI-workflow scenario in scenarios.md to state that reusable check-matrix jobs execute on GitHub-hosted capacity and add the parked-gate outcome to that scenario's Gherkin without adding a new H2 heading.
