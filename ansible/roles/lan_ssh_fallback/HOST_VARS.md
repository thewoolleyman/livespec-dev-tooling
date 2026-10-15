# `lan_ssh_fallback` — a direct-LAN OpenSSH path between the home-lab hosts

**What it is for.** poweredge-xubuntu, hp-xubuntu and gmktec-xubuntu sit on the
maintainer's home LAN, and on 2026-10-15 their only remote access was Tailscale
SSH. The maintainer ruled (plan `petri-factory-on-gmktec`, epic `bd-ib-fyozyd`
in livespec-orchestrator-beads-fabro) that each must reach the others by direct
SSH without Tailscale, through an OpenSSH server on a non-standard port that
does not conflict with Tailscale SSH, with Tailscale's configuration left
exactly as it is. The control node `vps` is a cloud host, so it reaches a
home-lab host through a jump over another one. Design and its independent
reviews: that repository's `plan/petri-factory-on-gmktec/research/004`.

## How it stays out of Tailscale SSH's way

| | Tailscale SSH | this OpenSSH |
| --- | --- | --- |
| port | 22 | `lan_ssh_fallback_port` (22022) |
| address | the tailnet address | only `lan_ssh_fallback_address`, the wired LAN address |
| host key | `/etc/ssh/ssh_host_*_key` if present, else tailscaled's own store | `/etc/ssh/lan-fallback/ssh_host_ed25519_key` |
| authorized keys | tailnet policy | `/etc/ssh/lan-fallback/authorized_keys/<user>`, then the user's own `~/.ssh/authorized_keys` |

Measured 2026-10-15: hp-xubuntu had no `/etc/ssh/ssh_host_*` keys, so
Tailscale SSH presented tailscaled's own. A default `openssh-server` install
generates those files, which would have changed the key Tailscale SSH presents
on hp. This role's explicit `HostKey` means `sshd -G` lists only the fallback's
key, so the package's postinst creates none of them; the server phase refuses
to activate if any `/etc/ssh/ssh_host_*` file appeared or changed, and if the
key Tailscale SSH presents (read from the control node with `ssh-keyscan`)
differs at the end from the start.

## Variables

| variable | default | where set | meaning |
| --- | --- | --- | --- |
| `lan_ssh_fallback_interface` | `""` (refused) | host_vars | the wired interface, checked to carry the address on every run |
| `lan_ssh_fallback_address` | `""` (refused) | host_vars | the wired LAN address OpenSSH binds and the client aliases dial |
| `lan_ssh_fallback_must_stay_running` | `[tailscaled.service]` | host_vars | units that must be active before and after the change |
| `lan_ssh_fallback_port` | `22022` | defaults | never 22 |
| `lan_ssh_fallback_packages` | `openssh-server`, `openssh-client`, `openssh-sftp-server` at `1:10.2p1-2ubuntu3.8` | defaults | installed or upgraded where the host does not already carry exactly these |
| `lan_ssh_fallback_upgradable` | the three openssh packages | defaults | the only installed packages the transaction may upgrade |
| `lan_ssh_fallback_apt_timers` | `apt-daily.timer`, `apt-daily-upgrade.timer` | defaults | stopped during the install, restarted after |
| `lan_ssh_fallback_user` / `_user_home` | `cwoolley` / `/home/cwoolley` | defaults | the only login |
| `lan_ssh_fallback_client_pubkey_path` | `/home/ubuntu/.ssh/id_ed25519.pub` | defaults | the control node's key, authorised everywhere |

```yaml
# poweredge-xubuntu
lan_ssh_fallback_interface: eno1
lan_ssh_fallback_address: 192.168.1.200
lan_ssh_fallback_must_stay_running: [tailscaled.service, k3s.service]
# hp-xubuntu
lan_ssh_fallback_interface: enp11s0
lan_ssh_fallback_address: 192.168.1.4
lan_ssh_fallback_must_stay_running:
  [tailscaled.service, k3s-agent.service, docker.service,
   fabro-server.service, fabro-server-candidate.service]
# gmktec-xubuntu
lan_ssh_fallback_interface: eno1
lan_ssh_fallback_address: 192.168.1.156
lan_ssh_fallback_must_stay_running:
  [tailscaled.service, k3s-agent.service, local-homelab-llama-server.service]
```

Why the listener is bound by ADDRESS. hp and gmktec also have Wi-Fi on the same
/24 with `arp_ignore=0`, so a peer's packets for the wired address can arrive on
the Wi-Fi interface. An address-bound listener accepts them; a device-bound one
(`BindToDevice=`) would refuse them intermittently, which an earlier draft did.
The wired addresses are `valid_lft forever` and are the addresses the k3s units
already pin (`--node-ip`, `--server`), so the listener is as durable as the
cluster; every run still checks the interface carries the address.

## Three fail-safes against a password-capable listener

