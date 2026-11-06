# 009 — Phase E: placing arm64 CI on the worker without drawing in amd64 workloads (2026-11-06)

Groundwork for Phase E (plan assertions 15-19 in [008](008-lan-worker-and-test-strategy-2026-11-05.md) §6), written while
the M4 Max worker's join (livespec-dev-tooling-p4gsn5) waits on its PRs. It records one design problem found by reading the
fleet's runner configuration, and the direction proposed for it. Nothing here is implemented yet.

## What exists

- The worker's kubelet registers with the taint `homelab-worker.livespec.dev/admission=hold:NoSchedule` and the labels
  `homelab-worker.livespec.dev/class=worker` and `homelab-worker.livespec.dev/host=<host>`
  (`homelab-worker/image/systemd/kubelet.service`). The spec says only a separate operator action lifts the hold.
- The fleet's three existing nodes are amd64 (`kubectl get nodes -o wide`, 2026-11-06). The worker is the only arm64 node.
- CI runners are ARC `gha-runner-scale-set` releases. Per-repository sets live under `ci-runner/k3s/phase2/arc/`; a
  host-unique set, `poweredge-xubuntu-k3s` (`ci-runner/k3s/arc/values-host-unique.yaml`), exists so a workflow can address
  one host: "validate a newly joined host" is one of its stated purposes. A set is selected by name through `runs-on:`.

## The problem

The admission hold is the only thing keeping other pods off the worker. Lifting it for Phase E would let the scheduler
place any pod without an architecture constraint on the arm64 node: CI job pods, runner pods, listener pods and fleet
services whose images are amd64-only. Those would fail to start (`exec format error` or a missing manifest), and the
failure would surface as flaky CI, not as a placement error.

## Proposed direction

1. **A permanent class taint, separate from the hold.** The worker also registers with
   `homelab-worker.livespec.dev/class=worker:NoSchedule`, which is never lifted. Only pods meant for homelab workers tolerate
   it. The admission hold keeps its meaning (the operator has not yet admitted this worker), and lifting it no longer opens
   the node to the fleet.
2. **A host-unique arm64 scale set**, following `poweredge-xubuntu-k3s`: `macbook-m4-max-homelab-worker-k3s`, minRunners 0,
   whose runner and job pod templates carry a nodeSelector for `homelab-worker.livespec.dev/host=macbook-m4-max`, a
   toleration for the class taint, and `kubernetes.io/arch: arm64`. The runner image (`ghcr.io/actions/actions-runner`)
   publishes arm64; every image a representative job uses must too (assertion 16).
3. **The representative job** runs from a workflow that addresses that set by name, so no existing CI traffic moves.

Adding the class taint changes the kubelet's registration flags, so it lands in the worker image and its tests before
Phase E's children are filed. Whether to retrofit it onto an already-registered Node (a `kubectl taint` operator action) or
re-register is decided then.

## Open questions for Phase E

- Which existing job is "representative" (assertions 15-17): a Rust build with the shared sccache, or a Python check run.
- Whether the ARC listener for the new set runs on an existing node (it must, under this design) and how its pod template
  is pinned to amd64.
- How the worker's node-local caches (assertion 17) are mounted for jobs without breaking job-state privacy.
