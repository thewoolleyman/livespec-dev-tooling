# cache-telemetry/ — the pod-side cache spans (plan `ci-runner-cache-tiers`)

The pod-side half of SPECIFICATION v054 §"Runner-pool cache telemetry"
(child `livespec-dev-tooling-mlg5sf`; contract in the plan's
`research/003-cache-observability.md`). The host-side half — the
`livespec.ci_cache.*` gauges and their triggers — is
`../../../observability/ci-cache-gauges.sh`.

| File | Role |
| --- | --- |
| `ci-cache-span.sh` | The emitter. Installed as `/opt/ci-runner/bin/ci-cache-span` inside every job container (read-only pool mount). `warm-copy <tier> <hit> <generation> <copy_ms> <copy_bytes> <copy_method> <error>` emits one `cache.warm-copy` span; `job-summary` emits one `cache.job-summary` span with `build.cache.sccache.{enabled,hits,misses,errors,hit_ratio,backend,rw_mode}` read from the job's own sccache server if one is listening. Every span: `repo`, `git.commit.sha`, `git.branch`, `ci.event` (from the runner's `event.json`), `build.env=ci`, `host.name`, `build.cache.kill_switch` (`""` / `operator` / `canary`), `k8s.pod.name`. `publish-endpoint` derives this pod's collector address from its own default route and publishes it for both consumers (see "Why the default gateway"). POSIX sh around an inline `python3` (the job image carries `/usr/bin/python3`); no jq, no curl, no key. |
| `install-cache-telemetry.sh` | Node-local (root), run by `../install-node.sh` after the sccache installer: copies the emitter to `/usr/local/lib/ci-runner-k3s/bin/ci-cache-span`. Re-run after changing the emitter; the ConfigMap converge does not carry it. |

Where the calls live: `../arc/hook-pod-template.yaml` (header item 6) sets
`CI_CACHE_CANARY_N` and
`CI_RUNNER_NODE_NAME`; its postStart calls `publish-endpoint` FIRST — which
derives the pod-reachable keyless `otlp/pods` listener of the collector on the
pod's own node, port 4319, from the `otel-collector` repo's
`config.ci-runner-host.yaml` (see "Why the default gateway") — then decides
the kill-switch value (operator
switch, else the canary: pod-name `cksum` ≡ 0 mod N), writes it with the
start time to `/__w/_temp/_ci_cache/`, and RECORDS the per-tier warm-copy
facts to `warm-copy.tsv` there; its preStop runs `job-end`, which replays
them with their recorded timestamps and the job identity (the runner writes
`event.json` ~10 s after the pod starts — measured 2026-09-04 — so postStart
cannot carry repo/sha/branch without delaying the job) plus the summary, in
one POST. `../local-path-provisioner/` stamps the seeded
uv generation's name at `_warm/.uv-generation`, which is the generation AND
its age (the populator names generations `%Y%m%dT%H%M%SZ`).

## Why the default gateway

The endpoint is DERIVED per node, not written down, and — since carrier R7 —
derived IN THE POD rather than in the manifest. `postStart` calls

```sh
/opt/ci-runner/bin/ci-cache-span publish-endpoint
```

which reads the pod's default route (`ip route`, falling back to
`/proc/net/route` for a job image without iproute2) and publishes
`http://<gateway>:4319` two ways: to `$CI_CACHE_STATE_DIR/otlp_endpoint`, which
the emitter reads back at `job-end`, and as an `/etc/hosts` alias
`otlp-collector.ci-runner.internal`, which is what the pod template's one
literal `LIVESPEC_SANDBOX_OTEL_ENDPOINT` resolves through. **No default route
means nothing is published and both consumers SKIP** — the emitter exits before
`python3` because neither the state file nor the env names an endpoint, and the
alias resolves nowhere.

The gateway is the right value because it IS the node's cni0 bridge address,
and that is the ONLY address the collector's pod-facing receiver binds. That
bind is not incidental: `config.ci-runner-host.yaml` states it as the access
control for a KEYLESS receiver — reachable from the pod CIDR and from the host,
from nothing on the LAN or Tailscale.

### The two derivations this replaced, and why each failed