If the first drop-in were ever lost or unparsable, `sshd-socket-generator` falls
back to the packaged `ssh.socket` (port 22, all addresses) and a fresh main
`sshd_config` defaults to password authentication. Two independent layers keep
such a listener key-only: the auth-only drop-in `01-lan-fallback-auth.conf`
repeats the key-only, no-root, one-user settings, and on a FRESH install (hp,
gmktec) the role preseeds debconf `openssh-server/password-authentication` to
false, so the postinst writes `PasswordAuthentication no` into the main file
itself (on poweredge, whose main file already exists, the preseed changes
nothing). Such a listener would still never answer Tailscale SSH's traffic:
tailscaled intercepts port 22 on the tailnet address in its own network stack.
The drift report shows any listener that is not exactly the fallback address.

## A local-only listener the package adds

With an `sshd` binary present, systemd's `ssh-generator` also generates
`sshd-unix-local.socket` on `/run/ssh-unix-local/socket` (AF_UNIX). It is not
reachable from the LAN or the tailnet, and `ss -ltn` does not show it. This
role neither creates nor removes it; "nothing listens" in this document means
no TCP listener.

## Operator procedure

```bash
just ansible-drift ansible/lan-ssh-fallback.yml   # read it
just ansible-apply ansible/lan-ssh-fallback.yml -e lan_ssh_fallback_only=hp-xubuntu
just ansible-apply ansible/lan-ssh-fallback.yml   # then the rest
```

Never `--limit`: the key plays must reach every home-lab host and the control
node, because every host's authorized keys and pinned known_hosts are rendered
from all of them. `lan_ssh_fallback_only` changes one host's server and proves
only that host. A host that is already converged (pinned packages, unchanged
drop-ins, listener already on the fallback address, no off switch) is left
alone, so re-applying does not restart its listener.

The server phase runs one host at a time and stops the whole play at the first
failure. On a host without `openssh-server` it holds OpenSSH off with the
package's own switch (`/etc/ssh/sshd_not_to_be_run`, honoured by the packaged
`ssh.socket`), writes the configuration, installs the pinned packages inside an
apt fence that refuses any removal or any upgrade but `openssh-client`, proves
the configuration and the untouched `/etc/ssh` keys while nothing listens, and
only then releases the switch and restarts `ssh.socket`.

Using the fallback: from a home-lab host, `ssh <other-host>-lan`. From the
control node, `ssh <home-lab-host>-lan`, or `ssh <home-lab-host>-lan-via-<jump>`
to choose the jump. The hop is an ordinary Tailscale SSH session on the jump
host running `nc` toward the target's LAN address, so it needs no port-forwarding
grant from the tailnet policy; authentication to the target is the control
node's own key, end to end.

## Rollback

Automatic, inside the server phase, on any failed ACTIVATION check: the off
switch is restored and `ssh.socket` and `ssh.service` are stopped. A failure in
the inert verification before activation leaves the off switch in place, so
nothing of OpenSSH's listens. A failure in the verify play (the end-to-end
logins) rolls nothing back: the servers are in their intended state, and the
failed login is what to investigate. If an apply is abandoned with the off
switch in place on a host that ran OpenSSH before (poweredge), remove it by
hand or its next unattended openssh upgrade leaves OpenSSH stopped. By hand:

```bash
sudo touch /etc/ssh/sshd_not_to_be_run
sudo systemctl stop ssh.socket ssh.service
```

then remove this role's files (`/etc/ssh/sshd_config.d/00-lan-fallback.conf`,
`/etc/ssh/lan-fallback/`, `/etc/ssh/ssh_config.d/50-lan-fallback.conf`) if
the fallback is being retired. On poweredge, whose OpenSSH listened on port 22
before this role and had no login in the 30 days before it, rollback leaves
OpenSSH stopped rather than returning it to port 22. No firewall, interface,
route, sysctl or Tailscale state is changed by this role, so there is nothing
else to restore.

## Hazards outside this role, recorded so the next reader sees them

- **Never delete or rotate `/etc/ssh/ssh_host_*_key` on these hosts as
  "unused by OpenSSH".** OpenSSH no longer uses them, but Tailscale SSH presents
  them (per key type, re-read on every connection), and
  `node_status_credential` pins poweredge's ed25519 one on every k3s agent.
- **A first boot would generate them on hp.** `sshd-keygen.service`
  (`ssh-keygen -A`, all default types into `/etc/ssh`, ignoring sshd_config) is
  enabled by the package and gated by `ConditionFirstBoot=yes`. A future first
  boot (a wiped machine-id, a factory reset) would create `/etc/ssh` keys on hp
  and change every Tailscale SSH pin for hp. Masking that unit is a separate
  decision, not this role's.
- **Unattended openssh upgrades restart the fallback listener.** Every future
  openssh-server upgrade stops `ssh.socket` in its preinst and restarts it in
  its postinst; the fallback flaps for the duration. With the drop-ins in place
  the restarted socket comes back on the fallback port, bound to the interface.
- **The boot path has not been exercised.** The generator, `FreeBind`,
  the address binding and socket activation are only combined at boot. Prove it once
  on the least critical host, through the sanctioned reboot path, when the
  maintainer chooses.

## Retirement

Retire this role when the home-lab hosts move to the Talos fleet (the header of
`inventory/legacy.yml`), whose machines expose no shell.
