# Delegated gates — the source path

How the exact tree under test reaches a gate pod, without going through
GitHub. R4.S4 of plan livespec `k3s-on-gmktec-for-vps-usage` (epic
`livespec-sab5gn`, work-item `livespec-dev-tooling-2hno`); the design is that
plan's `research/003` section E and correction 3.

## The whole path in one picture

```
driver host                  poweredge-xubuntu                     any pool node
(the VPS)                    (the ci-cache tier carrier)

git push  ──Tailscale SSH──▶ /var/cache/ci-runner/gates-mirror/     gate Job pod
HEAD:refs/gates/<tree>       └── <repo>.git  (bare, export-ok)      └── initContainer
                                      │                                  │
                                      └──hostPath, read-only──▶ git-gates ┘
                                                                 Deployment + Service
                                                     git://git-gates.gates.svc.cluster.local:9418
```

`<tree>` is `git rev-parse HEAD^{tree}`. It is the same value
`livespec_dev_tooling.green_token` keys its marker on and the same value the
gate Job's `initContainer` re-derives after checkout and refuses to proceed
without, so ONE value names the pushed tree, the served ref and the written
token. A verdict cannot be separated from the tree it was produced against.

## The artifacts

| File | What it is |
|---|---|
| `converge-gates-mirror.sh` | The converge: creates the bare mirrors on the `ci-cache` tier with the ownership and mode the receive path and the daemon both need, sweeps once, applies the daemon. Run on every boot by `../reconstruct/converge-ci-stack.sh` step 10c. |
| `git-daemon.yaml` | The read-only in-cluster daemon (`ConfigMap` + `Deployment` + `Service`) serving those mirrors at `git://git-gates.gates.svc.cluster.local:9418`. |
| `prune-gate-refs.sh` | The `refs/gates/*` sweep. Run once per converge and hourly by the timer. |
| `gate-ref-prune.service` / `.timer` | The host timer that runs the sweep. Installed and enabled by `../reconstruct/install-converge-unit.sh`. |
| `gates-mirror-exit-tests.sh` | Proves mirror-creation idempotence and the pruning cutoff without touching a host or a cluster. |
| `gates-rbac.yaml` | R4.S2: the gate submitter's ServiceAccount and Role. |
| `gate-job-template.yaml`, `render-gate-job.sh` | R4.S5: the Job a gate run instantiates, and its renderer. |
| `gate-credentials.yaml` | R4.S6: the credentials a gate pod's checks need. |

## The receive path

The driver host pushes over **Tailscale SSH**, which lands it on
`poweredge-xubuntu` as `cwoolley`:

```bash
tree="$(git rev-parse 'HEAD^{tree}')"
repo="$(basename "$(git rev-parse --show-toplevel)")"
git push "cwoolley@poweredge-xubuntu:/var/cache/ci-runner/gates-mirror/${repo}.git" \
    "HEAD:refs/gates/${tree}"
# ... submit the gate Job, wait for the verdict, then:
git push --delete "cwoolley@poweredge-xubuntu:/var/cache/ci-runner/gates-mirror/${repo}.git" \
    "refs/gates/${tree}"
```

SSH, not the git daemon, is deliberately the only way in. The daemon runs
without `--export-all`, serves `upload-pack` alone, forbids a per-repository
override of `receive-pack`, and mounts the mirror `readOnly`. Nothing that can
reach port 9418 can write to a mirror.

The mirror is owned by `cwoolley` at mode `2775`, and every repository sets
`core.sharedRepository = 0664`, so a push writes group-writable,
world-READABLE objects: the receive account can write them and the daemon's
unprivileged uid can read them. `--shared=0664` rather than `--shared=group`
because the latter's result depends on the pushing process's umask, and the
world-read bit is not optional here.

### The tailnet-ACL grant this needs

ACLs for the `perch-rudd` tailnet are owned by the **`tailscale-admin`**
repository and are edited **there, by PR, only**
(`https://github.com/thewoolleyman/tailscale-admin`, `policy.hujson`). Nothing
in this repository edits an ACL, and this section states a requirement rather
than making a change.

**The grant already exists, and no ACL edit is required to make the receive
path work.** It is this rule in `policy.hujson`, which permits a tailnet
member to SSH to a device the same user owns, as any of the listed accounts:

```jsonc
{
    "action": "accept",
    "src":    ["autogroup:member"],
    "dst":    ["autogroup:self"],
    "users":  ["autogroup:nonroot", "root", "ubuntu", "cwoolley"],
},
```

Two properties make it cover this path, and BOTH were verified live on
2026-09-09 rather than assumed:

1. Every persistent device on the tailnet — the VPS and `poweredge-xubuntu`
   included — is untagged and owned by `thewoolleyman@gmail.com`
   (`tailscale status --json`), so `autogroup:self` matches.
