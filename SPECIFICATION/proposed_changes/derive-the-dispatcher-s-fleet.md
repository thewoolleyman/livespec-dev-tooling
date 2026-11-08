---
topic: derive-the-dispatcher-s-fleet
author: claude-opus-5-5
created_at: 2026-11-08T15:36:51Z
---

## Proposal: The committed run caps of every sandbox-placing Fabro instance fit within the ci_pool hosts' factory pod budgets

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend §"Fabro factory registry" so that, while any ci_pool host declares a factory_pod_budget, the sum of every sandbox-placing Fabro instance's committed max_concurrent_runs must not exceed the sum of the ci_pool hosts' resolved budgets. A check in the aggregate refuses a tree that breaks this and names the caps, the budgets and both sums. max_concurrent_runs stays the one number per queue, so the run-cap file this section already renders remains the only launch-cap source and no second, budget-derived value is rendered. Three scenarios cover the refusal, the class-wide default and the retired state.

### Motivation

livespec-dev-tooling#3799 adds a per-node `factory_pod_budget` (gmktec-xubuntu 6, poweredge-xubuntu 15, hp-xubuntu 0; sum 21) as the TEMPORARY fixed factory-vs-CI CPU share the maintainer adopted on 2026-11-08 ("OK, go with fixed CPU share, as a temporary workaround to a better solution"; plan gmktec-factory-placement, livespec-dev-tooling-me5aqz, research note 003). Its reconciler admits a factory node only while the node holds fewer sandbox pods than its budget, and fails open when every node is full. A sandbox's first placement that no node admits would otherwise wait out sandbox-driver-kubernetes' 600 s start timeout and fail as an infrastructure failure. So the budgets only hold the CPU share while the launch caps of every instance that places sandboxes stay at or below their sum. Today that rule is prose in the role's HOST_VARS.md ("lower the fleet cap FIRST, then the budget"), and nothing enforces it.

legacy-coordinator-agent made enforcing it condition 1 of the mechanism's approval, under its duties §10 rule that one queue gets one number. Work item livespec-dev-tooling-zsbvp3 carries the work. Its spec-change-tier record names this topic, and the coordinator will approve the item only once this proposal is ratified.

Why a check over committed values, and not a value rendered from the budget sum: zsbvp3's draft Definition of Done asked for a fleet cap rendered as the budget sum minus the other instances' caps. That would be a SECOND number for the petri queue, beside the `max_concurrent_runs` this section already renders into `petri.max_concurrent_runs` through livespec-dev-tooling-o5xpdy, the one renderer. legacy-dispatcher-agent committed on 2026-11-04 to point the launchers at that file. The proposal keeps `max_concurrent_runs` as the only number for each queue and makes the budget sum a ceiling that a commit cannot cross. A change that lowers a budget then has to lower the caps in the same tree, which turns the "lower the cap first" ordering into a mechanical rule.

Fleet scope (coordinator rule K): the rule counts every `ci_pool` host and every sandbox-placing instance on any host, so a node or instance enrolled later is counted without editing the check. Budgets resolve through Ansible's own precedence, so homelab-k8s-worker-nodes' planned class-wide container-worker default of 1 counts once for each worker host that does not override it, and an undeclared host counts 0, as the reconciler treats it. The rule retires itself when the temporary budgets are deleted at the workaround's end condition: with no budget declared, the check passes.

Measured on origin/master 7457a68e (2026-11-08): `gmktec-xubuntu`'s committed sandbox-placing instances declare `max_concurrent_runs` 20 (`fabro-server`), 16 (`fabro-server-candidate`) and 2 (`fabro-server-mi-homelab`). That sums to 38 against the budget sum of 21, while the live launch caps are 18, 1 and 2 (sum 21), held in runtime files and launcher config. The check therefore must not be armed before the committed values are brought to the launch caps (confirm the reader before the write). The implementing change lowers them in the same tree that adds the check, or earlier. Lowering petri's `max_concurrent_runs` from 20 to 18 retires the two-run server headroom that coordinator ruling R71 kept, which is the intended result of one number per queue.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Fabro factory registry", insert this paragraph directly after the paragraph headed "Run caps rendered beside the registry.":

