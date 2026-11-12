# Reaching a fleet host over SSH

Read this before recording that a fleet host cannot be reached, before asking
the maintainer or a coordinator for "a route" to a host, and on any of these
three errors:

- `tailscale: failed to look up local user "<name>"`
- `No ED25519 host key is known for <host>.perch-rudd.ts.net. and you have requested strict checking.`
- `Permission denied (publickey)` from a fleet host

Each of them is a wrong account or a wrong method. None of them means the host
is unreachable.

## Where the routes are written down

The `tailscale-admin` repository (a sibling clone, `/data/projects/tailscale-admin`
on the VPS) is the record of every tailnet machine: its `AGENTS.md` "Machines"
and "Remote Access" sections and its `README.md` machine table give each host's
SSH account and SSH server, with the date each was last measured. Read it
first. Do not restate its table here; it changes there.

Every machine is on the tailnet and the tailnet is how every host is reached.
The maintainer's direction is to use it, and not to build or maintain a
separate per-host SSH setup (maintainer, 2026-11-12).

## The two shapes that fail, and why

- **A bare `ssh <host>`.** It logs in as the calling host's own account name.
  From the VPS that is `ubuntu`, which exists on the VPS and on
  `gamingpc-xubuntu` only. Name the account the record gives:
  `ssh cwoolley@poweredge-xubuntu`, `ssh cwoolley@macbook-m4-max.perch-rudd.ts.net`.
- **`tailscale ssh` to a Mac.** The macOS GUI Tailscale client cannot host a
  Tailscale SSH server, so a Mac publishes no Tailscale SSH host key and the
  client refuses it with the "No ED25519 host key is known" line above. The
  Macs take ordinary `ssh <account>@<host>.perch-rudd.ts.net` over the tailnet.
  Which nodes host Tailscale SSH can be read locally:
  `tailscale status --json`, a peer's `sshHostKeys` list (present on the Linux
  nodes, absent on the Macs).

## Before you write "no route" anywhere

1. Read the `tailscale-admin` record for the host and retry with its account
   and method.
2. Search the plan's own timeline for how the host was reached before. A plan
   that has worked on a host has a record of how.
3. Record the exact command, its exit code and its error text. A "no route"
   claim with no measurement beside it is not a finding.

Only then may a blocker be recorded or carried to the maintainer.

## What this cost (2026-11-12, plan homelab-k8s-worker-nodes)

A session on the VPS tried `ssh macbook-m4-max` and
`tailscale ssh cwoolley@macbook-m4-max`, got the first and second errors above,
and recorded "NO agent route to the macbook-m4-max host exists" on
livespec-dev-tooling-nxxqf5. A coordinator ratified it and carried "give agents
a route" to the maintainer. The next session inherited the claim from a handoff
and repeated it for five hours. The route,
`ssh cwoolley@macbook-m4-max.perch-rudd.ts.net`, had been in `tailscale-admin`
since 2026-09-09, the plan's own timeline recorded the M4 being reached over
the tailnet on 2026-11-04 and 2026-11-06, and one command proved it. The plan's
host work sat blocked for about eight hours on a question nobody needed to ask.