2. `cwoolley` is named explicitly in `users`, so the receive account resolves.
   `ssh cwoolley@poweredge-xubuntu 'id'` from the VPS returns
   `uid=1000(cwoolley)`.

**What to ask `tailscale-admin` for is therefore a TEST, not a grant.** The
path depends on a rule written for interactive human SSH, so a future
narrowing of that rule — dropping `cwoolley` from `users`, or replacing
`autogroup:self` with something tighter — would break every delegated gate
with no signal in this repository. Pinning it as an `sshTests` entry makes
that repository's own CI refuse the narrowing. Paste into `policy.hujson`'s
`sshTests` array:

```jsonc
// The delegated-gate receive path (livespec plan
// k3s-on-gmktec-for-vps-usage, R4.S4): the driver host pushes the tree
// under test to a bare mirror on poweredge-xubuntu over Tailscale SSH as
// cwoolley. Covered today by the autogroup:member -> autogroup:self rule;
// this test is what keeps that coverage from being narrowed away silently.
{
    "src":    "thewoolleyman@gmail.com",
    "dst":    ["poweredge-xubuntu"],
    "accept": ["cwoolley"],
},
```

If tailnet ownership ever stops being uniform — the VPS re-enrolled under a
different user, or tagging reintroduced — `autogroup:self` stops matching and
the path DOES need a grant of its own. The narrowest one that restores it,
for that case only:

```jsonc
{
    "action": "accept",
    "src":    ["vps-ci-deploy"],
    "dst":    ["poweredge-xubuntu"],
    "users":  ["cwoolley"],
},
```

`vps-ci-deploy` is the existing stable-IP host alias `policy.hujson` already
declares for the VPS.

## Pruning

One gated push creates one ref. Nothing in the protocol removes it, so the
namespace and the objects it keeps reachable grow without bound. Two
collectors, in this order:

1. **The client deletes its own ref** as soon as it has a verdict (the
   `git push --delete` above). Immediate, and it is R4.S7's job
   (`livespec-dev-tooling-2u2c`). It cannot be the only collector: a client
   that dies between the push and the verdict leaves its ref behind, and that
   is exactly when nobody is left to clean up.
2. **`prune-gate-refs.sh` sweeps what the client did not**, on an age cutoff
   of one day, from `gate-ref-prune.timer` hourly and once per boot converge.
   It then runs `git prune` at the same cutoff to reclaim the objects.

A ref's age is the time it was **pushed**, read from its reflog entry, falling
back to the loose ref file's mtime. It is deliberately NOT the commit's
committer date: re-gating a month-old tree pushes a month-old commit, and
aging by that would delete the ref out from under a gate that is still
running. A ref with neither source is reported and left alone — a sweep that
quietly stopped collecting is the failure the sweep exists to prevent.

`gc.auto` is `0` on every mirror. `git gc` packs refs, and a packed ref has no
loose file; the reflog survives packing, which is why the reflog is the
preferred age source rather than the only-just-adequate one.

## Operations

```bash
# What is served, and to whom
kubectl -n gates get deploy,svc,pods -l app.kubernetes.io/name=git-gates
kubectl -n gates logs deploy/git-gates          # `git daemon --verbose`

# What the mirrors hold (on poweredge-xubuntu)
ls /var/cache/ci-runner/gates-mirror
git --git-dir=/var/cache/ci-runner/gates-mirror/<repo>.git for-each-ref refs/gates/

# Converge by hand; --dry-run prints every command and runs none of them
sudo /usr/local/lib/ci-runner-k3s/gates/converge-gates-mirror.sh --dry-run
sudo /usr/local/lib/ci-runner-k3s/gates/converge-gates-mirror.sh

# Sweep by hand
sudo /usr/local/lib/ci-runner-k3s/gates/prune-gate-refs.sh --dry-run
sudo systemctl start gate-ref-prune.service
systemctl list-timers gate-ref-prune.timer
```

### When a gate Job dies at its fetch

`unable to look up git-gates.gates.svc.cluster.local (port 9418)` means the
Service is absent — the converge has not run since the last boot, or its
step 10c failed. Check `kubectl -n gates get svc git-gates` first, then the
Deployment: a `Pending` pod means the `ci-runner.io/cache-tier-carrier` node
label is missing or `/var/cache/ci-runner/gates-mirror` does not exist, which
is the hostPath's `type: Directory` doing its job rather than letting kubelet
create a root-owned directory the receive path could not write to.

`Repository not exported` means the mirror exists but has no
`git-daemon-export-ok`; re-run the converge. A ref that will not fetch when
the repository does means the push did not land — check the SSH path, not the
daemon.
