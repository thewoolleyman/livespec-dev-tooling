## The maintainer's statement of what done means

Question: "Do we have proper honeycomb observability in place for all of the Kubernetes usage to know the load and utilization of all the Kubernetes worker nodes?" Then: "Unless the answer is yes, completely, and we will need everything, then you need to spin up a new plan to put that in place and implement it as the priority (so we can have visibility into the Kubernetes load and not fly blind)."

## Definition of Done assertions derived from that statement

- Every node the k3s cluster lists (today poweredge-xubuntu, gmktec-xubuntu and hp-xubuntu) reports kubelet CPU usage (k8s.node.cpu.usage) and memory working set (k8s.node.memory.working_set) into the Honeycomb livespec environment's metrics dataset, attributed by k8s.node.name, with datapoints in every 15-minute window.
- Every cluster node reports kubelet filesystem usage and capacity (k8s.node.filesystem.usage, k8s.node.filesystem.capacity) and network traffic (k8s.node.network.io) into that dataset, attributed by k8s.node.name.
- Every cluster node reports its Ready, MemoryPressure, DiskPressure and PIDPressure condition gauges into that dataset, attributed by k8s.node.name.
- Every running pod's CPU and memory usage rows carry k8s.node.name and k8s.namespace.name, and the node named equals the node the API server scheduled that pod on, including pods in the factory namespace.
- Every cluster node runs a host collector whose hostmetrics (CPU utilization, load average, memory usage, filesystem usage, disk and network I/O) reach the livespec environment's metrics dataset with host.name equal to that node's name.
- Per cluster node, the CPU and memory requests and limits of the containers scheduled on it are queryable in Honeycomb grouped by k8s.node.name, beside that node's allocatable CPU and memory.
- A Honeycomb board in the livespec environment shows, per cluster node, CPU, memory, filesystem and network usage, pressure conditions, requests and limits against allocatable, and pod usage by node and namespace.
- A Honeycomb trigger in the livespec environment fires when any cluster node's CPU usage stays at or above a saturation threshold of its capacity.
- A Honeycomb trigger in the livespec environment fires when any cluster node reports MemoryPressure or its memory working set crosses a threshold of its capacity.
- A Honeycomb trigger in the livespec environment fires when any cluster node stops reporting kubelet usage.
- Every cluster node's collector is converged from committed GitOps state by ansible/ci-pool.yml, so a drift report on a node whose collector differs from the merged configuration reports the difference.

# kubernetes-node-observability — charter

Opened 2026-10-24 by seat `kubernetes-node-observability`, launched by the
coordinator session `gitops-fleet-capacity-monitoring` (plan epic
livespec-dev-tooling-dfixhe) at the maintainer's direction. The maintainer
named this the fleet's PRIORITY work, alongside the Kubernetes cutover itself.

The assertions above are SESSION-DERIVED (unattended creation under a standing
direction); the first handoff records that.

## The answer to the maintainer's question was NO

Measured by the coordinator 2026-10-24 ~01:1xZ (Honeycomb env `livespec`,
dataset `metrics`) and re-read by this seat on the hosts at 01:2xZ:

| Signal | poweredge-xubuntu (server) | gmktec-xubuntu (agent) | hp-xubuntu (factory-only agent) |
|---|---|---|---|
| `k8s_cluster` allocatable | yes (72 CPU) | yes (32 CPU) | yes (0.5 CPU, 4.7 GiB) |
| `kubeletstats` node usage | yes | **no** | **no** |
| `hostmetrics` in env `livespec` | yes | **no** (no collector at all) | **no** (goes to env agent-activity) |
| pod usage carries `k8s.node.name` | **no** | **no** | **no** |

## Root causes (read from source and the live hosts)

1. **One kubelet is scraped.** `thewoolleyman/otel-collector`
   `config.ci-runner-host.yaml` (running unchanged on poweredge, otelcol-contrib
   0.147.0) declares ONE `kubeletstats` receiver with
   `endpoint: ${env:OTEL_K8S_NODE_NAME}` = poweredge-xubuntu. Its own comment:
   "Single-node cluster, so one receiver covers it; a second node would add a
   second instance." The cluster grew to three nodes and nobody added one.
2. **No node attribution on pod rows.** `kubeletstats` pod/container resources
   carry pod uid/name and namespace but not `k8s.node.name`, and no
   `k8sattributes` processor runs. Worse, `resourcedetection/system` stamps the
   COLLECTOR's `host.name` (poweredge) on every k3s row, so a pod row reads as
   poweredge's whatever node it ran on.
3. **gmktec has no collector.** `/usr/local/bin/otelcol-contrib` is absent; its
   `otel-receiver.service` is the Fabro span receiver, not a metrics collector.
4. **hp's host metrics go to the other environment.** `config.hp-factory.yaml`
   exports hostmetrics + docker_stats to env agent-activity dataset
   `livespec-host-metrics` (Route A, bd-ib-bdcmok.3) and holds no livespec key.
