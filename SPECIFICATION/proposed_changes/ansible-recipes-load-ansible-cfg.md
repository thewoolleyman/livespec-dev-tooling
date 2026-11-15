---
topic: ansible-recipes-load-ansible-cfg
author: claude-opus-5-5 (tenant-fleet-credentials seat)
created_at: 2026-11-15T15:08:45Z
---

## Proposal: The ansible recipes load the provisioning tree's own ansible.cfg

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add an obligation under §"Host provisioning tree": every `just` recipe that runs `ansible-playbook` (or any other ansible command) against the provisioning inventory MUST make that command load `ansible/ansible.cfg`, so the settings it commits (pipelining included) are in effect, and the `just check` aggregate MUST assert this. Add a scenario that states the behaviour.

### Motivation

Measured 2026-11-15 (work item livespec-dev-tooling-d2ysfg, found while authoring livespec-ai/livespec-dev-tooling#4799): `just ansible-drift` and `just ansible-apply` run `uvx --from ansible-core==2.21.4 ansible-playbook -i ansible/inventory/legacy.yml ...` from the repository root. Ansible reads `ansible.cfg` only from `ANSIBLE_CONFIG`, the current directory, `~/.ansible.cfg` or `/etc/ansible/ansible.cfg`, so `ansible-config dump` reports `CONFIG_FILE() = None` and nothing in `ansible/ansible.cfg` applies, including `pipelining = True` (line 23). Pipelining is load-bearing for secrets: a task that hands a credential to a target command through `stdin:` under `no_log` relies on the module and its arguments travelling over the ssh pipe instead of being written to a remote temporary file. `ansible/claim-token-race-drill.yml` (lines 45-46) states exactly that assumption, and the poweredge-xubuntu bootstrap-key mint in #4799 carries an issuer session on stdin. Today each such playbook has to set `ANSIBLE_CONFIG` by hand or refuse on its own; the committed config is silently ignored by the sanctioned entry points. The obligation belongs in non-functional-requirements.md because it governs this repository's own provisioning tree (a contributor-facing concern), beside the existing §"Host provisioning tree" obligations.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Host provisioning tree", insert the following paragraph immediately after the **Enforced in the aggregate.** paragraph:

> **The recipes load the tree's own configuration.** Every `just` recipe that runs an ansible command (`ansible-playbook`, `ansible`, `ansible-config`, `ansible-inventory`) against the provisioning inventory MUST make that command load `ansible/ansible.cfg` as its configuration file, whatever directory the recipe is run from, by exporting `ANSIBLE_CONFIG` as that file's absolute path. A playbook MAY rely on any setting `ansible/ansible.cfg` commits, and a playbook that hands a secret to a target command through a task's `stdin:` MAY rely on the committed `pipelining = True` to keep that value off the target's disk. A recipe MUST NOT run an ansible command that resolves no configuration file or a different one. This repository's `just check` aggregate MUST include `check-ansible-recipes-load-config`, a repo-private check that runs each such recipe's ansible invocation from the repository root in a mode that changes no host (for example `ansible-config dump --only-changed`) and fails when the resolved configuration file is not `ansible/ansible.cfg` or when `DEFAULT_PIPELINING` is not `True`.

In `SPECIFICATION/scenarios.md`, add the following scenario, and in `tests/heading-coverage.json` link it, and the new paragraph's heading coverage, to the test that implements `check-ansible-recipes-load-config`:

```gherkin
## Scenario: an ansible recipe run from the repository root loads the provisioning tree's configuration

Given `ansible/ansible.cfg` sets `pipelining = True`

When an operator runs `just ansible-drift` or `just ansible-apply` from the repository root

Then the ansible command the recipe runs MUST resolve `ansible/ansible.cfg` as its configuration file

And `DEFAULT_PIPELINING` MUST be `True` for that command

And `check-ansible-recipes-load-config` MUST fail when a recipe's ansible invocation resolves no configuration file
```

The implementation is work item livespec-dev-tooling-d2ysfg (factory), dispatched after this proposal is ratified.
