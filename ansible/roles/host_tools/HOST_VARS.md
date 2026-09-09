# `host_tools` — per-host values for the inventory's `host_vars`

**None.** This role needs no `host_vars` entry on any host.

`fabro-hosts/services/host-tools/hosts/hp-xubuntu.env` carried exactly two keys,
`HOST_TOOLS_CANONICAL_HOST` (`hp-xubuntu.perch-rudd.ts.net`) and
`HOST_TOOLS_SYSTEM_HOSTNAME` (`hp-xubuntu`), and its own header says why: the
service "installs plain executables and has no tunables", so the keys existed
only so `install.sh` could refuse to run one host's file on another. Inventory
targeting is that guard now, so neither key becomes a variable.

`hp-xubuntu` is the only host this service has ever had a values file for; it
was installed there 2026-09-08.
