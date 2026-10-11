---
topic: delegated-pre-push-gate
author: claude-opus-5-5
created_at: 2026-10-11T05:08:56Z
---

## Proposal: Specify this repository's delegated pre-push gate — opt-in, host eligibility, verdict, and gates credential

### Target specification files

- SPECIFICATION/contracts.md
- tests/heading-coverage.json

### Summary

Adds one new section, `## Delegated pre-push gate`, to `SPECIFICATION/contracts.md`, placed immediately after §"Consumer configuration schema". It states the consumer-facing contract of the delegated pre-push gate this repository already ships (`livespec_dev_tooling/gate_remote_delegate.py`, `gate_remote_client.py`, `gate_remote_verdict.py`, the `check-pre-push` recipe, and the `gates_kubeconfig` Ansible role): how a consuming repository opts in, when a pushing host delegates and when it gates locally, what verdict a push needs, and how the gates credential is used and installed.

### Motivation

The delegated gate shipped as plan `k3s-on-gmktec-for-vps-usage` (livespec epic `livespec-sab5gn`) slices S7a–S7c, and no heading of this repository's specification governs it. §"Consumer configuration schema" governs only the layout role keys and says in so many words that keys outside the role-key inventory are not governed there. The follow-up work-item `livespec-dev-tooling-pj7q4m`, which makes the gate usable from the VPS and opts this repository in, was therefore refused by the factory's Definition-of-Done gate (Fabro run `01M4MBZJ3N2K4A5NC4YXAGES8B`): its assertions name behaviour no spec heading states.

This proposal does NOT revive livespec core's `SPECIFICATION/proposed_changes/delegated-gate-execution.md`, which was closed unratified by maintainer instruction on 2026-09-08. That proposal sought a fleet-wide rule in core about any delegated gate. This one states only what this repository's own shipped tooling does for a consumer that opts in, at the level a consumer and the factory's grader need, and the maintainer chose this route explicitly on 2026-10-11.

### Proposed Changes

Insert the following section into `SPECIFICATION/contracts.md` immediately before the line `## Composite Actions wire contract` (so it follows §"Consumer configuration schema" and its sub-sections):

> ## Delegated pre-push gate
>
> A consuming repository MAY run its pre-push gate on the cluster gate executor instead of on the pushing host. This section is the consumer-facing contract of that delegation as this repository ships it.
>
> - **Opt-in.** Delegation is switched on by `delegated_gate = true` in the consumer's `[tool.livespec_dev_tooling]` table. The key is read by its own loader, not by `load_config`, and is not a role key. Only the literal boolean `true` enables delegation; an absent key, `false`, a value of another type, or an unreadable `pyproject.toml` all leave the repository gating locally.
> - **Host eligibility.** With delegation switched on, a push delegates only when the pushing user can read the gates kubeconfig on that host. Otherwise the push runs the local `just check` fall-through and prints a line saying it gated locally. A host that holds no gates credential, such as a factory sandbox, therefore keeps gating locally in an opted-in repository.
> - **What the delegated gate runs.** The delegated gate runs the same aggregate the local fall-through would run, against the exact tree being pushed, which is published to the gate executor under a ref named by that tree's hash.
> - **Verdict.** A delegated push completes only on a green verdict for the pushed tree. When no verdict arrives — the API server is unreachable, the credential cannot be refreshed, the gate Job cannot be submitted, or it is lost or times out — the push is refused, never completed. A green delegated verdict records the same green token a green local aggregate records, so a byte-identical tree is not gated twice.
> - **Explicit local route.** Running `just check` locally on the tree records the green token, after which the pre-push gate skips both paths for that tree. An unavailable executor therefore never prevents pushing.
> - **Credential use.** Every cluster command the gate client issues runs through `with-gates-kubeconfig` against the gates kubeconfig. When the API server rejects the credential, the wrapper refreshes it exactly once through `refresh-gates-kubeconfig` — invoked through non-interactive `sudo` when the caller is not root — and retries the command once. A second rejection is reported as itself.
> - **Credential installation.** The `gates_kubeconfig` Ansible role installs the gates kubeconfig owned by root and by a declared gate-client group that contains the login user of each delegating host, at mode `0640`. The credential is never world-readable, and a refresh replaces it in place without loosening that ownership or mode.

Add the matching entry to `tests/heading-coverage.json` for the new `contracts.md` heading `Delegated pre-push gate`, as a `TODO` entry whose `reason` names work-item `livespec-dev-tooling-pj7q4m` as the implementing item.
