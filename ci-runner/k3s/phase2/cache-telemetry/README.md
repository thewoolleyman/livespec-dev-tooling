# cache-telemetry/ — the pod-side cache spans (plan `ci-runner-cache-tiers`)

The pod-side half of SPECIFICATION v054 §"Runner-pool cache telemetry"
(child `livespec-dev-tooling-mlg5sf`; contract in the plan's
`research/003-cache-observability.md`). The host-side half — the
`livespec.ci_cache.*` gauges and their triggers — is
`../../../observability/ci-cache-gauges.sh`.

| File | Role |
| --- | --- |
| `ci-cache-span.sh` | The emitter. Installed as `/opt/ci-runner/bin/ci-cache-span` inside every job container (read-only pool mount). `warm-copy <tier> <hit> <generation> <copy_ms> <copy_bytes> <copy_method> <error>` emits one `cache.warm-copy` span; `job-summary` emits one `cache.job-summary` span with `build.cache.sccache.{enabled,hits,misses,errors,hit_ratio,backend,rw_mode}` read from the job's own sccache server if one is listening. Every span: `repo`, `git.commit.sha`, `git.branch`, `ci.event` (from the runner's `event.json`), `build.env=ci`, `host.name`, `build.cache.kill_switch` (`""` / `operator` / `canary`), `k8s.pod.name`. POSIX sh around an inline `python3` (the job image carries `/usr/bin/python3`); no jq, no curl, no key. |
| `install-cache-telemetry.sh` | Node-local (root), run by `../install-node.sh` after the sccache installer: copies the emitter to `/usr/local/lib/ci-runner-k3s/bin/ci-cache-span`. Re-run after changing the emitter; the ConfigMap converge does not carry it. |

Where the calls live: `../arc/hook-pod-template.yaml` (header item 6) sets
`CI_CACHE_OTLP_ENDPOINT` (the pod-reachable keyless `otlp/pods` listener of
the collector on the pod's own node, port 4319, from the `otel-collector`
repo's `config.ci-runner-host.yaml` — see "Why status.hostIP"),
`CI_CACHE_CANARY_N` and
`CI_RUNNER_NODE_NAME`; its postStart decides the kill-switch value (operator
switch, else the canary: pod-name `cksum` ≡ 0 mod N), writes it with the
start time to `/__w/_temp/_ci_cache/`, and RECORDS the per-tier warm-copy
facts to `warm-copy.tsv` there; its preStop runs `job-end`, which replays
them with their recorded timestamps and the job identity (the runner writes
`event.json` ~10 s after the pod starts — measured 2026-09-04 — so postStart
cannot carry repo/sha/branch without delaying the job) plus the summary, in
one POST. `../local-path-provisioner/` stamps the seeded
uv generation's name at `_warm/.uv-generation`, which is the generation AND
its age (the populator names generations `%Y%m%dT%H%M%SZ`).

## Why status.hostIP

The endpoint is DERIVED per node, not written down. The template declares

```yaml
- name: CI_RUNNER_NODE_HOST_IP
  valueFrom:
    fieldRef:
      fieldPath: status.hostIP
- name: CI_CACHE_OTLP_ENDPOINT
  value: http://$(CI_RUNNER_NODE_HOST_IP):4319
```

and Kubernetes expands `$(VAR)` against env vars declared EARLIER in the same
container's env list, so each pod gets its own node's address with no
templating step, no per-node manifest and no key.

Until the two-node work (plan `k3s-on-gmktec-for-vps-usage`, carrier R3) this
was the literal `http://10.42.0.1:4319` — the cni0 gateway of the first node.
That is not merely the wrong node's address once a second node exists: it does
not exist there at all, because flannel gives each node its own `/24`, so the
second node's gateway is `10.42.1.1`. Every span from a pod on node 1 would
have gone to a bounded, silent, fail-soft timeout — the telemetry disappearing
exactly on the node whose behaviour is new.

Three derivations were possible; this one was chosen:

- **`status.hostIP` (chosen).** Per node, expressible IN THE MANIFEST, and
  therefore usable by BOTH consumers. That last point decides it: the cache
  emitter is a shell script that could compute an address, but the other
  consumer of the same listener is the sandbox image's baked cargo shim
  (`LIVESPEC_SANDBOX_OTEL_ENDPOINT`, header item 7), which only ever reads an
  env var. A derivation that is not expressible as an env value cannot serve it.
- **The node's cni0 gateway.** Also per node, and it is what the pod's default
  route points at — but it is not in the downward API, so a pod can only learn
  it by reading its own routing table at runtime. That is unavailable to the
  cargo shim, and it would put an `ip route` parse in the job's start path.
- **A hostNetwork listener.** Rejected outright: sharing the host network
  namespace with a workflow pod is the containment model this pool is built
  around, and `../warm-cache/README.md` already records "Do not add
  `hostNetwork`" for the populator on the same grounds.

What this asks of the host collector, co-maintained in the `otel-collector`
repo (`config.ci-runner-host.yaml`) and NOT changed from this repository:

1. The `otlp/pods` receiver binds an address the node's OWN address reaches —
   `0.0.0.0:4319`, or the node address — not the cni0 gateway alone. A receiver
   bound only to `10.42.0.1` is unreachable at `status.hostIP` even on the node
   it runs on.
2. Every pool node runs a collector. A node without one costs its jobs their
   spans and nothing else: the emitter is fail-soft by contract (below), so an
   unanswered endpoint changes no job's outcome.

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
kubectl -n arc-runners get configmap arc-hook-pod-template -o jsonpath='{.data.hook-pod-template\.yaml}' | grep -c ci-cache-span   # 3
# in Honeycomb env livespec, dataset github-ci, after one routed job:
#   name = cache.warm-copy   breakdown build.cache.tier, build.cache.hit, build.cache.kill_switch
#   name = cache.job-summary breakdown build.cache.sccache.enabled, repo
```

Fail-soft is the contract: an absent emitter, an empty endpoint, a dead
collector or a slow POST changes nothing about the job. The emitter always
exits 0 and bounds itself with `timeout` (`CI_CACHE_SPAN_TIMEOUT_S`, 4 s).
