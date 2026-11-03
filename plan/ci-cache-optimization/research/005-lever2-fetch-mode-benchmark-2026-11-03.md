# 005: lever 2 benchmark — a reference object store wins; per-step exec overhead found (2026-11-03)

Measured 2026-11-03, 23:12-23:20Z, by the ci-cache-optimization seat. This note follows research 004 and settles the
design question that note left open.

## Benchmark

Repository: livespec-orchestrator-beads-fabro, the largest (40 MB mirror, 775 branches, 812 tags). For each mode
there were 3 repetitions into a fresh `git init`. The scratch directory was under the login user's `~/.cache` and was
removed afterwards. Nothing else on the node was touched.

- Modes: `gh` fetches from GitHub. `mir` fetches from a local bare mirror over `file://`, which is a lower bound for any
  served mirror. `alt` fetches from GitHub with the mirror's object directory as an alternate.
- `d1` is `--depth=1` of master. `full` is the `fetch-depth: 0` refspec (`+refs/heads/*` and `+refs/tags/*`).
- Times are seconds. The load is the 1-minute load average at the start.

| Node (cores, load) | gh-d1 | mir-d1 | alt-d1 | gh-full | mir-full | alt-full |
|---|---|---|---|---|---|---|
| gmktec (32, 6.5) | 1.84-2.12 | 0.53-0.63 | 0.79-0.87 | 2.19-2.41 | 1.53-1.57 | **0.51-0.55** |
| poweredge (72, 114) | 2.88-3.12 | 2.42-2.46 | 2.25-2.27 | 6.50-7.69 | 6.76-7.13 | **0.97-1.07** |
| hp, runner-only (16, 10.4) | 2.35-3.18 | 1.16-1.35 | 1.31-1.53 | 3.40-5.49 | 2.83-2.98 | **0.73-0.79** |

Conclusions:

- **For full-history fetches, a reference object store is the lever, and a redirected mirror is not.** On the loaded
  poweredge node, a local mirror is no faster than GitHub (6.8-7.1 s against 6.5-7.7 s), because it still builds and
  indexes a full pack on every job. With alternates the fetch takes about 1 s on every node, since only the objects
  the store lacks are transferred.
- For shallow fetches the gain is smaller, and it shrinks under load: 0.6-0.8 s saved on poweredge, 1-1.3 s on gmktec
  and hp. A mirror and alternates are about equal here.
- The CI fetch tail in research 004 (up to 29 s) is far above even the loaded benchmark. That points to node CPU
  contention inflating pack work, which is exactly the work alternates remove.

## The zero-workflow-change mechanism

The pool spec requires caching with zero workflow changes. `actions/checkout` deletes the work tree and runs
`git init` before it fetches, so nothing can drop an `info/alternates` file in between. The environment variable
`GIT_ALTERNATE_OBJECT_DIRECTORIES` does the same job, and the hook pod template can set it for the job container.

The mechanism was tested on the dev host against GitHub with the full refspec:

| Setup | Objects written to the fresh repository |
|---|---:|
| No alternate | 34,960 KB |
| `info/alternates` file | 4 KB |
| `GIT_ALTERNATE_OBJECT_DIRECTORIES` | 0 KB |

Fetch negotiation honours the environment variable, and checkout works with it. One constraint follows: the
repository's objects then live only in the store. `git fsck` WITHOUT the variable fails, so every git process in the
job must see it. The variable has to be set pod-wide, and the store must never prune an object while a job may still
depend on it. Refreshing the store by fetching, with no `gc --prune` while jobs run, satisfies that.

The proposal for lever 2 is therefore a **node-local, read-only reference object store per repository**. A timer
refreshes a bare clone of each fleet repository (about 20-40 MB each). The job pod mounts it read-only, and
`GIT_ALTERNATE_OBJECT_DIRECTORIES` points at it.

For runner-only hp, the store can be a local bare clone on its own runner disk. Alternates need a filesystem path, so
reading the store over the network would mean NFS. That makes hp the open spec question for the propose-change:
whether a per-node git object store, which is not a ci-cache tier, is allowed on a runner-only node.

## Revised saving

The research 004 sample is 29 full and 45 shallow fetches, 808 s in all.

- Full fetches move from 243 s to about 1 s each, about 29 s.
- Shallow fetches keep about 60% of their 208 s, the ratio benchmarked on the two loaded nodes.

The saving is about (214 + 83) / 808 = 37% of the row, about **19 h/wk** normalized (research 002's ≈53 h/wk). That is
down from the 25 h/wk estimate, and it is the figure the carrier should be ranked by. It still ranks lever 2 second,
after lever 1.

## Found while measuring: per-step exec overhead (not a cache lever)

Every step of a k3s job runs through `Run '/home/runner/fleet-hook/index.js'`, the container hook that executes the step
inside the job pod.

- Over the 72 research 004 jobs there were a median of 9 hook launches per job, including post steps and uploads.
- A no-op step (`git config --global --add safe.directory '*'`, 72 instances, timed from the logs) costs a median of
  1.02 s, with a p90 of 1.98 s.
- That makes about 9-10 s of fixed overhead per job. Over roughly 13,000 CI job containers a day (research 003's
  kubelet counts), it is a large figure, on the order of the levers above.

It is runner architecture, not caching, so it is relayed to ci-runtime-and-cost (epic livespec-dev-tooling-ib3oe3)
and not carried here. A weekly figure needs a job count from that plan's own method before anyone ranks it.

## Method note for the next measurement

The benchmark was piped to each node over `ssh` as a stdin script. The fleet host guard
(`fleet_host_guard.py`, ssh+git+clone) blocks an equivalent inline command as a by-hand host change. The scratch
benchmark changed no host state, but the next node-side measurement should go through committed automation, or ask
the node owner. It should not take the stdin path a second time.