**Run caps fit the factory pod budgets.** A host's *factory pod budget* is the value Ansible resolves for `factory_pod_budget` in that host's `hostvars`, so a `host_vars` value overrides a class-wide `group_vars` default and a host that resolves none contributes 0. A *sandbox-placing instance* is a `fabro_server_instances` mapping, on any inventory host, whose `sandbox_providers` declares at least one provider whose `path` names an executable whose file name begins `sandbox-driver-kubernetes`. Whenever at least one host in the inventory's `ci_pool` group resolves a factory pod budget, the sum of the committed `max_concurrent_runs` of every sandbox-placing instance MUST be less than or equal to the sum of the factory pod budgets of every host in the `ci_pool` group. This repository's check aggregate MUST include a check that reads the committed inventory and refuses a tree that breaks that inequality, and its refusal MUST name each sandbox-placing instance with its `max_concurrent_runs`, each `ci_pool` host with its factory pod budget, and both sums. The same check MUST refuse a resolved `factory_pod_budget` that is not a non-negative integer, naming the host. When no `ci_pool` host resolves a factory pod budget, the check MUST pass on that inequality, so that removing every budget retires the rule without a further change. A `max_concurrent_runs` value is the one committed number for its factory's queue: the run-cap file this section renders from it is the file a launcher reads as that factory's launch cap, so this repository MUST NOT commit a second number for the same queue, and this paragraph MUST NOT be satisfied by a second renderer that derives a different value from the budget sum.

In `SPECIFICATION/scenarios.md`, insert these three scenarios directly after `## Scenario: the fabro-hosts play renders each registered factory's run cap from its instance's max_concurrent_runs`:

## Scenario: a run cap above the factory pod budget sum is refused at commit

Given the `ci_pool` group holds `gmktec-xubuntu` with `factory_pod_budget: 6`, `poweredge-xubuntu` with `factory_pod_budget: 15` and `hp-xubuntu` with `factory_pod_budget: 0`

And `gmktec-xubuntu`'s `fabro_server_instances` declares three sandbox-placing instances, `fabro-server` with `max_concurrent_runs: 20`, `fabro-server-candidate` with `max_concurrent_runs: 1` and `fabro-server-mi-homelab` with `max_concurrent_runs: 2`

When the repository's check aggregate runs

Then the run-cap budget check MUST fail

And its refusal MUST name `fabro-server` 20, `fabro-server-candidate` 1, `fabro-server-mi-homelab` 2, the cap sum 23, each of the three hosts with its budget, and the budget sum 21

Given `fabro-server`'s `max_concurrent_runs` is changed to `18` and nothing else is changed

When the repository's check aggregate runs

Then the run-cap budget check MUST pass

## Scenario: a class-wide budget default counts once for every host that does not override it

Given the `ci_pool` group holds `gmktec-xubuntu` with `factory_pod_budget: 6` in its `host_vars` and two container-worker hosts that declare no `factory_pod_budget` of their own

And a `group_vars` file for a group containing both container-worker hosts declares `factory_pod_budget: 1`

And the sandbox-placing instances' `max_concurrent_runs` sum to `8`

When the repository's check aggregate runs

Then the run-cap budget check MUST count a budget sum of 8 and MUST pass

Given one of the container-worker hosts declares `factory_pod_budget: 0` in its own `host_vars`

When the repository's check aggregate runs

Then the run-cap budget check MUST count a budget sum of 7 and MUST fail, naming that host with budget 0

## Scenario: with no factory pod budget declared the run-cap budget check passes

Given no host in the `ci_pool` group resolves a `factory_pod_budget`

And the sandbox-placing instances' `max_concurrent_runs` sum to `23`

When the repository's check aggregate runs

Then the run-cap budget check MUST pass

