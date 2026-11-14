# Diagnosing a gate Job whose pod is already gone

A delegated gate client that reports `was admitted but reached no terminal
condition within 3600s` has already deleted the Job, through its
`delete-abandoned-gate-job` step. Kubelet then removes the pod's logs, and no
gate log is exported. livespec-dev-tooling-yrjatv owns capturing them before
the delete. Until it ships, the evidence below survives.

Measured on 2026-11-11 for gate-livespec-orchestrator-beads-fabro-9p9pc
(livespec-dev-tooling-ddy5xu). With these sources the session could name the
CLASS of cause (a step hung inside the container) but not the step itself.

## What the gates credential can and cannot read

`with-gates-kubeconfig` runs as `system:serviceaccount:gates:gate-submitter`
and is scoped to namespace `gates`.

- It CAN get jobs and pods, and read pod logs (`kubectl -n gates logs <pod>`).
- It CANNOT exec into a pod, list events or create configmaps. A cluster-scope
  read such as `kubectl get jobs -A` or `get events -A` is Forbidden.

## Where the evidence is

- **Node and the Killing event.** Read the events from the control-plane node:
  `ssh poweredge-xubuntu 'sudo -n k3s kubectl -n gates get events -o custom-columns=FIRST:.firstTimestamp,REASON:.reason,OBJ:.involvedObject.name,HOST:.source.host,MSG:.message'`.
  Events last about an hour. Send ONE plain command per ssh call:
  fleet_host_guard refuses a `for` loop or a compound remote command as
  "unparseable" and treats it as a hand change.
- **Start, image pull and OOM.** Read the journal on the node the pod ran on:
  - `ssh <node> 'journalctl -u k3s-agent --since ... | grep <job>'` gives
    "Observed pod startup duration" with `podStartE2EDuration` and
    `totalImagesPullingTime`;
  - `journalctl -k` shows OOM kills and hung tasks.
- **Node load.** `ssh <node> 'LC_ALL=C sar -u|-q|-r|-n DEV -f /var/log/sysstat/saDD -s HH:MM:SS -e HH:MM:SS'`.
  A node that sits idle while its gate "runs" points to a stall, not
  contention.
- **When the work stopped.** In Honeycomb, environment `livespec`, dataset
  `metrics`, query `k8s.pod.cpu.usage` and `k8s.pod.memory.usage` (MAX) with
  filter `k8s.pod.name starts-with <job name>` and granularity 120. It survives
  the pod's deletion. On 9p9pc it showed 1-2 CPU, then about 0 from 17:28Z, then
  a flat 0.37 with 4.6 GB resident: the processes were alive and not
  progressing. A healthy orchestrator gate holds 3-4 CPU for its whole run.
- **The client side.** The gate run's own record,
  `<repo>/tmp/gate-runs/<run>/output.log`, holds the "not finished yet, waited
  Ns" lines and the final refusal. Grep it for the Job name.
- **Siblings on the same node.** Query the same Honeycomb metric with a
  breakdown on `k8s.pod.name`, filtered to `k8s.node.name = <node>`. That shows
  whether every gate on that node behaves the same. On gamingpc-xubuntu, 2 of
  2 full-suite gates hung, which made the cause node-specific.
