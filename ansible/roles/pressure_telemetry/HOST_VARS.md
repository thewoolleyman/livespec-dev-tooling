# `pressure_telemetry` — per-node cgroup pressure

Every execution target emits the kernel's host pressure stall information. A
host may also export the CPU pressure of named cgroups, so a saturation window
can be graded from Honeycomb after it has passed.

| Variable | Default | Meaning |
| --- | --- | --- |
| `pressure_telemetry_cgroups` | `[]` | cgroup paths relative to `/sys/fs/cgroup`. For each, the emitter reads `<path>/cpu.pressure` and sends `livespec.cgroup.pressure.cpu.{some,full}.{avg10,avg60,avg300}` with a `cgroup=<path>` datapoint attribute, in the same request as the host datapoints. A configured path whose file is missing fails the whole run and sends nothing. |

```yaml
# poweredge-xubuntu — the k3s server's own CPU pressure, so its share during a
# node saturation window can be read from Honeycomb afterwards
# (livespec-dev-tooling-3gm5rb). Revert by setting it to [] and re-applying
# --tags pressure_telemetry.
pressure_telemetry_cgroups:
  - system.slice/k3s.service
```

The agents run `system.slice/k3s-agent.service` (measured on `gmktec-xubuntu`
and `hp-xubuntu`) and may be added later. The dev host has no k3s cgroup and
keeps the empty default.
