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

Adds to ## Host provisioning tree an obligation for any role that writes SSH authorized_keys entries into a file other keys share. Each entry is declared from host vars and marked as managed, and is written without disturbing any other line, in pinned order and mode. --check reports it without writing it, and a reapply is a no-op. A forward-only entry is restricted to exactly its forwards, with the unused direction locked by a value measured to admit nothing. The obligation is proved by a named repo-private offline control. Adds a scenario that exercises it.

### Motivation

The work item 'Place the hetzner-xubuntu Dolt-tunnel and existing forward-only authorized_keys entries on vps through committed provisioning' needs a role that writes two restricted entries into ~ubuntu/.ssh/authorized_keys on the vps dev host: a new forward-only entry for the hetzner-xubuntu Dolt tunnel (permitopen 127.0.0.1:3307) and the existing hand-placed forward-only entry (permitlisten 127.0.0.1:2223), adopted so fleet_host_guard's no-hand-edit rule holds. The classify-tier judge found that ## Host provisioning tree states the provisioning model in general but nothing about managing authorized_keys entries, restricted forward-only options, marker-managed lines that leave other lines untouched, or --check reporting a pending entry.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, ## Host provisioning tree, add this paragraph after **A held service is still installed by a role.**:

**An authorized_keys entry is declared, marked and narrow.** A role that writes an SSH authorized_keys entry into a file that holds, or may hold, keys the role does not manage MUST take each entry's public key and options from a host variable documented in the role's `HOST_VARS.md`, and a private key MUST NOT be committed. A role that renders an entire authorized_keys file it alone owns is outside this paragraph, because no other key shares that file. Each entry the role writes MUST carry a managed marker that names the role and the entry. The role MUST add, update or remove only lines that carry its own marker, and every other line in the file MUST be left byte-for-byte as found and in its original order. The role MUST place its marked entries after all unmarked lines, in the order its host variable declares them, and MUST leave the file owned by the account with mode `0600`. Under `--check` the role MUST report each entry it would add or change without writing the file, and a reapply with unchanged host variables MUST report no change.

An entry that exists only to carry a port forward MUST be restricted to that forward. It MUST carry `restrict`, MUST enable only port forwarding, and MUST carry a command that does nothing, so the key yields no shell and runs no command. `port-forwarding` enables both directions, so the entry MUST name exactly the forwards its use needs and MUST lock the direction it does not use. A local-forward entry MUST carry `permitopen` for exactly its destinations and `permitlisten="invalid.invalid:1"`. A remote-forward entry MUST carry `permitlisten` for exactly its listen addresses and `permitopen="invalid.invalid:1"`. The literal `none` that `sshd_config` accepts for these settings is not accepted in authorized_keys: OpenSSH 10.0p2 refuses the whole key. The `invalid.invalid:1` value admits nothing, because the reserved `.invalid` name never resolves and port 1 cannot be bound by an unprivileged session. Such an entry MUST be reached through the host's OpenSSH server, never through Tailscale SSH. Tailscale SSH ignores authorized_keys, so its tailnet accept rule would give the forwarding process a full shell instead of this entry's single forward.

**Enforced for managed authorized_keys entries.** This repository's `just check` aggregate MUST include `check-ansible-authorized-keys-managed`. It is a repo-private check, outside the canonical fleet-universal slug set, because this repository alone owns the provisioning tree. It MUST converge each role that writes authorized_keys entries against a fixture file holding unrelated keys, and assert three things: only the role's marked entries change, the unmarked lines keep their bytes and order, and every forward-only entry carries `restrict`, a no-op command, exact forwards and the locked opposite direction. It MUST fail the aggregate on any violation. A run that finds no such role MUST report itself as vacuous rather than as a pass.

In SPECIFICATION/scenarios.md, add:

## Scenario: a managed forward-only authorized_keys entry leaves every other key untouched

Given an inventory host account whose authorized_keys file holds keys no role manages, and a role whose host variables declare a forward-only entry for one destination

When the role is converged under --check and then applied

Then the check MUST report the pending entry without writing the file, and the apply MUST add exactly that entry with the role's managed marker, restrict, port forwarding to only the declared destination, the remote-forward direction locked with `permitlisten="invalid.invalid:1"`, and a command that does nothing

And every line the role does not mark MUST remain byte-for-byte unchanged and in its original order, the file MUST keep mode 0600, and a reapply MUST report no change

And with that entry's key, a local forward to any other destination, any remote forward, and a shell MUST each be refused
