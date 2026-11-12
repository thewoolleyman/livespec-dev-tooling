# `tailscale_serve` — per-host values for the inventory's `host_vars`

| Variable | Default | Meaning |
| --- | --- | --- |
| `tailscale_serve_mappings` | `[]` | The `tailscale serve` mappings this host publishes. Each entry carries `https_port` (the tailnet HTTPS port) and `backend` (the loopback URL it proxies to). |
| `tailscale_serve_retired_ports` | `[]` | The tailnet HTTPS ports this host retires. Each one the node still serves is turned off with `tailscale serve --https=<port> off` (`tasks/retire.yml`). A port that is also a declared mapping is refused before any change. |

An empty list leaves the host exactly as it is. The role is additive: it publishes
a declared mapping the node does not already serve, re-points a declared port that
serves a different backend, and never turns a mapping off or touches a port it was
not given.

Why it exists: `tailscale-admin` documents each Fabro mapping as a one-line
`sudo tailscale serve --bg --https=<port> http://127.0.0.1:<port>` run by hand on the
host, and the fleet host guard refuses that to an agent. On 2026-10-18 the first
`fabro-hosts.yml` converge of `gmktec-xubuntu` brought its Fabro server up on
loopback port 32276, unreachable at its tailnet URL until a mapping existed.

Declared today on `gmktec-xubuntu`:

```yaml
tailscale_serve_mappings:
  - https_port: 32276
    backend: http://127.0.0.1:32276
```

and on `vps`, the tailnet fronts of its two Fabro instances (`fabro-hosts.yml`'s
dev-host play runs this role, livespec-dev-tooling-jxw2ve) and of the incident
observer's loopback listener (`roles/incident_observer/README.md`; `dev-host.yml`
runs this role right after that one):

```yaml
tailscale_serve_mappings:
  - https_port: 32276
    backend: http://127.0.0.1:32276
  - https_port: 32277
    backend: http://127.0.0.1:32277
  - https_port: 8765
    backend: http://127.0.0.1:8765
```

`hp-xubuntu` publishes nothing: it runs no Fabro server since it left the docker
factory role on 2026-11-02. Its three hand-made legacy Fabro mappings, made before
this role existed, outlived that server, and it retires them (bd-ib-iud52v, the
legacy Fabro carrier retirement). `ansible/former-sandbox-hosts.yml` runs this role
for it:

```yaml
tailscale_serve_retired_ports:
  - 32276
  - 32277
  - 32278
```

`vps`'s other hand-made mappings (8010, 8443) are named nowhere and are left as
they are.
