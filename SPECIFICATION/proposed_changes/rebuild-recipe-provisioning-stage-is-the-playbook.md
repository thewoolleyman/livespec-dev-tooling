---
topic: rebuild-recipe-provisioning-stage-is-the-playbook
author: claude-fable-5-1
created_at: 2026-10-10T06:12:00Z
---

## Proposal: Runner-pool node rebuild recipe — the node-provisioning stage is the committed playbook applied from the control node, not a shell runbook on the node

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Amend the existing `## Runner-pool node rebuild recipe` section's **One procedure, staged.** paragraph so the recipe's node-provisioning stage — today the ordered node-local shell runbook `ci-runner/k3s/phase2/install-node.sh`, run with `sudo` ON the node — becomes the committed Ansible playbook `ansible/ci-pool.yml`, applied FROM the control node `vps` by `just ansible-apply ansible/ci-pool.yml`, with the drift report `just ansible-drift ansible/ci-pool.yml` run and read first. The bare-metal stages and the pinned k3s install remain committed shell, and the amendment says why: they run before k3s exists, so there is no converged node for the provisioning layer to reach. No `## ` heading changes, so `tests/heading-coverage.json` needs no co-edit; the section's mapped test module `tests/spec/test_runner_pool_node_rebuild.py` is rewritten in the same change set to hold the playbook to the no-embedded-identity rule as the procedure's final stage, to assert the documented sequence's provisioning step is the playbook apply and names no node-local shell runbook, and to assert the playbook selects the `ci_pool` inventory group rather than a node.

### Motivation

livespec plan `gitops-deployment-discipline` (epic `livespec-qurhq2`), design record `plan/gitops-deployment-discipline/research/000-failures-root-causes-and-binding-fixes-2026-09-12.md` §3, failure 2 ("inverted layers"): the Ansible migration made `ansible/roles/*` the installers, yet the ratified recipe still names the shell runbook as its provisioning stage — the inverted-layer hazard the plan exists to remove, written into the specification. Rule 3 of the discipline is that a mechanism change lands in the layer the automation APPLIES; while the spec names the shell runbook, a reader following the spec exactly lands it in the retired layer. `ansible/ci-pool.yml` is on master with parity to the runbook (livespec-dev-tooling PR #2274, merged 2026-09-12), and ledger child C5 `livespec-lfie5z` retires the runbook next; C5 is blocked on this amendment because deleting `install-node.sh` while the ratified recipe names "the ordered node-local runbook" would leave the specification binding a stage that no longer exists (`research/001-definition-of-done-and-rescoping-2026-10-10.md` §"What the statement keeps and what it defers"). This proposal is ledger child C12 `livespec-obsinx`, which carries the plan's assertion 3 together with C5; it carries ONLY this finding — the sibling `## Host provisioning tree` finding is deferred to a follow-up plan by the maintainer's 2026-10-10 ruling and is not part of this proposal.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Runner-pool node rebuild recipe", paragraph **One procedure, staged.**, replace this sentence fragment, which today reads verbatim:

> and that stage MUST precede the pinned k3s install and the ordered node-local runbook, whose preconditions (an installed operating system; an installed k3s and its admin kubeconfig) the bare-metal stage MUST establish.

with:

> and that stage MUST precede the pinned k3s install and the node-provisioning stage, whose preconditions (an installed operating system; an installed k3s and its admin kubeconfig) the bare-metal stage MUST establish. The node-provisioning stage MUST be the committed Ansible playbook `ansible/ci-pool.yml`, applied from the control node `vps` by `just ansible-apply ansible/ci-pool.yml` against the node's entry in `ansible/inventory/legacy.yml` (whose `cluster_role` selects the server-only and agent-only roles), and the drift report `just ansible-drift ansible/ci-pool.yml` MUST be run and read before that apply; the stage MUST NOT be a shell runbook executed on the node. The bare-metal stages and the pinned k3s install remain committed shell because they run before k3s exists, so the provisioning layer has no converged node to reach until they have run.

and replace the paragraph's final sentence, which today reads verbatim:

> The documented rebuild sequence MUST name the bare-metal stage as its first step, so that a rebuild done exactly as written starts from empty storage and not from a prepared disk.

with:

> The documented rebuild sequence MUST name the bare-metal stage as its first step, so that a rebuild done exactly as written starts from empty storage and not from a prepared disk, and MUST name the playbook apply as its node-provisioning step, so that a rebuild done exactly as written lands every node-local facility through the layer the automation applies.

Every other sentence of the section is unchanged. The section's `## ` heading is unchanged, so its `tests/heading-coverage.json` row (mapped to `tests.spec.test_runner_pool_node_rebuild.test_no_stage_of_the_procedure_embeds_a_value_that_belongs_to_one_node`) stays as it is; that test module is rewritten in the same change set so its procedure list names `ansible/ci-pool.yml` in place of `ci-runner/k3s/phase2/install-node.sh`, asserts the documented sequence's provisioning step is `just ansible-apply ansible/ci-pool.yml` and that no step names `install-node.sh`, and asserts the committed playbook carries one play whose `hosts:` is `ci_pool`. `ci-runner/k3s/README.md` §"Rebuild sequence" step 4 is the documentation the amended clause binds and is rewritten with it; the README's "Files" table rows describing `phase2/install-node.sh` are left for C5 `livespec-lfie5z`, which deletes that file.
