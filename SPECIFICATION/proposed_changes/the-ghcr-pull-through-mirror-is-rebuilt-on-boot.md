---
topic: the-ghcr-pull-through-mirror-is-rebuilt-on-boot
author: claude-opus-5-5 (ci-pool-provisioning-leftovers)
created_at: 2026-11-13T18:36:32Z
---

## Proposal: The ghcr pull-through image mirror is rebuilt on boot and role-managed on every pool node

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph, "The image pull-through mirror is rebuilt, never hand-staged.", to non-functional-requirements.md section "Runner-pool node rebuild recipe", directly after "Re-runnable, and destructive only on consent.". It states two halves. The CI server's boot converge rebuilds the ghcr.io pull-through image mirror from manifests installed on the host from this tree, so a boot from an empty datastore restores it with no manual step. Every ci_pool node's /etc/rancher/k3s/registries.yaml is installed by ansible/ci-pool.yml from the committed installer and template, never restarts k3s or containerd, and falls back to ghcr.io when the mirror is unreachable. It also adds one scenario to scenarios.md. This is a spec catch-up: the behaviour already shipped (cluster half 9e7250164, node half 34e6eed5b, first released in v1.196.0), and SPECIFICATION does not mention the registry mirror anywhere.

### Motivation

Work item livespec-dev-tooling-y1t5 (plan ci-pool-provisioning-leftovers, epic livespec-dev-tooling-fby3sx) found on 2026-09-09 that a poweredge reboot rebuilt every CI cluster object except the ghcr pull-through registry mirror. converge-ci-stack.sh had no step for it, so after every boot from the volatile tmpfs datastore the mirror was silently gone and each image pull paid a failed dial before falling back to ghcr.io. The cluster half was fixed by 9e7250164 (boot converge step 8d plus staging the mirror's manifests in the installed tree), and a real reboot proved it on 2026-10-17: deploy/registry-mirror was recreated with no manual step. The node half, registries.yaml, was a hand-written file on poweredge and absent on the agents. livespec-dev-tooling-e2gv6n moved it into the registry_mirror_node role in ansible/ci-pool.yml (34e6eed5b, v1.196.0). On 2026-11-13 at master 4b26a47eb, `just ansible-drift ansible/ci-pool.yml --limit poweredge-xubuntu --tags registry_mirror_node` read changed=0, with the installer's dry run reporting ours-unchanged. On 2026-11-13 dispatcher classify-tier recorded y1t5 at spec-change tier, because SPECIFICATION never mentions the registry mirror. legacy-coordinator-agent then ruled that y1t5 closes resolved-out-of-band, with this proposal as the owed spec catch-up. Stating the behaviour keeps a later change from dropping either half without a ratified clause to say it was required.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Runner-pool node rebuild recipe", insert the following paragraph immediately after the paragraph that begins "**Re-runnable, and destructive only on consent.**":

**The image pull-through mirror is rebuilt, never hand-staged.** The pool's ghcr.io pull-through image mirror MUST be among the cluster objects the CI stack converge applies when the CI server boots (`ci-runner/k3s/phase2/reconstruct/converge-ci-stack.sh`, run at boot by `converge-ci-stack.service`). The CI stack converge MUST apply it from the mirror's manifests and converge script, which the node-provisioning stage installs on the CI server from `ci-runner/k3s/phase2/warm-cache/registry-mirror/`. A boot that starts the cluster from an empty datastore therefore restores the mirror with no manual step and no file staged by hand. A failure to converge the mirror MUST NOT fail the rest of the CI stack converge; the converge MUST report it, and image pulls then go to ghcr.io directly. On every pool node (each member of the `ci_pool` group of `ansible/inventory/legacy.yml`), `/etc/rancher/k3s/registries.yaml` MUST be installed by `ansible/ci-pool.yml` through the committed installer `install-registry-mirror.sh` and its template in that same directory, rendered for the node's cluster role from its committed profile, so that the drift report reads it unchanged exactly when the node's file is the installer's rendering. That install MUST NOT restart k3s or containerd; the node takes the file at its next k3s start. A node whose mirror endpoint is unreachable MUST still pull its images from ghcr.io.

In SPECIFICATION/scenarios.md, append the following scenario:

## Scenario: a pool reboot restores the ghcr pull-through mirror and every node's registries.yaml is the role's rendering

Given the CI server boots with an empty cluster datastore, and every pool node has been provisioned by `ansible/ci-pool.yml`

When the CI stack converge that `converge-ci-stack.service` runs at boot finishes

Then the `ci-registry-mirror` namespace MUST hold the mirror's Deployment and Service, applied from the manifests installed on the host from `ci-runner/k3s/phase2/warm-cache/registry-mirror/`, with no file staged by hand

And `just ansible-drift ansible/ci-pool.yml --tags registry_mirror_node` MUST report no change on any node whose `/etc/rancher/k3s/registries.yaml` is the installer's rendering for that node

And neither the converge nor the role MUST have restarted k3s or containerd on any node

And a node that cannot reach the mirror MUST still pull its images from ghcr.io

The revise that accepts this proposal MUST add a tests/heading-coverage.json row for the new scenario heading. tests/livespec_dev_tooling/test_ci_pool_registry_mirror_node.py and tests/livespec_dev_tooling/test_ci_runner_k3s_boot_converge_reachability.py already exercise the two halves, so the row MAY name one of them as its test rather than a TODO.
