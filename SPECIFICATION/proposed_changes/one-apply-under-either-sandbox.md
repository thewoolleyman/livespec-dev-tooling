---
topic: one-apply-under-either-sandbox
author: claude-opus-5-5
created_at: 2026-11-13T02:40:00Z
---

## Proposal: A role entry point a playbook includes more than once under tags shares one tag across those inclusions

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add one paragraph to §"Host provisioning tree", **A repeated tagged role entry point shares a tag.**

- When a committed playbook under `ansible/` includes the same role ENTRY POINT more than once, and at least one of those inclusions carries a tag, every one of them MUST carry at least one tag that all of them carry. A role entry point is the role plus its `tasks_from`, with `main` when none is given.
- A single `--tags` apply under the shared tag then converges every copy the role installs in that playbook.
- The check aggregate enforces it as `check-ansible-repeated-role-shared-tag`.

One scenario covers:
- the refusal;
- the shared-tag pass and convergence;
- the same-tag repeat that already conforms;
- an untagged repeat that is out of scope;
- distinct entry points of one role, which are not a repeat.

### Motivation

Work item livespec-dev-tooling-t5fbgf was held at the ledger screen on the spec-change tier, with this linked topic, because no ratified clause states the rule. legacy-coordinator-agent (session 56ce1bcd) routed it as a spec-tier orphan on 2026-11-13. It had first been routed as a coordinator-duties §10 STRUCTURAL finding ("a change needed in more than one place").

Measured on 2026-11-12 under livespec-dev-tooling-e2gv6n (plan ci-cache-optimization):

- `ansible/ci-pool.yml` includes `sandbox_image_warm` twice. One inclusion is under tag `sandbox_image_warm_containerd`: the factory warm, runner `/usr/local/sbin/livespec-sandbox-image-warm-containerd`. The other is under tag `sandbox_image_warm_ci_containerd`: the CI warm, runner `/usr/local/sbin/livespec-sandbox-image-warm-ci-containerd`. Both install the SAME `ansible/roles/sandbox_image_warm/files/sandbox-image-warm.sh`.
- e2gv6n's apply on 2026-11-11 05:49Z used only the CI tag. That apply was of master 34e6eed5b, which changed that script to warm workflow-pinned tags. The factory warm's copy therefore stayed on the pre-change script on hp-xubuntu, gmktec-xubuntu and poweredge-xubuntu.
- It read as drift on every factory-warm read until the factory tag was applied at 2026-11-12 03:54Z (gate 20261112T035417Z-2804601). Nothing errored at any point, so the stale copy was silent.

Still true on origin/master c488172c4 (read 2026-11-13): the two `ci-pool.yml` inclusions carry `[sandbox_image_warm_containerd]` and `[sandbox_image_warm_ci_containerd]`, with no tag in common. No check in the aggregate looks at repeated role inclusions.

**What counts as a repeat, and when the rule applies.**

- A repeat is the same role ENTRY POINT included again in one playbook: the same role with the same `tasks_from`, with `main` when none is given. Two inclusions of one role with different `tasks_from` run different task files, so they are not a repeat.
- The rule applies only when at least one of the repeated inclusions carries a tag. An untagged repeat runs under any untagged apply, so it cannot be split by `--tags`.
- An inclusion "carries" a tag when the tag is on its `roles:` entry or task, or is inherited from the play or an enclosing block.
- For `include_role` the tag MUST also be passed through `apply: {tags: [...]}`. Without it, `--tags` runs the include task and skips every task of the role, so the copy is not converged.

**Fleet scope, read on origin/master 2026-11-13 over every playbook under `ansible/`.**

- `sandbox_image_warm` in `ansible/ci-pool.yml` is the only repeated, tagged entry point with no shared tag. It is the case this rule fixes.
- `ansible/fabro-hosts.yml` repeats `tailscale_serve` twice, `container_reclaim` and `storage_reclaim`, each under the SAME tag every time. These already conform, and the check MUST accept them.
- EXEMPT, because each is outside the rule as worded:
  - `ansible/fabro-hosts.yml` includes `fabro_server` twice through `include_role`, both untagged.
  - `ansible/lan-ssh-fallback.yml` includes `lan_ssh_fallback` five times with distinct `tasks_from` (`keys.yml`, `control_node_key.yml`, `server.yml`, `client.yml` and `verify.yml`, all untagged), so they are distinct entry points.
