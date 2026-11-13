---
topic: one-apply-under-either-sandbox
author: claude-opus-5-5
created_at: 2026-11-13T02:40:00Z
---

## Proposal: A role a playbook includes more than once shares one tag across those inclusions

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add one paragraph to §"Host provisioning tree": **A role included more than once shares a tag.** When a committed playbook under `ansible/` includes one role more than once, every one of those inclusions MUST carry at least one tag that all of them carry. A single `--tags` run under that shared tag then converges every copy the role installs in that playbook. The check aggregate enforces it as `check-ansible-repeated-role-shared-tag`.

One scenario covers the refusal, the pass with a shared tag, the same-tag repeat that is already conforming, and the single-apply convergence.

### Motivation

Work item livespec-dev-tooling-t5fbgf was held at the ledger screen on the spec-change tier, with this linked topic, because no ratified clause states the rule. legacy-coordinator-agent (session 56ce1bcd) routed it as a spec-tier orphan on 2026-11-13. It had first been routed as a coordinator-duties §10 STRUCTURAL finding ("a change needed in more than one place").

Measured on 2026-11-12 under livespec-dev-tooling-e2gv6n (plan ci-cache-optimization):

- `ansible/ci-pool.yml` includes `sandbox_image_warm` twice, under tag `sandbox_image_warm_containerd` (the factory warm, runner `/usr/local/sbin/livespec-sandbox-image-warm-containerd`) and under tag `sandbox_image_warm_ci_containerd` (the CI warm, runner `/usr/local/sbin/livespec-sandbox-image-warm-ci-containerd`). Both inclusions install the SAME `ansible/roles/sandbox_image_warm/files/sandbox-image-warm.sh`.
- e2gv6n's apply on 2026-11-11 05:49Z (master 34e6eed5b, which changed that script to warm workflow-pinned tags) used only the CI tag. The factory warm's copy stayed on the pre-change script on hp-xubuntu, gmktec-xubuntu and poweredge-xubuntu.
- It read as drift on every factory-warm read until the factory tag was applied at 2026-11-12 03:54Z (gate 20261112T035417Z-2804601). Nothing errored at any point, so the stale copy was silent.

Still true on origin/master c488172c4 (read 2026-11-13): the two `ci-pool.yml` inclusions carry the tags `[sandbox_image_warm_containerd]` and `[sandbox_image_warm_ci_containerd]`, with no tag in common, and no check in the aggregate looks at repeated role inclusions.

Fleet scope, measured 2026-11-12 over every playbook under `ansible/`:

- No other role is included more than once under different tags.
- `ansible/fabro-hosts.yml` repeats `container_reclaim`, `storage_reclaim` and `tailscale_serve` under the SAME tag each time. Those already conform, and the check MUST accept them.
- `sandbox_image_warm` also appears once in `ansible/fabro-hosts.yml` (tag `sandbox_image_warm`) and once in `ansible/former-sandbox-hosts.yml` (tag `sandbox_image_warm_docker_retire`, state absent). The rule is per playbook, so those single inclusions are out of its scope.

The rule pins every role, not only this one, so the next role that gains a second inclusion cannot reopen the gap. Either remedy satisfies it: add a shared tag (for example `sandbox_image_warm_runner`) beside each inclusion's own tag, or move the shared install into a task file tagged once. The proposal requires the property, not the shape.

In-flight survey (pending in-tree proposals, 2026-11-13 ~02:40Z, grepped for "Host provisioning tree", `sandbox_image_warm` and `--tags`):

- `place-the-hetzner-xubuntu-dolt` (livespec-dev-tooling-sr46h2) also adds a paragraph to §"Host provisioning tree" after **A held service is still installed by a role.**. The two paragraphs are independent. Whichever revises second goes after the other's paragraph. Relation: `align`.
- `the-factory-runs-resourcequota-restates` names the `--limit` / `--tags` rule of the run-cap files, and `delete-the-dead-phase-1` touches `ci-runner/k3s/` phase-1 artifacts. Neither touches role inclusion tags. Relation: `independent`.

### Proposed Changes

**1. `non-functional-requirements.md` §"Host provisioning tree".** After the paragraph that begins "**A held service is still installed by a role.**" (and after the paragraph `place-the-hetzner-xubuntu-dolt` adds there, if that proposal revises first), insert:

> **A role included more than once shares a tag.** When a committed playbook under `ansible/` includes the same role more than once, counting every `roles:` entry and every `include_role` or `import_role` task of every play in that playbook, every one of those inclusions MUST carry at least one tag that every other one of them also carries. Two inclusions under the same tag already satisfy this. So that an apply under one tag cannot converge one copy of a role's installed files and leave another stale, `ansible-playbook <playbook> --tags <that shared tag>` MUST run every one of those inclusions. A role included once in a playbook is outside this rule, and so is a role included in different playbooks. The rule MUST be asserted by this repository's `just check` aggregate as `check-ansible-repeated-role-shared-tag`, a repo-private check beside `check-ansible-inventory-hosts-covered` and `check-ansible-replaced-installers-retired`. The check MUST fail the aggregate on any violation, naming the playbook, the role and the tag set of each of its inclusions there.

**2. Scenario (`scenarios.md`).** Insert directly after `## Scenario: a held service converges installed and disabled`:

## Scenario: a role a playbook includes twice under unrelated tags is refused, and a shared tag converges both copies

Given a committed playbook under `ansible/` that includes the role `sandbox_image_warm` twice, once with tags `[sandbox_image_warm_containerd]` and once with tags `[sandbox_image_warm_ci_containerd]`

And both inclusions install the role's `files/sandbox-image-warm.sh`, each at its own runner path

When the repository's `just check` aggregate runs

Then `check-ansible-repeated-role-shared-tag` MUST fail, naming the playbook, the role `sandbox_image_warm` and the tag set of each inclusion

Given each inclusion also carries the tag `sandbox_image_warm_runner` and nothing else is changed

When the aggregate runs

Then that check MUST pass

And `ansible-playbook <that playbook> --tags sandbox_image_warm_runner` MUST install the current `sandbox-image-warm.sh` at both runner paths

Given another committed playbook includes the role `tailscale_serve` three times, each with tags `[tailscale_serve]`

When the aggregate runs

Then that check MUST NOT fail on that playbook

**3. `tests/heading-coverage.json`.** Add one entry in the same revise: `spec_root` `SPECIFICATION`, `spec_file` `scenarios.md`, heading `## Scenario: a role a playbook includes twice under unrelated tags is refused, and a shared tag converges both copies`, `"test": "TODO"`, `"work_item": "livespec-dev-tooling-t5fbgf"`, and a non-empty `reason`. The reason states that the clause is spec-first and that livespec-dev-tooling-t5fbgf owes the check and its test, at the integration tier or above: the real check run against fixture playbooks for the refusal, the shared-tag pass and the same-tag repeat, plus the committed `ansible/ci-pool.yml` with its repaired inclusions. Regenerate `tests/heading-coverage-debt.json` in the same commit.
