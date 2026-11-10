# honeycomb_mcp -- per-host values for the inventory

One value is a property of the machine rather than a fleet default: where this
host keeps its `vps-info` checkout. The role writes that path into the plugin's
`.mcp.json` as the command Claude Code executes, so it is load-bearing at every
session start, long after any playbook has exited. Merge the block below into
that host's `host_vars` in `ansible/inventory/legacy.yml`.

```yaml
# vps
honeycomb_mcp_checkout: /data/projects/vps-info
```

Write the real path, not `~/workspace/vps-info`. `/home/ubuntu/workspace` is a
symlink to `/data/projects`, and the installer this role replaces resolved it
with `pwd -P` before writing it into the config for exactly that reason.

## Out-of-band, not provisioned here

Every input below is asserted before the role's first changed task, so an apply
on a host missing one fails at that assert and names it.

- `/usr/local/bin/with-homelab-env.sh`, from the `1password-env-wrapper` repo.
  The role asserts it exists and refuses otherwise.
- `HONEYCOMB_MGMT_API_KEY` in the 1Password `homelab` Environment
  (`7lpbsdt5yncopgiw3pqbls26xy`), a Honeycomb **Management** key in
  `<KeyID>:<Secret>` form. The legacy name `HONEYCOMB_MCP_KEY` is still
  accepted; the role reports when it is what resolved.
- The `honeycomb@honeycomb-plugins` Claude Code plugin must already be
  installed. The role asserts at least one `.mcp.json` exists under the cache
  and refuses otherwise.
- `npx` (node), which the wrapper calls at every session start.

### Post-apply steps an operator still performs

- **Re-apply this role after every plugin update.** Do it right after running
  `claude plugin update honeycomb@honeycomb-plugins` as the operator account:
  `just ansible-apply ansible/dev-host.yml --tags honeycomb_mcp`. The update
  re-fetches the vendor OAuth definition into the cache and reverts the patch,
  so until the role is applied again every Claude session on the host gets the
  OAuth transport this role exists to replace. Re-applying is also how a NEW
  version directory gets patched at all. Nothing triggers it: no timer, unit or
  release hook runs it, so the operator who updates the plugin owns this step.
  `just ansible-drift ansible/dev-host.yml` reports the unpatched definition as a
  change, which is the check that the step was done.
