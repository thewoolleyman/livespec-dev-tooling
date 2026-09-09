# claude_ntfy -- per-host values for the inventory

One value here is genuinely per-machine: the ntfy topic is the host's
notification address, so two machines must never share one. Merge the block
below into that host's `host_vars` in `ansible/inventory/legacy.yml`.

Taken from `vps-info` `services/claude-ntfy/install.sh` (`CLAUDE_NTFY_TOPIC`
default) and its `AGENTS.md` entry, both read at `origin/master`.

```yaml
# vps
claude_ntfy_topic: vps-claude-ready-4267
```

The topic is not a credential, but anyone holding it can publish to it
unauthenticated, so the tasks that write it are `no_log`. It is in the clear
here and in `defaults/main.yml` because it is already in the clear in the
`vps-info` repository and in the phone's subscription list; hiding it in one
place while it is published in three would buy nothing.

`claude_ntfy_server` stays empty on this host. The plugin then uses
`https://ntfy.sh`, and the key is absent from `settings.json` rather than
present with the default written into it.

## Out-of-band, not provisioned here

- `~/.claude/settings.json` must already exist. The role refuses when it does
  not, naming the fix: launch Claude Code once.
- The phone must be subscribed to the topic in the ntfy app. That is device
  state; nothing on the host can establish it.
