# `ssh_hardening` — the public OpenSSH endpoint on the dev host

**What it is for.** The dev host has a routable public IPv4 address and no
host firewall, so its OpenSSH daemon is internet-facing. This role makes that
endpoint key-only for every account but one, binds it to the public address
alone, rate-limits it with fail2ban, and leaves Tailscale SSH (which answers
the tailnet address in tailscaled's own network stack) exactly as it is.

**Where the design comes from.** `vps-info` `services/ssh-hardening/`, commits
`011bb42` and `92d265d` (2026-10-02), operator-approved so that the Herdr
Android client can reach the host by password as `ubuntu`. That installer put
the files on the live host on 2026-10-02 and reloaded `ssh.service` at
22:41:50 that day. An earlier copy of this role predated it, and applying that
copy would have dropped the public `ListenAddress`, `MaxAuthTries`,
`LoginGraceTime`, `MaxStartups` and `PermitEmptyPasswords no`, and known
nothing of the password exception, the `ssh.socket` drop-in or fail2ban. On
2026-10-16 the maintainer ruled "Update role to live": the role now renders
the live files byte for byte, so converging the host changes and reloads
nothing.

## Per-host values

These are properties of the machine, not role defaults. The role refuses to
run until the first two are set.

```yaml
# vps
ssh_hardening_public_address: 66.94.121.15
ssh_hardening_password_user: ubuntu
ssh_hardening_negative_control_addresses:
  - 127.0.0.1
  - 100.89.189.118
```

| variable | default | where set | meaning |
| --- | --- | --- | --- |
| `ssh_hardening_public_address` | `""` (refused) | host_vars | the public IPv4 address: sshd's `ListenAddress`, `ssh.socket`'s `ListenStream` and the password Match's `LocalAddress` all render from it |
| `ssh_hardening_password_user` | `""` (refused) | host_vars | the one account allowed password authentication, and only on the public address |
| `ssh_hardening_negative_control_addresses` | `[127.0.0.1]` | host_vars | local addresses where the proof requires password authentication to be OFF for that account; vps adds its tailnet address |
| `ssh_hardening_port` | `22` | defaults | the public port |
| `ssh_hardening_max_auth_tries` | `3` | defaults | `MaxAuthTries` |
| `ssh_hardening_login_grace_time` | `30` | defaults | `LoginGraceTime` |
| `ssh_hardening_max_startups` | `10:30:30` | defaults | `MaxStartups` |
| `ssh_hardening_dropin_dir` / `_dropin_name` | `/etc/ssh/sshd_config.d` / `00-ssh-hardening.conf` | defaults | the drop-in; `00-` must sort before cloud-init's `50-` |
| `ssh_hardening_legacy_dropin_name` | `00-disable-password-auth.conf` | defaults | an older hand-applied drop-in, removed |
| `ssh_hardening_sshd_config` | `/etc/ssh/sshd_config` | defaults | the main file the Include is appended to |
| `ssh_hardening_password_match_path` | `/etc/ssh/vps-ubuntu-password.conf` | defaults | the password Match file |
| `ssh_hardening_socket_name` / `_socket_dropin_dir` / `_socket_dropin_name` | `ssh.socket` / `/etc/systemd/system/ssh.socket.d` / `vps-listen.conf` | defaults | the listener drop-in |
| `ssh_hardening_fail2ban_packages` | `fail2ban`, `python3-systemd`, `nftables` | defaults | installed if absent |
| `ssh_hardening_fail2ban_jail_path` | `/etc/fail2ban/jail.d/vps-sshd.local` | defaults | the sshd jail |
| `ssh_hardening_fail2ban_service_name` / `_client_bin` | `fail2ban.service` / `/usr/bin/fail2ban-client` | defaults | |
| `ssh_hardening_service_name` / `_sshd_bin` | `ssh.service` / `/usr/sbin/sshd` | defaults | |

The `vps-` file names are the paths the `vps-info` installer created. They are
kept so the role converges that host with no change; renaming one is a
deliberate change that removes nothing (the old file would stay on disk).

## What the role writes

| path | from | change triggers |
| --- | --- | --- |
| `/etc/ssh/sshd_config.d/00-ssh-hardening.conf` | `templates/00-ssh-hardening.conf.j2` | `ssh.service` reload |
| `/etc/ssh/vps-ubuntu-password.conf` | `templates/password-match.conf.j2` | `ssh.service` reload |
| `/etc/ssh/sshd_config` | one appended line, `Include /etc/ssh/vps-ubuntu-password.conf`, only when absent | `ssh.service` reload |
| `/etc/systemd/system/ssh.socket.d/vps-listen.conf` | `templates/ssh-socket-listen.conf.j2` | daemon-reload, then stop and start `ssh.service` and `ssh.socket`, refused unless `KillMode=process` |
| `/etc/fail2ban/jail.d/vps-sshd.local` | `templates/fail2ban-sshd.local.j2` | `fail2ban-client -t`, restart, wait for the `nftables-multiport` action |

The Include must be the LAST active directive of `sshd_config`: a `Match`
block applies to everything after it, so a global directive appended later
would apply only to the password account. The role asserts this on every run,
including `--check`. The drop-in's first comment still reads "Managed by
vps-info/services/ssh-hardening/install.sh"; rewording it is a byte change and
therefore a reload, so it is left for a deliberate follow-up.

## The password is out of band

No file this role writes holds a secret. The Match file only PERMITS password
authentication for one account on one address; the password itself is that
account's entry in `/etc/shadow`, which this role never reads or writes. It is
set by an explicit rotation outside any converge (`vps-info`
`services/ssh-hardening/set-ubuntu-password.sh`, which reads a one-line file
the operator places, sets it through `chpasswd` and shreds the file). If the
account has no usable password the Match is harmless: password logins fail
and key logins are unaffected.

## Operator procedure

```bash
just ansible-drift ansible/dev-host.yml --tags ssh_hardening   # read it
just ansible-apply ansible/dev-host.yml --tags ssh_hardening   # converge
```

On a host already converged the drift report shows `changed=0` for this role
and the apply notifies no handler. Keep a Tailscale SSH session open while
applying any real change; it does not depend on anything this role touches.
