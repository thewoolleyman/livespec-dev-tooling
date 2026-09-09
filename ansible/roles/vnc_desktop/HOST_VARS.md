# `vnc_desktop` — host-specific values

Everything else in `roles/vnc_desktop/defaults/main.yml` is a deployment default
and should stay there. The one value below is a fact about this machine.

```yaml
# vps
vnc_desktop_tailscale_ip: 100.89.189.118
```

`x11vnc -listen` is given this literal rather than a wildcard, so the address IS
the access control: the desktop is reachable over the tailnet and from nowhere
else. It changes if the node is re-registered on the tailnet, and a stale value
makes the service start and then bind nothing, which the role's `wait_for` on
the port catches.
