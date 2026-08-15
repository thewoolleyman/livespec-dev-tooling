# Phase-2 validation checklist

**Not run by this design pass (`livespec-s43svm.15`).** Everything
below requires a live k3s + ARC + Kueue cluster
(`livespec-s43svm.14`'s remaining live-host install steps, owned by a
separate, actively-in-flight track as of this writing) — this design
pass does not touch `poweredge-xubuntu` or any live cluster. Run this
checklist once that cluster exists, in order; each item names what it
depends on and what "pass" means concretely.

1. **Confirm the `Cohort`/Fair-Sharing API shape against the real
   v0.19.1 CRDs.** `README.md` "Fair Sharing, and what it changes"
   documents an assumption (the simpler string-typed
   `ClusterQueue.spec.cohort` field, plus per-`ClusterQueue`
   `spec.fairSharing.weight`, plus cluster-wide `fairSharing.enable` in
   the Kueue `Configuration`) reasoned from public documentation, not
   confirmed against a running v0.19.1 install. Run
   `kubectl explain clusterqueue.spec.cohort` and
   `kubectl explain clusterqueue.spec.fairSharing` against the live
   cluster and confirm the fields exist with the expected shape before
   applying `kueue/cluster-queue-*.yaml` for real.
2. **Determine whether ARC's own controller needs
   `admission_response.py`'s classification logic.**
   **PARTIALLY ANSWERED (2026-08-15, source-read leg — no live cluster
   needed for this part):** ARC's modern `gha-runner-scale-set` path
   calls into the [`actions/scaleset`](https://github.com/actions/scaleset)
   Go client. Its two minting-relevant calls —
   `getRunnerRegistrationToken` (`POST .../actions/runners/
   registration-token`, the exact endpoint `.14`'s live install hit a
   404 on) and `GenerateJitRunnerConfig` (`POST .../generatejitconfig`)
   — both route through `commonClient.do`, which wraps
   `hashicorp/go-retryablehttp` (`RetryMax=4`, `RetryWaitMax=30s`, no
   custom `CheckRetry`). `go-retryablehttp`'s default policy retries
   `429` (honoring a `Retry-After` header) and `5xx`, but explicitly
   NOT a bare `403`. A custom `CheckRetry` that DOES add `401`/`403`
   retry exists in `client.go`, but it is scoped ONLY to
   `getActionsServiceAdminConnectionRequest` (the separate tenant-URL/
   JWT exchange), not to either minting call. One layer up, the
   controller-runtime reconcile loop
   (`controllers/actions.github.com/options.go`) does eventually retry
   via the default `workqueue.DefaultTypedControllerRateLimiter`
   (per-item exponential backoff + a 10 QPS/100-bucket token bucket
   across the whole controller) — but that is a generic K8s-controller-
   pattern limiter, not GitHub-response-aware: it neither distinguishes
   a genuine secondary-rate-limit `403` from a permanent error nor
   honors `Retry-After`/reset-time guidance, and it throttles the
   controller's own reconcile rate rather than coordinating against
   GitHub's actual REST point budget. **Conclusion: this is a real,
   confirmed gap** — `admission_response.py`'s classification logic is
   NOT redundant with what ARC ships today. The actionable fix, if this
   gap is ever observed live, is a custom `retryablehttp.CheckRetry`
   wired via `scaleset.Client`'s own `WithRetryableHTTPClint`
   constructor option (confirmed to exist for exactly this purpose),
   not a fork or reimplementation. **STILL OPEN (needs a live
   cluster):** this gap has not been OBSERVED live — `.14`'s actual
   404 is a separate, permission-scope issue, unrelated to rate
   limiting — so provisioning a throwaway installation-token
   exhaustion scenario against the real cluster to confirm the gap
   manifests as predicted remains a live-cluster validation step.
3. **Prove the extended-resource patch survives a real kubelet
   restart.** Apply `node-extended-resource/patch-node-churn-capacity.sh`
   with a test capacity, confirm `kubectl get node -o
   jsonpath='{.status.allocatable.ci-runner\.io/churn-slot}'` reflects
   it, then restart the k3s service
   (`systemctl restart k3s`) and check WITHOUT the reapply timer
   running whether the value survives or resets. This confirms (or
   corrects) `README.md`'s "Known caveat" claim rather than trusting it
   asserted. If it does NOT reset, the `reapply-node-extended-resource
   .timer`/`.service` pair may be unnecessary belt-and-suspenders
   rather than load-bearing — note which.
4. **Decide the side-by-side capacity split with the podman pool.**
   Per `README.md` "Why per-repo quotas summing above 482 must NOT be
   set to 482 during side-by-side migration": before running
   `patch-node-churn-capacity.sh` for real, measure the podman pool's
   ACTUAL current concurrent `runner@` unit count on `poweredge-xubuntu`
   (not the ~479-482 figure recorded at `.14`'s inventory time, which
   ages) and choose a k3s-pool capacity that keeps the SUM comfortably
   under 482. This is a live-host capacity decision belonging to
   whoever drives `livespec-s43svm.16`'s incremental cutover, not a
   number this design pass invents.
5. **Prove a synthetic fair-borrowing scenario end-to-end.** With at
   least two repos' `ClusterQueue`/`AutoscalingRunnerSet` pairs applied
   (e.g. `livespec` plus one more derived per README.md "Deriving a new
   repository's ClusterQueue"), synthetically saturate one repo's
   `nominalQuota` while the other has spare capacity, and confirm the
   first repo's excess demand is admitted by borrowing from the cohort
   — this is `.15`'s own acceptance criterion ("Kueue ClusterQueues in
   one Cohort with Fair Sharing enabled demonstrably borrow unused
   quota across repositories under synthetic concurrent load").
6. **Decide whether a generator is worth building.** `README.md` "Two
   enforcement points, one number" explicitly defers a
   `ClusterQueue`/`AutoscalingRunnerSet` generator (or a lockstep check
   that fails when the two files' doubled-ceiling numbers drift) as
   out of scope for the design pass. Once the manifest SHAPE above is
   proven against a live cluster (items 1 and 5), re-evaluate whether
   rolling this out to the remaining ~8 fleet repositories
   (`livespec-s43svm.16`) justifies building one, or whether hand-
   authoring per repo (as `livespec` demonstrates) stays tractable at
   this fleet's size.
7. **Confirm the physical-cap invariant under real load.** Per
   `README.md` "Why per-repo quotas summing above 482 is safe": with
   the extended resource's node capacity set below the sum of applied
   `ClusterQueue` `nominalQuota`s (by construction, once more than one
   repo is onboarded), synthetically drive combined demand across
   every onboarded repo above the node's `ci-runner.io/churn-slot`
   capacity and confirm the count of `Running` runner pods never
   exceeds that capacity, regardless of how many `ClusterQueue`s admit
   workloads logically — mirroring the existing "JIT fleet capacity
   borrows fairly without exceeding 482 runners" scenario in
   `SPECIFICATION/scenarios.md`.
