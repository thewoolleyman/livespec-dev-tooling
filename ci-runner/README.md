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
| `sanitize-hook.js` | `ACTIONS_RUNNER_CONTAINER_HOOKS` shim: strips the host docker socket and host-namespace/privilege escalations from container create-options before delegating to the real container hook. |
| `containers.conf` | `ci-runner`'s rootless podman defaults: private netns + public DNS (host-loopback services stay unreachable from the job container). |
| `dockershim/docker` | Serialization shim in front of the real `docker` CLI (first on the runner agent's `PATH`). Every slot shares one rootless podman, and podman's `network prune` scans the **global** container database, so one job's prune dies on a container another job is removing. The shim readers-writer-locks prune against removal and passes everything else through unlocked. **Required for more than one slot** — without it a 12-job matrix reds 8–10 of 12 in teardown. |
| `dockershim/dockershim-exit-tests.sh` | 11 behavioral exit tests for that lock discipline (which calls block on a held lock, which do not), against a fake docker — no podman or runner needed. |
| `supervisor/` | The ephemeral JIT-runner supervisor (systemd units, polkit bridge, mint/launch scripts) + its README. |
| `observability/` | Fleet liveness heartbeat (5-min OTLP gauge `livespec.ci_runners.active` → the host collector → `livespec-host-metrics`, paired with a Honeycomb below-1 trigger) and the daily age-aware rootless-podman cache prune, plus `install-observability.sh` (the only sanctioned way to install/update the live copies). Part of the `3lev.1` resource-health work; the CI sentinel job (`check-self-hosted-routing` pinned to `local-ci`) is the end-to-end backstop for the heartbeat's own blind spot. |

## Nature

These are **host operational artifacts** (shell, systemd units, polkit
rules, JS, config), not Python product code — they are not part of the
`just check` aggregate. Recreatability is the contract: re-running
`provision-ci-runner.sh` converges a fresh host, and
`isolation-exit-tests.sh` proves the containment invariants still hold.
