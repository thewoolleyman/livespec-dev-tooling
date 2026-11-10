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

## Out-of-band, not provisioned here

- `/usr/local/bin/with-homelab-env.sh`, from the `1password-env-wrapper` repo.
  The role asserts it exists before its first changed task and refuses
  otherwise.
- `CLOUDFLARE_MCP_TOKEN` in the 1Password `homelab` Environment, a Cloudflare
  API token for the Cloudflare API MCP server. The role asserts it resolves
  through the wrapper before its first changed task, and only then writes the
  `[mcp_servers.cloudflare-api]` entry into `~/.codex/config.toml` with
  `codex mcp add`. The entry holds the variable's NAME
  (`bearer_token_env_var`), never the token. An entry already present, such as
  one added by hand, is adopted and left as it is; to change its URL, remove it
  with `codex mcp remove cloudflare-api` and apply again.
