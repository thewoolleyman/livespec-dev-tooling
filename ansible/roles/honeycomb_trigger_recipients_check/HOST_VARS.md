# honeycomb_trigger_recipients_check -- per-host values for the inventory

One value is a property of the machine rather than a fleet default: where this
host keeps its `vps-info` checkout. The installed systemd unit's `ExecStart`
names the check script at that path, so it is load-bearing at every daily run,
long after any playbook has exited. Merge the block below into that host's
`host_vars` in `ansible/inventory/legacy.yml`.

```yaml
# vps
honeycomb_trigger_recipients_check_checkout: /home/ubuntu/workspace/vps-info
```

Write the explicit `/home/ubuntu/workspace/vps-info`, not `~` or `%h`: this is a
system unit, where both name root's home. Canonical clones live under
`~/workspace` on every host; on the VPS it is a symlink to the data disk.

`honeycomb_trigger_recipients_check_service_user` is `ubuntu` here, which is
also the account that owns the checkout and that the 1Password wrapper serves.
It stays in `defaults/main.yml` because the unit shipped in `vps-info` hardcodes
`User=ubuntu`; move it to `host_vars` if a second host ever runs this check
under a different account.

## Out-of-band, not provisioned here

- `/usr/local/bin/with-homelab-env.sh`, from the `1password-env-wrapper` repo.
  It is the unit's `ExecStart`, so the role asserts it and refuses otherwise.
- `HONEYCOMB_TRIGGER_RECIPIENT_AUDIT_CONFIG_API_KEY` in the 1Password `homelab`
  Environment. It must be a Honeycomb **Configuration** (v1) key holding
  `manageTriggers` **and** `manageRecipients`. A Management key will not work:
  v1 rejects it at `/1/auth`, before scopes are consulted, and v2 has no trigger
  endpoints at all. The role asserts that it resolves, for the account the unit
  runs as, before its first changed task, and refuses otherwise: apply it only
  after the key is in the Environment.
- `host-unit-alert@.service`, from role `host_unit_alert`, which
  `dev-host.yml` runs first. It is this unit's `OnFailure` target. The role warns when it is absent: that dependency decides
  only whether a failing run is HEARD, not whether the check can run.
