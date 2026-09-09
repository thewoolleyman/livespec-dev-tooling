# `disk_guard` — per-host values for the inventory's `host_vars`

Measured from the live host and carried here verbatim from
`fabro-hosts/services/disk-guard/hosts/hp-xubuntu.env` (measured 2026-09-06;
`hostname -s` -> `hp-xubuntu`, and the untracked `/usr/local/sbin/disk-guard.sh`
carried `THRESHOLD_GB=40`).

`hp-xubuntu` is the only host this service has ever had a values file for.

```yaml
# hp-xubuntu
disk_guard_threshold_gb: 40
```

The env file's other two keys — `DISK_GUARD_CANONICAL_HOST`
(`hp-xubuntu.perch-rudd.ts.net`) and `DISK_GUARD_SYSTEM_HOSTNAME`
(`hp-xubuntu`) — are deliberately **not** host vars. They existed only so
`install.sh` could refuse to apply one host's values on another; inventory
targeting is that guard now.
