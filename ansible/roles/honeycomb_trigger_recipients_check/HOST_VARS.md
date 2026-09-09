# honeycomb_trigger_recipients_check -- per-host values for the inventory

One value is a property of the machine rather than a fleet default: where this
host keeps its `vps-info` checkout. The installed systemd unit's `ExecStart`
names the check script at that path, so it is load-bearing at every daily run,
long after any playbook has exited. Merge the block below into that host's
`host_vars` in `ansible/inventory/legacy.yml`.

```yaml
# vps
honeycomb_trigger_recipients_check_checkout: /data/projects/vps-info
```

Write the real path, not `~/ubuntu/workspace/vps-info`. `/home/ubuntu/workspace`
is a symlink to `/data/projects`, and a unit file resolved through a symlink is
one more thing that can be replaced underneath it.

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
  endpoints at all. The role warns rather than refusing, so the units can be
  staged before the key exists -- but every run exits 2 until it does.
- `dolt-backup-alert@.service`, from the `dolt-server` repo. It is this unit's
  `OnFailure` target. The role warns when it is absent.
