---
topic: the-root-dev-host-retention
author: claude-sonnet-5-5
created_at: 2026-11-18T17:29:29Z
---

## Proposal: A privileged unit executes and resolves only from root-controlled trees

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Root or otherwise privileged units this repository ships MUST NOT execute a file from, or resolve a plugin or code path through, a tree a non-root account can write. The dev host retention script applies it by skipping an unsafe checkout with a named SKIP while still cleaning aged terminal gate runs from safe checkouts.

### Motivation

Tracked as livespec-dev-tooling-jm2tkj (spec-change tier, linked topic the-root-dev-host-retention), filed at the ruling of legacy-coordinator-agent, who ruled it a security guarantee and therefore spec scope. A fleet sweep recorded on livespec-dev-tooling-o6u7jm found two hits: the incident-merge runner's plugin registry, which pointed at a user-writable installed_plugins.json whose installPath the root runner would execute (repaired in the in-flight o6u7jm change), and dev-tooling retention's executing dev-tooling/gate-run.sh from ubuntu-writable checkouts at dev-host-retention.sh:263. Either lets any process that can write as the ubuntu user obtain root execution. The rule is stated generally so a third unit cannot repeat the shape. Placement follows the coordinator's named generalization target, the 'Dev host disk retention' section; a reviser MAY relocate the general paragraph to 'Host provisioning tree' if that reads better, and should keep the retention-specific paragraph here. In-flight survey: open PR livespec-dev-tooling#4699 (branch spec/dev-host-retention-s-uv) amends the uv cache bullet of the same section; this proposal adds a separate paragraph and aligns with it. The pending proposals dev-host-retention-reports-merged-aged-worktrees and the-dev-host-retention-bulk touch other bullets of the section and also align. Implementation is owned by jm2tkj.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Dev host disk retention", add one paragraph immediately before the paragraph that begins **Alert before full.**:

```
**A privileged unit executes and resolves only from root-controlled trees.** This rule binds EVERY unit this repository's provisioning tree installs that runs with root or other elevated privilege, whether a systemd service, a timer's service or a oneshot, and not only the retention units of this section. Such a unit MUST NOT execute a file from, source a file from, or resolve an interpreter, plugin, registry or code path through, any tree that a non-root account can write. A tree is writable by a non-root account when the tree, any directory on its path, or the file itself is owned by a non-root user, or carries a group or other write bit that a non-root account holds. A path under a governed checkout, a user's home directory, a user-owned plugin cache or an installed-plugins registry a user account can write is therefore never an execution or resolution source for a privileged unit. A privileged unit MAY read data from such a tree, but it MUST NOT treat what it reads as code to run or as a path to follow into code.

When a privileged unit needs code that lives in a user-writable tree, it MUST execute a root-owned copy of that code, installed by the provisioning tree, that no non-root account can write, and a unit that finds no such copy MUST refuse to start and name the missing path rather than fall back to the user-writable one.

The retention script applies this rule to the governed checkouts it visits. Before it executes `dev-tooling/gate-run.sh` from a checkout, it MUST verify that the script, every directory from the checkout root to it, and the checkout root itself are owned by root or by the retention user and are not group- or other-writable by any other account. For a checkout that fails that check it MUST NOT execute the script, MUST log `SKIP <store>: <reason>` naming the unsafe path, and MUST continue with its remaining checkouts and steps, never abort. It MUST still clean aged terminal gate runs from every checkout that passes the check.
```

In SPECIFICATION/scenarios.md, add three scenarios at the end of the file:

```
## Scenario: dev host retention skips an unsafe checkout with a named SKIP

Given a governed checkout whose `dev-tooling/gate-run.sh` lies in a directory that a non-root account other than the retention user can write

When the dev host retention run visits that checkout

Then it does not execute that `gate-run.sh`

And it logs a `SKIP` line naming the unsafe path

And it continues with its remaining checkouts and steps

## Scenario: dev host retention still cleans aged terminal gate runs from safe checkouts

Given one governed checkout that fails the writability check and another that passes it

And the passing checkout holds an aged terminal gate run

When the dev host retention run completes

Then the aged terminal gate run in the passing checkout is removed

And the run exits without aborting on the unsafe checkout

## Scenario: a privileged unit refuses to start rather than resolve code through a user-writable tree

Given a root unit this repository provisions whose code is installed as a root-owned copy

And that copy is absent

When the unit starts

Then it exits non-zero naming the missing root-owned path

And it does not execute any file from a tree a non-root account can write
```