5. **The class of cause: hand-run installers.** poweredge's and hp's collectors
   were put there by `scripts/install-*.sh` run by hand; the
   `ansible/roles/otel_collector` GitOps role converges only the dev host
   (`vps`). Nothing in `ansible/ci-pool.yml` names a collector, so a rebuilt
   node comes back silent and its drift report says zero changes — the exact
   failure `ci_observability` was turned into a role to end.

## Design (decided)

- **Every kubelet, discovered, from the one collector holding a cluster
  credential.** On poweredge, replace the single `kubeletstats` with
  `receiver_creator` over `k8s_observer` (`observe_nodes: true`,
  `auth_type: kubeConfig`), instantiating one `kubeletstats` per node through
  the API-server proxy with the node's name as endpoint. A node that joins is
  scraped with no config edit. The existing read-only ClusterRole already
  grants nodes list/watch, nodes/proxy and nodes/stats.
- **Attribution.** Add `k8sattributes` (`auth_type: kubeConfig`, pod
  association by `k8s.pod.uid`, extracting `k8s.node.name`,
  `k8s.namespace.name`, `k8s.pod.name`, `k8s.deployment.name`) to the k3s
  pipeline; the ClusterRole already grants pods, namespaces, nodes, replicasets.
  Then set `host.name` from `k8s.node.name` where present, so a k3s row's
  host.name names the node it is ABOUT, and keep the collector's own name as
  `collector.host.name`.
- **Utilization against requests/limits.** Enable kubeletstats' optional
  `k8s.pod.{cpu,memory}_{request,limit}_utilization` and
  `k8s.node.{cpu,memory}`-level metrics; `k8s_cluster` already emits
  `k8s.container.{cpu,memory}_{request,limit}` with `k8s.node.name`.
- **Host metrics on every node, in env livespec.** gmktec gets a collector of a
  new `config.k3s-agent-host.yaml` shape (hostmetrics only → env livespec). hp
  keeps its agent-activity feed (its triggers depend on it) and gains a second
  hostmetrics pipeline exporting to env livespec, which needs
  `HONEYCOMB_INGEST_KEY_LIVESPEC` placed in its `/etc/otel-collector/.env`.
- **GitOps.** Generalize `ansible/roles/otel_collector` (config file, service
  user, extra environment files and KUBECONFIG become per-host variables) and
  add it to `ansible/ci-pool.yml` for every `ci_pool` host, so the CI nodes'
  collectors converge from the merged config exactly as the dev host's does.
  The binary, the ingest key and poweredge's identity render remain asserted
  preconditions, matching the role's existing posture.
- **Board and triggers as code**, beside the existing ones:
  `ci-runner/observability/boards/` and `ci-runner/observability/triggers/`,
  converged by their `apply-*.sh` with `HONEYCOMB_CONFIG_KEY_LIVESPEC`.
  Per-node silence triggers are one per node, because a grouped query cannot
  fire on a group's absence.

## Routing

- Collector configuration and per-node installs (otel-collector repo, the three
  hosts, secret placement): host work, `factory-exempt:infra-in-person` — it is
  a different repository with no factory lane, and its acceptance is a running
  collector on the nodes holding a placed credential.
- The `otel_collector` role generalization + `ci-pool.yml` wiring + its tests:
  factory-eligible; dispatched as `impl:<id>`.
- Board and trigger definitions: applied with a Honeycomb configuration key
  and validated against columns that exist only after the collector changes
  land; host work, `factory-exempt:infra-in-person`.

## Side finding handed to the coordinator, not carried here

hp-xubuntu's allocatable is 0.5 CPU / 4.7 GiB, and the one live `factory`
namespace pod is scheduled on poweredge-xubuntu (untainted), not hp. Where
factory pods may land is the cutover's question; this plan only makes it
visible.

## Routing amendment, 2026-10-24 ~01:40Z: the GitOps role is the critical path

The fleet host guard (`fleet_host_guard.py`, PreToolUse) refuses ANY by-hand
change to a fleet host — including uploading a file to `/tmp` — so the
otel-collector repository's hand-run installers cannot deliver the merged
configurations at all. The generalized `otel_collector` role, applied by
`ansible/ci-pool.yml`, is therefore the ONLY deployment path, and it must also
do what the installers did: create the `otel-collector` service user, install
the pinned otelcol-contrib 0.147.0 binary (sha256-verified), and append a
missing ingest-key line from the control node's credential-wrapper environment.
That child stays factory-routed; the configuration change it deploys is merged
(otel-collector `cb42f5f`, PR thewoolleyman/otel-collector#11), validated with
`otelcol-contrib validate` 0.147.0 on the control node.

Already true before any deploy (Honeycomb livespec/metrics, 01:15–01:45Z):
`k8s_cluster`'s node condition gauges, allocatable and
`k8s.container.cpu_request` arrive for all three nodes with `k8s.node.name`,
so assertions 3 and 6 need only the board to show them.

The epic's creation timestamp was passed as 03:30Z; the real time was ~01:30Z
(local file mtimes were misread as UTC).
