---
topic: host-provisioning-tree
author: claude-opus-5-5
created_at: 2026-10-19T01:49:26Z
---

## Proposal: Host provisioning tree — every inventory host is reachable by a playbook, and a replaced installer is retired

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add a new final `## Host provisioning tree` section to non-functional-requirements.md. It states two obligations over the committed `ansible/` provisioning tree. (a) Every host declared in the provisioning inventory MUST be selected by the `hosts:` of at least one committed play, with groups and host patterns resolved. (b) A role that declares it replaces an in-repository shell installer (`# Replaces <path>`) MUST NOT coexist with that installer; a partial replacement is stated in prose, and a claim naming another repository's path is outside the obligation. (c) Both are asserted by the `just check` aggregate through two repo-private checks that fail on any violation and report a vacuous run as vacuous. They land armed, with no severity lever, because the live tree already meets both: all four inventory hosts are selected by at least one play, and all fourteen in-repository `# Replaces` paths are already deleted (measured on origin/master 2026-10-19). The section adds one `## ` heading, so `tests/heading-coverage.json` is co-edited with a TODO entry owned by livespec-hsdguf.

### Motivation

livespec plan `gitops-deployment-instructions-and-enforcement` (epic `livespec-okypgg`), child C4 `livespec-hsdguf`; design in livespec `plan/archive/gitops-deployment-discipline/research/000-failures-root-causes-and-binding-fixes-2026-09-12.md` §2–§3. Phase 3 of the Ansible migration built the k3s-node roles and the `ci_pool` inventory group, but no playbook targeted `ci_pool`. So `just ansible-drift` and `just ansible-apply` both skipped the two k3s nodes, and they sat at 2026-09-08 code while every playbook was green: coverage was never an obligation, so the tree could not see the drift. In the same window a session edited the retired installer `install-reapply-unit.sh` as if it were live, while the `node_extended_resource` role that actually deploys the file stayed stale, because the retired installer still sat in the tree beside its replacement. The research note binds each failure to a mechanical check and to a spec clause this repository ratifies, so that the checks assert something the specification says. This supersedes the 2026-09-12 draft of the same topic, which was never filed: its second finding (the rebuild-recipe node-provisioning stage) was ratified separately as v068, and its warn-level lever is no longer needed now that the tree conforms.

### Proposed Changes

Append the following section to `SPECIFICATION/non-functional-requirements.md` as its new final section, directly after the last paragraph of `## Docker engine install guard`. That paragraph currently ends verbatim: `The recovery bound — one in-flight operation's budget plus 30 seconds, plus the dead-man's 60-second interval, plus one rollback budget — is claimed for killed, hung or crashing processes, not for kernel or storage failure.`

```markdown
## Host provisioning tree

**Scope.** The `ansible/` tree is this repository's committed provisioning model for the fleet's legacy Ubuntu hosts: the inventory that declares them, the playbooks that select them, and the roles that install onto them. A host reaches its converged state only through a play whose `hosts:` selects it, applied from the control node by the committed drift and apply commands, from committed source. There is deliberately no checkout on a target. The obligations below keep that model whole. The agent-facing statement of the discipline they serve is livespec's `.ai/gitops-deployment-discipline.md`, together with this repository's own `.ai/gitops-deployment.md` layer map.

**Every inventory host is reachable by a playbook.** Every host declared in the provisioning inventory (`ansible/inventory/*.yml`) MUST be selected by the `hosts:` of at least one play in a committed playbook under `ansible/`, with inventory group membership and Ansible host patterns resolved, so that both the drift report and the apply reach it. A declared host that no play selects is a defect in the provisioning tree, never an accepted state: the inventory declares it managed while nothing manages it, and no committed command can see its drift.

**A replaced installer is retired.** A role that declares it replaces a shell installer, by a `# Replaces <path>` claim in one of its files naming a path in this repository, MUST NOT coexist with that installer: the named path MUST NOT exist in the tree once the role lands, and the commit that deletes it MUST cite the pre-deletion commit in its body. A claim naming a path in another repository is outside this obligation, since that repository owns its own tree. A role that replaces only part of an installer MUST say so in prose rather than in the claim form, so that an installer which legitimately survives for its other half is never the subject of a retirement claim.

**Enforced in the aggregate.** Both obligations MUST be asserted by this repository's `just check` aggregate, as `check-ansible-inventory-hosts-covered` and `check-ansible-replaced-installers-retired`. They are repo-private checks, outside the canonical fleet-universal slug set, because this repository alone owns the provisioning tree. Each MUST fail the aggregate on any violation. A run that inspects nothing, with no inventory host or no in-repository replacement claim, MUST report itself as vacuous rather than as a pass.
```

Co-edit `tests/heading-coverage.json` in the same revise pass, because this proposal adds one `## ` heading. Append the following entry directly after the existing entry whose `heading` is `## Docker engine install guard`, so that file order follows heading order:

```json
{
  "spec_root": "SPECIFICATION",
  "spec_file": "non-functional-requirements.md",
  "heading": "## Host provisioning tree",
  "test": "TODO",
  "reason": "A unit-tier test over a fixture provisioning tree is owed for this heading: an inventory host that no play selects fails check-ansible-inventory-hosts-covered with the host and its groups named, and an in-repository '# Replaces <path>' whose path exists fails check-ansible-replaced-installers-retired with the file, line and path named. livespec-hsdguf owns it.",
  "work_item": "livespec-hsdguf"
}
```

Nothing else in the specification mentions inventory coverage or installer retirement, so no other statement needs amending. The `## ` heading set of every other spec file is unchanged.

