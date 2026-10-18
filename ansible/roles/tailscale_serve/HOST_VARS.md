# `tailscale_serve` — per-host values for the inventory's `host_vars`

| Variable | Default | Meaning |
| --- | --- | --- |
| `tailscale_serve_mappings` | `[]` | The `tailscale serve` mappings this host publishes. Each entry carries `https_port` (the tailnet HTTPS port) and `backend` (the loopback URL it proxies to). |

An empty list leaves the host exactly as it is. The role is additive: it publishes
a declared mapping the node does not already serve, re-points a declared port that
serves a different backend, and never turns a mapping off or touches a port it was
not given.

Why it exists: `tailscale-admin` documents each Fabro mapping as a one-line
`sudo tailscale serve --bg --https=<port> http://127.0.0.1:<port>` run by hand on the
host, and the fleet host guard refuses that to an agent. On 2026-10-18 the first
`fabro-hosts.yml` converge of `gmktec-xubuntu` brought its Fabro server up on
loopback port 32276, unreachable at its tailnet URL until a mapping existed.

Declared today on `gmktec-xubuntu` only:

```yaml
tailscale_serve_mappings:
  - https_port: 32276
    backend: http://127.0.0.1:32276
```

`hp-xubuntu` and `vps` declare nothing: their mappings were made by hand before this
role existed, and they are left as they are.
