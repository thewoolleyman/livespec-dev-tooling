---
topic: the-factory-runs-resourcequota-restates
author: claude-opus-5-5
created_at: 2026-11-12T21:00:00Z
---

## Proposal: The fleet launch cap is declared once, and the factory namespace quota is checked against it

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add two paragraphs to §"Fabro factory registry":

- **The fleet launch cap is declared once.** The fleet launchers' shared cap, how many factory runs the fleet launches at once across every sandbox-placing instance, gets ONE required committed home: `fabro_fleet_launch_cap` in `ansible/inventory/group_vars/dev_hosts.yml`. It is rendered beside the per-factory run caps as the file `fleet-launch-cap`, a name outside their `<factory>.max_concurrent_runs` pattern, for the launchers to read.
- **The factory namespace quota holds it, term by term.** A check in the aggregate fails when ANY `hard` term of the committed `factory-runs` ResourceQuota that a factory sandbox pod consumes (`requests.cpu`, `limits.cpu`, `requests.memory`, `limits.memory` and `pods`) is below that cap times the largest per-sandbox value of the term, plus one sandbox's value of slack. It also fails when the cap is not declared. The failure names the term, the cap, the per-sandbox value and its source, the slack, the quota value and the committed path of each.

One scenario covers the cpu refusal, the pass, a memory refusal, the missing-cap refusal and the rendering. The heading-coverage entry ships in the same change.

### Motivation

Work item livespec-dev-tooling-mlimt3 was refused at the dispatcher's ledger screen as spec-change with this linked topic, because no ratified clause states the quota-derivation check. legacy-coordinator-agent (session 2420058a) routed the draft on 2026-11-12 under its §10 rule ("a change needed in more than one place").

Measured 2026-11-12 19:31Z by gmktec-factory-placement: bd-ib-t5aju3 run 01M78KW65M3F died at sandbox acquire with `exceeded quota: factory-runs, requested limits.cpu=6, used 114100m, limited 120`. That was 19 sandboxes at `limits.cpu` 6 plus one 0.1-cpu pod. `limits.cpu` 120 was exactly the launchers' fleet cap of 20 times the sandbox limit of 6, so it held no room for any other limits-bearing pod. The quota is now 126 (21 × 6, livespec-dev-tooling `ci-runner/k3s/phase2/factory/DERIVATION.md` "One limits slot over the fleet cap (2026-11-12)").

The quota stays a second copy of the fleet cap, and the cap has no committed home at all. The launchers read it from a runtime state file of the orchestrator's `fleet-launch/` (`FLEET_LAUNCH_FLEET_CAP_FILE`), and this repository records it only in host_vars comments. The per-instance `max_concurrent_runs` this section already renders is not that number: on origin/master the `factory` namespace's sandbox-placing instances commit `fabro-server` 20 and `fabro-server-candidate` 16, while the launchers hold both to one shared cap of 20. So the next cap raise can strand a launch again.

The coordinator ruled the rule that closes it: whoever raises the runtime cap raises the committed value FIRST, in the same change or before it. It is recorded on epic livespec-dev-tooling-6tgd2z. The launcher-side half ("the launcher refuses a runtime cap above the committed value") is carried by legacy-dispatcher-agent's rtzhfc launch-scripts proposal in livespec-orchestrator-beads-fabro (topic each-gmktec-fabro-server-s, "Committed fleet cap bound."). That proposal reads the value this one renders.

Fleet scope: every factory namespace whose quota bounds factory sandboxes. Today that is `factory`. `factory-mi-homelab` is bounded by its own instance's `max_concurrent_runs` and is out of this check until a shared cap governs it.

In-flight survey (pending in-tree proposals, 2026-11-12 ~21:00Z):
- `derive-the-dispatcher-s-fleet` (livespec-dev-tooling-zsbvp3) bounds the sum of the sandbox-placing instances' `max_concurrent_runs` by the sum of the factory pod budgets, keeping `max_concurrent_runs` the one number per queue. This proposal adds the one number for the CROSS-queue launch cap and bounds the quota by it. Neither renders a value from the other. Relation: `align`.
- `factory-budget-admission-counts-memory` makes each admitted node slot real, and does not touch the quota. Relation: `align`.
- No other pending proposal touches §"Fabro factory registry" or the `factory-runs` quota.

### Proposed Changes

**1. `non-functional-requirements.md` §"Fabro factory registry".** Immediately after the paragraph that begins "**Run caps rendered beside the registry.**", insert:

