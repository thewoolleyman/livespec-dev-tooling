# 002 — The per-artifact disposition table, re-measured (2026-11-13)

Plan `ci-pool-provisioning-leftovers`, epic `livespec-dev-tooling-fby3sx`. This
note is the table that plan Definition of Done bullet 10 asks this plan's
research to carry: every class (a) host-glue artifact in the archived livespec
plan `k3s-on-gmktec-for-vps-usage`'s `research/005-estate/` inventories, each
with its disposition. It re-measures note 001 §3 (2026-11-05) after the
children that carried its open rows closed. It is read-only: no host or
ledger was written.

## 1. What was read, and at which commit

| Source | Ref measured |
|---|---|
| `livespec-dev-tooling` | `origin/master` = `84370f014` (2026-11-13), after `git fetch` |
| `vps-info` | `origin/master` = `256c9a3` (2026-11-12), after `git fetch` |
| `fabro-hosts` | `origin/master` = `ee8a71b` (2026-11-12), after `git fetch` |
| Row set | The 190 class (a) rows of note 001 §3, which counted them from the four `005-estate/` inventories (190, not the inventories' 191; see note 001 §0) |

**Method.** A script read note 001's 190 rows and checked each one again:

1. **Existence** on its repository's `origin/master`, with `git cat-file -e`.
2. **For a deleted row**, that it is still absent, and the deleting commit with
   `git log --diff-filter=D -1`. The pre-deletion commit comes from the
   deleting commit's own message.
3. **For a role row**, that the file still exists and that each named role's
   `ansible/roles/<role>/tasks/main.yml` still exists on master.

Every row that changed since note 001 was then read by hand. The role-row check
does not re-prove that the role still sources the file; nothing in the 31 rows
read by hand suggested a role had stopped doing so.

## 2. Tally

| Disposition (DoD bullet 10's three) | Rows |
|---|---|
| Installed by a committed Ansible role | 105 |
| Deleted, pre-deletion commit cited | 81 |
| Named by an open work-item that owns its disposition | 0 |
| **Residual: none of the three** | **4** (§3) |

Changes since note 001 §3:

- **Gate-runner tier, 13 rows (62-74):** deleted by `f243de605` on the
  bd-ib-te4h RETIRE ruling; pre-deletion `65335aee`. `6fl7a4` closed.
- **Editor stack, 6 rows (120-125):** deleted from vps-info by `256c9a3`;
  pre-deletion `2e912f7`. The `vps_editor_stack` role installs it held
  disabled. `fmbnyd` closed.
- **`check-settings` env files, 4 rows (168-171):** deleted from fabro-hosts by
  `ee8a71b`; pre-deletion `931442c`. `po2nrg` closed.
- **Registry mirror node half, 2 rows (52-53):** now installed by the
  `registry_mirror_node` role in `ansible/ci-pool.yml`. The host leg (the role
  reading drift-clean on poweredge) stays with open `y1t5`.
- **Node profiles, 2 rows (76-77):** reclassified from "kept (spec-sanctioned
  data)" to role-installed. `ci_converge_unit` installs each profile onto the
  node (`tasks/main.yml:161`).
- **Container-hook bundle, 3 rows (12-14):** version-renamed by `210f22aa2`
  from `bundle/2.336.0/` to `bundle/2.338.2/`. Still installed by
  `container_hook`.
- **The 49 vps-info duplicates** are unchanged: a role installs each one, and
  the superseded vps-info copy is still committed (W3, deferred to the PARKING
  LOT).

## 3. The four residual rows, and the decision they need

| # | Artifact | Why it fits none of the three |
|---|---|---|
| 75 | `ci-runner/k3s/phase0-bare-metal/profile.sh` | Ratified as committed shell: NFR §"One procedure, staged" says "The bare-metal stages and the pinned k3s install remain committed shell because they run before k3s exists". |
| 78 | `ci-runner/k3s/provision-k3s.sh` | The pinned k3s install, under that same clause. |
| 83 | `ci-runner/k3s/secret-reinjection/seed-k3s-agent-join-token.sh` | The attended seed of rebuild stage 3, run before `provision-k3s.sh` on an agent (`phase0-bare-metal/README.md:26`). It is pre-k3s, so the same clause covers it. |
| 82 | `ci-runner/k3s/secret-reinjection/seed-github-app-creds.sh` | An attended seed that writes a 1Password value into the credstore. `secret_reinjection` names it, warns while its credential is unseeded, and records the step in its `HOST_VARS.md` "Out-of-band" section. That is the treatment DoD bullet 2 accepts for a manual step. No role runs it. |

DoD bullet 10 allows three dispositions: role-installed, deleted with the
pre-deletion commit cited, or named by an open work-item. A spec-ratified
"stays committed shell" or "attended seed" is not one of them. The 2026-11-05
carrier map (DoD 10) lists the children that carried the open rows and does
not mention these four. Note 001 §3 marked them "Keep … record as such", and
nothing recorded them since.

**Options.**

- **(A) Re-word bullet 10** through a carrier-map scope event, adding a fourth
  disposition: "or is retained as committed shell, or as an attended step
  recorded in a role's `HOST_VARS.md`, under a ratified specification clause
  this table cites". This matches what the spec already requires, and it files
  nothing.
- **(B) File one open item** that "owns the disposition" of the four. Its only
  honest Definition of Done is "they stay as the spec says". That makes it a
  no-op ticket that blocks the archive gate, or one that must be re-parented
  out of the plan to let it archive.
- **(C) Bootstrap them through Ansible.** This contradicts the ratified clause,
  so it would need a propose-change, and it buys nothing: nothing converged
  exists for the provisioning layer to reach before k3s.

**Recommendation: (A).** The archiving session drafted the plan's Definition
of Done assertions on the maintainer's instruction ("draft the proper
definition of done in them with the context that you already have", note 000).
They are not the maintainer's own words. Re-wording one of its assertions still changes the plan's goal,
though, so the re-word goes to legacy-coordinator-agent before any carrier-map
event is written.

## 4. The table

Repository `ldt` is `livespec-dev-tooling`. Evidence carried over unchanged
from note 001 names that note's measured refs (for example vps-info `ac89b07`).
This note re-read every such file at the refs in §1.

| # | Repo | Artifact | Disposition | Evidence |
|---|---|---|---|---|
| 1 | ldt | `ci-runner/k3s/phase2/install-node.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `b39c9930`; still absent |
| 2 | ldt | `ci-runner/k3s/phase2/k3s-runtime-ready.sh` | Role `container_hook` | staged by `container_hook` (defaults/main.yml:19) for extract-externals.sh, applied by `ansible/ci-pool.yml` |
| 3 | ldt | `ci-runner/k3s/phase2/remove-server-only-units.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `1eba2e54`; still absent |
| 4 | ldt | `ci-runner/k3s/phase2/apparmor/ci-runner-workflow` | Role `apparmor_profile` | `ansible/roles/apparmor_profile/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 5 | ldt | `ci-runner/k3s/phase2/apparmor/install-apparmor-profile.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `5b39c8c3`; still absent |
| 6 | ldt | `ci-runner/k3s/phase2/arc-log-archive/archive-arc-logs.service` | Role `arc_log_archive` | `ansible/roles/arc_log_archive/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 7 | ldt | `ci-runner/k3s/phase2/arc-log-archive/archive-arc-logs.sh` | Role `arc_log_archive` | `ansible/roles/arc_log_archive/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 8 | ldt | `ci-runner/k3s/phase2/arc-log-archive/archive-arc-logs.timer` | Role `arc_log_archive` | `ansible/roles/arc_log_archive/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 9 | ldt | `ci-runner/k3s/phase2/arc-log-archive/install-arc-log-archive.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `1eba2e54`; still absent |
| 10 | ldt | `ci-runner/k3s/phase2/cache-telemetry/ci-cache-span.sh` | Role `cache_telemetry` | `ansible/roles/cache_telemetry/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 11 | ldt | `ci-runner/k3s/phase2/cache-telemetry/install-cache-telemetry.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `fad2489b`; still absent |
| 12 | ldt | `ci-runner/k3s/phase2/container-hook/bundle/2.336.0/BUILD-INFO` | Role `container_hook` | Version-renamed: `bundle/2.336.0/` deleted by `210f22aa2` (runner bump), the same file now at `bundle/2.338.2/`; `container_hook` pins `container_hook_runner_version: 2.338.2` |
| 13 | ldt | `ci-runner/k3s/phase2/container-hook/bundle/2.336.0/index.js` | Role `container_hook` | Version-renamed: `bundle/2.336.0/` deleted by `210f22aa2` (runner bump), the same file now at `bundle/2.338.2/`; `container_hook` pins `container_hook_runner_version: 2.338.2` |
| 14 | ldt | `ci-runner/k3s/phase2/container-hook/bundle/2.336.0/index.js.sha256` | Role `container_hook` | Version-renamed: `bundle/2.336.0/` deleted by `210f22aa2` (runner bump), the same file now at `bundle/2.338.2/`; `container_hook` pins `container_hook_runner_version: 2.338.2` |
| 15 | ldt | `ci-runner/k3s/phase2/container-hook/extract-externals.sh` | Role `container_hook` | `ansible/roles/container_hook/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 16 | ldt | `ci-runner/k3s/phase2/container-hook/install-container-hook.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `4fb6b82a`; still absent |
| 17 | ldt | `ci-runner/k3s/phase2/container-hook/runner-image.sh` | Role `container_hook` | `ansible/roles/container_hook/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 18 | ldt | `ci-runner/k3s/phase2/datastore-tmpfs/20-requires-datastore-mount.conf` | Role `datastore_tmpfs` | `ansible/roles/datastore_tmpfs/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 19 | ldt | `ci-runner/k3s/phase2/datastore-tmpfs/install-datastore-tmpfs.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `a222494c`; still absent |
| 20 | ldt | `ci-runner/k3s/phase2/datastore-tmpfs/var-lib-rancher-k3s-server-db.mount` | Role `datastore_tmpfs` | `ansible/roles/datastore_tmpfs/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 21 | ldt | `ci-runner/k3s/phase2/host-thermal/apply-idrac-thermal.service` | Role `host_thermal` | `ansible/roles/host_thermal/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 22 | ldt | `ci-runner/k3s/phase2/host-thermal/apply-idrac-thermal.sh` | Role `host_thermal` | `ansible/roles/host_thermal/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 23 | ldt | `ci-runner/k3s/phase2/host-thermal/install-host-thermal.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `d92e0212`; still absent |
| 24 | ldt | `ci-runner/k3s/phase2/host-thermal/install-racadm.sh` | Deleted, pre-deletion cited | deleting commit `1dcf9ac5`; pre-deletion `d92e0212`; still absent |
| 25 | ldt | `ci-runner/k3s/phase2/host-tools/btop-loop` | Role `host_tools_ci` | `ansible/roles/host_tools_ci/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 26 | ldt | `ci-runner/k3s/phase2/host-tools/install-host-tools.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `b9433e15`; still absent |
| 27 | ldt | `ci-runner/k3s/phase2/k3s-config/config.agent.yaml` | Role `k3s_config` | `ansible/roles/k3s_config/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 28 | ldt | `ci-runner/k3s/phase2/k3s-config/config.yaml` | Role `k3s_config` | `ansible/roles/k3s_config/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 29 | ldt | `ci-runner/k3s/phase2/k3s-config/install-k3s-config.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `5d79cd5a`; still absent |
| 30 | ldt | `ci-runner/k3s/phase2/node-extended-resource/install-reapply-unit.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `4fd213bc`; still absent |
| 31 | ldt | `ci-runner/k3s/phase2/node-extended-resource/patch-node-churn-capacity.sh` | Role `node_extended_resource` | `ansible/roles/node_extended_resource/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 32 | ldt | `ci-runner/k3s/phase2/node-extended-resource/reapply-node-extended-resource.service` | Role `node_extended_resource` | `ansible/roles/node_extended_resource/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 33 | ldt | `ci-runner/k3s/phase2/node-extended-resource/reapply-node-extended-resource.timer` | Role `node_extended_resource` | `ansible/roles/node_extended_resource/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 34 | ldt | `ci-runner/k3s/phase2/node-inotify-budget/99-ci-runner-inotify.conf` | Role `node_sysctl` | `ansible/roles/node_sysctl/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 35 | ldt | `ci-runner/k3s/phase2/node-inotify-budget/install-inotify-sysctl.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `a45e6be4`; still absent |
| 36 | ldt | `ci-runner/k3s/phase2/node-keyring-budget/60-k3s-container-keyring.conf` | Role `node_sysctl` | `ansible/roles/node_sysctl/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 37 | ldt | `ci-runner/k3s/phase2/node-keyring-budget/install-keyring-sysctl.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `db6e4166`; still absent |
| 38 | ldt | `ci-runner/k3s/phase2/reconstruct/converge-ci-stack.service` | Role `ci_converge_unit` | `ansible/roles/ci_converge_unit/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 39 | ldt | `ci-runner/k3s/phase2/reconstruct/install-converge-unit.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `b39c9930`; still absent |
| 40 | ldt | `ci-runner/k3s/phase2/reconstruct/render-sa-kubeconfig.sh` | Role `ci_converge_unit` | `ansible/roles/ci_converge_unit/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 41 | ldt | `ci-runner/k3s/phase2/runner-pod-lifecycle/install-runner-pod-lifecycle-scan.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `1eba2e54`; still absent |
| 42 | ldt | `ci-runner/k3s/phase2/runner-pod-lifecycle/scan-runner-pod-lifecycle.service` | Role `runner_pod_lifecycle` | `ansible/roles/runner_pod_lifecycle/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 43 | ldt | `ci-runner/k3s/phase2/runner-pod-lifecycle/scan-runner-pod-lifecycle.sh` | Role `runner_pod_lifecycle` | `ansible/roles/runner_pod_lifecycle/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 44 | ldt | `ci-runner/k3s/phase2/runner-pod-lifecycle/scan-runner-pod-lifecycle.timer` | Role `runner_pod_lifecycle` | `ansible/roles/runner_pod_lifecycle/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 45 | ldt | `ci-runner/k3s/phase2/sccache/install-sccache-binary.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `3b6f347b`; still absent |
| 46 | ldt | `ci-runner/k3s/phase2/storage-layout/10-requires-storage-mounts.conf` | Role `storage_layout` | `ansible/roles/storage_layout/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 47 | ldt | `ci-runner/k3s/phase2/storage-layout/install-storage-layout.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `c53ec28b`; still absent |
| 48 | ldt | `ci-runner/k3s/phase2/storage-sweep/agent-ordering.conf` | Role `storage_sweep` | `ansible/roles/storage_sweep/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 49 | ldt | `ci-runner/k3s/phase2/storage-sweep/install-storage-sweep.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `e2be3362`; still absent |
| 50 | ldt | `ci-runner/k3s/phase2/storage-sweep/sweep-runner-scratch.service` | Role `storage_sweep` | `ansible/roles/storage_sweep/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 51 | ldt | `ci-runner/k3s/phase2/storage-sweep/sweep-runner-scratch.sh` | Role `storage_sweep` | `ansible/roles/storage_sweep/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 52 | ldt | `ci-runner/k3s/phase2/warm-cache/registry-mirror/install-registry-mirror.sh` | Role `registry_mirror_node` | `ansible/ci-pool.yml:200` applies `registry_mirror_node`, whose `defaults/main.yml:12-16` source this tree. The host leg (drift-clean on poweredge) is owned by open **y1t5** (blocked by **e2gv6n**) |
| 53 | ldt | `ci-runner/k3s/phase2/warm-cache/registry-mirror/registries.yaml.template` | Role `registry_mirror_node` | `ansible/ci-pool.yml:200` applies `registry_mirror_node`, whose `defaults/main.yml:12-16` source this tree. The host leg (drift-clean on poweredge) is owned by open **y1t5** (blocked by **e2gv6n**) |
| 54 | ldt | `ci-runner/k3s/phase2/warm-cache/sandbox-image-prune/install-sandbox-image-prune.sh` | Deleted, pre-deletion cited | deleting commit `d51e93f1`; pre-deletion `356e0454`; still absent |
| 55 | ldt | `ci-runner/k3s/phase2/warm-cache/sandbox-image-prune/prune-sandbox-images.service` | Role `sandbox_image_prune` | `ansible/roles/sandbox_image_prune/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 56 | ldt | `ci-runner/k3s/phase2/warm-cache/sandbox-image-prune/prune-sandbox-images.sh` | Role `sandbox_image_prune` | `ansible/roles/sandbox_image_prune/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 57 | ldt | `ci-runner/k3s/phase2/warm-cache/sandbox-image-prune/prune-sandbox-images.timer` | Role `sandbox_image_prune` | `ansible/roles/sandbox_image_prune/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 58 | ldt | `ci-runner/k3s/phase2/wedged-runner/install-wedged-runner-scan.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `1eba2e54`; still absent |
| 59 | ldt | `ci-runner/k3s/phase2/wedged-runner/scan-wedged-runners.service` | Role `wedged_runner` | `ansible/roles/wedged_runner/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 60 | ldt | `ci-runner/k3s/phase2/wedged-runner/scan-wedged-runners.sh` | Role `wedged_runner` | `ansible/roles/wedged_runner/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 61 | ldt | `ci-runner/k3s/phase2/wedged-runner/scan-wedged-runners.timer` | Role `wedged_runner` | `ansible/roles/wedged_runner/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 62 | ldt | `ci-runner/gate-runner/50-gate-runner-supervisor.rules` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 63 | ldt | `ci-runner/gate-runner/app-installation-token.sh` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 64 | ldt | `ci-runner/gate-runner/gate-optin-expiry.service` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 65 | ldt | `ci-runner/gate-runner/gate-optin-expiry.sh` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 66 | ldt | `ci-runner/gate-runner/gate-optin-expiry.timer` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 67 | ldt | `ci-runner/gate-runner/gate-optin.sh` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 68 | ldt | `ci-runner/gate-runner/gate-runner-supervisor.service` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 69 | ldt | `ci-runner/gate-runner/gate-runner-supervisor.sh` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 70 | ldt | `ci-runner/gate-runner/gate-runner@.service` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 71 | ldt | `ci-runner/gate-runner/hosted-only.conf` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 72 | ldt | `ci-runner/gate-runner/mint-jitconfig.sh` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 73 | ldt | `ci-runner/gate-runner/provision-gate-runner.sh` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 74 | ldt | `ci-runner/gate-runner/run-gate-jit-runner.sh` | Deleted, pre-deletion cited | Deleted by `f243de605` (2026-11-05, bd-ib-te4h RETIRE ruling); pre-deletion `65335aee`. Role `gate_runner_retired` (`ansible/fabro-hosts.yml`) holds every installed path absent |
| 75 | ldt | `ci-runner/k3s/phase0-bare-metal/profile.sh` | RESIDUAL (see §3) | Committed shell by ratified clause NFR §"One procedure, staged" ("The bare-metal stages and the pinned k3s install remain committed shell"). No role installs it; no open item owns it |
| 76 | ldt | `ci-runner/k3s/phase0-bare-metal/profiles/gmktec-xubuntu.env` | Role `ci_converge_unit` | `ci_converge_unit/tasks/main.yml:161` installs the profile to the node; `k3s_config`, `node_labels`, `node_taints`, `node_extended_resource` read it (spec §"One profile per node") |
| 77 | ldt | `ci-runner/k3s/phase0-bare-metal/profiles/poweredge-xubuntu.env` | Role `ci_converge_unit` | `ci_converge_unit/tasks/main.yml:161` installs the profile to the node; `k3s_config`, `node_labels`, `node_taints`, `node_extended_resource` read it (spec §"One profile per node") |
| 78 | ldt | `ci-runner/k3s/provision-k3s.sh` | RESIDUAL (see §3) | Committed shell by ratified clause NFR §"One procedure, staged" ("The bare-metal stages and the pinned k3s install remain committed shell"). No role installs it; no open item owns it |
| 79 | ldt | `ci-runner/k3s/secret-reinjection/inject-github-app-secret.service` | Role `secret_reinjection` | `ansible/roles/secret_reinjection/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 80 | ldt | `ci-runner/k3s/secret-reinjection/inject-github-app-secret.sh` | Role `secret_reinjection` | `ansible/roles/secret_reinjection/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` |
| 81 | ldt | `ci-runner/k3s/secret-reinjection/install-secret-reinjection-unit.sh` | Deleted, pre-deletion cited | deleting commit `988285fc`; pre-deletion `833086dc`; still absent |
| 82 | ldt | `ci-runner/k3s/secret-reinjection/seed-github-app-creds.sh` | RESIDUAL (see §3) | Attended seed. `secret_reinjection` names it (`defaults/main.yml:13`), warns when its credential is unseeded, and records the step in `HOST_VARS.md` "Out-of-band" (line 17). c763up closed. No role installs the script; no open item owns it |
| 83 | ldt | `ci-runner/k3s/secret-reinjection/seed-k3s-agent-join-token.sh` | RESIDUAL (see §3) | Attended pre-k3s seed, rebuild stage 3 (`phase0-bare-metal/README.md:26`). Runs before k3s exists, so under the same clause. No role installs it; no open item owns it |
| 84 | ldt | `ci-runner/observability/ci-cache-gauges.service` | Role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` |
| 85 | ldt | `ci-runner/observability/ci-cache-gauges.sh` | Role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` |
| 86 | ldt | `ci-runner/observability/ci-cache-gauges.timer` | Role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` |
| 87 | ldt | `ci-runner/observability/ci-kueue-webhook-probe.service` | Role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` |
| 88 | ldt | `ci-runner/observability/ci-kueue-webhook-probe.sh` | Role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` |
| 89 | ldt | `ci-runner/observability/ci-kueue-webhook-probe.timer` | Role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` |
| 90 | ldt | `ci-runner/observability/ci-pool-attributed-gauges.service` | Role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` |
| 91 | ldt | `ci-runner/observability/ci-pool-attributed-gauges.sh` | Role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` |
| 92 | ldt | `ci-runner/observability/ci-pool-attributed-gauges.timer` | Role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` |
| 93 | ldt | `ci-runner/observability/ci-runner-heartbeat.service` | Role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` |
| 94 | ldt | `ci-runner/observability/ci-runner-heartbeat.sh` | Role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` |
| 95 | ldt | `ci-runner/observability/ci-runner-heartbeat.timer` | Role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` |
| 96 | ldt | `ci-runner/observability/install-observability.sh` | Deleted, pre-deletion cited | deleting commit `d51e93f1`; pre-deletion `c13617d0`; still absent |
| 97 | vps-info | `services/1password-desktop/install.sh` | Role `onepassword_desktop` | `ansible/roles/onepassword_desktop/tasks/main.yml` header "Replaces vps-info services/1password-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 98 | vps-info | `services/1password-desktop/1password-desktop.service` | Role `onepassword_desktop` | `ansible/roles/onepassword_desktop/tasks/main.yml` header "Replaces vps-info services/1password-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 99 | vps-info | `services/1password-desktop/restart-1password.desktop` | Role `onepassword_desktop` | `ansible/roles/onepassword_desktop/tasks/main.yml` header "Replaces vps-info services/1password-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 100 | vps-info | `services/1password-desktop/sudoers.d-1password-desktop` | Role `onepassword_desktop` | `ansible/roles/onepassword_desktop/tasks/main.yml` header "Replaces vps-info services/1password-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 101 | vps-info | `services/arq-vps-docker-volume-snapshot/arq-vps-docker-volume-snapshot.service` | Role `arq_docker_volume_snapshot` | `ansible/roles/arq_docker_volume_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-docker-volume-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 102 | vps-info | `services/arq-vps-docker-volume-snapshot/arq-vps-docker-volume-snapshot.sh` | Role `arq_docker_volume_snapshot` | `ansible/roles/arq_docker_volume_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-docker-volume-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 103 | vps-info | `services/arq-vps-docker-volume-snapshot/arq-vps-docker-volume-snapshot.timer` | Role `arq_docker_volume_snapshot` | `ansible/roles/arq_docker_volume_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-docker-volume-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 104 | vps-info | `services/arq-vps-docker-volume-snapshot/install.sh` | Role `arq_docker_volume_snapshot` | `ansible/roles/arq_docker_volume_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-docker-volume-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 105 | vps-info | `services/arq-vps-root-snapshot/arq-vps-root-snapshot.service` | Role `arq_root_snapshot` | `ansible/roles/arq_root_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-root-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 106 | vps-info | `services/arq-vps-root-snapshot/arq-vps-root-snapshot.sh` | Role `arq_root_snapshot` | `ansible/roles/arq_root_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-root-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 107 | vps-info | `services/arq-vps-root-snapshot/arq-vps-root-snapshot.timer` | Role `arq_root_snapshot` | `ansible/roles/arq_root_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-root-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 108 | vps-info | `services/arq-vps-root-snapshot/install.sh` | Role `arq_root_snapshot` | `ansible/roles/arq_root_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-root-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 109 | vps-info | `services/arq-vps-smb-source/arq-vps-smb-source-proxy.service` | Role `arq_smb_source` | `ansible/roles/arq_smb_source/tasks/main.yml` header "Replaces vps-info services/arq-vps-smb-source"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 110 | vps-info | `services/arq-vps-smb-source/arq-vps-smb-source-proxy.socket` | Role `arq_smb_source` | `ansible/roles/arq_smb_source/tasks/main.yml` header "Replaces vps-info services/arq-vps-smb-source"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 111 | vps-info | `services/arq-vps-smb-source/install.sh` | Role `arq_smb_source` | `ansible/roles/arq_smb_source/tasks/main.yml` header "Replaces vps-info services/arq-vps-smb-source"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 112 | vps-info | `services/arq-vps-smb-source/smb.conf` | Role `arq_smb_source` | `ansible/roles/arq_smb_source/tasks/main.yml` header "Replaces vps-info services/arq-vps-smb-source"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 113 | vps-info | `services/btop-loop/btop-loop` | Role `btop_loop` | `ansible/roles/btop_loop/tasks/main.yml` header "Replaces vps-info services/btop-loop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 114 | vps-info | `services/btop-loop/install.sh` | Role `btop_loop` | `ansible/roles/btop_loop/tasks/main.yml` header "Replaces vps-info services/btop-loop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 115 | vps-info | `services/claude-code-hooks/tmux-fleet-guard.py` | Role `claude_code_hooks` | `ansible/roles/claude_code_hooks/tasks/main.yml` header "Replaces vps-info services/claude-code-hooks"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 116 | vps-info | `services/claude-code-hooks/install.sh` | Role `claude_code_hooks` | `ansible/roles/claude_code_hooks/tasks/main.yml` header "Replaces vps-info services/claude-code-hooks"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 117 | vps-info | `services/claude-desktop/claude-desktop.desktop` | Role `claude_desktop` | `ansible/roles/claude_desktop/tasks/main.yml` header "Replaces vps-info services/claude-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 118 | vps-info | `services/claude-desktop/install.sh` | Role `claude_desktop` | `ansible/roles/claude_desktop/tasks/main.yml` header "Replaces vps-info services/claude-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 119 | vps-info | `services/claude-ntfy/install.sh` | Role `claude_ntfy` | `ansible/roles/claude_ntfy/tasks/main.yml` header "Replaces vps-info services/claude-ntfy"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 120 | vps-info | `services/code-pwa-proxy/code-pwa-proxy.service` | Deleted, pre-deletion cited | Deleted by vps-info `256c9a3` (2026-11-12, fmbnyd); pre-deletion `2e912f7`. Role `vps_editor_stack` (`ansible/dev-host.yml:38`) installs the stack held disabled |
| 121 | vps-info | `services/code-pwa-proxy/install.sh` | Deleted, pre-deletion cited | Deleted by vps-info `256c9a3` (2026-11-12, fmbnyd); pre-deletion `2e912f7`. Role `vps_editor_stack` (`ansible/dev-host.yml:38`) installs the stack held disabled |
| 122 | vps-info | `services/code-pwa-proxy/nginx.conf` | Deleted, pre-deletion cited | Deleted by vps-info `256c9a3` (2026-11-12, fmbnyd); pre-deletion `2e912f7`. Role `vps_editor_stack` (`ansible/dev-host.yml:38`) installs the stack held disabled |
| 123 | vps-info | `services/code-pwa-proxy/static/sw.js` | Deleted, pre-deletion cited | Deleted by vps-info `256c9a3` (2026-11-12, fmbnyd); pre-deletion `2e912f7`. Role `vps_editor_stack` (`ansible/dev-host.yml:38`) installs the stack held disabled |
| 124 | vps-info | `services/code-serve-web/code-serve-web.service` | Deleted, pre-deletion cited | Deleted by vps-info `256c9a3` (2026-11-12, fmbnyd); pre-deletion `2e912f7`. Role `vps_editor_stack` (`ansible/dev-host.yml:38`) installs the stack held disabled |
| 125 | vps-info | `services/code-serve-web/install.sh` | Deleted, pre-deletion cited | Deleted by vps-info `256c9a3` (2026-11-12, fmbnyd); pre-deletion `2e912f7`. Role `vps_editor_stack` (`ansible/dev-host.yml:38`) installs the stack held disabled |
| 126 | vps-info | `services/codex-config/install.sh` | Role `codex_config` | `ansible/roles/codex_config/tasks/main.yml` header "Replaces vps-info services/codex-config"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 127 | vps-info | `services/gates-kubeconfig/install.sh` | Role `gates_kubeconfig` | `ansible/roles/gates_kubeconfig/tasks/main.yml` header "Replaces vps-info services/gates-kubeconfig"; applied by `ansible/gates-kubeconfig.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 128 | vps-info | `services/gates-kubeconfig/refresh-gates-kubeconfig` | Role `gates_kubeconfig` | `ansible/roles/gates_kubeconfig/tasks/main.yml` header "Replaces vps-info services/gates-kubeconfig"; applied by `ansible/gates-kubeconfig.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 129 | vps-info | `services/gates-kubeconfig/with-gates-kubeconfig` | Role `gates_kubeconfig` | `ansible/roles/gates_kubeconfig/tasks/main.yml` header "Replaces vps-info services/gates-kubeconfig"; applied by `ansible/gates-kubeconfig.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 130 | vps-info | `services/honeycomb-mcp/install.sh` | Role `honeycomb_mcp` | `ansible/roles/honeycomb_mcp/tasks/main.yml` header "Replaces vps-info services/honeycomb-mcp"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 131 | vps-info | `services/honeycomb-trigger-recipients-check/check-trigger-recipients.sh` | Role `honeycomb_trigger_recipients_check` | `ansible/roles/honeycomb_trigger_recipients_check/tasks/main.yml` header "Replaces vps-info services/honeycomb-trigger-recipients-check"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 132 | vps-info | `services/honeycomb-trigger-recipients-check/honeycomb-trigger-recipients-check.service` | Role `honeycomb_trigger_recipients_check` | `ansible/roles/honeycomb_trigger_recipients_check/tasks/main.yml` header "Replaces vps-info services/honeycomb-trigger-recipients-check"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 133 | vps-info | `services/honeycomb-trigger-recipients-check/honeycomb-trigger-recipients-check.timer` | Role `honeycomb_trigger_recipients_check` | `ansible/roles/honeycomb_trigger_recipients_check/tasks/main.yml` header "Replaces vps-info services/honeycomb-trigger-recipients-check"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 134 | vps-info | `services/honeycomb-trigger-recipients-check/install.sh` | Role `honeycomb_trigger_recipients_check` | `ansible/roles/honeycomb_trigger_recipients_check/tasks/main.yml` header "Replaces vps-info services/honeycomb-trigger-recipients-check"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 135 | vps-info | `services/keyring-quota/99-keyring-quota.conf` | Role `keyring_quota` | `ansible/roles/keyring_quota/tasks/main.yml` header "Replaces vps-info services/keyring-quota"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 136 | vps-info | `services/keyring-quota/install.sh` | Role `keyring_quota` | `ansible/roles/keyring_quota/tasks/main.yml` header "Replaces vps-info services/keyring-quota"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 137 | vps-info | `services/ssh-hardening/00-ssh-hardening.conf` | Role `ssh_hardening` | `ansible/roles/ssh_hardening/tasks/main.yml` header "Replaces vps-info services/ssh-hardening"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 138 | vps-info | `services/ssh-hardening/install.sh` | Role `ssh_hardening` | `ansible/roles/ssh_hardening/tasks/main.yml` header "Replaces vps-info services/ssh-hardening"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 139 | vps-info | `services/tmux-config/install.sh` | Role `tmux_config` | `ansible/roles/tmux_config/tasks/main.yml` header "Replaces vps-info services/tmux-config"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 140 | vps-info | `services/tmux-config/tmux.conf.local` | Role `tmux_config` | `ansible/roles/tmux_config/tasks/main.yml` header "Replaces vps-info services/tmux-config"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 141 | vps-info | `services/vnc-desktop/com.google.Chrome.desktop` | Role `vnc_desktop` | `ansible/roles/vnc_desktop/tasks/main.yml` header "Replaces vps-info services/vnc-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 142 | vps-info | `services/vnc-desktop/google-chrome-wrapper.sh` | Role `vnc_desktop` | `ansible/roles/vnc_desktop/tasks/main.yml` header "Replaces vps-info services/vnc-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 143 | vps-info | `services/vnc-desktop/google-chrome.desktop` | Role `vnc_desktop` | `ansible/roles/vnc_desktop/tasks/main.yml` header "Replaces vps-info services/vnc-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 144 | vps-info | `services/vnc-desktop/install.sh` | Role `vnc_desktop` | `ansible/roles/vnc_desktop/tasks/main.yml` header "Replaces vps-info services/vnc-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 145 | vps-info | `services/vnc-desktop/vnc-desktop-start.sh` | Role `vnc_desktop` | `ansible/roles/vnc_desktop/tasks/main.yml` header "Replaces vps-info services/vnc-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 146 | vps-info | `services/vnc-desktop/vnc-desktop.service` | Role `vnc_desktop` | `ansible/roles/vnc_desktop/tasks/main.yml` header "Replaces vps-info services/vnc-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 147 | vps-info | `services/vps-restic-backup/install.sh` | Role `restic_backup` | `ansible/roles/restic_backup/tasks/main.yml` header "Replaces vps-info services/vps-restic-backup"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 148 | vps-info | `services/vps-restic-backup/vps-restic-backup.service` | Role `restic_backup` | `ansible/roles/restic_backup/tasks/main.yml` header "Replaces vps-info services/vps-restic-backup"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 149 | vps-info | `services/vps-restic-backup/vps-restic-backup.sh` | Role `restic_backup` | `ansible/roles/restic_backup/tasks/main.yml` header "Replaces vps-info services/vps-restic-backup"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 150 | vps-info | `services/vps-restic-backup/vps-restic-backup.timer` | Role `restic_backup` | `ansible/roles/restic_backup/tasks/main.yml` header "Replaces vps-info services/vps-restic-backup"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 151 | vps-info | `services/vps-restic-backup/vps-restic-excludes.txt` | Role `restic_backup` | `ansible/roles/restic_backup/tasks/main.yml` header "Replaces vps-info services/vps-restic-backup"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07`. The superseded vps-info copy is still committed (W3, deferred to the PARKING LOT) |
| 152 | fabro-hosts | `services/container-reclaim/container-reclaim.service.in` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 153 | fabro-hosts | `services/container-reclaim/container-reclaim.timer.in` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 154 | fabro-hosts | `services/container-reclaim/container-reclaim.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 155 | fabro-hosts | `services/container-reclaim/hosts/hp-xubuntu.env` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 156 | fabro-hosts | `services/container-reclaim/hosts/vps.env` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 157 | fabro-hosts | `services/container-reclaim/install.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 158 | fabro-hosts | `services/disk-guard/disk-guard.service.in` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 159 | fabro-hosts | `services/disk-guard/disk-guard.timer.in` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 160 | fabro-hosts | `services/disk-guard/docker-prune.service.in` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 161 | fabro-hosts | `services/disk-guard/docker-prune.timer.in` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 162 | fabro-hosts | `services/disk-guard/disk-guard.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 163 | fabro-hosts | `services/disk-guard/hosts/hp-xubuntu.env` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 164 | fabro-hosts | `services/disk-guard/install.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 165 | fabro-hosts | `services/disk-guard/render-unit.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 166 | fabro-hosts | `services/fabro-server/fabro-server-verify-web` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 167 | fabro-hosts | `services/fabro-server/fabro-server.service.in` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 168 | fabro-hosts | `services/fabro-server/hosts/hp-xubuntu-mi-homelab.env` | Deleted, pre-deletion cited | Deleted by fabro-hosts `ee8a71b` (2026-11-12, po2nrg); pre-deletion `931442c`. The `fabro_server` drift report now compares resolved settings |
| 169 | fabro-hosts | `services/fabro-server/hosts/hp-xubuntu.env` | Deleted, pre-deletion cited | Deleted by fabro-hosts `ee8a71b` (2026-11-12, po2nrg); pre-deletion `931442c`. The `fabro_server` drift report now compares resolved settings |
| 170 | fabro-hosts | `services/fabro-server/hosts/vps-mi-homelab.env` | Deleted, pre-deletion cited | Deleted by fabro-hosts `ee8a71b` (2026-11-12, po2nrg); pre-deletion `931442c`. The `fabro_server` drift report now compares resolved settings |
| 171 | fabro-hosts | `services/fabro-server/hosts/vps.env` | Deleted, pre-deletion cited | Deleted by fabro-hosts `ee8a71b` (2026-11-12, po2nrg); pre-deletion `931442c`. The `fabro_server` drift report now compares resolved settings |
| 172 | fabro-hosts | `services/fabro-server/install.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 173 | fabro-hosts | `services/fabro-server/otel.conf` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 174 | fabro-hosts | `services/fabro-server/render-settings.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 175 | fabro-hosts | `services/fabro-server/render-unit.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 176 | fabro-hosts | `services/fabro-server/settings.toml.in` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 177 | fabro-hosts | `services/host-tools/btop-loop` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 178 | fabro-hosts | `services/host-tools/hosts/hp-xubuntu.env` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 179 | fabro-hosts | `services/host-tools/install.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 180 | fabro-hosts | `services/sccache-redis/hosts/hp-xubuntu.env` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 181 | fabro-hosts | `services/sccache-redis/install.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 182 | fabro-hosts | `services/sccache-redis/render-unit.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 183 | fabro-hosts | `services/sccache-redis/sccache-redis.service.in` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 184 | fabro-hosts | `services/storage-reclaim/hosts/hp-xubuntu.env` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 185 | fabro-hosts | `services/storage-reclaim/hosts/vps.env` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 186 | fabro-hosts | `services/storage-reclaim/install.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 187 | fabro-hosts | `services/storage-reclaim/render-unit.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 188 | fabro-hosts | `services/storage-reclaim/storage-reclaim.service.in` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 189 | fabro-hosts | `services/storage-reclaim/storage-reclaim.timer.in` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
| 190 | fabro-hosts | `services/storage-reclaim/storage-reclaim.sh` | Deleted, pre-deletion cited | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml`; still absent |
