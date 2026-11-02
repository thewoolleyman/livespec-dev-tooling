# `fabro_server_cpu_weight` — the inventory values this role reads

| Variable | Default | Meaning |
| --- | --- | --- |
| `fabro_server_cpu_weight_value` | `""` | The systemd `CPUWeight=` (1 to 10000) every unit in the host's `fabro_server_instances` runs with. Empty manages no weight and removes a drop-in an earlier converge wrote. |
| `fabro_server_instances` | (the `fabro_server` role's) | Read only for each instance's `unit_name`. |

The role writes `/etc/systemd/system/<unit_name>.service.d/50-cpu-weight.conf`
for each instance and runs one `systemctl daemon-reload` when a drop-in changed.
It never restarts an instance: systemd applies a changed `CPUWeight=` to the
running unit's cgroup on the reload. It has no handler, so it cannot reach the
`fabro_server` role's restart chain.

## Hosts that declare it

- `gmktec-xubuntu`: `2000`. It is both the factory host and the host of the
  main Fabro server (:32276). Measured 2026-11-02 at about 19:40Z, with CPU PSI
  some avg10 at 51-55% under a CI burst, `kubepods.slice` held cpu.weight 1250
  against `system.slice`'s 100 (orchestrator work-item `bd-ib-s6a2ex`).

## Applying it alone

```bash
just ansible-drift ansible/fabro-hosts.yml --limit <host> --tags fabro_server_cpu_weight
just ansible-apply ansible/fabro-hosts.yml --limit <host> --tags fabro_server_cpu_weight
```

The tag selects only this role's tasks: no Fabro binary, unit file, settings or
other drop-in is touched, and no instance is restarted.

## What a unit weight does not change

`CPUWeight=` on a unit divides CPU among that unit's SIBLINGS inside
`system.slice`. It does not change `system.slice`'s own share against
`kubepods.slice`, which is set by the two slices' weights at the cgroup root.
