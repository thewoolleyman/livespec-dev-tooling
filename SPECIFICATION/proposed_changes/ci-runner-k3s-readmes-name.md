---
topic: ci-runner-k3s-readmes-name
author: claude-opus-5-5 (ci-pool-provisioning-leftovers)
created_at: 2026-11-13T07:06:07Z
---

## Proposal: A ci-runner/k3s README names the root boot converge as the apply path for what the converge applies

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph, "The boot converge is the documented apply path.", to non-functional-requirements.md section "Runner-pool node rebuild recipe", directly after "Live converge from the control node.". A README under ci-runner/k3s/ that documents applying a cluster object the CI stack converge applies MUST name converge-ci-stack.service, running as root, as the normal apply path, and any by-hand converge command it keeps MUST run as root and MUST NOT apply through the k3s admin kubeconfig as a non-root user. Adds one scenario to scenarios.md. The NFR paragraph carries no H2 of its own, so the only new heading is the scenario's.

### Motivation

Plan ci-pool-provisioning-leftovers (epic livespec-dev-tooling-fby3sx), item livespec-dev-tooling-dwmssn, a slice of livespec-dev-tooling-nmrf34 approved by legacy-coordinator-agent. Four README commands apply cluster objects as a non-root user through the k3s admin kubeconfig: `KUBECONFIG=/etc/rancher/k3s/k3s.yaml <converge>.sh` at ci-runner/k3s/crates-proxy/README.md:40, ci-runner/k3s/warm-cache/pypi-proxy/README.md:47, ci-runner/k3s/warm-cache/README.md:586 and ci-runner/k3s/warm-cache/README.md:1023. converge-ci-stack.service already applies all of master as root on every run, so these are redundant second routes, and they depend on the admin kubeconfig staying world-readable, which nmrf34 tightens to 0600. The coordinator's condition is that the READMEs state converge-ci-stack.service (root) as the normal apply path, so the lines become documentation and not a second route. The launch screen held dwmssn at spec-change tier: the ratified "Live converge from the control node" paragraph names the converge as the path for a merged change but says nothing about what a README documents or about the user a by-hand converge runs as.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Runner-pool node rebuild recipe", insert the following paragraph immediately after the paragraph that begins "**Live converge from the control node.**" (and after any paragraph inserted directly after it by a revise ratified earlier):

**The boot converge is the documented apply path.** A README under `ci-runner/k3s/` that documents applying a cluster object which the CI stack converge applies MUST name `converge-ci-stack.service`, running as root, as the normal apply path for that object. A by-hand converge command such a README keeps MUST run as root, and MUST NOT apply through the k3s admin kubeconfig as a non-root user.

In SPECIFICATION/scenarios.md, append the following scenario:

## Scenario: a ci-runner/k3s README documents the root boot converge as the apply path

Given `converge-ci-stack.service` applies the crates proxy, the PyPI proxy, the warm cache and the registry mirror as root on every run

When an operator reads the apply instructions in `ci-runner/k3s/crates-proxy/README.md`, `ci-runner/k3s/warm-cache/pypi-proxy/README.md` and `ci-runner/k3s/warm-cache/README.md`

Then each of them MUST name `converge-ci-stack.service`, running as root, as the normal apply path

And every by-hand converge command they keep MUST run as root rather than as a non-root user through `KUBECONFIG=/etc/rancher/k3s/k3s.yaml`

The revise that accepts this proposal MUST add a tests/heading-coverage.json row for the new scenario heading, a spec-first TODO row naming its tier and an owning work_item (livespec-dev-tooling-dwmssn), and MUST register it in tests/heading-coverage-debt.json.
