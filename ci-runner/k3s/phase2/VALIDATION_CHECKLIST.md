# Phase-2 validation checklist

Items 1, 3, 5, and 7 were run live against the real k3s + ARC + Kueue
cluster on `poweredge-xubuntu` (`livespec-s43svm.14`, closed
2026-08-16) and are CONFIRMED below. Item 6 was DECIDED and item 4 was
SUPERSEDED on 2026-08-19 by `livespec-s43svm.15`'s derivation
(`kueue/DERIVATION.md`). Only item 2 remains open — it says exactly
what's still needed and why. The podman pool was
re-verified unaffected (482 `runner@` units, 0 failed) before and
after every live action taken for this checklist.

1. **Confirm the `Cohort`/Fair-Sharing API shape against the real
   v0.19.1 CRDs.** **CONFIRMED (2026-08-16).** `kubectl explain
   clusterqueue.spec.cohort` returns `error: field "cohort" does not
   exist`. The live field is `spec.cohortName` (string) under
   `kueue.x-k8s.io/v1beta2` — `kubectl apply`-ing the OLD
   `v1beta1`/`spec.cohort` shape IS accepted (Kueue's conversion
   webhook handles it) but logs `"Warning: This version is deprecated.
   Use v1beta2 instead."` `spec.fairSharing.weight` exists exactly as
   designed, unchanged. `kueue/cluster-queue-*.yaml` and
   `kueue/resource-flavor.yaml` are updated to
   `kueue.x-k8s.io/v1beta2` / `cohortName` accordingly. Separately
   confirmed the `Configuration.fairSharing.enable` field this
   checklist item and `README.md` originally assumed does NOT exist at
   this version (see item 5's finding) — the `enable-fair-sharing.sh`
   script that assumed it has been removed.
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
   restart.** **CONFIRMED, and the original caveat was WRONG
   (2026-08-16).** Patched `ci-runner.io/churn-slot` capacity=4 on the
   live node, then ran a full `systemctl restart k3s` (which restarts
   k3s's embedded kubelet along with everything else). Both
   `status.capacity` and `status.allocatable` for the extended resource
   read back as `4` immediately after the node reported `Ready` again
   — the patch was NOT dropped. (The kubeconfig file's permissions DID
   reset to `0600 root:root` across the restart, needing
   `chmod 0644` again — an unrelated, already-known operational step
   `provision-k3s.sh` already documents.) **Scope of this
   confirmation:** a `systemctl restart k3s` service restart, not a
   full host reboot or a k3s version upgrade — those remain untested
   and may behave differently, which is why
   `reapply-node-extended-resource.timer` stays installed as cheap
   belt-and-suspenders rather than being removed.
4. **Decide the side-by-side capacity split with the podman pool.**
   **SUPERSEDED 2026-08-19 (`livespec-s43svm.15`).** The side-by-side
   framing this item was written under no longer applies: the podman
   pool has been stopped since 2026-08-13, so the two pools no longer
   share the iowait budget concurrently and there is no split left to
   decide. What replaced it is the single question of the k3s pool's
   permanent capacity `C` — OPEN, and deliberately not answered by the
   formula. See `kueue/DERIVATION.md` "The permanent C is still an open
   question": `C = 8` and `C = 16` are both proven under real load,
   `C = 482` is the inherited design-envelope target, and nothing in
   between has been measured. Raising `C` is a host capacity decision
   journaled on the `livespec-s43svm` epic; the derivation apportions
   whatever `C` it is given. Original 2026-08-16 disposition follows.

   **(2026-08-16) STILL OPEN — not decided by this pass.** Measured the podman
   pool's actual live state before touching anything: 482 `runner@`
   units, all `running`, 0 failed, `ci-runner-supervisor.service`
   INACTIVE (stopped since 2026-08-13, unrelated to this work, not
   restarted or touched). The `4`-unit `churn-slot` capacity applied
   for items 3/5/7's tests was chosen as a deliberately tiny, brief,
   synthetic load (plain `busybox sleep` jobs, no real container-image
   churn, each test window under a minute) specifically BECAUSE this
   pass was validating Kueue's OWN quota/admission math, not exercising
   real iowait-generating CI workloads — it was not a considered
   answer to "what capacity is safe to run continuously alongside a
   482-unit podman pool," and reads as nominally `482 + 4 = 486` if
   taken as a literal combined-count decision. That real sizing
   decision — accounting for actual concurrent container churn, not a
   raw unit count — still belongs to whoever drives
   `livespec-s43svm.16`'s incremental cutover once real traffic is
   under consideration.
5. **Prove a synthetic fair-borrowing scenario end-to-end.**
   **CONFIRMED (2026-08-16).** Applied `livespec-cq`/`livespec-lq` for
   real (the genuine `nominalQuota: 36`, as designed — left in place,
   `PENDING WORKLOADS: 0`, zero real traffic routed to it). For the
   borrowing proof itself, added two temporary, clearly-labeled
   synthetic `ClusterQueue`s in the SAME `fleet-ci-runner-pool` cohort
   (`proof-a-cq` `nominalQuota: 3`, `proof-b-cq` `nominalQuota: 1`,
   deleted after the test) rather than reusing `livespec-cq`'s real
   `36` quota, to keep the test's numbers small enough to reason about
   exactly against the tiny `4`-unit test capacity. Submitted 3
   concurrent `batch/v1` Jobs to `proof-b-lq` (which alone only has
   quota for 1): all 3 were admitted and ran — `proof-b-cq`'s status
   showed `total: 3, borrowed: 2`, i.e. it borrowed 2 units from
   `proof-a-cq`'s unused `3`-unit quota, entirely automatically, with
   ZERO Kueue `Configuration` changes (see item 1's finding — there was
   no "enable" step to run). This directly satisfies `.15`'s own
   acceptance criterion. Test resources (both synthetic
   `ClusterQueue`/`LocalQueue` pairs, all Jobs) deleted afterward;
   only the real `livespec-cq`/`livespec-lq` pair remains applied.
6. **Decide whether a generator is worth building.** **DECIDED: NO
   (2026-08-19, `livespec-s43svm.15`).** With the derivation
   parameterized in `kueue/DERIVATION.md` and eight repositories,
   regenerating every quota is a table recomputation and eight one-line
   edits, done a handful of times in this pool's life. A generator adds
   a source file, a test, a place for generated and committed manifests
   to disagree, and a second thing to keep working — against a manual
   step verified by adding eight integers. Full reasoning, including
   the one narrower check that WOULD be earned first (a
   quotas-sum-to-registered-capacity assertion, which is a summation
   rather than a code generator, and needs a committed home for the
   current `C` that the provisioning scripts do not have yet), is in
   that file's "Is a generator worth building?". Original disposition
   follows.

   **(2026-08-16) STILL OPEN.**
   `README.md` "Two enforcement points, one number" explicitly defers a
   `ClusterQueue`/`AutoscalingRunnerSet` generator (or a lockstep check
   that fails when the two files' doubled-ceiling numbers drift) as
   out of scope for the design pass. The manifest SHAPE is now proven
   against a live cluster (items 1 and 5 confirmed); re-evaluate
   whether rolling this out to the remaining ~8 fleet repositories
   (`livespec-s43svm.16`) justifies building one, or whether hand-
   authoring per repo (as `livespec` demonstrates) stays tractable at
   this fleet's size.
7. **Confirm the physical-cap invariant under real load.**
   **CONFIRMED (2026-08-16).** With the same two synthetic
   `ClusterQueue`s from item 5 (combined `nominalQuota` = 4 = node
   capacity), submitted 6 concurrent Jobs (3 to each queue, `sleep 60`,
   submitted in the same batch to force genuine contention) — deliberate
   over-demand against the 4-unit physical ceiling. Result: **exactly 4
   pods reached `Running`, exactly 2 stayed `Pending`** — the physical
   cap was never exceeded. Notably, Kueue's OWN `Workload` "Admitted"
   condition showed `True` for ALL 6 (its cohort-borrowing quota
   bookkeeping, with neither `ClusterQueue` setting an explicit
   `borrowingLimit`, allowed logical reservation beyond the node's
   actual physical capacity) — so Kueue's own "Admitted" status is
   NECESSARY BUT NOT SUFFICIENT for a pod to actually run; the
   extended resource's finite node capacity, enforced by the
   Kubernetes scheduler itself, is the real, final, authoritative gate
   — exactly the property `README.md` "Why per-repo quotas summing
   above 482 is safe" claims, now empirically proven rather than
   asserted. Mirrors the existing "JIT fleet capacity borrows fairly
   without exceeding 482 runners" scenario in `SPECIFICATION/
   scenarios.md`.

8. **Prove the inotify budget survives a real reboot.** **OPEN.**
   Run `node-inotify-budget/install-inotify-sysctl.sh` as root on
   `poweredge-xubuntu` (it is idempotent), then confirm
   `sysctl -n fs.inotify.max_user_instances` reports `8192`. Then, at
   the next maintenance reboot (never during CI), confirm the value is
   STILL `8192` after boot with no manual re-apply — i.e. that
   `systemd-sysctl` picked up `/etc/sysctl.d/99-ci-runner-inotify.conf`.
   Unlike item 3's extended-resource patch, this needs no reapply timer:
   a `/etc/sysctl.d/` drop-in is applied at every boot by design, so the
   reboot check is the whole proof. The interim value was hand-applied on
   2026-09-01 (livespec plan `ci-runner-pod-lifecycle-reliability`,
   research/002, carrier `livespec-a6lxuv`); this item confirms the
   shipped installer reproduces it durably.