1. **A bare literal** (the first node's cni0 gateway) — correct on one node and
   nonexistent on a second, because flannel gives each node its own `/24`.
   Unfixable by editing it.
2. **`status.hostIP`** (carrier R3, PR #1903) — per node and expressible in the
   manifest, which is why it was chosen: the other consumer of the same
   listener, the sandbox image's baked cargo shim, only ever reads an env var.
   But it names the node's LAN address, where nothing listens. Measured on
   `poweredge-xubuntu` 2026-09-07: a POST to the cni0 gateway and to
   `127.0.0.1` returned HTTP 200; a POST to the node's `InternalIP`
   `192.168.1.200` — exactly what `status.hostIP` resolves to — was refused
   (`curl` exit 7). Every job's cache and build spans went to a refused address
   for a month with no error, no alert and no rows, because the emitter fails
   soft. R3's note that the receiver "must bind an address reached by the
   node's OWN address" was the tell: that precondition was never satisfiable
   without widening a keyless ingest endpoint onto the homelab LAN, which is
   why the fix is on this side and not the collector's.

### Alternatives weighed for R7 and rejected

- **A per-node value.** Correct, and it needs one template per node — but the
  hook reads exactly ONE ConfigMap for the whole cluster, so this multiplies
  the artifact that `status.hostIP` already proved is easy to get silently
  wrong. The default gateway gives the same per-node correctness from one file.
- **A Service in front of the collector.** Does not avoid the bind question at
  all: a Service's endpoint address is still a real node address, so the
  receiver would still have to bind something wider than the cni0 gateway.
- **A hostNetwork listener.** Rejected outright, as in R3: sharing the host
  network namespace with a workflow pod is the containment model this pool is
  built around, and `../warm-cache/README.md` already records "Do not add
  `hostNetwork`" for the populator on the same grounds.

What this asks of the host collector, co-maintained in the `otel-collector`
repo (`config.ci-runner-host.yaml`) and NOT changed from this repository:
every pool node runs a collector whose `otlp/pods` receiver binds THAT node's
cni0 gateway on port 4319 — which is what the first node's already does, so
this asks for no config change and no new listener. A node without one costs
its jobs their spans and nothing else: the emitter is fail-soft by contract
(below), so an unanswered endpoint changes no job's outcome.

The `/etc/hosts` alias is the only part that can degrade on its own. It is
written by `postStart` as the container's root; a job image whose `/etc/hosts`
is not writable keeps its cache spans (they read the state file) and loses only
the cargo shim's build spans, and `publish-endpoint` says so on stderr — which
lands in the pod's postStart log.

The loopback receiver the HOST-side gauges post to (`127.0.0.1:4319`,
`../../../observability/`) is untouched by any of this — it is a different
receiver on the same collector, and it is already per-node by construction.

## What the spans mean today

No tier copies bytes at job start any more — uv is a reflink seed made at
volume provisioning (`reflink-seed`; it reported `hardlink-seed` from
2026-09-04 to 2026-09-06), the crate registry is host-served — so `copy_ms`
is the postStart's own elapsed time at emission (the cost the tier imposes
at start), `copy_bytes` is 0 and `copy_method` names the realization
(`reflink-seed`, `served`) rather than `copy | reflink`. The per-repo
`target` tier (B2, `livespec-dev-tooling-c5byjh`) will be the first to report
real bytes. `build.cache.kill_switch` is a three-valued string, not the bool
research/003 first sketched: a canary job and an operator-switched job are
both cold and must be told apart in the hit-floor trigger's exclusion.

## Verify

```bash
# on the node, after install-node.sh / a converge:
ls -l /usr/local/lib/ci-runner-k3s/bin/ci-cache-span
kubectl -n arc-runners get configmap arc-hook-pod-template -o jsonpath='{.data.hook-pod-template\.yaml}' | grep -c ci-cache-span   # 4
# the derived endpoint IS the cni0 gateway, and it answers (run on the node):
ip -4 addr show cni0 | awk '/inet /{print $2}'          # <gateway>/24
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'content-type: application/json' \
  --data '{"resourceSpans":[]}' "http://<gateway>:4319/v1/traces"   # 200
# and from inside a live workflow pod (both must agree with the line above):
kubectl -n arc-runners exec <job pod> -- sh -c 'ip route | awk "/^default/{print \$3}"'
kubectl -n arc-runners exec <job pod> -- cat /__w/_temp/_ci_cache/otlp_endpoint
# in Honeycomb env livespec, dataset github-ci, after one routed job:
#   name = cache.warm-copy   breakdown build.cache.tier, build.cache.hit, build.cache.kill_switch
#   name = cache.job-summary breakdown build.cache.sccache.enabled, repo
#   name = build.cargo-*     filter build.env = ci   (the hosts-alias half)
```

A node whose emitter predates `publish-endpoint` writes no
`otlp_endpoint` and emits nothing at all, so **re-run
`install-cache-telemetry.sh` on every pool node** as part of landing this —
the ConfigMap converge does not carry the emitter.

Fail-soft is the contract: an absent emitter, an empty endpoint, a dead
collector or a slow POST changes nothing about the job. The emitter always
exits 0 and bounds itself with `timeout` (`CI_CACHE_SPAN_TIMEOUT_S`, 4 s).
