---
topic: place-the-hetzner-xubuntu-dolt
author: claude-opus-5-5
created_at: 2026-11-12T03:26:18Z
---

## Proposal: Managed authorized_keys entries in the host provisioning tree

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds to ## Host provisioning tree an obligation for any role that writes SSH authorized_keys entries into a file other keys share. Each entry is declared from host vars and marked as managed, and is written without disturbing any other line, in pinned order and mode. --check reports it without writing it, and a reapply is a no-op. A forward-only entry is restricted to exactly its forwards, with the unused direction locked by a value measured to admit nothing. A hand-placed key can be retired by its key blob through a host var, and a key both managed and retired refuses the converge. The obligation is proved by a named repo-private offline control and three scenarios. Adds scenarios that exercise it, including retiring a hand-placed key and refusing a key both managed and retired.

### Motivation

The work item 'Place the hetzner-xubuntu Dolt-tunnel and existing forward-only authorized_keys entries on vps through committed provisioning' needs a role that writes two restricted entries into ~ubuntu/.ssh/authorized_keys on the vps dev host: a new forward-only entry for the hetzner-xubuntu Dolt tunnel (permitopen 127.0.0.1:3307) and the existing hand-placed forward-only entry (permitlisten 127.0.0.1:2223), adopted so fleet_host_guard's no-hand-edit rule holds. The classify-tier judge found that ## Host provisioning tree states the provisioning model in general but nothing about managing authorized_keys entries, restricted forward-only options, marker-managed lines that leave other lines untouched, or --check reporting a pending entry.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, ## Host provisioning tree, add this paragraph after **A held service is still installed by a role.**:

**An authorized_keys entry is declared, marked and narrow.** A role that writes an SSH authorized_keys entry into a file that holds, or may hold, keys the role does not manage MUST take each entry's public key and options from a host variable documented in the role's `HOST_VARS.md`, and a private key MUST NOT be committed. A role that renders an entire authorized_keys file it alone owns is outside this paragraph, because no other key shares that file. Each entry the role writes MUST carry a managed marker that names the role and the entry. The role MUST add, update or remove only lines that carry its own marker, with one exception. It MAY remove an unmarked line whose public key a host variable documented in `HOST_VARS.md` names as retired, so that a hand-placed entry is retired through committed provisioning rather than a hand edit. A retired key MUST be matched on its key blob, the key type together with its base64 body, and never on the whole line, because a hand-placed line's options and comment are not known in advance. A key that is both declared as a managed entry and named as retired MUST make the converge refuse before writing anything, with a diagnostic that names the key. Every other unmarked line in the file MUST be left byte-for-byte as found and in its original order. The role MUST place its marked entries after all unmarked lines, in the order its host variable declares them, and MUST leave the file owned by the account with mode `0600`. Under `--check` the role MUST report each line it would add, change or remove, both its marked entries and the lines carrying retired keys, without writing the file, and a reapply with unchanged host variables MUST report no change.

An entry that exists only to carry a port forward MUST be restricted to that forward. It MUST carry `restrict`, MUST enable only port forwarding, and MUST carry a command that does nothing, so the key yields no shell and runs no command. `port-forwarding` enables both directions, so the entry MUST name exactly the forwards its use needs and MUST lock the direction it does not use. A local-forward entry MUST carry `permitopen` for exactly its destinations and `permitlisten="invalid.invalid:1"`. A remote-forward entry MUST carry `permitlisten` for exactly its listen addresses and `permitopen="invalid.invalid:1"`. The literal `none` that `sshd_config` accepts for these settings is not accepted in authorized_keys: OpenSSH 10.0p2 refuses the whole key. The `invalid.invalid:1` value admits nothing, because the reserved `.invalid` name never resolves and port 1 cannot be bound by an unprivileged session. Such an entry MUST be reached through the host's OpenSSH server, never through Tailscale SSH. Tailscale SSH ignores authorized_keys, so its tailnet accept rule would give the forwarding process a full shell instead of this entry's single forward.

**Enforced for managed authorized_keys entries.** This repository's `just check` aggregate MUST include `check-ansible-authorized-keys-managed`. It is a repo-private check, outside the canonical fleet-universal slug set, because this repository alone owns the provisioning tree. It MUST converge each role that writes authorized_keys entries against a fixture file holding unrelated keys, and assert four things: only the role's marked entries and the lines carrying its declared retired keys change, every other unmarked line keeps its bytes and order, every forward-only entry carries `restrict`, a no-op command, exact forwards and the locked opposite direction, and a key declared both as a managed entry and as retired makes the converge refuse. It MUST fail the aggregate on any violation. A run that finds no such role MUST report itself as vacuous rather than as a pass.


In the same revise commit, the revise that accepts this proposal MUST add one `tests/heading-coverage.json` row for each of the three new `scenarios.md` headings, and MUST regenerate `tests/heading-coverage-debt.json` to match:

- `## Scenario: a managed forward-only authorized_keys entry leaves every other key untouched`
- `## Scenario: a managed authorized_keys role retires a hand-placed key by its key blob`
- `## Scenario: a key both managed and retired refuses the converge`

Each row has `spec_root` `SPECIFICATION`, `spec_file` `scenarios.md`, `test` `TODO` and `work_item` `livespec-dev-tooling-sr46h2`, which owes the role and the `check-ansible-authorized-keys-managed` control. Its `reason` states that a real test at the consumer tier (`tests.consumer`, this repository's `scenario_tiers`) is owed, converging the role against an authorized_keys fixture, and that a unit-tier test does not satisfy a scenario. The new paragraphs in `non-functional-requirements.md` sit under the existing `## Host provisioning tree` heading and add no heading.

In SPECIFICATION/scenarios.md, add:

## Scenario: a managed forward-only authorized_keys entry leaves every other key untouched

Given an inventory host account whose authorized_keys file holds keys no role manages, and a role whose host variables declare a forward-only entry for one destination

When the role is converged under --check and then applied

Then the check MUST report the pending entry without writing the file, and the apply MUST add exactly that entry with the role's managed marker, restrict, port forwarding to only the declared destination, the remote-forward direction locked with `permitlisten="invalid.invalid:1"`, and a command that does nothing

And every other unmarked line MUST remain byte-for-byte unchanged and in its original order, the file MUST keep mode 0600, and a reapply MUST report no change

And with that entry's key, a local forward to any other destination, any remote forward, and a shell MUST each be refused

## Scenario: a managed authorized_keys role retires a hand-placed key by its key blob

Given an inventory host account whose authorized_keys file holds a hand-placed unmarked line for a key, with options and a comment the role does not know, and other unmarked lines for unrelated keys

And a role whose host variables name that key, by key type and base64 body, as retired

When the role is converged under --check and then applied

Then the check MUST report the retired line as a removal without writing the file, and the apply MUST remove exactly that line

And every other unmarked line MUST remain byte-for-byte unchanged and in its original order, an unmarked line whose key is not named as retired MUST be left in place, and a reapply MUST report no change

## Scenario: a key both managed and retired refuses the converge

Given a role whose host variables declare a managed authorized_keys entry for a key and also name the same key blob as retired

When the role is converged, under --check or as an apply

Then the converge MUST refuse before writing the file, with a diagnostic naming the conflicting key, and the authorized_keys file MUST be unchanged
