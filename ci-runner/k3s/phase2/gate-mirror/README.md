# The gate mirror — how the tree under test reaches a gate pod

A gate Job runs this repository's own `just check` against the **exact tree
being pushed**. That tree has not been pushed to GitHub — not pushing it until
it is green is the entire point — so there is no fetchable remote for a pod to
clone from. This directory is the answer: a bare mirror on the pool's ci-cache
tier that the driver host pushes into over Tailscale SSH, and a read-only
in-cluster git daemon that serves it to a pod on either node.

R4 slice 4 of the livespec plan `k3s-on-gmktec-for-vps-usage` (epic
`livespec-sab5gn`), design in that plan's `research/003` section "The
recommended shape" item E and its correction 3.

## One value names three things

`<tree-hash>` is `git rev-parse HEAD^{tree}` — the hash of the TREE, not of the
commit. It is the same value the green token
(`livespec_dev_tooling/green_token.py`) is keyed on, and that is deliberate:

| what | named by |
|---|---|
| the ref the driver host pushes | `refs/gates/<tree-hash>` |
| the ref the gate pod fetches | `refs/gates/<tree-hash>` |
| the green token the verdict writes | `<tree-hash>` |

Keying on the tree rather than the commit means a rebase, an amended message,
or a re-run of the same content resolves to the same gate result, and there is
exactly one identifier to correlate a push, a served ref and a verdict.

## Where the mirror lives, and where it must not

`/var/cache/ci-runner/gate-mirror.git` — on the **ci-cache tier**, alongside
the sccache snapshot and the PyPI proxy's store.

**Not `/var/lib/git`.** That directory is the packaged git-daemon's default
base path and belongs to the `git` Debian package (`dpkg -S /var/lib/git`
reports git `1:2.53.0-1ubuntu1`), which is exactly why a survey finds it empty
and root-owned: it predates this pool and nothing here put it there. A mirror
placed in it would sit on the **root volume**, outside the storage tiers
(`.ai/ci-node-storage-tiers.md`), competing with the OS for space and lost on a
root rebuild. `ensure-gate-mirror.sh` refuses that path outright rather than
relying on this paragraph being read.

## The receive path

The driver host — the VPS — pushes the tree it is about to gate:

```bash
tree="$(git rev-parse HEAD^{tree})"
git push cwoolley@poweredge-xubuntu:/var/cache/ci-runner/gate-mirror.git \
  "HEAD:refs/gates/${tree}"
```

That works because Tailscale SSH already lands the VPS on `poweredge-xubuntu`
as `cwoolley`, so `git-receive-pack` runs as that account — which is why
`converge-gate-mirror.sh` chowns the mirror to it (`GATE_MIRROR_OWNER`,
default `cwoolley`; it is a host fact, so it is a variable rather than a pin).

### The tailnet-ACL grant this depends on

**Named here, edited nowhere here.** The tailnet policy file is owned by the
`tailscale-admin` repository and is changed **by PR in that repository only**.
This repository contains no ACL and this change edits none. What the receive
path requires of that policy, so that removing it is recognised as breaking
gating rather than as an unrelated cleanup:

1. **Network reach to tcp:22** from the VPS node to `poweredge-xubuntu` — an
   `acls`/`grants` entry whose destination includes port 22 on the node. Without
   it the push fails at connect.
2. **A Tailscale SSH rule admitting the login as `cwoolley`** — an `ssh` entry
   whose `src` covers the VPS, whose `dst` covers `poweredge-xubuntu`, and
   whose `users` includes `cwoolley`.
3. **`"action": "accept"` on that SSH rule, not `"check"`.** A `check` action
   requires an interactive re-authentication in a browser at session start. The
   driver host's push is unattended, so a `check` rule turns every gate into a
   silent hang — this is the one property of the grant that is easy to change
   for good-looking reasons and would break the path.

The exact `src`/`dst` selectors (tags, users, or autogroups) are the
`tailscale-admin` repository's to choose; the three properties above are what
this path consumes.

## Serving it in-cluster

The mirror is a directory on ONE node's tier. A gate Job is admitted onto the
OTHER pool node (`../kueue/DERIVATION.md` "The gates quota on gmktec-xubuntu"),
where a hostPath cannot reach it. `gate-mirror.yaml` therefore runs `git
daemon` pinned to the tier-carrying node behind a ClusterIP Service, and a gate
pod fetches:

