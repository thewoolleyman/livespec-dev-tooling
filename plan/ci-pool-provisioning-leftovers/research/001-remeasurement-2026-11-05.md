# 001 — First re-measurement of the Ansible migration's leftovers (2026-11-05)

Plan `ci-pool-provisioning-leftovers`, epic `livespec-dev-tooling-fby3sx`. This
is the plan's first measurement. The brief (`000-brief-…-2026-10-13.md`) says
the leftovers' status was "unverified". This note measures each one against
committed code. It is read-only: no repository, host or ledger was written.

**What was read, and at which commit.**

| Source | Ref measured |
|---|---|
| `livespec-dev-tooling` | `origin/master` = `d8ec42a6` (2026-11-05), after `git fetch` |
| `vps-info` | `origin/master` = `ac89b07` (2026-11-04), after `git fetch` |
| `fabro-hosts` | `origin/master` = `931442c` (2026-10-21), after `git fetch` |
| livespec archive | `plan/archive/k3s-on-gmktec-for-vps-usage/research/005-…-2026-09-09.md` and the four files in `005-estate/` (also `006-…` for its counts) |
| Ledger | `with-livespec-env.sh -- bd list --status all --limit 0 --json`: 1193 records, 902 closed. That is the tenant and not the stray `embeddeddolt/` (dated 2026-08-21) beside `.beads/`. `bd-ib-te4h` was read once with `bd show`, read-only, from the orchestrator tenant. |

No host was contacted. Every "current state" below is about **committed
code**, not about live hosts. §5 lists what this does and does not cover.

**Definition of class (a).** The inventories define it as "(a) HOST GLUE,
migrates to Ansible" (`005-estate/ci-runner-k3s-phase2.md:39`,
`ci-runner-other.md:10`, `vps-info-services.md:7`,
`fabro-hosts-services.md:12`). Note 005 §1 adds: "Class (a) migrates to
Ansible. … Class (c) is deleted with its pre-deletion SHA cited."

## 0. Findings that change how the brief reads

1. **The "twelve dead artifacts" are the inventories' class (c) rows. That
   class is "DEAD / ONE-SHOT", not "dead".** These are the four (c) rows in
   `ci-runner-k3s-phase2.md:320` and the eight in `ci-runner-other.md`. Seven
   of the twelve are in use today, and two more are cited records (§1). Note
   005 §2 also contradicts itself about the subset:
   - It says "eight of those are a superseded phase".
   - The four it names include `install-arc.sh` and `install-kueue.sh`, which
     its own inventory classes as **(b)**, not (c) (`ci-runner-other.md:72-73`).
   - Note 006:426 says "four of them".

   This note measures the twelve (c) rows. It adds the two named (b) scripts
   as supplementary rows S1 and S2.
2. **Nothing records which eight fabro-hosts steps are meant.** No archived
   note lists them. `fabro-hosts-services.md` §4 lists **eleven** out-of-band
   items, and the vps-info inventory's eleven (e) rows match its count
   exactly. Items 9 to 11 of the fabro-hosts list are not install steps (a
   digest comparison, a pointer to another repository, an open measurement).
   So items 1 to 8 are taken to be "the eight". That is an inference. All
   eleven are measured, so nothing is lost if it is wrong.
3. **The class (a) count is 190, not 191.** The fabro-hosts table has 64
   rows, of which 39 are class (a). Its own footer says 65 rows and 40 (a)
   (`fabro-hosts-services.md:116`). The other three slices match their
   footers: 61, 35 and 55.
