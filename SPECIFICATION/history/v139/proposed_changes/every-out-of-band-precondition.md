---
topic: every-out-of-band-precondition
author: claude-opus-5-5
created_at: 2026-11-05T08:12:25Z
---

## Proposal: A role's out-of-band preconditions fail its converge at the start

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add an obligation to §"Host provisioning tree" in non-functional-requirements.md. Any role whose converge depends on state it cannot create must assert that state before its first task that can change the host, and must name the missing input. Any post-apply operator step that no assert can check must be listed in an out-of-band section of the role's HOST_VARS.md. Add one scenario that states the behaviour.

### Motivation

Plan ci-pool-provisioning-leftovers (epic livespec-dev-tooling-fby3sx), research note 001 (2026-11-05), re-measured the nineteen manual steps that survived the Ansible migration. The archived livespec plan k3s-on-gmktec-for-vps-usage, note 005 §2, said: "They must be recorded as inventory-level preconditions with a preflight assert per role, or the first apply on a rebuilt host fails in the middle rather than at the start." That obligation was never ratified. Measured on origin/master d8ec42a6, the gaps are: restic_backup asserts its wrapper but not the six VPS_RESTIC_* names; honeycomb_mcp changes the checkout before its key and plugin asserts run; honeycomb_trigger_recipients_check only warns about a missing key; gates_kubeconfig installs kubectl and two scripts before it fetches the remote file it needs; and the Cloudflare Codex MCP entry and several GUI sign-ins are recorded nowhere in ansible/. The carrier is livespec-dev-tooling-c763up, which the filing-time tier classifier held at spec-change tier because the ratified text does not state this behaviour.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Host provisioning tree", insert this paragraph after **A replaced installer is retired.** and before **Enforced in the aggregate.**:

**Out-of-band preconditions fail at the start.** A role MAY depend on state that it cannot itself create. Examples are a credential or key resolved through an environment wrapper, a file it fetches from another host, and a build an operator stages on the control node. Such a role MUST assert each such input before the first of its tasks that can change the target host. When an input is missing, the converge MUST fail at that assert, and the failure MUST name the missing input, so that an apply on a rebuilt host that lacks the input fails before it has changed anything. Some steps can only be performed after the apply, and no assert on the target can check them, such as an interactive sign-in, a first backup, or re-applying the role after an external plugin it reads is updated. Each such step MUST be listed in an "Out-of-band" section of the role's `HOST_VARS.md`, which names the step and says when an operator performs it. A role MUST NOT record such a precondition only as a warning that lets the converge continue.

The **Enforced in the aggregate.** paragraph is unchanged: this obligation is judged by review and by the drift and apply runs, not by a `just check` member.

In SPECIFICATION/scenarios.md, add after §"Scenario: an apply refuses a plugin binary whose digest differs from an instance pin, and drift compares live pins to the installed binary":

## Scenario: an apply on a host missing a role's out-of-band input fails before the role changes anything

Given a role in a committed playbook under `ansible/` that reads a credential through an environment wrapper on the target host

And a target host on which that credential does not resolve

When `just ansible-apply` runs that playbook against the host

Then the role MUST fail at an assert that names the missing credential

And no task of that role that can change the host MUST have run

And a post-apply step of that role which no assert can check MUST be listed in the "Out-of-band" section of the role's `HOST_VARS.md`

## Proposal: A service held disabled is still installed by its role

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add an obligation to §"Host provisioning tree": a host service from the fleet's committed host glue that the maintainer holds disabled must still be installed by a role. The role installs it in the held state, and a single role variable is the only switch that enables it. Add one scenario.

### Motivation

Research note 001 of plan ci-pool-provisioning-leftovers found six class (a) host-glue files of vps-info's editor stack (services/code-serve-web, services/code-pwa-proxy) with no role and no owning item. The maintainer held the stack "until further notice" (vps-info 6458250). Without a stated rule, a hold reads as permission to leave the service outside the provisioning tree, where no drift report sees it. The carrier is livespec-dev-tooling-fmbnyd, whose filing-time judgement rested at needs-human because no ratified heading states this behaviour.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Host provisioning tree", insert this paragraph immediately after the **Out-of-band preconditions fail at the start.** paragraph:

**A held service is still installed by a role.** Some host services come from this fleet's committed host glue and are held disabled by the maintainer. Each such service MUST still be installed by a role that a committed playbook applies to its host. The role MUST install the service in the held state, with its units disabled and inactive, and a role variable documented in the role's `HOST_VARS.md` MUST be the only switch that enables it. A converge with that variable at its held value MUST NOT enable or start the service, and the drift report MUST show a host on which the service has been enabled by hand as drift.

In SPECIFICATION/scenarios.md, add after the scenario this change adds above:

## Scenario: a held service converges installed and disabled

Given a host service the maintainer holds disabled, installed by a role whose enable variable is at its held value

When `just ansible-apply` converges the role on the host

Then the service's units MUST be installed, disabled and inactive

And a second converge MUST report no change

And `just ansible-drift` MUST report the service as drift after an operator enables it by hand
