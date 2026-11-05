# `incident_observer` — per-host values for the inventory's `host_vars`

| Variable | Default | Meaning |
| --- | --- | --- |
| `incident_observer_candidate_user` | `""` (refused) | The login account the host's CANDIDATES run as. Its uid becomes controller.json `candidate_uid`, which the loader requires to differ from the serving controller's own euid. |

Every other value is a fleet default in `defaults/main.yml`: the released tag
and its repository, the canonical reader's released tag, the required master
leaf jobs, the controller account, the layout under `/opt/livespec-incident`,
`/etc/livespec-incident` and `/var/lib/livespec-incident`, the three secret
file paths with the environment variable each is written from, and the
loopback port.

The host's tailnet TLS front is not this role's variable: the `tailscale_serve`
role publishes the loopback port from the same host's
`tailscale_serve_mappings`, and `dev-host.yml` runs it right after this role.

Declared today on `vps` only:

```yaml
incident_observer_candidate_user: ubuntu
```
