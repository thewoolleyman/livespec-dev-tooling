# `arq_smb_source` — host-specific values

These are properties of the machine, not defaults of the role. Merge them into
the inventory's `host_vars` for the host in question.

```yaml
# vps
arq_smb_source_tailscale_ip: 100.89.189.118
arq_smb_source_public_listeners:
  - "66.94.121.15:445"
```

`arq_smb_source_tailscale_ip` is the address `systemd-socket-proxyd` binds, so
the socket unit fails to start if it is wrong. `arq_smb_source_public_listeners`
is the eth0 address the role asserts is NOT serving SMB; leaving it unset
weakens that check to the wildcard patterns alone.