- `sandbox_image_warm` is also included once in `ansible/fabro-hosts.yml` (tag `sandbox_image_warm`) and once in `ansible/former-sandbox-hosts.yml` (tag `sandbox_image_warm_docker_retire`, state absent). The rule is per playbook, so those single inclusions are out of its scope.

The rule pins every role entry point, not only this one, so the next tagged entry point that gains a second inclusion cannot reopen the gap. Either remedy satisfies it: add a shared tag (for example `sandbox_image_warm_runner`) beside each inclusion's own tag, or move the shared install into a task file tagged once. The proposal requires the property, not the shape.

### Proposed Changes

**1. `non-functional-requirements.md` §"Host provisioning tree".** After the last paragraph of the section, insert:

> **A repeated tagged role entry point shares a tag.** A role ENTRY POINT is a role together with the task file an inclusion runs: its `tasks_from`, or `main` when none is given. When a committed playbook under `ansible/` includes the same role entry point more than once, counting every `roles:` entry and every `include_role` or `import_role` task of every play in that playbook, and at least one of those inclusions carries a tag, every one of those inclusions MUST carry at least one tag that every other one of them also carries. An inclusion carries a tag when the tag is on its `roles:` entry or task, or is inherited from its play or an enclosing block. An `include_role` inclusion carries a tag only when that tag is ALSO passed to the role's tasks through `apply: {tags: [...]}`. Without that, a `--tags` run reaches the include and skips every task of the role. Inclusions that all carry the same tag satisfy this. `ansible-playbook <playbook> --tags <the shared tag>` MUST then run every one of those inclusions, so an apply under one tag cannot converge one copy of a role's installed files and leave another stale. Outside this rule are:
>
> - a role entry point included once in a playbook;
> - inclusions of one role with different `tasks_from`, which are different entry points;
> - a repeat none of whose inclusions carries a tag;
> - the same entry point included in different playbooks.
>
> The rule MUST be asserted by this repository's `just check` aggregate as `check-ansible-repeated-role-shared-tag`, a repo-private check beside `check-ansible-inventory-hosts-covered` and `check-ansible-replaced-installers-retired`. The check MUST fail the aggregate on any violation, naming the playbook, the role entry point and the tag set each of its inclusions carries there.

**2. Scenario (`scenarios.md`).** Insert directly after `## Scenario: a held service converges installed and disabled`:

## Scenario: a role entry point a playbook includes twice under unrelated tags is refused, and a shared tag converges both copies

Given a committed playbook under `ansible/` that includes the role `sandbox_image_warm` twice with no `tasks_from`, once with tags `[sandbox_image_warm_containerd]` and once with tags `[sandbox_image_warm_ci_containerd]`

And both inclusions install the role's `files/sandbox-image-warm.sh`, each at its own runner path

When the repository's `just check` aggregate runs

Then `check-ansible-repeated-role-shared-tag` MUST fail, naming the playbook, the role entry point `sandbox_image_warm` (`main`) and the tag set of each inclusion

Given each inclusion also carries the tag `sandbox_image_warm_runner` and nothing else is changed

When the aggregate runs

Then that check MUST pass

And `ansible-playbook <that playbook> --tags sandbox_image_warm_runner` MUST install the current `sandbox-image-warm.sh` at both runner paths

Given a fixture playbook that includes the role `tailscale_serve` twice, each with tags `[tailscale_serve]`

When the aggregate runs

Then that check MUST NOT fail on that playbook

Given a fixture playbook that includes one role through `include_role` three times, untagged, each with a different `tasks_from`

And a fixture playbook that includes one role entry point twice through `include_role`, both untagged

When the aggregate runs

Then that check MUST NOT fail on either playbook

**3. `tests/heading-coverage.json`.** Add one entry in the same revise for the new scenario heading, with:
- `spec_root` `SPECIFICATION`;
- `spec_file` `scenarios.md`;
- `"test": "TODO"`;
- `"work_item": "livespec-dev-tooling-t5fbgf"`;
- a non-empty `reason`.

The reason states that the clause is spec-first and that livespec-dev-tooling-t5fbgf owes the check and its test at the integration tier or above. That test is the real check run against fixture playbooks for the refusal, the shared-tag pass, the same-tag repeat, the distinct-`tasks_from` repeat and the untagged repeat, plus the committed `ansible/ci-pool.yml` with its repaired inclusions. Regenerate `tests/heading-coverage-debt.json` in the same commit.
