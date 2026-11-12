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

Adds to ## Host provisioning tree an obligation for any role that places SSH authorized_keys entries on an inventory host: each entry is declared from host vars, marked as managed, restricted to the narrowest options its use needs, written without disturbing any other line, reported by --check without writing, and proved by an offline control against a fixture holding unrelated keys. Adds a scenario that exercises it.

### Motivation

The work item 'Place the hetzner-xubuntu Dolt-tunnel and existing forward-only authorized_keys entries on vps through committed provisioning' needs a role that writes two restricted entries into ~ubuntu/.ssh/authorized_keys on the vps dev host: a new forward-only entry for the hetzner-xubuntu Dolt tunnel (permitopen 127.0.0.1:3307) and the existing hand-placed forward-only entry (permitlisten 127.0.0.1:2223), adopted so fleet_host_guard's no-hand-edit rule holds. The classify-tier judge found that ## Host provisioning tree states the provisioning model in general but nothing about managing authorized_keys entries, restricted forward-only options, marker-managed lines that leave other lines untouched, or --check reporting a pending entry.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, ## Host provisioning tree, add this paragraph after **A held service is still installed by a role.**:

**An authorized_keys entry is declared, marked and narrow.** A role that places an SSH authorized_keys entry for an account on an inventory host MUST take each entry's public key and options from a host variable documented in the role's `HOST_VARS.md`, and a private key MUST NOT be committed. Each entry the role writes MUST carry a managed marker that names the role and the entry, and the role MUST add, update or remove only lines that carry its own marker: every other line in the file MUST be left byte-for-byte as found. An entry that exists only to carry a port forward MUST be restricted to that forward: it MUST carry `restrict`, MUST enable only port forwarding, MUST name exactly the forward destinations or listen addresses its use needs, and MUST carry a command that does nothing, so the key yields no shell, no command and no other forward. Under `--check` the role MUST report each entry it would add or change without writing the file. This repository's `just check` aggregate MUST include an offline control that converges the role against a fixture file holding unrelated keys and asserts that only the role's marked entries change.

In SPECIFICATION/scenarios.md, add:

## Scenario: a managed forward-only authorized_keys entry leaves every other key untouched

Given an inventory host account whose authorized_keys file holds keys no role manages, and a role whose host variables declare a forward-only entry for one destination

When the role is converged under --check and then applied

Then the check MUST report the pending entry without writing the file, and the apply MUST add exactly that entry with the role's managed marker, restrict, port forwarding to only the declared destination, and a command that does nothing

And every line the role does not mark MUST remain byte-for-byte unchanged, and a reapply MUST report no change