4. **Two of the four named children look already satisfied on master but are
   still open.**
   - `u3f6bw` (status `ready`): its single fstab fragment
     `ansible/roles/storage_layout/files/ci-tiers.fstab` landed in `aba1607a`
     (2026-09-12). Both the role and `base-os-install.sh:28` read it.
   - `y1t5` (status `backlog`): the boot converge started re-applying the
     registry mirror in `9e725016` (2026-09-09, "rebuild the ghcr registry
     mirror on every boot and stage it in the installed tree"), and
     `ci_converge_unit` installs both files
     (`ansible/roles/ci_converge_unit/defaults/main.yml:130-140`). What is
     still uncovered is the **node** half (`registries.yaml`); see §3 rows 52
     and 53.

   I did not read either item's comments (8 and 4), so I cannot say whether
   their host-captured proofs are recorded. Read
   `.ai/already-satisfied-items.md` before closing either one.
5. **DoD bullet 3 is still false on master.** `ci-runner/README.md:3-4` still
   says the tooling provisions capacity "on `poweredge-xubuntu`", and lines
   15-19 do not name the host the gate tier runs on.

## 1. The twelve "dead" artifacts (class (c)), plus the two named phase-1 scripts

None of the twelve has been deleted. All twelve are present on
`origin/master` (`git ls-tree -r origin/master ci-runner/`). Each row searched
the whole tree for callers and readers with
`git grep -n -F <name> origin/master -- . ':!plan'`. A "reader" here means
something that **executes or opens** the file. A comment that only cites the
file is listed separately as a citation.

| # | Artifact | 2026-09-09 claim | Current state (last commit touching it) | Evidence: callers and readers (file:line) | Verdict, then proposed disposition |
|---|---|---|---|---|---|
| 1 | `ci-runner/k3s/phase2/VALIDATION_CHECKLIST.md` | (c) "Historical validation record; only cited by README, DERIVATION.md and two script comments" | Present (`33d7af63`, 2026-10-10) | **No reader.** Cited as evidence by `phase2/kueue/DERIVATION.md:103,157,697,1798`, `phase2/node-extended-resource/patch-node-churn-capacity.sh:31`, `…/reapply-node-extended-resource.service:12`, `phase2/arc/values-livespec-console-beads-fabro.yaml:219`, `tests/consumer/test_jit_fleet_capacity_scenarios.py:28,346` (docstrings only), `phase2/README.md:16,21,143,161,207,215,263,277,315,2361` | **Cited record, not executed.** Keep it and reclassify it as (d) documentation. Deleting it would orphan about 20 live citations. The plan session must decide whether a citation counts as "used" under DoD bullet 1. |
| 2 | `ci-runner/k3s/phase2/gates/gate-credentials.yaml` | (c) "One-shot operator step recorded as a manifest header; not applied" | Present (`833086dc`, 2026-09-10) | **Never applied, by design** (its own header, lines 11-13). It is the declared shape of Secret `gates/gate-forge-credential` and its break-glass recipe. It is referenced as that declaration by `ci-runner/k3s/secret-reinjection/inject-gate-forge-secret.sh:12,82`, `…/inject-gate-forge-secret.service:10`, `…/seed-gate-forge-cred.sh:20,44`, `phase2/gates/gate-job-template.yaml:718`, `livespec_dev_tooling/checks/credential-reading-targets.md:90`, `ci-runner/k3s/README.md:493` and `phase2/gates/README.md:39` | **Used as documentation.** The boot reinjection added in `833086dc` cites it as the source of truth for the Secret's shape. Keep it and reclassify it as (d). |
| 3 | `ci-runner/k3s/phase2/isolation/negative-control-job.yaml` | (c) "Diagnostic one-shot; not applied by anything" | Present (`11d516fc`, 2026-09-06) | **Read by automation.** The `sandbox_image_prune` role collects every `*.yaml` in the repo and extracts sandbox-image pins from them (`ansible/roles/sandbox_image_prune/tasks/main.yml:101-128`). This file's pin `livespec-fabro-sandbox:python-v1.40.1` (line 38) is one of the protected pins, recorded as a measured need in `phase2/warm-cache/sandbox-image-prune/prune-sandbox-images.sh:66-85` (`livespec-ifwnqj.7`). It is also the negative control that `phase2/isolation/cache-negative-tests.sh:31` tells an operator to apply. That test runs from `.github/workflows/ci-cache-negative-tests.yml`. | **Used.** Keep. |
| 4 | `ci-runner/k3s/phase2/storage-layout/migrate-tier.sh` | (c) "One-shot operator procedure … stays a script" | Present (`eb976d4e`, 2026-11-03) | An attended procedure. `.ai/ci-node-storage-tiers.md:18-49,94` names it THE tier-move procedure. It is the one place `role_fstype` is decided, and these must agree with it: `ansible/roles/storage_layout/files/ci-tiers.fstab:31`, `phase0-bare-metal/profiles/poweredge-xubuntu.env:42-43,135`, `…/gmktec-xubuntu.env:180`, `phase2/arc/hook-pod-template.yaml:82`, `phase2/local-path-provisioner/local-path-provisioner.yaml:60`. Also `phase2/README.md:356,942`. | **Used** (attended, one-shot by nature). Keep. |
| 5 | `ci-runner/k3s/arc/values-host-unique.yaml` | (c) "superseded by `phase2/arc/values-poweredge-xubuntu-k3s.yaml`; nothing but the superseded `install-arc.sh` reads this file" | Present (`e568c588`, 2026-09-04) | Its only reader is `ci-runner/k3s/install-arc.sh:82`, which is itself dead (S1). `phase2/reconstruct/converge-ci-stack.sh:234-237,561` says the converge "never touches" it. | **Still dead.** Delete together with S1 (W1). |
| 6 | `ci-runner/k3s/kueue/resources.yaml` | (c) "superseded by `phase2/kueue/cluster-queue-phase1-proof.yaml`" | Present (`427abef9`, 2026-08-15) | Its only reader is `ci-runner/k3s/install-kueue.sh:34` (S2, dead). Comment-only mentions: `converge-ci-stack.sh:456`, `test-job/proof-job-kueue.yaml:2`. | **Still dead.** Delete together with S2 (W1). |
| 7 | `ci-runner/k3s/phase0-bare-metal/base-os-install.sh` | (c) "one-time bare-metal runbook … not an Ansible target" | Present (`eb976d4e`, 2026-11-03) | It is stage 2 of the spec-mandated rebuild procedure (`SPECIFICATION/non-functional-requirements.md:343` "One procedure, staged"; `ci-runner/k3s/README.md:45`). `tests/spec/test_runner_pool_node_rebuild.py:64-70` lists it in `_PROCEDURE`. It reads `ansible/roles/storage_layout/files/ci-tiers.fstab` (`base-os-install.sh:28`). Open item `lr5uby` will run it at the next poweredge rebuild. | **Used.** Keep. |
| 8 | `ci-runner/k3s/phase0-bare-metal/recovery-usb/build-recovery-usb.sh` | (c) "one-shot rescue-media builder" | Present (`53e6a206`, 2026-09-06) | `ci-runner/k3s/README.md:104` ("the rescue environment every stage below is rebuilt FROM"). `phase0-bare-metal/storage-layout.sh:465` sends the operator to the stick. `recovery-usb/recovery-usb-exit-tests.sh`. The DoD of `lr5uby` (backlog) requires a stick "built by `build-recovery-usb.sh`" to boot poweredge. | **Used** (attended rebuild tooling). Keep. |
| 9 | `ci-runner/k3s/phase0-bare-metal/recovery-usb/test-recovery-usb.sh` | (c) "one-shot verification harness" | Present (`53e6a206`) | `recovery-usb/recovery-usb-exit-tests.sh`, `recovery-usb/build-recovery-usb.sh`, `recovery-usb/README.md` | **Used** with row 8. Keep. |
| 10 | `ci-runner/k3s/phase0-bare-metal/storage-layout.sh` | (c) "one-time bare-metal storage runbook" | Present (`88646d89`, 2026-11-03) | Stage 1 of the rebuild (`ci-runner/k3s/README.md:38`). Executed in `--dry-run` by `tests/consumer/test_pool_node_rebuild_scenario.py:80,452-480`, `tests/livespec_dev_tooling/test_hp_xubuntu_profile_and_storage_refusals.py:66,162` and `tests/livespec_dev_tooling/test_factory_workspace_root_not_reclaimed.py:65`. Read by `tests/spec/test_runner_pool_node_rebuild.py:65,173`. | **Used** (by tests and by the rebuild). Keep. |
| 11 | `ci-runner/k3s/test-job/proof-job-kueue.yaml` | (c) "proof/test Job; nothing applies it" | Present (`427abef9`) | **No reader.** It is mentioned only as a manual proof in `ci-runner/k3s/README.md:113,536`. It targets `phase1-proof-lq`, which still exists through `phase2/kueue/cluster-queue-phase1-proof.yaml`. | **Still dead.** Delete with the phase-1 set (W1). |
| 12 | `ci-runner/k3s/test-job/proof-job.yml` | (c) "superseded by the live, diverged `.github/workflows/k3s-arc-proof-job.yml`; this copy is stale" | Present (`b7c365f0`, 2026-08-25) | **Read by a test.** `tests/consumer/test_pool_node_rebuild_scenario.py:82` (`_PROOF_JOB`) and `:512` (`_PROOF_JOB.read_text(...)`) hold the rebuilt nodes against this file, not against the workflow. | **Used.** Keep. Repoint the test at the workflow first if the copy should go. |
| S1 | `ci-runner/k3s/install-arc.sh` | (b) "NOT invoked by anything … superseded by `converge-ci-stack.sh`". Named as dead in note 005 §2. | Present (`cc1784b0`, 2026-08-23) | **No executor.** It is still **advertised as a rebuild step**: `ci-runner/k3s/README.md:76-77` (step 5), `:108,122-123,535`, and the operator log line `ci-runner/k3s/provision-k3s.sh:587` ("then install-arc.sh and install-kueue.sh"). Comment-only mentions: `converge-ci-stack.sh:65,69,168,233-237,423,559`, `secret-reinjection/inject-github-app-secret.service:8,31`, `…/inject-github-app-secret.sh:8,89`, `ci-runner/README.md:80`. | **Dead, but documented as a step.** Delete it and repoint every mention (W1). |
| S2 | `ci-runner/k3s/install-kueue.sh` | (b), as S1 | Present (`427abef9`) | No executor. Advertised at `ci-runner/k3s/README.md:76-77,110,125,535` and `provision-k3s.sh:587`. Comment-only mentions: `phase2/kueue/core/kustomization.yaml:34`, `converge-ci-stack.sh:70,169,455-459`, `install-arc.sh:89`. | **Dead, but documented as a step.** Delete it and repoint every mention (W1). |

**Tally.** 0 of the 12 have been deleted. 3 of the 12 are still dead
(rows 5, 6 and 11), plus S1 and S2. 7 are used by code, tests or a named
procedure (rows 3, 4, 7, 8, 9, 10 and 12). 2 are cited documentation
(rows 1 and 2).

## 2. The nineteen manual steps

Each step was checked against the role that replaced its installer. The three
outcomes are the DoD's:

- **AUTOMATED**: committed automation now performs the step.
- **PRECONDITION + ASSERT**: the step is recorded and a preflight `assert`
  refuses to continue before any change.
- **MANUAL**: the step is still manual. Where a role comment or a `HOST_VARS.md`
  records it, the row says so.

All paths are under `livespec-dev-tooling` `origin/master` unless the row
names another repository. Only the four playbooks below apply these roles, and
"runs before any change" was checked against each task's line order.

- `ansible/dev-host.yml` targets `dev_hosts` = `vps` (`ansible/inventory/legacy.yml:49-51`).
- `ansible/gates-kubeconfig.yml`.
- `ansible/fabro-hosts.yml`.
- `ansible/ci-pool.yml`.

### 2.1 vps-info: eleven steps (the inventory's eleven (e) rows)

| # | Step (2026-09-09 claim) | Role now | Current state | Evidence | Proposed disposition |
|---|---|---|---|---|---|
| V1 | 1password-desktop: sign in on the first VNC connect, and set auto-lock to 15 min | `onepassword_desktop` (`dev-host.yml:35`) | **MANUAL. The role does not record it.** It is interactive and happens after install, so no pre-apply assert can check it. | `git grep -i 'sign in\|auto-lock' ansible/roles/onepassword_desktop` is empty. The only preflight is the VNC session assert, `tasks/main.yml:19-37`. | Record it as an out-of-band post-apply step in the role's `HOST_VARS.md` (W5a). Accept that it stays manual. |
| V2 | arq-vps-smb-source: create and maintain the Arq plan on the Mac | `arq_smb_source` (`dev-host.yml:29`) | **MANUAL, recorded.** The Mac side has no CLI. | Role header `tasks/main.yml:14-19` ("The Arq plan on the Mac is out of band entirely"). Host-side preconditions are asserted at `:21-34` (socket-proxyd) and `:35-47` (tailnet IP). | Accept as recorded. Nothing on the host can assert Mac state. |
| V3 | claude-desktop: first sign-in through VNC, and unlock gnome-keyring | `claude_desktop` (`dev-host.yml:37`) | **MANUAL, recorded.** The keyring package is now installed. | `tasks/main.yml:7-9` (header), `defaults/main.yml:11-19` (gnome-keyring). The VNC check is a warning by design (`:93-`). | Accept as recorded. Add it to `HOST_VARS.md` with V1 (W5a). |
| V4 | claude-ntfy: `~/.claude/settings.json` must exist, and the phone must subscribe to the topic | `claude_ntfy` (`dev-host.yml:51`) | **PRECONDITION + ASSERT** for the file. The phone half is MANUAL and recorded. | Assert at `tasks/main.yml:63-77`. The first change is at `:79` and later. Phone: `HOST_VARS.md:25-30`. | Done. |
| V5 | cloudflare-mcp: add `[mcp_servers.cloudflare-api]` to `~/.codex/config.toml` by hand, and put `CLOUDFLARE_MCP_TOKEN` in 1Password | none | **MANUAL. Ansible does not record it.** | No role. `git grep mcp_servers ansible/` is empty. vps-info `AGENTS.md:1460-1483` documents the hand step. | New work (W6). |
| V6 | gates-kubeconfig: ssh trust to poweredge, passwordless sudo there and locally, and the converge must have rendered the file | `gates_kubeconfig` (`gates-kubeconfig.yml:25`) | **AUTOMATED.** Ansible reads the file on poweredge under its own `become` (`delegate_to`). The ssh and sudo legs are now the inventory's own connection, which was measured reachable in note 005 §5. | Fetch: `tasks/main.yml:47-58`. Content assert: `:60-70`. The 005 §8 defect is resolved: the file is installed `root:gates-client 0640` (`:141-157`). Gap: `kubectl` and two scripts are installed (`:14-45`) **before** the fetch, so a missing remote file fails after those changes. | Done. Moving the fetch first is optional (W5a). |
| V7 | honeycomb-mcp: the plugin is installed, the Management key is in 1Password, re-run after every plugin update | `honeycomb_mcp` (`dev-host.yml:55`) | **PRECONDITION + ASSERT** for the plugin, key, wrapper and checkout. **Ordering gap:** `:66` ("Make the stdio wrapper executable in the checkout") runs before the key and plugin asserts. **Re-run after a plugin update: MANUAL.** I found no trigger. | Asserts: `tasks/main.yml:29-44` (checkout), `:51-65` (wrapper), `:141-160` (key), `:186-198` (plugin). | Move `:66` after the asserts (W5a). Record the re-run step (W5a). |
| V8 | honeycomb-trigger-recipients-check: add the Configuration key to 1Password | `honeycomb_trigger_recipients_check` (`dev-host.yml:57`) | **Recorded but WARN-only, deliberately.** The role asserts the wrapper but not the key. | Wrapper assert: `tasks/main.yml:52-68`. Key: `:111-153`, a `debug` warning with a stated rationale. | Does not meet DoD bullet 2 as written. Either promote it to an assert, or have the plan record the warning as an accepted exception (W5a). |
| V9 | vnc-desktop: set the VNC password once, and hand-build the Chrome profile | `vnc_desktop` (`dev-host.yml:33`) | **PRECONDITION + ASSERT** for the password and for Chrome itself. The Chrome profile contents are MANUAL and not recordable. | `tasks/main.yml:42-55` (password) and `:20-35` (Chrome), both before the first install at `:79`. | Done. |
| V10 | vps-restic-backup: create the S3 bucket, IAM user and restic password, import them to 1Password, run `doctor`, run the first backup | `restic_backup` (`dev-host.yml:31`) | **Recorded in a comment, NOT asserted.** Only the wrapper is asserted. `doctor` and the first backup are MANUAL after apply. | Header `tasks/main.yml:13-20`. Wrapper assert `:27-41`. No check that the six `VPS_RESTIC_*` names resolve. | Add a key-presence assert, as `honeycomb_mcp:141` does (W5a). |
| V11 | Fleet prerequisite: `/usr/local/bin/with-homelab-env.sh`, `with-homelab-aws.sh` and `/etc/credstore.encrypted/homelab-aws-bootstrap` | none installs them | `with-homelab-env.sh`: **PRECONDITION + ASSERT** in three roles. Creating it is MANUAL (`1password-env-wrapper/create-1password-env-wrapper.sh`). `with-homelab-aws.sh` and the credstore: **no role references them.** | `restic_backup/tasks/main.yml:27-41`, `honeycomb_mcp/tasks/main.yml:51-65`, `honeycomb_trigger_recipients_check/tasks/main.yml:52-68`. `git grep with-homelab-aws ansible/` is empty. | Partly done. I could not establish who now owns `with-homelab-aws.sh` (§5). |

### 2.2 fabro-hosts: eight steps (inventory §4 items 1-8; see §0.2)

| # | Step (2026-09-09 claim) | Role now | Current state | Evidence | Proposed disposition |
|---|---|---|---|---|---|
| F1 | Build the Fabro binary and place it | `fabro_server` (`fabro-hosts.yml:142-152,198-`) | **PRECONDITION + ASSERT** for the build, which is still a manual `cargo` build. **AUTOMATED** placement from a digest-pinned build staged on the control node. | Preflight block `tasks/main.yml:362-373`. Control-node digest assert `:391-408`. Host binary assert `:442-465`. Pins: `inventory/host_vars/vps.yml:85-87,101-103`. | Done. |
| F2 | Create `<home>/storage/server.env` (mint `SESSION_SECRET` and `FABRO_DEV_TOKEN`) | `fabro_server` | **AUTOMATED.** The role generates it once and asserts it. | Generate: `tasks/main.yml:573-601` (`creates:`, 0600). Asserts: `:668-681` and `:708-719`. | Done. |
| F3 | Apply `settings.toml` by hand | `fabro_server` | **AUTOMATED when opted in, otherwise report-only.** gmktec opts in. **vps does not**, so vps's file is still hand-maintained. | Drift report `tasks/main.yml:1327-1357`, write `:1359-1377`. `fabro_server_manage_settings: true` at `host_vars/gmktec-xubuntu.yml:175`. Default `false` at `defaults/main.yml:284`. vps sets nothing. | Decide opt-in for vps (W5b). |
| F4 | Load `GITHUB_APP_PRIVATE_KEY` into the instance's vault | `fabro_server` (`tasks/vault.yml`) | **AUTOMATED with an assert** for instances that declare `vault_secrets`. That is gmktec only. **vps instances declare none**, so a rebuilt vps would start with an empty vault and nothing would refuse. | Assert `vault.yml:54-69`, create `:71-108`. Declarations: `host_vars/gmktec-xubuntu.yml:424,617,759`. None in `host_vars/vps.yml:55-103`. | Declare it on vps (W5b). |
| F5 | Add the `tailscale serve` mapping (in tailscale-admin) | `tailscale_serve` (`fabro-hosts.yml:115`, `sandbox_hosts` play only) | **AUTOMATED on gmktec.** **MANUAL on vps**, and the role says so. `fabro_server` deliberately does not verify it. | `tailscale_serve/HOST_VARS.md:18-27` ("`hp-xubuntu` and `vps` declare nothing … made by hand"). `fabro_server/tasks/main.yml:723-738`. | Declare vps's 32276/32277 mappings and apply the role to vps (W5b). |
| F6 | Decide whether vps gets `otel.conf` | `fabro_server` (`otel_dropin`) | **Now a declared decision, still undecided for vps `fabro-server`.** Not a manual step any more; a ruling is owed. | Validity assert `tasks/main.yml:176-186`. `host_vars/vps.yml:64-72` (`otel_dropin: unmanaged`, "Do not decide it by default"). Run-output note `tasks/main.yml:1289-1298`. | A ruling (W5b). |
| F7 | Wait for a quiet server before re-installing | `fabro_server` | **AUTOMATED.** A quiet-server assert, plus a deferred restart that a later run claims. | `tasks/main.yml:1036-1058` (assert). Deferred restart `:795-960`, gated by `fabro_server_restart_allowed`. | Done. |
| F8 | `host-tools`: pre-install `btop` | `host_tools` | **AUTOMATED.** A package task replaces the refusal. On vps, `btop_loop` instead asserts that btop is present. | `host_tools/tasks/main.yml:26-41`. `btop_loop/tasks/main.yml:47-58`. | Done. |
| (F9) | disk-guard: compare printed digests | `disk_guard` | Obsolete. The installer was deleted (fabro-hosts `a933250`), and `--check --diff` replaces the comparison. | fabro-hosts `a933250` | none |
| (F10) | sccache-redis: the sandbox half is elsewhere | — | Not a step | — | none |
| (F11) | container-reclaim: re-derive hp's 48h horizon | — | Not an install step. hp left `sandbox_hosts` on 2026-11-02 (`inventory/legacy.yml:30`). | — | none |

**Tally of the nineteen.**

- AUTOMATED: 5 (V6, F2, F7, F8, and F1's placement).
- PRECONDITION + ASSERT and done: 4 (V4, V9, F1's build, V11's env wrapper).
- Partly done, or done on one host only: 5 (V7, V10, F3, F4, F5).
- Still manual or unrecorded: 5. V1 and V5 are unrecorded. V8 is warn-only. F6 is an undecided ruling. V11's `with-homelab-aws.sh` is unrecorded.
- V2 and V3 are manual but recorded, and accepted. They are Mac or GUI state that no assert can reach.

The rows overlap, so these counts are a reading guide and not a partition.

## 3. Every class (a) host-glue artifact in the 005-estate inventories

**Method.** Each row was checked in four ways:

1. **Existence** on its repository's `origin/master`, with `git cat-file -e`.
2. **The deleting commit**, with `git log --diff-filter=D -1`.
3. **The pre-deletion commit.** It is taken from the deleting commit's own
   message, which lists one per file:
   - `988285fc` lists one per file.
   - `1dcf9ac5` and `d51e93f1` each list theirs.
   - fabro-hosts `a933250` names `60c99562` (its parent `60c9956`) for every file it removed.
4. **The installing role.** A role counts only if one of two things holds:
   - its `defaults/main.yml` sources the file from the `ci-runner/` tree
     (`<role>_phase2_dir` and the like, `src:` in `tasks/`);
   - its `tasks/main.yml` header says "Replaces vps-info services/<svc>", or
     the deleting commit maps the file to it.

A file name that only appears in a comment did not count.

**Tally (190 rows).**

| Disposition | Rows |
|---|---|
| Deleted, pre-deletion commit cited | 58 (23 in `livespec-dev-tooling`, 35 in `fabro-hosts`) |
| Installed by a committed role, no duplicate left | 52 |
| Installed by a committed role, but the superseded vps-info copy is still committed | 49 |
| Kept as committed shell or data by the spec (`SPECIFICATION/non-functional-requirements.md:343`, "One procedure, staged" / "One profile per node") | 5 |
| Neither, owned by an open item | 15 (13 gate-runner → `6fl7a4`; 2 registry-mirror node half → `e2gv6n` / `y1t5`) |
| Neither, no owning open item found | 11 (6 vps-info editor stack, 4 fabro-hosts `check-settings` env files, 1 `seed-github-app-creds.sh`) |

### 3.1 `livespec-dev-tooling` `ci-runner/k3s/phase2/` (61 class (a) rows)

| # | Artifact | 2026-09-09 claim | Current state | Evidence | Proposed disposition |
| --- | --- | --- | --- | --- | --- |
| 1 | `ci-runner/k3s/phase2/install-node.sh` | (a), both | Deleted; replaced by `ansible/ci-pool.yml` | deleting commit `988285fc`; pre-deletion `b39c9930` | Done (deleted, SHA cited) |
| 2 | `ci-runner/k3s/phase2/k3s-runtime-ready.sh` | (a), both | Exists; installed by role `container_hook` | staged by `container_hook` (defaults/main.yml:19) for extract-externals.sh, applied by `ansible/ci-pool.yml` | Done (role) |
| 3 | `ci-runner/k3s/phase2/remove-server-only-units.sh` | (a), agent | Deleted; replaced by `remove_units.yml` in `wedged_runner`, `arc_log_archive`, `runner_pod_lifecycle` | deleting commit `988285fc`; pre-deletion `1eba2e54` | Done (deleted, SHA cited) |
| 4 | `ci-runner/k3s/phase2/apparmor/ci-runner-workflow` | (a), both | Exists; installed by role `apparmor_profile` | `ansible/roles/apparmor_profile/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 5 | `ci-runner/k3s/phase2/apparmor/install-apparmor-profile.sh` | (a), both | Deleted; replaced by `apparmor_profile` | deleting commit `988285fc`; pre-deletion `5b39c8c3` | Done (deleted, SHA cited) |
| 6 | `ci-runner/k3s/phase2/arc-log-archive/archive-arc-logs.service` | (a), server | Exists; installed by role `arc_log_archive` | `ansible/roles/arc_log_archive/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 7 | `ci-runner/k3s/phase2/arc-log-archive/archive-arc-logs.sh` | (a), server | Exists; installed by role `arc_log_archive` | `ansible/roles/arc_log_archive/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 8 | `ci-runner/k3s/phase2/arc-log-archive/archive-arc-logs.timer` | (a), server | Exists; installed by role `arc_log_archive` | `ansible/roles/arc_log_archive/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 9 | `ci-runner/k3s/phase2/arc-log-archive/install-arc-log-archive.sh` | (a), server (refuses on agent) | Deleted; replaced by `arc_log_archive` | deleting commit `988285fc`; pre-deletion `1eba2e54` | Done (deleted, SHA cited) |
| 10 | `ci-runner/k3s/phase2/cache-telemetry/ci-cache-span.sh` | (a), both | Exists; installed by role `cache_telemetry` | `ansible/roles/cache_telemetry/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 11 | `ci-runner/k3s/phase2/cache-telemetry/install-cache-telemetry.sh` | (a), both | Deleted; replaced by `cache_telemetry` | deleting commit `988285fc`; pre-deletion `fad2489b` | Done (deleted, SHA cited) |
| 12 | `ci-runner/k3s/phase2/container-hook/bundle/2.336.0/BUILD-INFO` | (a), both | Exists; installed by role `container_hook` | `ansible/roles/container_hook/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 13 | `ci-runner/k3s/phase2/container-hook/bundle/2.336.0/index.js` | (a), both | Exists; installed by role `container_hook` | `ansible/roles/container_hook/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 14 | `ci-runner/k3s/phase2/container-hook/bundle/2.336.0/index.js.sha256` | (a), both | Exists; installed by role `container_hook` | `ansible/roles/container_hook/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 15 | `ci-runner/k3s/phase2/container-hook/extract-externals.sh` | (a), both | Exists; installed by role `container_hook` | `ansible/roles/container_hook/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 16 | `ci-runner/k3s/phase2/container-hook/install-container-hook.sh` | (a), both | Deleted; replaced by `container_hook` | deleting commit `988285fc`; pre-deletion `4fb6b82a` | Done (deleted, SHA cited) |
| 17 | `ci-runner/k3s/phase2/container-hook/runner-image.sh` | (a), both | Exists; installed by role `container_hook` | `ansible/roles/container_hook/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 18 | `ci-runner/k3s/phase2/datastore-tmpfs/20-requires-datastore-mount.conf` | (a), server | Exists; installed by role `datastore_tmpfs` | `ansible/roles/datastore_tmpfs/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 19 | `ci-runner/k3s/phase2/datastore-tmpfs/install-datastore-tmpfs.sh` | (a), server | Deleted; replaced by `datastore_tmpfs` | deleting commit `988285fc`; pre-deletion `a222494c` | Done (deleted, SHA cited) |
| 20 | `ci-runner/k3s/phase2/datastore-tmpfs/var-lib-rancher-k3s-server-db.mount` | (a), server | Exists; installed by role `datastore_tmpfs` | `ansible/roles/datastore_tmpfs/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 21 | `ci-runner/k3s/phase2/host-thermal/apply-idrac-thermal.service` | (a), server | Exists; installed by role `host_thermal` | `ansible/roles/host_thermal/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 22 | `ci-runner/k3s/phase2/host-thermal/apply-idrac-thermal.sh` | (a), server | Exists; installed by role `host_thermal` | `ansible/roles/host_thermal/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 23 | `ci-runner/k3s/phase2/host-thermal/install-host-thermal.sh` | (a), server | Deleted; replaced by `host_thermal` | deleting commit `988285fc`; pre-deletion `d92e0212` | Done (deleted, SHA cited) |
| 24 | `ci-runner/k3s/phase2/host-thermal/install-racadm.sh` | (a), server | Deleted; replaced by `host_thermal` | deleting commit `1dcf9ac5`; pre-deletion `d92e0212` | Done (deleted, SHA cited) |
| 25 | `ci-runner/k3s/phase2/host-tools/btop-loop` | (a), both | Exists; installed by role `host_tools_ci` | `ansible/roles/host_tools_ci/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 26 | `ci-runner/k3s/phase2/host-tools/install-host-tools.sh` | (a), both | Deleted; replaced by `host_tools_ci` | deleting commit `988285fc`; pre-deletion `b9433e15` | Done (deleted, SHA cited) |
| 27 | `ci-runner/k3s/phase2/k3s-config/config.agent.yaml` | (a), agent | Exists; installed by role `k3s_config` | `ansible/roles/k3s_config/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 28 | `ci-runner/k3s/phase2/k3s-config/config.yaml` | (a), server | Exists; installed by role `k3s_config` | `ansible/roles/k3s_config/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 29 | `ci-runner/k3s/phase2/k3s-config/install-k3s-config.sh` | (a), both | Deleted; replaced by `k3s_config` | deleting commit `988285fc`; pre-deletion `5d79cd5a` | Done (deleted, SHA cited) |
| 30 | `ci-runner/k3s/phase2/node-extended-resource/install-reapply-unit.sh` | (a), server (refuses on agent) | Deleted; replaced by `node_extended_resource` | deleting commit `988285fc`; pre-deletion `4fd213bc` | Done (deleted, SHA cited) |
| 31 | `ci-runner/k3s/phase2/node-extended-resource/patch-node-churn-capacity.sh` | (a), server | Exists; installed by role `node_extended_resource` | `ansible/roles/node_extended_resource/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 32 | `ci-runner/k3s/phase2/node-extended-resource/reapply-node-extended-resource.service` | (a), server | Exists; installed by role `node_extended_resource` | `ansible/roles/node_extended_resource/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 33 | `ci-runner/k3s/phase2/node-extended-resource/reapply-node-extended-resource.timer` | (a), server | Exists; installed by role `node_extended_resource` | `ansible/roles/node_extended_resource/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 34 | `ci-runner/k3s/phase2/node-inotify-budget/99-ci-runner-inotify.conf` | (a), both | Exists; installed by role `node_sysctl` | `ansible/roles/node_sysctl/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 35 | `ci-runner/k3s/phase2/node-inotify-budget/install-inotify-sysctl.sh` | (a), both | Deleted; replaced by `node_sysctl` | deleting commit `988285fc`; pre-deletion `a45e6be4` | Done (deleted, SHA cited) |
| 36 | `ci-runner/k3s/phase2/node-keyring-budget/60-k3s-container-keyring.conf` | (a), both | Exists; installed by role `node_sysctl` | `ansible/roles/node_sysctl/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 37 | `ci-runner/k3s/phase2/node-keyring-budget/install-keyring-sysctl.sh` | (a), both | Deleted; replaced by `node_sysctl` | deleting commit `988285fc`; pre-deletion `db6e4166` | Done (deleted, SHA cited) |
| 38 | `ci-runner/k3s/phase2/reconstruct/converge-ci-stack.service` | (a), server | Exists; installed by role `ci_converge_unit` | `ansible/roles/ci_converge_unit/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 39 | `ci-runner/k3s/phase2/reconstruct/install-converge-unit.sh` | (a), server | Deleted; replaced by `ci_converge_unit` | deleting commit `988285fc`; pre-deletion `b39c9930` | Done (deleted, SHA cited) |
| 40 | `ci-runner/k3s/phase2/reconstruct/render-sa-kubeconfig.sh` | (a), server | Exists; installed by role `ci_converge_unit` | `ansible/roles/ci_converge_unit/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 41 | `ci-runner/k3s/phase2/runner-pod-lifecycle/install-runner-pod-lifecycle-scan.sh` | (a), server (refuses on agent) | Deleted; replaced by `runner_pod_lifecycle` | deleting commit `988285fc`; pre-deletion `1eba2e54` | Done (deleted, SHA cited) |
| 42 | `ci-runner/k3s/phase2/runner-pod-lifecycle/scan-runner-pod-lifecycle.service` | (a), server | Exists; installed by role `runner_pod_lifecycle` | `ansible/roles/runner_pod_lifecycle/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 43 | `ci-runner/k3s/phase2/runner-pod-lifecycle/scan-runner-pod-lifecycle.sh` | (a), server | Exists; installed by role `runner_pod_lifecycle` | `ansible/roles/runner_pod_lifecycle/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 44 | `ci-runner/k3s/phase2/runner-pod-lifecycle/scan-runner-pod-lifecycle.timer` | (a), server | Exists; installed by role `runner_pod_lifecycle` | `ansible/roles/runner_pod_lifecycle/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 45 | `ci-runner/k3s/phase2/sccache/install-sccache-binary.sh` | (a), both | Deleted; replaced by `sccache_binary` | deleting commit `988285fc`; pre-deletion `3b6f347b` | Done (deleted, SHA cited) |
| 46 | `ci-runner/k3s/phase2/storage-layout/10-requires-storage-mounts.conf` | (a), both | Exists; installed by role `storage_layout` | `ansible/roles/storage_layout/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 47 | `ci-runner/k3s/phase2/storage-layout/install-storage-layout.sh` | (a), both | Deleted; replaced by `storage_layout` | deleting commit `988285fc`; pre-deletion `c53ec28b` | Done (deleted, SHA cited) |
| 48 | `ci-runner/k3s/phase2/storage-sweep/agent-ordering.conf` | (a), agent | Exists; installed by role `storage_sweep` | `ansible/roles/storage_sweep/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 49 | `ci-runner/k3s/phase2/storage-sweep/install-storage-sweep.sh` | (a), both | Deleted; replaced by `storage_sweep` | deleting commit `988285fc`; pre-deletion `e2be3362` | Done (deleted, SHA cited) |
| 50 | `ci-runner/k3s/phase2/storage-sweep/sweep-runner-scratch.service` | (a), both | Exists; installed by role `storage_sweep` | `ansible/roles/storage_sweep/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 51 | `ci-runner/k3s/phase2/storage-sweep/sweep-runner-scratch.sh` | (a), both | Exists; installed by role `storage_sweep` | `ansible/roles/storage_sweep/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 52 | `ci-runner/k3s/phase2/warm-cache/registry-mirror/install-registry-mirror.sh` | (a), both (planned) | Exists; no role installs it | `git grep registries.yaml ansible/` is empty; not run by any playbook | Owned by **e2gv6n** (agents) and **y1t5** (named "node half" in the brief); see §4 W9 |
| 53 | `ci-runner/k3s/phase2/warm-cache/registry-mirror/registries.yaml.template` | (a), both (planned) | Exists; no role installs it | `git grep registries.yaml ansible/` is empty; not run by any playbook | Owned by **e2gv6n** (agents) and **y1t5** (named "node half" in the brief); see §4 W9 |
| 54 | `ci-runner/k3s/phase2/warm-cache/sandbox-image-prune/install-sandbox-image-prune.sh` | (a), server (planned) | Deleted; replaced by `sandbox_image_prune` | deleting commit `d51e93f1`; pre-deletion `356e0454` | Done (deleted, SHA cited) |
| 55 | `ci-runner/k3s/phase2/warm-cache/sandbox-image-prune/prune-sandbox-images.service` | (a), server (planned) | Exists; installed by role `sandbox_image_prune` | `ansible/roles/sandbox_image_prune/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 56 | `ci-runner/k3s/phase2/warm-cache/sandbox-image-prune/prune-sandbox-images.sh` | (a), server (planned) | Exists; installed by role `sandbox_image_prune` | `ansible/roles/sandbox_image_prune/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 57 | `ci-runner/k3s/phase2/warm-cache/sandbox-image-prune/prune-sandbox-images.timer` | (a), server (planned) | Exists; installed by role `sandbox_image_prune` | `ansible/roles/sandbox_image_prune/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 58 | `ci-runner/k3s/phase2/wedged-runner/install-wedged-runner-scan.sh` | (a), server (refuses on agent) | Deleted; replaced by `wedged_runner` | deleting commit `988285fc`; pre-deletion `1eba2e54` | Done (deleted, SHA cited) |
| 59 | `ci-runner/k3s/phase2/wedged-runner/scan-wedged-runners.service` | (a), server | Exists; installed by role `wedged_runner` | `ansible/roles/wedged_runner/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 60 | `ci-runner/k3s/phase2/wedged-runner/scan-wedged-runners.sh` | (a), server | Exists; installed by role `wedged_runner` | `ansible/roles/wedged_runner/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 61 | `ci-runner/k3s/phase2/wedged-runner/scan-wedged-runners.timer` | (a), server | Exists; installed by role `wedged_runner` | `ansible/roles/wedged_runner/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |

### 3.2 `livespec-dev-tooling` `ci-runner/` outside `phase2/` (35 class (a) rows)

| # | Artifact | 2026-09-09 claim | Current state | Evidence | Proposed disposition |
| --- | --- | --- | --- | --- | --- |
| 62 | `ci-runner/gate-runner/50-gate-runner-supervisor.rules` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 63 | `ci-runner/gate-runner/app-installation-token.sh` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 64 | `ci-runner/gate-runner/gate-optin-expiry.service` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 65 | `ci-runner/gate-runner/gate-optin-expiry.sh` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 66 | `ci-runner/gate-runner/gate-optin-expiry.timer` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 67 | `ci-runner/gate-runner/gate-optin.sh` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 68 | `ci-runner/gate-runner/gate-runner-supervisor.service` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 69 | `ci-runner/gate-runner/gate-runner-supervisor.sh` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 70 | `ci-runner/gate-runner/gate-runner@.service` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 71 | `ci-runner/gate-runner/hosted-only.conf` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 72 | `ci-runner/gate-runner/mint-jitconfig.sh` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 73 | `ci-runner/gate-runner/provision-gate-runner.sh` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 74 | `ci-runner/gate-runner/run-gate-jit-runner.sh` | (a), VPS (shared factory host) | Exists; no role installs it; no playbook targets the VPS gate tier | no `gate_runner` role under `ansible/roles/`; `provision-gate-runner.sh` still the installer | Owned by **6fl7a4** (blocked on orchestrator `bd-ib-te4h`, still `backlog`) |
| 75 | `ci-runner/k3s/phase0-bare-metal/profile.sh` | (a), both (indirectly) | Exists; deliberately stays committed shell | `SPECIFICATION/non-functional-requirements.md:343` ("the bare-metal stages and the pinned k3s install remain committed shell") | Keep as shell (spec-sanctioned); record as such |
| 76 | `ci-runner/k3s/phase0-bare-metal/profiles/gmktec-xubuntu.env` | (a), agent | Exists; read by roles as the node profile (not converted to `host_vars`) | `k3s_config/defaults/main.yml:16`, `node_extended_resource/defaults/main.yml:7`, `node_labels/defaults/main.yml:2`, `node_taints/defaults/main.yml:2` read `phase0-bare-metal/profiles/`; spec §"One profile per node" | Keep (spec-sanctioned data); record as such |
| 77 | `ci-runner/k3s/phase0-bare-metal/profiles/poweredge-xubuntu.env` | (a), server | Exists; read by roles as the node profile (not converted to `host_vars`) | `k3s_config/defaults/main.yml:16`, `node_extended_resource/defaults/main.yml:7`, `node_labels/defaults/main.yml:2`, `node_taints/defaults/main.yml:2` read `phase0-bare-metal/profiles/`; spec §"One profile per node" | Keep (spec-sanctioned data); record as such |
| 78 | `ci-runner/k3s/provision-k3s.sh` | (a), both | Exists; deliberately stays committed shell | `SPECIFICATION/non-functional-requirements.md:343` ("the bare-metal stages and the pinned k3s install remain committed shell") | Keep as shell (spec-sanctioned); record as such |
| 79 | `ci-runner/k3s/secret-reinjection/inject-github-app-secret.service` | (a), server | Exists; installed by role `secret_reinjection` | `ansible/roles/secret_reinjection/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 80 | `ci-runner/k3s/secret-reinjection/inject-github-app-secret.sh` | (a), server | Exists; installed by role `secret_reinjection` | `ansible/roles/secret_reinjection/` sources it from the `ci-runner/` tree, applied by `ansible/ci-pool.yml` | Done (role) |
| 81 | `ci-runner/k3s/secret-reinjection/install-secret-reinjection-unit.sh` | (a), server | Deleted; replaced by `secret_reinjection` | deleting commit `988285fc`; pre-deletion `833086dc` | Done (deleted, SHA cited) |
| 82 | `ci-runner/k3s/secret-reinjection/seed-github-app-creds.sh` | (a), server | Exists; attended seed, no role runs it | `secret_reinjection/tasks/main.yml:32-55` only WARNS when the credstore is unseeded | Keep as attended seed; candidate for a precondition assert (§4 W5a) |
| 83 | `ci-runner/k3s/secret-reinjection/seed-k3s-agent-join-token.sh` | (a), agent | Exists; attended seed, no role runs it | `provision-k3s.sh:268-272` refuses a missing or over-wide token file (a shell preflight, before k3s exists) | Keep as attended pre-k3s seed (spec-sanctioned stage) |
| 84 | `ci-runner/observability/ci-cache-gauges.service` | (a), server | Exists; installed by role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` | Done (role) |
| 85 | `ci-runner/observability/ci-cache-gauges.sh` | (a), server (cache-tier carrier) | Exists; installed by role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` | Done (role) |
| 86 | `ci-runner/observability/ci-cache-gauges.timer` | (a), server | Exists; installed by role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` | Done (role) |
| 87 | `ci-runner/observability/ci-kueue-webhook-probe.service` | (a), server | Exists; installed by role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` | Done (role) |
| 88 | `ci-runner/observability/ci-kueue-webhook-probe.sh` | (a), server | Exists; installed by role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` | Done (role) |
| 89 | `ci-runner/observability/ci-kueue-webhook-probe.timer` | (a), server | Exists; installed by role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` | Done (role) |
| 90 | `ci-runner/observability/ci-pool-attributed-gauges.service` | (a), server (admin kubeconfig) | Exists; installed by role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` | Done (role) |
| 91 | `ci-runner/observability/ci-pool-attributed-gauges.sh` | (a), server | Exists; installed by role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` | Done (role) |
| 92 | `ci-runner/observability/ci-pool-attributed-gauges.timer` | (a), server | Exists; installed by role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` | Done (role) |
| 93 | `ci-runner/observability/ci-runner-heartbeat.service` | (a), server | Exists; installed by role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` | Done (role) |
| 94 | `ci-runner/observability/ci-runner-heartbeat.sh` | (a), server | Exists; installed by role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` | Done (role) |
| 95 | `ci-runner/observability/ci-runner-heartbeat.timer` | (a), server | Exists; installed by role `ci_observability` | `ci_observability/defaults/main.yml:9-28` lists it, applied by `ansible/ci-pool.yml` | Done (role) |
| 96 | `ci-runner/observability/install-observability.sh` | (a), server | Deleted; replaced by `ci_observability` | deleting commit `d51e93f1`; pre-deletion `c13617d0` | Done (deleted, SHA cited) |

### 3.3 `vps-info` `services/` (55 class (a) rows)

| # | Artifact | 2026-09-09 claim | Current state | Evidence | Proposed disposition |
| --- | --- | --- | --- | --- | --- |
| 97 | `services/1password-desktop/install.sh` | (a), vps | Replaced by role `onepassword_desktop`; the vps-info shell installer is still committed | `ansible/roles/onepassword_desktop/tasks/main.yml` header "Replaces vps-info services/1password-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 98 | `services/1password-desktop/1password-desktop.service` | (a), vps | Installed by role `onepassword_desktop`; the vps-info copy is still committed | `ansible/roles/onepassword_desktop/tasks/main.yml` header "Replaces vps-info services/1password-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 99 | `services/1password-desktop/restart-1password.desktop` | (a), vps | Installed by role `onepassword_desktop`; the vps-info copy is still committed | `ansible/roles/onepassword_desktop/tasks/main.yml` header "Replaces vps-info services/1password-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 100 | `services/1password-desktop/sudoers.d-1password-desktop` | (a), vps | Installed by role `onepassword_desktop`; the vps-info copy is still committed | `ansible/roles/onepassword_desktop/tasks/main.yml` header "Replaces vps-info services/1password-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 101 | `services/arq-vps-docker-volume-snapshot/arq-vps-docker-volume-snapshot.service` | (a), vps | Installed by role `arq_docker_volume_snapshot`; the vps-info copy is still committed | `ansible/roles/arq_docker_volume_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-docker-volume-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 102 | `services/arq-vps-docker-volume-snapshot/arq-vps-docker-volume-snapshot.sh` | (a), vps | Installed by role `arq_docker_volume_snapshot`; the vps-info copy is still committed | `ansible/roles/arq_docker_volume_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-docker-volume-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 103 | `services/arq-vps-docker-volume-snapshot/arq-vps-docker-volume-snapshot.timer` | (a), vps | Installed by role `arq_docker_volume_snapshot`; the vps-info copy is still committed | `ansible/roles/arq_docker_volume_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-docker-volume-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 104 | `services/arq-vps-docker-volume-snapshot/install.sh` | (a), vps | Replaced by role `arq_docker_volume_snapshot`; the vps-info shell installer is still committed | `ansible/roles/arq_docker_volume_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-docker-volume-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 105 | `services/arq-vps-root-snapshot/arq-vps-root-snapshot.service` | (a), vps | Installed by role `arq_root_snapshot`; the vps-info copy is still committed | `ansible/roles/arq_root_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-root-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 106 | `services/arq-vps-root-snapshot/arq-vps-root-snapshot.sh` | (a), vps | Installed by role `arq_root_snapshot`; the vps-info copy is still committed | `ansible/roles/arq_root_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-root-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 107 | `services/arq-vps-root-snapshot/arq-vps-root-snapshot.timer` | (a), vps | Installed by role `arq_root_snapshot`; the vps-info copy is still committed | `ansible/roles/arq_root_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-root-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 108 | `services/arq-vps-root-snapshot/install.sh` | (a), vps | Replaced by role `arq_root_snapshot`; the vps-info shell installer is still committed | `ansible/roles/arq_root_snapshot/tasks/main.yml` header "Replaces vps-info services/arq-vps-root-snapshot"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 109 | `services/arq-vps-smb-source/arq-vps-smb-source-proxy.service` | (a), vps | Installed by role `arq_smb_source`; the vps-info copy is still committed | `ansible/roles/arq_smb_source/tasks/main.yml` header "Replaces vps-info services/arq-vps-smb-source"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 110 | `services/arq-vps-smb-source/arq-vps-smb-source-proxy.socket` | (a), vps | Installed by role `arq_smb_source`; the vps-info copy is still committed | `ansible/roles/arq_smb_source/tasks/main.yml` header "Replaces vps-info services/arq-vps-smb-source"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 111 | `services/arq-vps-smb-source/install.sh` | (a), vps | Replaced by role `arq_smb_source`; the vps-info shell installer is still committed | `ansible/roles/arq_smb_source/tasks/main.yml` header "Replaces vps-info services/arq-vps-smb-source"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 112 | `services/arq-vps-smb-source/smb.conf` | (a), vps | Installed by role `arq_smb_source`; the vps-info copy is still committed | `ansible/roles/arq_smb_source/tasks/main.yml` header "Replaces vps-info services/arq-vps-smb-source"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 113 | `services/btop-loop/btop-loop` | (a), vps | Installed by role `btop_loop`; the vps-info copy is still committed | `ansible/roles/btop_loop/tasks/main.yml` header "Replaces vps-info services/btop-loop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 114 | `services/btop-loop/install.sh` | (a), vps | Replaced by role `btop_loop`; the vps-info shell installer is still committed | `ansible/roles/btop_loop/tasks/main.yml` header "Replaces vps-info services/btop-loop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 115 | `services/claude-code-hooks/tmux-fleet-guard.py` | (a), vps | Installed by role `claude_code_hooks`; the vps-info copy is still committed | `ansible/roles/claude_code_hooks/tasks/main.yml` header "Replaces vps-info services/claude-code-hooks"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 116 | `services/claude-code-hooks/install.sh` | (a), vps | Replaced by role `claude_code_hooks`; the vps-info shell installer is still committed | `ansible/roles/claude_code_hooks/tasks/main.yml` header "Replaces vps-info services/claude-code-hooks"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 117 | `services/claude-desktop/claude-desktop.desktop` | (a), vps | Installed by role `claude_desktop`; the vps-info copy is still committed | `ansible/roles/claude_desktop/tasks/main.yml` header "Replaces vps-info services/claude-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 118 | `services/claude-desktop/install.sh` | (a), vps | Replaced by role `claude_desktop`; the vps-info shell installer is still committed | `ansible/roles/claude_desktop/tasks/main.yml` header "Replaces vps-info services/claude-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 119 | `services/claude-ntfy/install.sh` | (a), vps | Replaced by role `claude_ntfy`; the vps-info shell installer is still committed | `ansible/roles/claude_ntfy/tasks/main.yml` header "Replaces vps-info services/claude-ntfy"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 120 | `services/code-pwa-proxy/code-pwa-proxy.service` | (a), vps | Exists; no role installs it | no role under `ansible/roles/`; held disabled by maintainer ruling (vps-info `6458250`, AGENTS.md:441-447) | Neither; no open item found in this ledger (§4 W4) |
| 121 | `services/code-pwa-proxy/install.sh` | (a), vps | Exists; no role installs it | no role under `ansible/roles/`; held disabled by maintainer ruling (vps-info `6458250`, AGENTS.md:441-447) | Neither; no open item found in this ledger (§4 W4) |
| 122 | `services/code-pwa-proxy/nginx.conf` | (a), vps | Exists; no role installs it | no role under `ansible/roles/`; held disabled by maintainer ruling (vps-info `6458250`, AGENTS.md:441-447) | Neither; no open item found in this ledger (§4 W4) |
| 123 | `services/code-pwa-proxy/static/sw.js` | (a), vps | Exists; no role installs it | no role under `ansible/roles/`; held disabled by maintainer ruling (vps-info `6458250`, AGENTS.md:441-447) | Neither; no open item found in this ledger (§4 W4) |
| 124 | `services/code-serve-web/code-serve-web.service` | (a), vps | Exists; no role installs it | no role under `ansible/roles/`; held disabled by maintainer ruling (vps-info `6458250`, AGENTS.md:441-447) | Neither; no open item found in this ledger (§4 W4) |
| 125 | `services/code-serve-web/install.sh` | (a), vps | Exists; no role installs it | no role under `ansible/roles/`; held disabled by maintainer ruling (vps-info `6458250`, AGENTS.md:441-447) | Neither; no open item found in this ledger (§4 W4) |
| 126 | `services/codex-config/install.sh` | (a), vps | Replaced by role `codex_config`; the vps-info shell installer is still committed | `ansible/roles/codex_config/tasks/main.yml` header "Replaces vps-info services/codex-config"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 127 | `services/gates-kubeconfig/install.sh` | (a), vps | Replaced by role `gates_kubeconfig`; the vps-info shell installer is still committed | `ansible/roles/gates_kubeconfig/tasks/main.yml` header "Replaces vps-info services/gates-kubeconfig"; applied by `ansible/gates-kubeconfig.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 128 | `services/gates-kubeconfig/refresh-gates-kubeconfig` | (a), vps | Installed by role `gates_kubeconfig`; the vps-info copy is still committed | `ansible/roles/gates_kubeconfig/tasks/main.yml` header "Replaces vps-info services/gates-kubeconfig"; applied by `ansible/gates-kubeconfig.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 129 | `services/gates-kubeconfig/with-gates-kubeconfig` | (a), vps | Installed by role `gates_kubeconfig`; the vps-info copy is still committed | `ansible/roles/gates_kubeconfig/tasks/main.yml` header "Replaces vps-info services/gates-kubeconfig"; applied by `ansible/gates-kubeconfig.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 130 | `services/honeycomb-mcp/install.sh` | (a), vps | Replaced by role `honeycomb_mcp`; the vps-info shell installer is still committed | `ansible/roles/honeycomb_mcp/tasks/main.yml` header "Replaces vps-info services/honeycomb-mcp"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 131 | `services/honeycomb-trigger-recipients-check/check-trigger-recipients.sh` | (a), vps | Installed by role `honeycomb_trigger_recipients_check`; the vps-info copy is still committed | `ansible/roles/honeycomb_trigger_recipients_check/tasks/main.yml` header "Replaces vps-info services/honeycomb-trigger-recipients-check"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 132 | `services/honeycomb-trigger-recipients-check/honeycomb-trigger-recipients-check.service` | (a), vps | Installed by role `honeycomb_trigger_recipients_check`; the vps-info copy is still committed | `ansible/roles/honeycomb_trigger_recipients_check/tasks/main.yml` header "Replaces vps-info services/honeycomb-trigger-recipients-check"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 133 | `services/honeycomb-trigger-recipients-check/honeycomb-trigger-recipients-check.timer` | (a), vps | Installed by role `honeycomb_trigger_recipients_check`; the vps-info copy is still committed | `ansible/roles/honeycomb_trigger_recipients_check/tasks/main.yml` header "Replaces vps-info services/honeycomb-trigger-recipients-check"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 134 | `services/honeycomb-trigger-recipients-check/install.sh` | (a), vps | Replaced by role `honeycomb_trigger_recipients_check`; the vps-info shell installer is still committed | `ansible/roles/honeycomb_trigger_recipients_check/tasks/main.yml` header "Replaces vps-info services/honeycomb-trigger-recipients-check"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 135 | `services/keyring-quota/99-keyring-quota.conf` | (a), vps | Installed by role `keyring_quota`; the vps-info copy is still committed | `ansible/roles/keyring_quota/tasks/main.yml` header "Replaces vps-info services/keyring-quota"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 136 | `services/keyring-quota/install.sh` | (a), vps | Replaced by role `keyring_quota`; the vps-info shell installer is still committed | `ansible/roles/keyring_quota/tasks/main.yml` header "Replaces vps-info services/keyring-quota"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 137 | `services/ssh-hardening/00-ssh-hardening.conf` | (a), vps | Installed by role `ssh_hardening`; the vps-info copy is still committed | `ansible/roles/ssh_hardening/tasks/main.yml` header "Replaces vps-info services/ssh-hardening"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 138 | `services/ssh-hardening/install.sh` | (a), vps | Replaced by role `ssh_hardening`; the vps-info shell installer is still committed | `ansible/roles/ssh_hardening/tasks/main.yml` header "Replaces vps-info services/ssh-hardening"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 139 | `services/tmux-config/install.sh` | (a), vps | Replaced by role `tmux_config`; the vps-info shell installer is still committed | `ansible/roles/tmux_config/tasks/main.yml` header "Replaces vps-info services/tmux-config"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 140 | `services/tmux-config/tmux.conf.local` | (a), vps | Installed by role `tmux_config`; the vps-info copy is still committed | `ansible/roles/tmux_config/tasks/main.yml` header "Replaces vps-info services/tmux-config"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 141 | `services/vnc-desktop/com.google.Chrome.desktop` | (a), vps | Installed by role `vnc_desktop`; the vps-info copy is still committed | `ansible/roles/vnc_desktop/tasks/main.yml` header "Replaces vps-info services/vnc-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 142 | `services/vnc-desktop/google-chrome-wrapper.sh` | (a), vps | Installed by role `vnc_desktop`; the vps-info copy is still committed | `ansible/roles/vnc_desktop/tasks/main.yml` header "Replaces vps-info services/vnc-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 143 | `services/vnc-desktop/google-chrome.desktop` | (a), vps | Installed by role `vnc_desktop`; the vps-info copy is still committed | `ansible/roles/vnc_desktop/tasks/main.yml` header "Replaces vps-info services/vnc-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 144 | `services/vnc-desktop/install.sh` | (a), vps | Replaced by role `vnc_desktop`; the vps-info shell installer is still committed | `ansible/roles/vnc_desktop/tasks/main.yml` header "Replaces vps-info services/vnc-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 145 | `services/vnc-desktop/vnc-desktop-start.sh` | (a), vps | Installed by role `vnc_desktop`; the vps-info copy is still committed | `ansible/roles/vnc_desktop/tasks/main.yml` header "Replaces vps-info services/vnc-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 146 | `services/vnc-desktop/vnc-desktop.service` | (a), vps | Installed by role `vnc_desktop`; the vps-info copy is still committed | `ansible/roles/vnc_desktop/tasks/main.yml` header "Replaces vps-info services/vnc-desktop"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 147 | `services/vps-restic-backup/install.sh` | (a), vps | Replaced by role `restic_backup`; the vps-info shell installer is still committed | `ansible/roles/restic_backup/tasks/main.yml` header "Replaces vps-info services/vps-restic-backup"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 148 | `services/vps-restic-backup/vps-restic-backup.service` | (a), vps | Installed by role `restic_backup`; the vps-info copy is still committed | `ansible/roles/restic_backup/tasks/main.yml` header "Replaces vps-info services/vps-restic-backup"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 149 | `services/vps-restic-backup/vps-restic-backup.sh` | (a), vps | Installed by role `restic_backup`; the vps-info copy is still committed | `ansible/roles/restic_backup/tasks/main.yml` header "Replaces vps-info services/vps-restic-backup"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 150 | `services/vps-restic-backup/vps-restic-backup.timer` | (a), vps | Installed by role `restic_backup`; the vps-info copy is still committed | `ansible/roles/restic_backup/tasks/main.yml` header "Replaces vps-info services/vps-restic-backup"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |
| 151 | `services/vps-restic-backup/vps-restic-excludes.txt` | (a), vps | Installed by role `restic_backup`; the vps-info copy is still committed | `ansible/roles/restic_backup/tasks/main.yml` header "Replaces vps-info services/vps-restic-backup"; applied by `ansible/dev-host.yml`; file present at vps-info `origin/master` `ac89b07` | Done (role); retire the vps-info duplicate (§4 W3) |

### 3.4 `fabro-hosts` `services/` (39 class (a) rows; the inventory says 40, see §0)

| # | Artifact | 2026-09-09 claim | Current state | Evidence | Proposed disposition |
| --- | --- | --- | --- | --- | --- |
| 152 | `services/container-reclaim/container-reclaim.service.in` | (a), both | Deleted; replaced by role `container_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 153 | `services/container-reclaim/container-reclaim.timer.in` | (a), both | Deleted; replaced by role `container_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 154 | `services/container-reclaim/container-reclaim.sh` | (a), both | Deleted; replaced by role `container_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 155 | `services/container-reclaim/hosts/hp-xubuntu.env` | (a), hp-xubuntu | Deleted; replaced by role `container_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 156 | `services/container-reclaim/hosts/vps.env` | (a), vps | Deleted; replaced by role `container_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 157 | `services/container-reclaim/install.sh` | (a), both | Deleted; replaced by role `container_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 158 | `services/disk-guard/disk-guard.service.in` | (a), hp-xubuntu | Deleted; replaced by role `disk_guard` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 159 | `services/disk-guard/disk-guard.timer.in` | (a), hp-xubuntu | Deleted; replaced by role `disk_guard` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 160 | `services/disk-guard/docker-prune.service.in` | (a), hp-xubuntu | Deleted; replaced by role `disk_guard` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 161 | `services/disk-guard/docker-prune.timer.in` | (a), hp-xubuntu | Deleted; replaced by role `disk_guard` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 162 | `services/disk-guard/disk-guard.sh` | (a), hp-xubuntu | Deleted; replaced by role `disk_guard` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 163 | `services/disk-guard/hosts/hp-xubuntu.env` | (a), hp-xubuntu | Deleted; replaced by role `disk_guard` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 164 | `services/disk-guard/install.sh` | (a), hp-xubuntu | Deleted; replaced by role `disk_guard` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 165 | `services/disk-guard/render-unit.sh` | (a), hp-xubuntu | Deleted; replaced by role `disk_guard` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 166 | `services/fabro-server/fabro-server-verify-web` | (a), both | Deleted; replaced by role `fabro_server` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 167 | `services/fabro-server/fabro-server.service.in` | (a), both, two instances each | Deleted; replaced by role `fabro_server` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 168 | `services/fabro-server/hosts/hp-xubuntu-mi-homelab.env` | (a), hp-xubuntu | Exists; consumed only by `check-settings.sh` from the checkout; duplicates `host_vars` | fabro-hosts `a933250` body ("Deliberately kept"); fabro-hosts AGENTS.md:75-81 ("an open decision") | Neither; no open item; fold into §4 W7 |
| 169 | `services/fabro-server/hosts/hp-xubuntu.env` | (a), hp-xubuntu | Exists; consumed only by `check-settings.sh` from the checkout; duplicates `host_vars` | fabro-hosts `a933250` body ("Deliberately kept"); fabro-hosts AGENTS.md:75-81 ("an open decision") | Neither; no open item; fold into §4 W7 |
| 170 | `services/fabro-server/hosts/vps-mi-homelab.env` | (a), vps | Exists; consumed only by `check-settings.sh` from the checkout; duplicates `host_vars` | fabro-hosts `a933250` body ("Deliberately kept"); fabro-hosts AGENTS.md:75-81 ("an open decision") | Neither; no open item; fold into §4 W7 |
| 171 | `services/fabro-server/hosts/vps.env` | (a), vps | Exists; consumed only by `check-settings.sh` from the checkout; duplicates `host_vars` | fabro-hosts `a933250` body ("Deliberately kept"); fabro-hosts AGENTS.md:75-81 ("an open decision") | Neither; no open item; fold into §4 W7 |
| 172 | `services/fabro-server/install.sh` | (a), both, per instance | Deleted; replaced by role `fabro_server` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 173 | `services/fabro-server/otel.conf` | (a), both per `install.sh` | Deleted; replaced by role `fabro_server` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 174 | `services/fabro-server/render-settings.sh` | (a), both (four env files) | Deleted; replaced by role `fabro_server` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 175 | `services/fabro-server/render-unit.sh` | (a), both | Deleted; replaced by role `fabro_server` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 176 | `services/fabro-server/settings.toml.in` | (a), both (four env files) | Deleted; replaced by role `fabro_server` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 177 | `services/host-tools/btop-loop` | (a), hp-xubuntu | Deleted; replaced by role `host_tools` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 178 | `services/host-tools/hosts/hp-xubuntu.env` | (a), hp-xubuntu | Deleted; replaced by role `host_tools` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 179 | `services/host-tools/install.sh` | (a), hp-xubuntu | Deleted; replaced by role `host_tools` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 180 | `services/sccache-redis/hosts/hp-xubuntu.env` | (a), hp-xubuntu | Deleted; replaced by role `sccache_redis` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 181 | `services/sccache-redis/install.sh` | (a), hp-xubuntu | Deleted; replaced by role `sccache_redis` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 182 | `services/sccache-redis/render-unit.sh` | (a), hp-xubuntu | Deleted; replaced by role `sccache_redis` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 183 | `services/sccache-redis/sccache-redis.service.in` | (a), hp-xubuntu | Deleted; replaced by role `sccache_redis` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 184 | `services/storage-reclaim/hosts/hp-xubuntu.env` | (a), hp-xubuntu | Deleted; replaced by role `storage_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 185 | `services/storage-reclaim/hosts/vps.env` | (a), vps | Deleted; replaced by role `storage_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 186 | `services/storage-reclaim/install.sh` | (a), both | Deleted; replaced by role `storage_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 187 | `services/storage-reclaim/render-unit.sh` | (a), both | Deleted; replaced by role `storage_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 188 | `services/storage-reclaim/storage-reclaim.service.in` | (a), both | Deleted; replaced by role `storage_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 189 | `services/storage-reclaim/storage-reclaim.timer.in` | (a), both | Deleted; replaced by role `storage_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |
| 190 | `services/storage-reclaim/storage-reclaim.sh` | (a), both | Deleted; replaced by role `storage_reclaim` | fabro-hosts deleting commit `a933250`; pre-deletion `60c9956`; role applied by `ansible/fabro-hosts.yml` | Done (deleted, SHA cited) |

## 4. Still-open rows, grouped into proposed work items (nothing filed)

Each item has a one-line title, a Definition-of-Done-style assertion, the rows
it closes, and its overlap with the existing children: `nmrf34`, `y1t5`,
`6fl7a4` and `u3f6bw`.

- **W1 — Delete the phase-1 by-hand set and stop advertising it as rebuild step 5.**
  - DoD: none of these five files is in `git ls-tree -r origin/master`:
    - `ci-runner/k3s/install-arc.sh`
    - `ci-runner/k3s/install-kueue.sh`
    - `ci-runner/k3s/arc/values-host-unique.yaml`
    - `ci-runner/k3s/kueue/resources.yaml`
    - `ci-runner/k3s/test-job/proof-job-kueue.yaml`
  - DoD: the deleting commit cites their last commits as pre-deletion SHAs (`cc1784b0`, `427abef9`, `e568c588`).
  - DoD: `ci-runner/k3s/README.md` and `provision-k3s.sh:587` no longer name either installer as a step.
  - DoD: `git grep -n 'install-arc.sh\|install-kueue.sh\|values-host-unique\|kueue/resources.yaml\|proof-job-kueue' origin/master -- . ':!plan' ':!CHANGELOG.md'` matches only lines that cite the deletion.
  - Closes: §1 rows 5, 6 and 11, S1 and S2.
  - Overlap: none. Retiring `phase2/kueue/cluster-queue-phase1-proof.yaml`, which note 005 calls a "candidate for retirement", is out of scope here. It is class (b) and still applied.
- **W2 — The plan accepts the "used" verdicts for the other nine class (c) rows.**
  - This is a decision, not an item. DoD bullet 1 is met by naming each user, and §1 names them.
  - The one judgement call is rows 1 and 2: they are cited and never executed.
  - Recommendation: count a citation from live code as use, and reclassify both rows as (d). The alternative is to delete them and rewrite about 30 citations.
- **W3 — Retire vps-info's superseded shell copies of the 17 services that have roles.**
  - DoD: for each service with a role in `ansible/dev-host.yml` or `ansible/gates-kubeconfig.yml`, vps-info `origin/master` carries no `install.sh` and no payload the role already ships, and the deleting commit cites its pre-deletion SHA, as fabro-hosts `a933250` did.
  - DoD: two files stay, because their roles run them in place from the checkout:
    - `honeycomb-mcp/honeycomb-mcp.sh` (`host_vars/vps.yml:127`);
    - `honeycomb-trigger-recipients-check/check-trigger-recipients.sh` (`:130`).
  - Closes: the 49 "role, duplicate still committed" rows in §3.3.
  - Overlap: none. The change lands in vps-info, which has no task runner or CI. The epic's DoD does not strictly require it ("installed by a committed role" is already true). It follows the retire-legacy-layers rule that `988285fc` cites.
- **W4 — Decide the vps-info editor stack: role it as held-disabled, or retire it.**
  - DoD, one of:
    - `code-serve-web` and `code-pwa-proxy` are installed by a role in `ansible/dev-host.yml` that keeps both units disabled, and the drift report is clean;
    - their six files are deleted from vps-info with the pre-deletion SHA cited.
  - Needs: the maintainer's ruling that held them "until further notice" (vps-info `6458250`, `AGENTS.md:441-447`) to be lifted or confirmed.
  - Closes: 6 rows in §3.3.
  - Overlap: none.
- **W5a — Every out-of-band precondition in the vps roles is a preflight assert that runs before the role's first change, or is recorded in that role's `HOST_VARS.md` as an accepted post-apply step.**
  - DoD, asserts:
    - `restic_backup` asserts that the six `VPS_RESTIC_*` names resolve;
    - `honeycomb_trigger_recipients_check`'s key check becomes an assert, or the plan records the warning as an accepted exception with its rationale;
    - `honeycomb_mcp:66` moves after its asserts;
    - `gates_kubeconfig` fetches before it installs.
  - DoD, `HOST_VARS.md` "Out-of-band" sections:
    - `onepassword_desktop`: sign-in and auto-lock;
    - `claude_desktop`: sign-in;
    - `restic_backup`: `doctor` and the first backup;
    - `honeycomb_mcp`: re-apply after a plugin update.
  - DoD: `secret_reinjection`'s unseeded-credstore warning (`tasks/main.yml:32-55`) gets the same treatment, which covers `seed-github-app-creds.sh`.
  - Closes: V1, V3, V6 (ordering), V7, V8, V10, and the `seed-github-app-creds.sh` row in §3.2.
  - Overlap: none.
- **W5b — vps's two Fabro instances declare what gmktec's declare.**
  - DoD: `ansible/inventory/host_vars/vps.yml` declares:
    - `tailscale_serve_mappings` for 32276 and 32277, with the role applied to vps;
    - `vault_secrets` naming `GITHUB_APP_PRIVATE_KEY`;
    - a decided `fabro_server_manage_settings`;
    - `otel_dropin: present` or `absent` for `fabro-server`, which needs a ruling.
  - DoD: `just ansible-drift ansible/fabro-hosts.yml` reports zero changes for vps.
  - Closes: F3, F4, F5 and F6.
  - Overlap: none.
- **W6 — The Cloudflare Codex MCP entry is provisioned and asserted.**
  - DoD: a committed role writes `[mcp_servers.cloudflare-api]` into `~/.codex/config.toml` (an extension of `codex_config` is acceptable).
  - DoD: the role asserts that `CLOUDFLARE_MCP_TOKEN` resolves through `with-homelab-env.sh` before writing.
  - Closes: V5.
  - Overlap: none.
- **W7 — Port `check-settings.sh` into an Ansible verification play, and delete fabro-hosts' `hosts/*.env`.**
  - DoD: a committed play compares each instance's resolved settings with `GET /api/v1/settings` against `host_vars`.
  - DoD: `services/fabro-server/hosts/*.env` (now 5 files, including `hp-xubuntu-candidate.env`) and `*.settings.expected` are deleted from fabro-hosts with the pre-deletion SHA cited.
  - Closes: 4 rows in §3.4.
  - Overlap: none. fabro-hosts `AGENTS.md:75-81` calls this "an open decision".
- **W8 — `ci-runner/README.md` attributes the gate-runner tier to the VPS.**
  - DoD: the README's opening paragraph and its privileged-tier bullet name the host the tier is installed on, which is the VPS / shared factory host.
  - Closes: DoD bullet 3.
  - Overlap: **6fl7a4**. If that ruling retires the tier, the sentence goes instead. The fix is independent of the blocked ruling, so it can land now.
- **W9 — A role installs `/etc/rancher/k3s/registries.yaml` on every `ci_pool` node, and `install-registry-mirror.sh` is deleted.**
  - DoD: every `ci_pool` node's `registries.yaml` is rendered from `registries.yaml.template` by a role in `ansible/ci-pool.yml`.
  - DoD: `install-registry-mirror.sh` is deleted with its pre-deletion SHA cited.
  - Closes: §3.1 rows 52 and 53.
  - Overlap: **y1t5**, which the brief calls the "node half". Its cluster half is already on master (§0.4). Also `e2gv6n` (`ready`), whose DoD requires agents to resolve ghcr through the mirror "as that node's `registries.yaml` declares". Fold this into one of those two; do not file it separately. poweredge's file was written by hand on 2026-09-08, per y1t5's description.
- **No new item: the gate-runner tier (13 rows)** stays with **6fl7a4**. It is blocked on orchestrator `bd-ib-te4h`, which was still `backlog` and last updated 2026-10-20 when read.
- **No new item: `u3f6bw` and `y1t5`'s cluster half.** Verify and close them per `.ai/already-satisfied-items.md` (§0.4).
- **No change: `nmrf34`.** Still open on master: `ci-runner/k3s/phase2/k3s-config/config.yaml:109` has `write-kubeconfig-mode: "0644"`.

## 5. What this measurement could not establish

- **Live state.** No host was contacted. "Installed by role" means a
  committed role installs the file when its playbook is applied. Whether the
  roles were applied, and whether the drift reports are clean, is not
  measured. The same goes for:
  - whether vps's Fabro vaults hold `GITHUB_APP_PRIVATE_KEY`;
  - whether vps's `tailscale serve` mappings exist;
  - whether the gate-runner units are still enabled on the VPS.
- **The fabro-hosts "eight".** No archived note lists them (§0.2).
- **`with-homelab-aws.sh` and `/etc/credstore.encrypted/homelab-aws-bootstrap` (V11).**
  - The 2026-09-09 inventory attributes them to a reconcile timer in the `homelab` repo.
  - On `homelab` `origin/main` (`caaa1a3`), `git grep` finds those names only in docs and archive files.
  - I did not trace what installs them now.
- **Re-applying `dev-host.yml` after a Claude plugin update (V7).** I found no
  committed trigger. I did not search every host timer, so "manual" here
  means "no committed automation found in `ansible/`".
- **The comments on `u3f6bw` and `y1t5`.** Not read. Whether each one's
  host-captured AC is satisfied is open.

## 6. Side observations (outside the 2026-09-09 inventory, logged only)

- **New shell host glue has landed in vps-info since 2026-09-09, with no
  role.** None of these names appears anywhere under `ansible/`:
  - `services/claude-config/` (`install.sh`, `install-unattended.sh`);
  - `services/codex-remote/` (a unit and `install.sh`);
  - `services/herdr/` (4 installers);
  - `services/hxi-source-credentials/` (`install.sh` / `install.py`);
  - `services/zsh-config/install.sh`;
  - `services/codex-config/`'s `codex-hook-trust{,-review}.{service,timer}` and three more installers.

  The epic's DoD is pinned to the 005 rows, so this is not in scope. It is
  the same drift the migration existed to end.
- **Inventory changes since 2026-09-09.** hp-xubuntu left `sandbox_hosts` on
  2026-11-02 and is now in `former_sandbox_hosts` and `ci_pool`
  (`inventory/legacy.yml:30,71,80`). gmktec-xubuntu now runs Fabro instances.
  So fabro-hosts rows attributed to hp describe a host role that has since
  been retired.

## 7. Plan-session dispositions (2026-11-05, session ci-pool-provisioning-leftovers)

The sections above are the read-only measurement. This section records what the
plan session decided and did with it the same day.

**Children already satisfied, now closed or narrowed.**

- `u3f6bw` is CLOSED, `resolved-out-of-band`. It was satisfied by `aba1607a`
  (livespec-dev-tooling#2286, first released in v1.90.0), whose message carries
  the byte-identity proof. The one leg the sandbox could not run was the drift
  read. It ran from the control node at `origin/master` `95b7afc1`:
  `just ansible-drift ansible/ci-pool.yml --tags storage_layout --limit
  poweredge-xubuntu,gmktec-xubuntu` gave `changed=0 failed=0` on both nodes.
  (§0.4 read its status as `ready` only because this session had briefly
  unblocked it before finding the merged commit.)
- `y1t5`: its cluster half is proven by a real reboot. poweredge booted
  2026-10-17 15:15:46Z on the tmpfs datastore, and `deploy/registry-mirror` was
  recreated at 15:17:53Z with no manual step. The mirror served 228 containerd
  `?ns=ghcr.io` requests in the 24h to 2026-11-05 07:25Z. Its node half is
  W9 below. It is CARRIED BY `livespec-dev-tooling-e2gv6n` (plan
  ci-cache-optimization), as agreed with that seat at about 07:50Z: one
  `ci-pool.yml` role for every `ci_pool` node, server included, that never
  restarts k3s. The edge `e2gv6n blocks y1t5` is recorded. y1t5 closes when that
  role reads drift-clean on poweredge, whose `registries.yaml` is still the
  hand-written file from 2026-09-08. Live facts: gmktec has no
  `registries.yaml` and reaches `http://192.168.1.200:5001/v2/` (200). hp was
  unreachable over ssh.

**Decisions.**

- **W2: citation counts as use.** Rows 1 and 2 (`VALIDATION_CHECKLIST.md`,
  `gate-credentials.yaml`) are kept as (d) documentation. Each is cited by live
  code or by a test as the record or declaration it is, and deleting them would
  orphan about 30 citations for no gain. With §1's named users, DoD bullet 1 is
  met for the nine non-dead (c) rows. Bullet 1 then rests only on W1.
- **W3 (parked, not filed).** vps-info's committed shell copies of services
  that now have roles do not fail any DoD bullet, because the class (a) bullet
  is met once a role installs the artifact. Retiring them is housekeeping in
  another repository with no task runner or CI. It is recorded as a PARKING LOT
  comment on the epic, together with §6's new role-less vps-info glue.
- **W4: the editor stack becomes a role that installs it held disabled.** This
  preserves the maintainer's "until further notice" hold exactly, with no fresh
  ruling, and puts the six files under drift control.
- **W5b: vps declares what gmktec declares** (settings management, vault
  secrets, tailscale serve mappings, `otel_dropin: present`). The exception is a
  declaration that the pre-apply drift read shows would change a live value:
  that value is declared as it is.
- **W6 is folded into W5a.** Both are dev-host out-of-band preconditions.
- **W7: port `check-settings.sh` into the `fabro_server` drift report,** and
  delete the fabro-hosts copies.
- **W8 is done in the PR that lands this note.** `ci-runner/README.md` now
  attributes the gating tier to the `ci_pool` nodes and the privileged gate
  tier to the VPS, where `gate-runner-supervisor.service` and
  `gate-optin-expiry.timer` were read enabled on 2026-11-05. That discharges
  DoD bullet 3.

**Filed children** (all under epic `livespec-dev-tooling-fby3sx`):

| Proposal | Item | Title |
|---|---|---|
| W1 | `livespec-dev-tooling-y4umcc` (ready) | Delete the dead phase-1 by-hand ARC and Kueue install set |
| W4 | `livespec-dev-tooling-fmbnyd` (pending-approval) | VPS editor stack installed by a dev-host role, held disabled |
| W5a (+W6) | `livespec-dev-tooling-c763up` (pending-approval, spec-change tier) | Every VPS dev-host out-of-band precondition is a preflight assert or a recorded post-apply step |
| W5b | `livespec-dev-tooling-jxw2ve` (ready) | VPS Fabro instances declare what gmktec's declare |
| W7 | `livespec-dev-tooling-po2nrg` (pending-approval, spec-change tier) | Port `check-settings.sh` into an Ansible verification |

**Still owed outside this plan.** `6fl7a4` waits on orchestrator `bd-ib-te4h`,
which has no parent plan and has been in backlog since 2026-08-05. Its 13
gate-runner rows stay with `6fl7a4`. `nmrf34` is unchanged.

The three `pending-approval` children are held by their filing-time judgement,
not by a DoD finding. `c763up` and `po2nrg` were classed spec-change tier. The
ratified text does not state the behaviour they deliver: preflight asserts and
recorded post-apply steps for dev-host roles under §"Host provisioning tree",
and settings comparison in the `fabro-hosts.yml` drift report under §"Fabro
factory host provisioning". `fmbnyd`'s governing heading is "unstated", and
the classifier picked §"Host provisioning tree" as its generalization target.
The plan's next step is therefore a propose-change that states those clauses,
followed by its revise.
