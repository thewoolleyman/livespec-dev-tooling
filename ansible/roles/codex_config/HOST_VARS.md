# codex_config -- per-host values for the inventory

One value is per-machine: the account whose `~/.codex/config.toml` this role
configures. Merge the block below into that host's `host_vars` in
`ansible/inventory/legacy.yml`.

```yaml
# vps
codex_config_user: ubuntu
```

The value is not cosmetic. The role asserts that Ansible is connected as this
account and refuses otherwise, reproducing the installer's own refusal
(`ERROR: run this installer as ubuntu without sudo`). The three other legacy
machines connect as `cwoolley`, so a fleet-wide default of `ubuntu` would make
the role refuse on each of them rather than configure the wrong account -- which
is the correct failure, but only if the value is set per host.

## Not host-specific, deliberately in `defaults/main.yml`

`codex_config_feature` is `default_mode_request_user_input` everywhere. Codex
CLI 0.146.0 classifies it as under development, so the NAME may change upstream;
that is a reason to keep it a variable, not a reason to vary it per host.
