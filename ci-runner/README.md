# Local self-hosted CI runner — containment tooling

Durable, re-runnable artifacts that provision and verify a **contained,
rootless, ephemeral** self-hosted GitHub Actions runner on a shared
multi-tenant host, so livespec CI can run inside the same baked
`fabro-sandbox` images the orchestrator uses — without exposing host
secrets, the multi-tenant Dolt server, or host root to
(possibly fork-controlled) workflow code.

The threat model, the containment planes, and the 11 isolation exit
tests are specified in the **livespec** repo at
`plan/fabro-ci-image-factoring/phase0-runner-containment-design.md`
(the design is single-sourced there; this tree is its implementation).

## Files

| Path | Role |
|---|---|
| `provision-ci-runner.sh` | Idempotently provisions the host: verifies the shipped AppArmor userns backbone (sysctls stay `=1`, no setuid runtime), installs the rootless stack (podman/uidmap/slirp4netns/passt/crun/fuse-overlayfs/aardvark-dns), creates the `ci-runner` user in **none** of `docker`/`sudo`/`dolt`, and installs the Actions runner + container-hooks + sanitizer. |
| `pregate-verify.sh` | Provisioning pre-gate verification (isolation tests 1–3 + 7): ci-runner group/sudoers containment, Kind-2 path unreadability, rootless mapping (container-root → non-host-root), sysctls `=1`, no setuid runtime, hostile-bind-mount + `--privileged` still confined. |
| `isolation-exit-tests.sh` | The full 11-test isolation exit suite, runnable + re-runnable against the live host (throwaway containers only). Exit 0 iff every non-skipped test passes. |
| `set-ci-runner-labels.sh` | **The only sanctioned way to write a repository's `CI_RUNNER_LABELS` variable.** That write is the exact moment a repository begins gating merges on self-hosted capacity, and therefore the moment the fork-exclusion precondition engages, so the script reads the repository's fork-pull-request approval tier first and REFUSES to point the variable at a self-hosted label unless the tier is `all_external_contributors` — refusing likewise when the tier cannot be read, since an unreadable tier is not a strict tier. `--set-tier` corrects a weak tier in the same operation and re-reads to verify before writing; routing back to hosted capacity reads no tier and is never blocked. Closes `livespec-s43svm.39`, filed after two repositories were found gating on self-hosted capacity at `first_time_contributors`. |
| `set-ci-runner-labels-exit-tests.sh` | 10 behavioral exit tests for those refusals, against a fake `gh` — no network, no credential, no repository touched. Proving a refusal against a live repository would mean weakening a real repository's tier to watch the refusal fire, creating the exposure the script exists to prevent. |
| `sanitize-hook.js` | `ACTIONS_RUNNER_CONTAINER_HOOKS` shim: strips the host docker socket and host-namespace/privilege escalations from container create-options before delegating to the real container hook. |
| `containers.conf` | `ci-runner`'s rootless podman defaults: private netns + public DNS (host-loopback services stay unreachable from the job container). |
| `dockershim/docker` | Serialization shim in front of the real `docker` CLI (first on the runner agent's `PATH`). Every slot shares one rootless podman, and podman's `network prune` scans the **global** container database, so one job's prune dies on a container another job is removing. The shim readers-writer-locks prune against removal and passes everything else through unlocked. **Required for more than one slot** — without it a 12-job matrix reds 8–10 of 12 in teardown. |
| `dockershim/dockershim-exit-tests.sh` | 11 behavioral exit tests for that lock discipline (which calls block on a held lock, which do not), against a fake docker — no podman or runner needed. |
| `supervisor/` | The ephemeral JIT-runner supervisor (systemd units, polkit bridge, mint/launch scripts) + its README. |
| `k3s-arc-kueue/` | **A new, separate runner path — not part of the podman stack above.** k3s + Actions Runner Controller + Kueue provisioning, installed *alongside* everything else on this page and routed **zero traffic**: no fleet workflow selects it. Phase 1 of the migration off rootless podman (`livespec-s43svm.14`). Nothing in this table changes because of it. See its own [`README.md`](k3s-arc-kueue/README.md). |
| `observability/` | Fleet liveness heartbeat (5-min OTLP gauge `livespec.ci_runners.active` → the host collector → `livespec-host-metrics`, paired with a Honeycomb below-1 trigger) and the daily age-aware rootless-podman cache prune, plus `install-observability.sh` (the only sanctioned way to install/update the live copies). Part of the `3lev.1` resource-health work; the CI sentinel job (`check-self-hosted-routing` pinned to `local-ci`) is the end-to-end backstop for the heartbeat's own blind spot. |
| `k3s/` | **Phase 1 of the k3s + Actions Runner Controller + Kueue migration** (see `k3s/README.md`): a SECOND, independent self-hosted runner pool standing up ALONGSIDE this tree's podman/dockershim pool, on new labels (`local-ci-k3s` shared, `poweredge-xubuntu-k3s` host-unique), routing zero traffic. Design record: livespec repo `plan/fleet-ci-runner-pool/research/k3s-arc-kueue-migration.md`. |

## Nature

These are **host operational artifacts** (shell, systemd units, polkit
rules, JS, config), not Python product code — they are not part of the
`just check` aggregate. Recreatability is the contract: re-running
`provision-ci-runner.sh` converges a fresh host, and
`isolation-exit-tests.sh` proves the containment invariants still hold.

## Two paths — and the podman one is DECOMMISSIONED

**Read this before trusting anything above it.** Most of this page describes the
**rootless-podman/dockershim** pool. That pool no longer exists. It was
decommissioned on 2026-08-21 under `livespec-s43svm.19`: every `runner@*` unit
stopped, and all 482 registrations deleted at the forge, verified as zero
remaining registrations carrying the `local-ci` + `poweredge` label set.

Every fleet repository that routes gating CI now routes it to a **k3s + Actions
Runner Controller + Kueue** scale set on `poweredge-xubuntu`, selected by
scale-set name through each repository's `CI_RUNNER_LABELS` variable. See
[`k3s/README.md`](k3s/README.md) and
[`k3s/phase2/README.md`](k3s/phase2/README.md), which are the live documentation.

This page's earlier text said the podman pool was "the only path currently
receiving CI traffic" and that its documentation "stays authoritative for the
live pool". Both were true when written and are now the opposite of true. They
are corrected here rather than left for a reader to discover, because a
provisioning page that confidently describes a pool that does not exist is worse
than one that is merely out of date — it reads as current.

**The tree above has NOT yet been deleted**, and that is deliberate rather than
an oversight: `livespec-s43svm.19`'s repo-side leg carries judgement calls (which
podman references in the k3s documentation are dangling versus historical
rationale worth keeping) that are being made as a reviewed change rather than a
sweep. Until it lands, treat everything above as a historical record of a pool
that is gone.

**Two things in this tree are NOT part of that deletion and stay live:**

- [`gate-runner/`](gate-runner/README.md) — the separate, deliberately-privileged,
  operator-triggered tier. Different trust boundary, different host, its own
  provisioning, and it owns its own supervisor identity and JIT minter. It was
  never part of the contained podman lane.
- [`observability/ci-runner-heartbeat.sh`](observability/) — carries no podman
  dependency at all and is the subject of `livespec-s43svm.20`.