> **The fleet launch cap is declared once.** The inventory MUST declare `fabro_fleet_launch_cap`, and MUST declare it only in `ansible/inventory/group_vars/dev_hosts.yml`, as a positive integer. It is the number of factory runs the fleet launchers launch at once, summed across every sandbox-placing instance they launch into, and it is the only committed copy of that number. On every host in the `dev_hosts` group, `ansible/fabro-hosts.yml` MUST render it into the run-cap directory as a file named `fleet-launch-cap`, holding exactly one line with the decimal value, world-readable, under the same validation and the same `--limit` / `--tags` rule as the per-factory run-cap files. The name is outside the `<factory>.max_concurrent_runs` pattern of those files, so no `fabro_factory_registry` name can overwrite it. A runtime launch cap that a launcher reads from any other file MUST NOT exceed this value. Whoever raises such a runtime cap MUST raise `fabro_fleet_launch_cap` first, in the same change or before it.
>
> **The factory namespace quota holds the fleet launch cap, term by term.** The repository's check aggregate MUST fail when the inventory declares no `fabro_fleet_launch_cap`, naming the missing key. It MUST also fail when any `hard` term of the committed `factory-runs` ResourceQuota (`ci-runner/k3s/phase2/factory/factory-namespace.yaml`) that a factory sandbox pod consumes is below `fabro_fleet_launch_cap` times V, plus V. The terms are `requests.cpu`, `limits.cpu`, `requests.memory`, `limits.memory` and `pods`. V is the largest value one sandbox pod takes for that term, across every `fabro_server_instances` mapping whose sandboxes the `factory` namespace holds, as derived from that instance's committed sandbox settings:
>
> - for `limits.cpu`, the environment's `cpu`;
> - for `requests.cpu`, the provider's committed CPU request where it sets one (`SANDBOX_DRIVER_KUBERNETES_CPU_REQUEST_CORES`), else the CPU limit;
> - for both memory terms, the sandbox memory the provider sets on the pod;
> - for `pods`, one.
>
> The extra V is one sandbox of slack, for any other pod in the namespace. A term the quota does not commit is not checked. The failure MUST name the term, the fleet launch cap, V and the instance and setting it was derived from, the slack, the quota's value for the term, and the committed path of each value. Each value MUST be read from that one committed home and from no other file or variable.

**2. Scenario (`scenarios.md`).** Insert directly after `## Scenario: the fabro-hosts play renders each registered factory's run cap from its instance's max_concurrent_runs`:

## Scenario: the factory namespace quota is refused at commit when it cannot hold the fleet launch cap

Given `ansible/inventory/group_vars/dev_hosts.yml` declares `fabro_fleet_launch_cap: 20`

And the largest committed sandbox CPU limit of any instance whose sandboxes the `factory` namespace holds is `6`, its largest committed CPU request is `3`, and its largest sandbox memory is `7630Mi`

And `ci-runner/k3s/phase2/factory/factory-namespace.yaml` commits `limits.cpu: "120"`, `requests.cpu: "84"`, `requests.memory: 171470Mi`, `limits.memory: 181710Mi` and `pods: "42"` for `factory-runs`

When the repository's check aggregate runs

Then it MUST fail on the term `limits.cpu`, naming the fleet launch cap 20, the per-sandbox value 6 with the instance and setting that set it, the slack 6, the quota's value 120, and the committed path of each

And it MUST NOT fail on `requests.cpu`, `requests.memory`, `limits.memory` or `pods`

Given the quota commits `limits.cpu: "126"` and nothing else is changed

When the check aggregate runs

Then that check MUST pass

Given the quota commits `requests.memory: 150000Mi` and nothing else is changed

When the check aggregate runs

Then it MUST fail on the term `requests.memory`, naming the fleet launch cap 20, the per-sandbox value 7630Mi, the slack 7630Mi and the quota's value 150000Mi

Given `fabro_fleet_launch_cap` is removed from `dev_hosts.yml` and the quota is otherwise passing

When the check aggregate runs

Then it MUST fail, naming the missing `fabro_fleet_launch_cap`

Given `fabro_fleet_launch_cap: 20` is restored

When `ansible/fabro-hosts.yml` converges and runs the rendering on a `dev_hosts` host

Then that host's run-cap directory MUST hold a world-readable file `fleet-launch-cap` whose single line is `20`

**3. `tests/heading-coverage.json`.** Add one entry in the same revise: `spec_file` `scenarios.md`, heading `## Scenario: the factory namespace quota is refused at commit when it cannot hold the fleet launch cap`, `"test": "TODO"`, `"work_item": "livespec-dev-tooling-mlimt3"`, and a non-empty `reason`. The reason states that the clause is spec-first and that livespec-dev-tooling-mlimt3 owes a test at the integration tier or above: the real check run against fixture trees for each quota term and for the missing key, plus the committed `ansible/fabro-hosts.yml` dev-host play run under the pinned `ansible-core` for the rendered file. Regenerate `tests/heading-coverage-debt.json` in the same commit.
