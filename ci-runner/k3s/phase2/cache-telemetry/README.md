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
`CI_CACHE_OTLP_ENDPOINT` (the host collector's pod-reachable keyless
`otlp/pods` listener, `http://10.42.0.1:4319`, from the `otel-collector`
repo's `config.ci-runner-host.yaml`), `CI_CACHE_CANARY_N` and
`CI_RUNNER_NODE_NAME`; its postStart decides the kill-switch value (operator
switch, else the canary: pod-name `cksum` ≡ 0 mod N), writes it with the
start time to `/__w/_temp/_ci_cache/`, and emits the per-tier spans; its
preStop emits the summary. `../local-path-provisioner/` stamps the seeded
uv generation's name at `_warm/.uv-generation`, which is the generation AND
its age (the populator names generations `%Y%m%dT%H%M%SZ`).

## What the spans mean today

No tier copies bytes at job start any more — uv is a hardlink seed made at
volume provisioning, the crate registry is host-served — so `copy_ms` is the
postStart's own elapsed time at emission (the cost the tier imposes at
start), `copy_bytes` is 0 and `copy_method` names the realization
(`hardlink-seed`, `served`) rather than `copy | reflink`. The per-repo
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
