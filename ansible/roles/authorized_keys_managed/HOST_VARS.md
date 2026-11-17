# `authorized_keys_managed` — narrow entries in a shared authorized_keys file

This role manages only its own marker-delimited entries and explicitly retired
public-key blobs. It leaves every other line unchanged and in place.

```yaml
authorized_keys_managed_user: ubuntu
authorized_keys_managed_group: ubuntu
authorized_keys_managed_path: /home/ubuntu/.ssh/authorized_keys
authorized_keys_managed_entries:
  - name: hetzner-xubuntu-dolt-tunnel
    public_key: ssh-ed25519 <base64> hetzner-xubuntu dolt-tunnel
    permitopen: 127.0.0.1:3307
authorized_keys_managed_retired_keys:
  - ssh-ed25519 <base64>
```

`authorized_keys_managed_retired_keys` contains exactly a key type and base64
body, never its options or comment. A retired blob that is also managed makes
the role refuse before it writes. Private keys are never committed.

Every managed entry is a local-forward-only key: `restrict`,
`port-forwarding`, an exact `permitopen`, `permitlisten="invalid.invalid:1"`,
and a forced `command` deny shells, client-chosen commands, remote forwards,
and other destinations. Apply against the OpenSSH public address, not Tailscale
SSH.

The forced command is
`/usr/bin/setpriv --pdeathsig KILL /usr/bin/sleep infinity`: it does nothing
and blocks. It blocks so that a forwarding client can open a session instead
of running `ssh -N`. On OpenSSH 10.0 (vps), sshd sets `TCP_NODELAY` on the
connection only when a session starts. Without it, Nagle's algorithm holds
small forwarded replies for about one extra round trip
(hetzner-xubuntu-info research note 024). `setpriv --pdeathsig KILL` kills
the sleep when its sshd parent exits. sshd does not kill a no-pty session's
child when the connection drops, so a bare `sleep` would be left behind on
every reconnect. A `-N` client never opens a session, so this command never
runs for it.

```text
just ansible-drift ansible/dev-host.yml --tags authorized_keys_managed
just ansible-apply ansible/dev-host.yml --tags authorized_keys_managed
```

## DRAFT: opt-in read-only `bd` exec (`bd_readonly_exec`) — not applied

`livespec-dev-tooling-tbhqye` route A. An entry may set `bd_readonly_exec: true`.
Its forced command is then `/usr/local/sbin/authorized-keys-bd-readonly-exec`
(installed by this role from `files/authorized-keys-bd-readonly-exec.sh`), which
keeps the blocking tunnel session and additionally accepts a client command only
if it is exactly `in <repo> bd show|list|comments <args>`. `<repo>` must be an
exact line of `/etc/authorized-keys-bd-readonly-exec/repos`, written from
`authorized_keys_managed_bd_readonly_exec_repos`; the tenant is resolved only as
`/data/projects/<repo>`, never from a client path. Arguments are limited to
`--json`, `--all`, `--limit`, `--status` and plain ids and words; anything else
exits 126. Per the maintainer (2026-11-17) the key may read every fleet tenant
and the output has no size cap, because the cost is latency, not bandwidth.
Default is unchanged: an entry without the key keeps the forward-only command, no
new key or account is added, and revert is removing the key from the entry.
Whether to switch it on at all is still open.
