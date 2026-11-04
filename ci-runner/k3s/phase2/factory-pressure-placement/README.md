# factory-pressure-placement: steer new factory sandbox pods off a CPU-pressured node

Orchestrator work-item `bd-ib-plon2p`, under plan `kubernetes-sandbox-backend`
(epic `bd-ib-nmuyjc`). The coordinator accepted this route under R301: a
host-side reconciler with a PreferNoSchedule taint, no plugin change, and no
change to the factory credential.

## Why

kube-scheduler scores nodes by CPU **requests**. The sandbox pods' hostname
topology spread counts **pods**. Neither sees actual load. ARC runner pods are
mostly best-effort with no CPU request, so a poweredge-xubuntu with 53-70 of
72 CPUs busy looks nearly empty to the scheduler. Measured 2026-11-04 from
Honeycomb, last 80 h:

| Measure | poweredge-xubuntu | gmktec-xubuntu |
|---|---|---|
| Median implement turn | 29.0 min | 21.4 min |
| CPU-bound per-file-coverage CI job | 2.0-2.2x slower | baseline |

## What runs where

| File | Runs on | What it does |
|---|---|---|
| `publish-node-cpu-pressure.sh` + `.service`/`.timer` (30 s) | every `FACTORY_NODE=true` node (role `factory_pressure_publisher`) | Writes `/proc/pressure/cpu` `some avg60` onto its OWN Node as the condition `LivespecCPUPressure` (`message: cpu.some.avg60=<v>`, `lastHeartbeatTime`). |
| `reconcile-factory-pressure-taint.sh` + `.service`/`.timer` (30 s) | the k3s server (role `factory_pressure_reconciler`) | Compares the factory nodes and sets or clears `livespec.io/factory-pressure=high:PreferNoSchedule`; annotates new sandbox pods with `livespec.io/placement-pressure`. |

**No new credential.** A condition is node *status*. On an agent the publisher
patches it through the scoped node-status kubeconfig `../node-status-credential/`
already mints: get and patch on `nodes/status`, `resourceNames` = that one node.
On the server it uses k3s's admin kubeconfig. That is the same split, and the
same one-refresh-on-rejection, as `../node-extended-resource/patch-node-churn-capacity.sh`.
The reconciler runs only on the server, under the admin kubeconfig.

## The rule

On each 30 s cycle the reconciler works through these steps:

1. **Unknown readings.** A factory node whose `LivespecCPUPressure` heartbeat is
   older than 90 s (or is absent) is UNKNOWN. Any unknown reading removes the
   taint from every factory node.
2. **Fit of the lowest-pressure node:**
   `fit = allocatable cpu - requested cpu (Pending/Running pods) - gates_reserve`.
3. **The gates reserve.** `gates_reserve` is `gates-cq`'s cpu `nominalQuota` for
   the flavor whose `ResourceFlavor.spec.nodeLabels` select that node (mapped
   by labels, never by flavor name), minus the cpu its Pending/Running gate pods
   (namespace `gates`, label `app.kubernetes.io/part-of=livespec-ci-gates`)
   already request. **The reconciler owns no CPU.** That rule was agreed with
   dev-host-test-gate-load, owner of `livespec-dev-tooling-cikd6m`, and recorded
   on `bd-ib-plon2p`.

   **The cap.** If that node's gates flavor sets `.spec.topologyName`, the
   reserve is `min(unused quota, cap)`, where the cap is
   `FACTORY_PRESSURE_GATES_RESERVE_CAP_MILLICPU` (default `5000`, committed in
   `reconcile-factory-pressure-taint.service`). A flavor without
   `topologyName` keeps the uncapped unused quota. The cap was agreed with
   dev-host-test-gate-load (cikd6m). Each cycle logs a `RESERVE` line naming
   the branch it took: `capped-topology` or `uncapped`.
4. **Taint.** If `fit >= 4000m`, every node at least 20 points above the lowest
   gets the taint. Otherwise the taint comes off everywhere, and placement falls
   back to the sandbox pods' own hostname spread.
5. **Quota fail-safe ladder.** Every successful `gates-cq` read is cached in
   `/var/lib/livespec/factory-pressure-placement/gates-quota.json`. If a read
   fails, the cached FULL nominal quota is reserved. If no read has ever
   succeeded, no taint is applied.

`PreferNoSchedule` only scores, so it never leaves a pod Pending. Its weight
(TaintToleration 3) beats the topology spread (2), even at the spread's largest
margin. Both properties were proven on a two-worker kind cluster in
thewoolleyman/sandbox-driver-kubernetes PR #11 (`tests/placement_scoring.rs`).

**Only factory pods are steered.** The ARC runner templates
(`../arc/values-*.yaml`), the ARC hook pod template
(`../arc/hook-pod-template.yaml`) and the gate Job template
(`../gates/gate-job-template.yaml`) all tolerate the key. So CI placement and
the CI slot ruling are unchanged.

**Nothing fights the taint.** `ansible/roles/node_taints` reconciles only
`node-role/ci`. `k3s_config` renders only the profile's `--node-taint`.
`../reconstruct/converge-ci-stack.sh` writes no taint. After a poweredge reboot
(tmpfs datastore) the reconciler restores the taint within one cycle.

## Rollout and inspection

```bash
just ansible-drift ansible/ci-pool.yml --tags ci_converge_unit,factory_pressure_placement
just ansible-apply ansible/ci-pool.yml --tags ci_converge_unit,factory_pressure_placement
```

- `ci_converge_unit` carries the tolerations onto the cluster.
- `factory_pressure_placement` installs the two timers: the publisher on
  poweredge-xubuntu and gmktec-xubuntu, the reconciler on poweredge-xubuntu.

To inspect, read-only:

```bash
journalctl -u reconcile-factory-pressure-taint
/usr/local/lib/ci-runner-k3s/reconcile-factory-pressure-taint.sh --dry-run
```
