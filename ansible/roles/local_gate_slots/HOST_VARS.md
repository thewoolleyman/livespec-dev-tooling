# local_gate_slots — host variables

Bounds how many fleet gate test runs this host executes at once. Governed by
the "Local gate concurrency limit" section of
`SPECIFICATION/non-functional-requirements.md`; the reading half is the
`livespec_dev_tooling.local_gate_slots` pytest plugin, which every fleet
repository already loads because every fleet repository depends on this
package.

## The one setting

| Variable | Default | Meaning |
| --- | --- | --- |
| `local_gate_slots_limit` | `0` | Pytest sessions a fleet gate may run at once on this host, across every repository and worktree. `0` means NO LIMIT. |

Nothing else in this role is expected to be set per host. The remaining
variables name the two paths the plugin reads and the mode the slot store
carries; each is documented at its default and each is held against the
plugin's own constant by `tests/livespec_dev_tooling/test_local_gate_slots.py`,
because neither side can see the other and a drift is a converge that writes a
limit nothing reads.

## Procedure

Declare the limit for a group in `inventory/group_vars/<group>.yml`, or for one
machine in `inventory/host_vars/<host>.yml`, then converge:

```bash
cd ansible
ansible-playbook dev-host.yml --tags local_gate_slots --check --diff
ansible-playbook dev-host.yml --tags local_gate_slots
```

Read the `--check --diff` output before the apply. It names the limit file it
would write and the tmpfiles rule it would install, and on a host that already
carries a limit it shows the value changing.

## Rollback

Remove the host's or group's `local_gate_slots_limit` declaration and converge
again. The role default of `0` then applies, and the converge removes the limit
file and the tmpfiles rule — so the host is returned to no limit rather than
left pinned at the last number it was given. Setting the value to `0`
explicitly does the same thing.

A gate already running is unaffected either way: a slot is held in a file
descriptor the kernel owns, so nothing this role does can take a slot from a
session that has one, and nothing it does can make a session that holds one
wait again.

## Why the slot store is world-writable

The store is created `1777` — world-writable with the sticky bit, exactly as
`/tmp` is. A slot is taken by whichever login runs the gate, so a store that
login cannot create a file in would make every one of its sessions queue behind
slots nobody holds; the sticky bit is then what stops one login removing
another's slot file. A host whose gates all run as one login does not need the
world-writable half, and loses nothing by having it.

## Sizing

The limit bounds CONCURRENT TEST RUNS, not cores. Each full local gate run on
this fleet is a `pytest -n 4 --cov` aggregate measured at about four cores, so a
limit of N reserves roughly `4N` of the host's cores for gates and leaves the
rest for agent sessions, the Fabro servers and Dolt.

The dev VPS (18 cores) is provisioned at `3`: about 12 cores to gates and about
6 to everything else. It was measured at 95.8% busy, load 78, with four to five
such aggregates running at once on 2026-10-24.

## This is a stopgap

The ratified clause says so: once the fleet's heavy gates run delegated on the
cluster (plan `delegated-gate-fleet-rollout`, epic
`livespec-dev-tooling-mvalxq`), the limit SHOULD be removed. Removing it is the
rollback above.
