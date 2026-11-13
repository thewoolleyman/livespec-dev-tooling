---
topic: a-read-only-serviceaccount-credential
author: claude-opus-5-5 (ci-pool-provisioning-leftovers)
created_at: 2026-11-13T07:06:06Z
---

## Proposal: A non-root reader of a pool server's cluster state reads a scoped read-only credential, never the k3s admin kubeconfig

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph, "A scoped credential for non-root readers.", to non-functional-requirements.md section "Runner-pool node rebuild recipe", directly after "Live converge from the control node.". A non-root login on a pool server node that reads cluster state MUST read it through a scoped, read-only credential that the node-provisioning stage provisions from committed source, never through the k3s admin kubeconfig. That credential's role grants only get, list and watch, covers the kinds the ci-runner/k3s READMEs' liveness reads use (nodes and the ARC custom resources included), and grants nothing on secrets, pods/exec, pods/attach, pods/portforward or serviceaccounts/token. Once every non-root reader uses it, the admin kubeconfig is written with mode 0600. Adds one scenario to scenarios.md. The NFR paragraph carries no H2 of its own, so the only new heading is the scenario's.

### Motivation

Plan ci-pool-provisioning-leftovers (epic livespec-dev-tooling-fby3sx) carries livespec-dev-tooling-nmrf34: the k3s admin kubeconfig /etc/rancher/k3s/k3s.yaml on poweredge-xubuntu is mode 0644 and should be 0600. Measured on nmrf34: on poweredge-xubuntu kubectl resolves to /usr/local/bin/k3s, and with KUBECONFIG unset `kubectl auth whoami` run as the operator login returns system:admin in system:masters, read through that 0644 file. Every operator or agent read of the form `ssh <operator>@poweredge-xubuntu kubectl get ...`, which fleet_host_guard.py allows, therefore runs as cluster-admin, and a bare flip to 0600 would break all of them at the next k3s start. legacy-coordinator-agent approved splitting nmrf34 into livespec-dev-tooling-cfojg2 (this credential), livespec-dev-tooling-dwmssn (README apply path) and livespec-dev-tooling-df6kvw (the 0600 flip, blocked by both), with the conditions that the role is get/list/watch only and excludes secrets, pods/exec, pods/attach, pods/portforward and serviceaccounts/token. The launch screen held cfojg2 at spec-change tier: at v208 the ratified "Runner-pool node rebuild recipe" text states no credential for non-root readers.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Runner-pool node rebuild recipe", insert the following paragraph immediately after the paragraph that begins "**Live converge from the control node.**":

**A scoped credential for non-root readers.** A non-root login on a pool server node that reads cluster state MUST read it through a scoped, read-only credential that the node-provisioning stage provisions from committed source, and MUST NOT read it through the k3s admin kubeconfig. That credential's role MUST grant only the verbs `get`, `list` and `watch`; it MUST cover the resource kinds that the liveness reads documented under `ci-runner/k3s/` use, nodes and the ARC custom resources included; and it MUST grant nothing on `secrets`, `pods/exec`, `pods/attach`, `pods/portforward` or `serviceaccounts/token`. The node-provisioning stage MUST make that credential the one a non-root login shell on the node resolves by default. Once every non-root reader of the admin kubeconfig reads the scoped credential instead, the admin kubeconfig MUST be written with mode `0600`.

In SPECIFICATION/scenarios.md, append the following scenario:

## Scenario: a non-root operator login on a pool server reads cluster state through the scoped read-only credential

Given the node-provisioning apply `just ansible-apply ansible/ci-pool.yml` has run against poweredge-xubuntu

When the non-root operator login on poweredge-xubuntu runs `kubectl auth whoami` with no KUBECONFIG of its own

Then the identity printed MUST be the scoped read-only ServiceAccount, not system:admin

And `kubectl get nodes` run by that login MUST list the cluster's nodes

And `kubectl auth can-i get secrets` run by that login MUST print `no`

The revise that accepts this proposal MUST add a tests/heading-coverage.json row for the new scenario heading, a spec-first TODO row naming its tier and an owning work_item (livespec-dev-tooling-cfojg2), and MUST register it in tests/heading-coverage-debt.json.
