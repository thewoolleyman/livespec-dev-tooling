---
topic: ansible-recipes-pipelining-setting-name-is-wrong
author: claude-sonnet-5-5
created_at: 2026-11-19T15:59:37Z
---

## Proposal: ansible-recipes-pipelining-setting-name-is-wrong

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Replace the nonexistent setting name `DEFAULT_PIPELINING` with `ANSIBLE_PIPELINING` in the NFR paragraph 'The recipes load the tree's own configuration.' and in the scenario 'an ansible recipe run from the repository root loads the provisioning tree's configuration', and state that `ansible/ansible.cfg` MUST set `pipelining = True` in a section the pinned ansible-core honours (`[connection]` for ansible-core 2.21.4).

### Motivation

Measured 2026-11-19 with the pinned ansible-core 2.21.4: `ANSIBLE_CONFIG=ansible/ansible.cfg uvx --from ansible-core==2.21.4 ansible-config dump --only-changed` shows no pipelining line for the committed `[ssh_connection] pipelining = True`, while a probe config with `[connection]` / `pipelining = True` reports `ANSIBLE_PIPELINING = True`. `DEFAULT_PIPELINING` does not exist in the full dump. The ratified setting name is therefore wrong, and the committed key sits in a section the pinned version ignores, which makes the promise that a task's `stdin:` secret stays off the target's disk false today. Implementation is owned by livespec-dev-tooling-d2ysfg; this proposal changes only the ratified text.

### Proposed Changes

1. non-functional-requirements.md, paragraph 'The recipes load the tree's own configuration.': replace `when `DEFAULT_PIPELINING` is not `True`` with `when `ANSIBLE_PIPELINING` is not `True``; and add the sentence: `ansible/ansible.cfg` MUST set `pipelining = True` in a section the pinned ansible-core honours (`[connection]` for ansible-core 2.21.4), so that the reported setting is `ANSIBLE_PIPELINING`.
2. scenarios.md, scenario 'an ansible recipe run from the repository root loads the provisioning tree's configuration': replace `And `DEFAULT_PIPELINING` is `True` for that command` with `And `ANSIBLE_PIPELINING` is `True` for that command`.
No `## ` heading is added, changed or removed.