```bash
git init --quiet gate-tree && cd gate-tree
git fetch --depth=1 \
  git://gate-mirror.gates.svc.cluster.local/gate-mirror.git \
  "refs/gates/${tree}"
git checkout --detach FETCH_HEAD
```

**Read-only, three ways** — `--disable=` and `--forbid-override=` for both
`receive-pack` and `upload-archive`, and a `readOnly: true` mount. The daemon
is reachable from every pod in the cluster, workflow pods included; a writable
one would let any of them forge the tree a gate is about to bless. **Export-all
is off**: no `--export-all` flag, so only a repository carrying a
`git-daemon-export-ok` marker is served, and the daemon's trailing directory
argument narrows it to this one path. `gate-mirror.yaml`'s header carries the
reasoning for each.

## Pruning

One ref per gated tree, pushed forever, is a ref namespace that grows without
bound — every push and every fetch pays to advertise it, and its objects stay
reachable so nothing reclaims them. Two mechanisms, in this order:

1. **The client deletes its own ref once it has a verdict.** This is the normal
   path and the fast one:

   ```bash
   git push cwoolley@poweredge-xubuntu:/var/cache/ci-runner/gate-mirror.git \
     --delete "refs/gates/${tree}"
   ```

   `ensure-gate-mirror.sh` sets `receive.denyDeletes false` so that this is
   permitted.

2. **A converge-owned sweep is the backstop**, for the client that is killed,
   loses its network, or dies between the verdict and the delete.
   `prune-gate-refs.sh` deletes any `refs/gates/*` ref older than **one day**
   and then reclaims the objects only it referenced; the `gate-mirror-prune`
   CronJob runs it hourly, so a stale ref outlives the cutoff by less than an
   hour.

**Why a day.** A gate is minutes of work, so a day is three orders of magnitude
of headroom over any run that is still in flight — the sweep can never race a
live gate — while still bounding the namespace to roughly the trees of one
day's pushes. It is short enough that the accumulation the sweep exists to
prevent cannot build up between two boots, and long enough that a maintainer
looking at yesterday's failure still finds the tree.

**How a ref is aged**: by the mtime of its loose ref file, which is the instant
the push wrote it. `ensure-gate-mirror.sh` turns `gc.auto` and `receive.autogc`
off so refs stay loose and that timestamp keeps existing; a hand-packed ref
falls back to its committer date, which is a lower bound on the push, and the
sweep reports every use of that fallback on its own line.

## Files

| Path | Role |
|---|---|
| `ensure-gate-mirror.sh` | Creates the bare mirror on the tier, idempotently: `git init --bare`, the config keys the daemon and the sweep depend on, the `git-daemon-export-ok` marker, and the chown to the receive account. |
| `gate-mirror.yaml` | The cluster objects: the `gates` Namespace, the `safe.directory` gitconfig ConfigMap, the sweep-script ConfigMap placeholder, the read-only daemon Deployment, its ClusterIP Service, and the prune CronJob. |
| `prune-gate-refs.sh` | The sweep. Deletes `refs/gates/*` past the cutoff (default one day) and prunes the objects left unreachable. Runs as the CronJob, from the ConfigMap the converge writes. |
| `converge-gate-mirror.sh` | The one idempotent converge: the tier pre-gate, the mirror, the sweep ConfigMap, the manifest, and a bounded rollout wait. Called on every boot by `../reconstruct/converge-ci-stack.sh`. |
| `converge-gate-mirror-exit-tests.sh` | Proves mirror-creation idempotence and the pruning cutoff against scratch repositories, and asserts the read-only/export-all posture and this document's ACL naming. Touches no host. |

## Operating it

```bash
# Converge by hand after editing the manifest or the sweep (as root, on the node):
KUBECONFIG=/etc/rancher/k3s/k3s.yaml ./converge-gate-mirror.sh

# What it WOULD do, from a checkout on any machine — touches nothing:
./converge-gate-mirror.sh --dry-run

# What the CronJob actually runs is the ConfigMap, not the file on disk.
# Confirm the reader before believing an edit landed:
kubectl -n gates get configmap gate-mirror-prune \
  -o jsonpath='{.data.prune-gate-refs\.sh}' | sha256sum
sha256sum ./prune-gate-refs.sh

# The refs currently held, and a sweep that deletes nothing:
git --git-dir=/var/cache/ci-runner/gate-mirror.git for-each-ref refs/gates/
./prune-gate-refs.sh --dry-run /var/cache/ci-runner/gate-mirror.git
```
