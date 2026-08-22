# Self-hosted CI runner tooling

Durable, re-runnable artifacts that provision and verify this fleet's
self-hosted GitHub Actions capacity on `poweredge-xubuntu`, so livespec CI
can run inside the same baked `fabro-sandbox` images the orchestrator uses —
without exposing host secrets, the multi-tenant Dolt server, or host root to
(possibly fork-controlled) workflow code.

Two runner trust tiers live here, and they are genuinely different things:

- The **contained gating tier** — k3s + Actions Runner Controller + Kueue.
  This is what every fleet repository's gating CI runs on. See
  [`k3s/README.md`](k3s/README.md) and
  [`k3s/phase2/README.md`](k3s/phase2/README.md).
- The **privileged gate tier** — a single operator-triggered runner with a
  deliberately wider trust boundary, used by
  `livespec-orchestrator-beads-fabro`'s golden-master acceptance gate. It has
  its own provisioning, its own supervisor identity, and its own JIT minter.
  See [`gate-runner/README.md`](gate-runner/README.md).

## The rootless-podman pool is gone

A third path used to live here: a **rootless-podman/dockershim** pool of
ephemeral `runner@*` units driven by a bash supervisor, addressed by the
`local-ci` + `poweredge` labels. It no longer exists, in either the live or
the source sense, and this page no longer documents it.

- **Live decommission, 2026-08-21** (`livespec-s43svm.19`): the replenisher
  stopped, every `runner@*` unit stopped, and all 482 forge registrations
  deleted — verified as zero remaining registrations carrying the
  `local-ci` + `poweredge` label set across the repositories the pool served.
- **Source deletion, this change** (`livespec-s43svm.19`): `provision-ci-runner.sh`,
  `supervisor/`, `dockershim/`, `sanitize-hook.js`, `containers.conf`,
  `pregate-verify.sh`, `isolation-exit-tests.sh`, `warm-ci-cache.sh`, and the
  rootless-podman cache-prune units.

The deleted tree is recoverable from git history at `b179cef0`, the last
commit before this deletion. Two facts about it are worth carrying forward
rather than leaving in history:

- Its SQLite lock-contention failure (`database is locked` / dockershim
  exit 255, `livespec-s43svm.21`) was **never root-caused**. It was retired
  unanswered, made moot by taking podman out of the CI path — not understood.
  A future reader finding "podman removed, no recurrence" must not infer the
  contention was diagnosed. If podman ever returns to this fleet's CI path,
  that knowledge gap returns with it.
- The podman references remaining in `k3s/**` are **historical rationale**,
  not dangling pointers: they explain WHY the migration happened. They are
  deliberately kept.

## Files

| Path | Role |
|---|---|
| `k3s/` | **The live gating path.** k3s + Actions Runner Controller + Kueue: the cluster install, the per-repository ARC scale sets and Kueue queues (`k3s/phase2/`), and the node-capacity and wedged-runner reconciliation units. Design record: livespec repo `plan/fleet-ci-runner-pool/research/k3s-arc-kueue-migration.md`. |
| `k3s-arc-kueue/` | The phase-1 standing-up artifacts for that path (`install-k3s.sh`, `install-arc.sh`, `install-kueue.sh`, proof-of-life manifests). See its own [`README.md`](k3s-arc-kueue/README.md). |
| `gate-runner/` | **The second, privileged trust tier** — on-demand, trigger-verified JIT minting for the operator-triggered acceptance gate. Separate boundary, separate provisioning, owns its `ci-sup` identity and `mint-jitconfig.sh`. See its own [`README.md`](gate-runner/README.md). |
| `set-ci-runner-labels.sh` | **The only sanctioned way to write a repository's `CI_RUNNER_LABELS` variable.** That write is the exact moment a repository begins gating merges on self-hosted capacity, and therefore the moment the fork-exclusion precondition engages, so the script reads the repository's fork-pull-request approval tier first and REFUSES to point the variable at a self-hosted label unless the tier is `all_external_contributors` — refusing likewise when the tier cannot be read, since an unreadable tier is not a strict tier. `--set-tier` corrects a weak tier in the same operation and re-reads to verify before writing; routing back to hosted capacity reads no tier and is never blocked. Closes `livespec-s43svm.39`, filed after two repositories were found gating on self-hosted capacity at `first_time_contributors`. |
| `set-ci-runner-labels-exit-tests.sh` | 10 behavioral exit tests for those refusals, against a fake `gh` — no network, no credential, no repository touched. Proving a refusal against a live repository would mean weakening a real repository's tier to watch the refusal fire, creating the exposure the script exists to prevent. |
| `observability/` | Fleet liveness heartbeat (5-min OTLP gauge `livespec.ci_runners.active` → the host collector → `livespec-host-metrics`, paired with a Honeycomb below-1 trigger), plus `install-observability.sh` (the only sanctioned way to install/update the live copy). Part of the `3lev.1` resource-health work. The heartbeat is the subject of `livespec-s43svm.20`. |

## Credential model

Both surviving tiers authenticate as the same GitHub App. This section is the
authoritative record; it was relocated here from the deleted
`supervisor/README.md`, which was its only home.

- **App** `thewoolleyman-ci-runners` (App ID `4278168`), `Administration:
  read+write` only, installed on selected repositories. One key (fingerprint
  `SHA256:mR4QpknOUHIjN/90xKsFGlfWVpB9+5UuECGhOO+/iL4=`).
- The **App private key** mints unlimited registrations, so it is read only by
  the `ci-sup` supervisor identity (gate tier) and by `install-arc.sh` when
  seeding the `arc-github-app` Kubernetes `Secret` — in both cases from the
  dedicated `github-ci-runners` 1Password environment, never the shared
  `livespec` one.
- A **runner** receives only a one-shot **JIT config** (one runner, one job),
  never the App key.

Injection is always through `/usr/local/bin/with-github-ci-runners-env.sh`,
the wrapper for that environment (analogous to `with-livespec-env.sh`). It
supplies, with the PEM carrying **real newlines** (the
`GITHUB_PRIVATE_KEY_E2E` convention):

```
GITHUB_APP_ID_CI_RUNNER=4278168
GITHUB_APP_INSTALLATION_ID_CI_RUNNER=146033367
GITHUB_APP_CLIENT_ID_CI_RUNNER=Iv23liMDgGWXDVWMYC07
GITHUB_PRIVATE_KEY_CI_RUNNER=<PEM>
```

Membership of the `github-ci-runners` group is what makes the key readable, so
it stays an explicit operator act — `provision-gate-runner.sh` checks for it
and fails loudly rather than creating it.

## Nature

These are **host operational artifacts** (shell, systemd units, polkit rules,
Kubernetes manifests, config), not Python product code — they are not part of
the `just check` aggregate. Recreatability is the contract: re-running a
tier's provisioning converges a fresh host, and each tier's own exit tests
prove its boundary still holds.
