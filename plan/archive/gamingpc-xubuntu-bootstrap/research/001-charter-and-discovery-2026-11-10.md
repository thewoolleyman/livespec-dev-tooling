## The maintainer's statement of what done means

I want to bootstrap my gaming PC running Xubuntu and create its host-information repository, `thewoolleyman/gamingpc-xubuntu-info`, following the same current conventions and workflow used for my other `*-xubuntu-info` repositories, especially the recent `gmktec-xubuntu-info` bootstrap.

## Definition of Done assertions derived from that statement

- The private thewoolleyman/gamingpc-xubuntu-info repository is clonable and records measured hardware, storage, operating system, networking, GPU, access and service facts with dated evidence and explicit unknowns.
- The gaming PC preserves its existing operating systems and data, and every irreversible disk operation has prior maintainer approval naming the measured disk, layout, proposed changes and consequences.
- The gaming PC receives the applicable shared baseline bootstrap through its authoritative provisioning repositories, with host-specific inputs derived from live measurements and no copied service implementations.
- The gaming PC boots and is reachable through the approved fleet access path, and each service provisioned by this plan operates as intended on the real host.
- The host-information repository uses the current instruction-only livespec adopter conventions and completed changes are pushed through the owning repository workflow.
- The homelab-k8s-worker-nodes track can resume worker enrollment from committed host facts, access instructions, validation evidence and explicit unresolved prerequisites without this bootstrap assigning CI or factory roles.

# Scope, sources and discovery

Maintainer requested a baseline Xubuntu host bootstrap and private host-information repository, followed by a handoff to the existing homelab-k8s-worker-nodes session for cluster worker setup. Creation of this plan and repository is explicitly requested. Derived assertions were presented in the bootstrap session; no new workload role is inferred.

## Current measured discovery

2026-11-10, executing on the Pro: Tailscale self is chads-macbook-pro; hostname macbook.local, LocalHostName macbook, HostName unset. GitHub API authenticates as thewoolleyman. Requested gamingpc-xubuntu-info did not resolve before creation. Current local tailnet netmap contains no gaming-PC identity; aperture is documented as an AWS application host, not evidence of the gaming PC. No gaming PC record was found in checked provisioning inventory, SSH config, or local host records. The maintainer has been asked for its current identity/access and whether it is powered on in Xubuntu. Hardware, account, installed OS, firmware boot mode, disk layout, persistent identifiers, network and GPU remain UNKNOWN. Purchase history is not a provisioning input.

The session is outside Herdr (HERDR_ENV unset). The installed herdr skill prohibits pane control in that context. Existing local and VPS sessions are preserved; no restart or new session was attempted. The worker-node epic livespec-dev-tooling-ko26ez exists, is open, and currently covers the M4 Max worker and production-load proof; gaming PC admission is not inferred from that existing scope.

## Current reference workflow

GMKtec host record read from GitHub main 01687f7fbb83c1b712653daaaf2402ec93214749 (local checkout was five commits behind). Its instruction-only adoption is commit a13b361. HP master and PowerEdge main AGENTS and service references were compared. Host-info repositories carry measured facts and references; shared services remain in livespec-dev-tooling, fabro-hosts, otel-collector, local-llm and tailscale-admin as applicable. Do not adopt a service merely because a peer runs it.

The GMKtec phase0 profile in livespec-dev-tooling preserves its running root and ESP, uses DISK_PLAN=free-space and explicitly skips base-OS installation. Its historical host note saying built from bare metal is not proof of a fresh desktop install. Existing live plan fleet-bare-metal-rebuild-proof (epic livespec-dev-tooling-jqbc3t) records this gap; do not claim it solved. Current ansible/ci-pool.yml provisions cluster roles and is NOT a general Xubuntu desktop bootstrap. Do not run it against an unmeasured or undeclared machine.

Livespec core manifest defines instruction-only adopters without a local .livespec.jsonc, toolchain, tenant or spec tree. GMKtec, HP and PowerEdge enable core plus Claude driver at release and the stdlib settings-derived ensure_plugins.py SessionStart hook. Codex core/driver are host-wide, independently verified on the Pro; that does not prove installation on the gaming PC. Registration comes LAST, only after the new repo is clonable and its plugin currency wiring is ready. Core owns the manifest; no manifest is duplicated here.

Tailscale policy is owned by tailscale-admin/policy.hujson. Current instructions require persistent untagged members and interactive human enrollment when enrollment is needed. Never mint a tagged OAuth key, alter policy, disable SSH access, or copy another host's credentials as an enrollment shortcut.

## Ordered dependencies and acceptance approach

1. Resolve an approved management endpoint and operator account from current evidence or the maintainer. Inspect reachability before changing access. If local console or interactive enrollment is necessary, prepare the exact action and record that human gate.
2. Read-only target survey: hostnamectl, id/getent, os-release and desktop packages; CPU/RAM/model without hardware UUIDs; UEFI/legacy and Secure Boot; lsblk with paths, type, size, filesystem, mounts, UUID/PARTUUID; persistent disk links retained in private local evidence and sanitized references in Git; partition-table/free-space reads; mount/fstab; interface names/routes/DNS; PCI GPU and bound driver; active/enabled/failed services. Do not dump environments or credentials. Verify disk identity privately before any future write.
3. If Xubuntu exists, preserve it and identify only missing baseline capabilities. If it does not, prepare a separate installation proposal naming exact media, target disk, all existing partitions and losses, bootloader consequences and recovery; require explicit approval before any disk mutation. The GMKtec base-OS stage is not a fresh Xubuntu desktop installer.
4. Route reusable gaps as scoped children in the owning governed repository after the plan carrier-map event; follow factory dispatch/review/release rules there. Host-captured installation and data collection use released committed provisioning sources, scoped dry-runs/check mode, backups and readback. Never hand-copy shared units into the host repo. Establish any additional role before its inventory/host_vars are authored.
5. Verify connectivity, installed OS/desktop, GPU driver, filesystems and preserved data, networking and every applied service on the actual target. Record future-login/reboot or physical checks as pending until observed; coordinate disruptive reboot with existing users/jobs and rollback readiness.
6. Push host facts and references. Complete the instruction-only plugin wiring and last-step core manifest registration through core's own workflow; conformance validates the selected adopter profile. Capture plan-level proof, commission independent completeness review and replay through the plan primitives, and archive only when the plan assertions are proved.
7. Handoff worker prerequisites to homelab-k8s-worker-nodes (livespec-dev-tooling-ko26ez), recording the exact host identity, access, resources, preserved disks, validation, remaining risks and accepted ownership. Worker enrollment, workload classes and capacity are that track's subsequent scope, not implicit permissions here.

## Explicit deferrals

Worker installation/enrollment and any Kubernetes, CI, factory, inference or model-server role are deferred to their named owning track after baseline handoff. No hardware capacity or disk profile is chosen until measured. No destructive operation or security-policy change is authorized by the bootstrap request alone. No claim of machine readiness can be made before a real target inspection.
