# Classification of plans outside livespec-dev-tooling and livespec-orchestrator-beads-fabro

Taken 2026-11-13. Sources: `inventory.json`, each plan's charter, open-child titles, and a few `bd show` reads.
Caveat on dates: almost every epic in the livespec and livespec-overseer tenants shows `updated 2026-11-12`. That looks like a bulk touch, not activity, so dormancy below is judged from `last_session` and the next_action text.
Overlaps with plans in the two out-of-scope repositories are named from their slugs and titles only; I did not read those plans.

# Ledger read failures

**hetzner-xubuntu-info: read now works (43 records).**
- Exact error: `Error: failed to open database: failed to check if database "hetzner-xubuntu-info" exists on server 127.0.0.1:3307: Error 1045 (28000): Access denied for user 'hetzner-xubuntu-info'`
- Cause: this tenant's password is not in the fleet wrapper. `.livespec.jsonc` declares its own `credential_wrapper`: `["./with-hetzner-xubuntu-credentials.sh", "--"]` (a scoped AWS launcher). `.beads/config.yaml` is correct (port 3307, user and database `hetzner-xubuntu-info`).
- Read-only path that works: `cd ~/workspace/hetzner-xubuntu-info && ./with-hetzner-xubuntu-credentials.sh -- bd list --status all --limit 0 --json`. Output saved to `rd-hxi.json` in the scratchpad.

**homelab: ledger unread.**
- Exact error: `Error: failed to open database: Dolt server unreachable at 127.0.0.1:0: dial tcp 127.0.0.1:0: connect: connection refused` then `Dolt server auto-start is disabled (dolt.auto-start: false).`
- Cause 1 (port): `.beads/config.yaml` does carry `dolt.server-port: 3307`, but the gitignored `.beads/metadata.json` has no `dolt_server_port` and there is no `.beads/dolt-server.port` file, so `bd` resolves port 0. Setting `BEADS_DOLT_SERVER_PORT=3307` for the one call gets past it and mutates nothing.
- Cause 2 (credential): with the port fixed the answer is `Error 1045 (28000): Access denied for user 'homelab'`. The repo's `credential_wrapper` is `/usr/local/bin/with-homelab-aws.sh --role homelab-workload /home/ubuntu/.nix-profile/bin/hl param run --bind BEADS_DOLT_PASSWORD=...`. Neither `with-homelab-aws.sh` nor `hl` is installed on this host. No read-only path exists here; plans below are classified from disk.

**openbrain: ledger unread.**
- Exact error: `Warning: dolt_server_port in metadata.json is deprecated (can cause cross-project data leakage). The port file (.beads/dolt-server.port) is now the primary source.` then `Error: failed to open database: failed to check if database "openbrain" exists on server 127.0.0.1:3307: Error 1045 (28000): Access denied for user 'openbrain'`
- Cause: the deprecation warning is noise; the failure is the 1045. openbrain is an independent tenant whose `credential_wrapper` is `/data/projects/1password-env-wrapper/with-openbrain-env.sh`. `/data/projects` does not exist on this host, and the in-repo `scripts/with-openbrain-env.sh` reports `installed wrapper not found at /usr/local/bin/with-openbrain-env.sh`. No read-only path exists here; plans below are classified from disk.

Side finding: three livespec plans (`github-request-budget-discipline`, `livespec-ci-on-hetzner`, `shipped-hook-seam-hardening`) have `associated_work_item_id = unassigned` on disk, so the inventory shows them empty. Each has a real ledger epic named in `epic.md` or its handoff (`livespec-httc`, `livespec-h22nve`, `livespec-hvtc`). I read those epics directly.

## livespec-overseer/caam-generic-limit-windows (overseer-rumvpf)
- items: X (an account whose limits cannot be read cannot be rotated to) — carrier `overseer-j5elif` "caam usage: record and show unrecognised limits without making the account unreadable" (acceptance).
- relevance: PARTIAL (weak; credential-rotation hygiene).
- state: epic backlog; na=impl, await j5elif closing through a merged PR then dispatch o9fn; 2/7 open; last session 2026-11-01, budget deadline 2026-11-07 passed. DORMANT.
- unrelated_open_children: 1 — `overseer-o9fn` (refactor under 200 LLOC).
- overlaps: livespec-overseer/caam-quota-resets, central-credential-service.

## livespec-overseer/caam-quota-resets (overseer-pv53ri)
- items: X (quota outages) — carriers `overseer-zelcaq` (reset reading and display, active), `overseer-34f6c6` (reset claim decision), `overseer-fecnyt` (claim transport and settlement), `overseer-gzjv4s` (rotation thresholds named each pass). The spend-side child `overseer-sozqxs` is parented under herdr-overseer.
- relevance: CORE for X (quota availability), no other item.
- state: epic backlog; na=await, three slices zelcaq → 34f6c6 → fecnyt, then sozqxs and a live claim proof; 5/7 open; last session 2026-11-13. LIVE.
- unrelated_open_children: 1 — `overseer-fr3hnj` (QUOTA RESETS table column and alignment).
- overlaps: livespec-overseer/herdr-overseer (holds `overseer-sozqxs`); orchestrator `anthropic-burn-mitigation` by slug.

## livespec-overseer/central-credential-service (overseer-iyfjbo)
- items: X (credential outages on factory hosts) — carriers `overseer-3evlnu` "factory runs on homelab and hetzner-xubuntu choose among per-account setup-token slots", `overseer-iyfjbo.1` "Fabro dev tokens: one stored copy per instance", `overseer-r7pymu` (host not shown stale between deliveries), `overseer-ceehcd` (host ahead of delivery sequence), `overseer-v6ppfr` (caam v0.1.25 on the role holder).
- relevance: CORE for X, no other item.
- state: epic backlog; na=human, merge overseer#3008 and close r7pymu, then #2992 and #3012; 8/26 open; last session 2026-11-13. LIVE (na kind is human but the seat is working).
- unrelated_open_children: 3 — `overseer-fdwat6` and `overseer-2h5xpe` (Remote Control re-issue, interactive sessions), `overseer-cwnedl` (retire a stale 1Password token copy).
- overlaps: livespec-overseer/llm-provider-manager; hetzner-xubuntu-info `hxi-b77rdt`; orchestrator `fabro-token-refresh`, `llm-provider-manager-consumer` by slug.

## livespec-overseer/codex-managed-daemon-session-discovery (overseer-62ccfq)
- items: none. relevance: NONE.
- state: epic backlog; na=human (choose a thread-id source); 1/1 open; last session 2026-10. DORMANT.

## livespec-overseer/fleet-plumbing-and-dispatch-reliability (overseer-cajdwp)
- items:
  - X — `overseer-cajdwp.10` "STOP-THE-LINE (factory path): unpinned callers refused since the App gained a second installation" (blocked, P1); `overseer-jj44d4` "post-merge disposition journals ledger-complete ... while the ledger transition never lands, leaving items ACTIVE over merged work"; `overseer-1hv` "Dispatcher killed by its caller leaves a phantom claim"; `overseer-7v5a73` "Every fabro sandbox leaks ~60 zombies/minute" (also touches N2 node pressure).
  - M1 — `overseer-fs4` "nothing consumes fabro's failure category, so a spend-limit failure burns a host dispatch cap slot per retry" (blocked). It is the consumer side of the failure category that bd-ib-2h6cfl must populate.
  - Y1 — `overseer-cajdwp.12` "A work-item can assert dispatch-safety and a factory tier while naming NO repository" (sibling-repo work dispatched against the wrong repo).
- relevance: PARTIAL (half the open children are X-shaped dispatch defects; the rest is docs and ledger audit).
- state: epic backlog; na=none ("Record this plan's next action; the migration found none"); 12/51 open; last session 2026-09-06 (migration). DORMANT.
- unrelated_open_children: 6 — `overseer-cajdwp.11`, `overseer-cajdwp.7`, `overseer-n77r`, `overseer-thk0`, `overseer-iwu` (also `overseer-vfz5v5`).
- overlaps: orchestrator `run-lifecycle-false-verdicts`, `factory-idle-with-ready-work`, `dispatch-retry-discipline`, `runaway-process-containment` by slug; M1 owner bd-ib-2h6cfl.

## livespec-overseer/herdr-overseer (overseer-uzvcbn)
- items:
  - X — `overseer-sozqxs` "caam: spend quota resets at the best-value moment" (ready).
  - N3 — `overseer-uzvcbn.23` "Hold a seat replacement while the host is below its memory floor" (ready); `overseer-5y7ebe` "Supervise seats on a saved remote herdr machine (hetzner-xubuntu first)" (blocked).
- relevance: PARTIAL (plan is about herdr/tmux pane supervision).
- state: epic backlog; na=await, merges of overseer#3014 and #3010 and a re-grade of #3013; 14/79 open; last session 2026-11-13. LIVE.
- unrelated_open_children: 11 — `overseer-llrj5k`, `overseer-i4cylq`, `overseer-uzvcbn.12`, `overseer-uzvcbn.10`, `overseer-lhjjqm`.
- overlaps: caam-quota-resets (sozqxs); hetzner-xubuntu-info bootstrap plan and dev-tooling `dev-host-test-gate-load` (N3).

## livespec-overseer/llm-provider-manager (overseer-tm2qtw)
- items: X (credential replacement without an outage) — carriers `overseer-p6pod4` "complete factory coexistence proof and record cutover disposition" (blocked), `overseer-v3tutb` (acquisition worker launcher).
- relevance: PARTIAL (weak).
- state: epic backlog; na=impl, re-arm a launcher for overseer-v3tutb on hp; 3/23 open; last session 2026-10-19, deadline 2026-10-21 passed. DORMANT.
- unrelated_open_children: 1 — `overseer-psqcmg` (headed browser acquisition).
- overlaps: central-credential-service; orchestrator `llm-provider-manager-consumer`; livespec `fleet-delivery-lane-visibility` next_action waits on it.

## livespec-overseer/overseer-validated-state-command (overseer-kwkx74)
- items: none. relevance: NONE.
- state: epic backlog; na=impl, await lift of the gmktec dispatch hold for overseer-ryc6sh; 3/3 open; last session 2026-11-01. DORMANT.

## livespec-overseer/remove-supervisor-skill (overseer-hnjolu)
- items: none. relevance: NONE.
- state: epic backlog; na=human; 0/0 children; last session 2026-10-10. DORMANT.

## livespec-overseer/repo-gates-and-test-integrity (overseer-4z97)
- items: none carried by an open child. The opening research lists two relevant rows, `overseer-tdfe.22` (nothing tests the merged tree; C1's "one full run guarding master") and `overseer-jdo` (flaky aggregate under concurrency; X), but neither is among the 12 open children.
- relevance: NONE (open work is gate-integrity defects: unverified owner markers, LLOC escape hatch, coverage sweeps).
- state: epic backlog; na=impl, dispatch overseer-csl2 on hp; 12/27 open; last session 2026-10-20, deadline 2026-10-21 passed. DORMANT.
- overlaps: dev-tooling `rop-railway-enforcement` (via `overseer-bjrm`).

## livespec-overseer/session-obligation-recovery (overseer-527by2)
- items: X (a failed gate or dispatch nobody is watching stalls work) — carrier `overseer-okf6bu` "Consume durable session obligations and execute safe bounded recovery after coordinator exit" (ready).
- relevance: PARTIAL (weak; single child).
- state: epic backlog; na=human, hold all dispatch until the 2026-10-14 factory stability freeze is lifted; 1/1 open; last session 2026-10-14. DORMANT.
- unrelated_open_children: 0.
- overlaps: orchestrator `agent-session-stall-prevention` and `relay-delivery-and-progress-deadline` (the charter names both as owners of the other halves).

## livespec-overseer/session-start-and-registry-integrity (overseer-zidpiu)
- items: none. relevance: NONE.
- state: epic backlog; na=human, ratify a watch-set proposal after overseer#2098; 2/7 open; last session 2026-09-12. DORMANT.

## livespec/citation-contract (livespec-3u5eok)
- items: none. relevance: NONE.
- state: epic backlog; na=human, PARKED by the maintainer; 2/2 open; last session 2026-09-12. DORMANT.

## livespec/create-agent-cockpit-repo (livespec-livyxu)
- items: none. relevance: NONE (13 pointer children to agent-cockpit-info issues).
- state: epic backlog; na=human, author a Definition of Done and schedule a poweredge reboot test; 13/27 open; last session 2026-10-10. DORMANT.

## livespec/fleet-delivery-lane-visibility (livespec-n33rwg)
- items: X — `livespec-n33rwg.10` "Acceptance written in an item's description is silently ungradeable: every child of this epic was undispatchable"; `livespec-n33rwg.3` "e2e-real weekly real-API lane: 14 consecutive failures" (a red lane, awaiting a second green).
- relevance: PARTIAL (weak). The plan is about merged-not-deployed release lanes, which delays fixes reaching the factory but does not gate PR merges.
- state: epic backlog; na=none, wait for llm-provider-manager to merge then dispatch bd-ib-4zdihj; 4/10 open; last session 2026-10-10. DORMANT.
- unrelated_open_children: 2 — `livespec-n33rwg.9` (Honeycomb trigger cannot represent a standing condition), `livespec-n33rwg.5` (release-lane watcher fleet-wide).
- overlaps: dev-tooling `red-master-self-healing`, `fleet-flaky-tests` by slug. Note: its "reader" enumerates every workflow per repo, which is a REST polling cost under G1.

## livespec/github-request-budget-discipline (livespec-httc; plan file says `unassigned`)
- items: G1 — carriers `livespec-j49m` "the livespec-pr-bot App installation's 5000/hr core budget is a finite SHARED resource across all 9 fleet repos — exhaustible, unattributed" (backlog, P1) and `livespec-umy2` "Retrofit: route core's direct GitHub calls through the budgeted client" (backlog). The handoff names three more retrofit items in other tenants (runtime, dev-tooling, orchestrator; 27 call sites in all) and the verifier `livespec-dev-tooling-t2q4`; I did not read those.
- relevance: CORE (G1). This is the design owner: ratified contract (spec v195), guard hook shipped in livespec-driver-claude v0.5.0, budgeted client merged in livespec-runtime with ZERO production callers.
- state: epic backlog; no next_action on the epic (plan never migrated: `associated_work_item_id` is `unassigned`, slug in metadata is a title-derived string); 2/2 open; last handoff entry 2026-08-14, last working reading 2026-08-08. DORMANT.
- unrelated_open_children: 0.
- overlaps: livespec-driver-claude/github-rate-limit-guard-false-positives (the Installer slot's guard); orchestrator `dispatcher-run-watch-cost` by slug (run-watch polling).

## livespec/gitops-deployment-instructions-and-enforcement (livespec-okypgg)
- items: none. relevance: NONE.
- state: epic backlog; na=human, re-arm a seat launcher for three items; 4/6 open; last session 2026-10-19. DORMANT.

## livespec/livespec-ci-on-hetzner (livespec-h22nve; plan file says `unassigned`)
- items: N2 (new CI capacity) — carriers `livespec-3on57g` "Adopt the dedicated Hetzner runner label and its liveness/freshness observation", `livespec-7wvyo7` "Live one-job exercise: prove a required gate ran on server 3039451", `livespec-q7sfu6` "Prove the hosted fallback unblocks the same required gate" (all pending-approval).
- relevance: CORE by charter (N2), but probably SUPERSEDED: hetzner-xubuntu-info research note 002 says the Hetzner machine is now an interactive workstation, "the previous reservation as a Kubernetes node is superseded", and it does not become a CI runner. The fleet's CI has since moved to k3s scale sets.
- state: epic active (held active on purpose to stop a re-groom); no next_action; 3/3 open; last reading in the handoff 2026-08-11 (thirteenth "gate shut" reading). DORMANT; candidate for close-as-superseded.
- unrelated_open_children: 0.
- overlaps: hetzner-xubuntu-info/bootstrap-credentials-and-onboarding (same machine, opposite use); dev-tooling `homelab-k8s-worker-nodes`, `ci-pool-provisioning-leftovers` by slug.

## livespec/rop-railway-enforcement (livespec-yodsfx)
- items: none. relevance: NONE.
- state: epic backlog; no next_action; 0/0 children. DORMANT (standing "do not arm" constraint).
- overlaps: same-slug plans in dev-tooling, git-jsonl, runtime.

## livespec/shipped-hook-seam-hardening (livespec-hvtc; plan file says `unassigned`)
- items: none now. Its Y5-adjacent child `livespec-dev-tooling-kfp` (RGR gate could never complete a Green amend in driver-claude) was CLOSED as landed 2026-09-07.
- relevance: NONE.
- state: epic backlog; no next_action; 0 children by edge; remaining work is `livespec-driver-claude-c90` (backlog, untouched since 2026-07-19). DORMANT.

## livespec-console-beads-fabro/optimize-console-builds (livespec-console-beads-fabro-gqmtwa)
- items (console builds only):
  - C4 — charter-only (the build-time work landed; no open child shortens a build).
  - M2 — `livespec-console-beads-fabro-gqmtwa.5` "run-level span for a factory dispatch (no factory per-run wall time)" (blocked on orchestrator bd-ib-cp2x); `...-u6sx` "factory prepare.* spans stopped landing"; `...-opdv` "sccache.hit_ratio ships as 0 on every factory span".
  - M4 — `...-gqmtwa.6` "derive ci.run-span ci.conclusion from job conclusions" (merged, awaiting Honeycomb evidence); `...-p5ci` "CI setup-step timing is not exported".
- relevance: CORE (build cycle time and its telemetry, for one repo).
- state: epic backlog; na=impl, re-auth Honeycomb then close gqmtwa.6, then p5ci; 6/35 open; last update 2026-10-10. DORMANT.
- unrelated_open_children: 1 — `...-fse7` (cache size and eviction bounds unobserved).
- overlaps: dev-tooling `console-factory-build-telemetry`, `console-factory-build-cache`, `ci-cache-optimization`; orchestrator `factory-run-correlation-observability` by slug.

## livespec-console-beads-fabro/retire-overseer-and-redesign-control-plane-around-console (livespec-console-beads-fabro-pzbdbo)
- items: none. relevance: NONE (three open children are BLOCKED-ON pointers to orchestrator items).
- state: epic backlog; na=impl, dispatch zzs2ig; 5/53 open; last update 2026-10-10. DORMANT.

## livespec-console-beads-fabro/tui-ux-improvements (livespec-console-beads-fabro-mx9u)
- items: none. relevance: NONE.
- state: epic backlog; na=impl; 3/36 open; last update 2026-09-08. DORMANT.

## livespec-driver-claude/github-rate-limit-guard-false-positives (livespec-driver-claude-mbg4zg)
- items: G1 — `livespec-driver-claude-32a` "a sleep FIRST in a loop body, or behind a command prefix, escapes the polling deny" (blocked, P0; a real polling loop passes the guard); `livespec-driver-claude-4bl` "Decide the bounded-loop budget: nested loops, multi-call bodies and --paginate exceed the threshold's own arithmetic"; `livespec-driver-claude-e5w` "telemetry: span attributes are stripped downstream, so the false-positive-rate query cannot run"; `livespec-driver-claude-3hk` (correct the 40.5% baseline).
- relevance: CORE (G1, the agent-side polling guard).
- state: epic backlog; na=human, commission a fresh completeness reviewer; 4/11 open; last session 2026-09-06, children untouched since 2026-08-26. DORMANT.
- unrelated_open_children: 0.
- overlaps: livespec/github-request-budget-discipline (same concern, contract owner); orchestrator `dispatcher-run-watch-cost` by slug. The guard covers Claude sessions only; the title's "port fleet-wide" (Codex) is not carried by an open child.

## livespec-driver-claude/resolve-core-root-predicate (livespec-driver-claude-cezqks)
- items: none. relevance: NONE.
- state: epic backlog; na=human; 1/4 open; last session 2026-09-06. DORMANT.

## livespec-driver-claude/work-item-state-machine (unassigned)
- items: none. relevance: NONE. state: no epic, one migration record on disk. DORMANT.

## livespec-driver-codex/work-item-state-machine (unassigned)
- items: none. relevance: NONE. state: no epic, no research files. DORMANT.

## livespec-driver-pi/full-pi-skills-support (livespec-driver-pi-6aeive)
- items: none. relevance: NONE.
- state: epic backlog; na=human, record a scope event and file children; 0/1 open; last session 2026-09-06. DORMANT.

## livespec-orchestrator-git-jsonl/make-git-jsonl-real (unassigned)
- items: none. relevance: NONE. state: no epic; one design note. DORMANT.

## livespec-orchestrator-git-jsonl/rop-railway-enforcement (bd-gj-b5fgoh)
- items: none. relevance: NONE. state: epic backlog; no next_action; 0/0; updated 2026-09-12. DORMANT.

## livespec-orchestrator-git-jsonl/work-item-state-machine (unassigned)
- items: none. relevance: NONE. state: no epic; three research notes. DORMANT.

## livespec-runtime/rop-railway-enforcement (livespec-runtime-fmbchu)
- items: none. relevance: NONE. state: epic backlog; no next_action; 0/0; updated 2026-09-12. DORMANT.

## dolt-server/honeycomb-observability-wiring (dolt-server-bvfyyu)
- items: none (it instruments the ci-writer filing path, not factory or gate metrics). relevance: NONE.
- state: epic backlog; na=human, maintainer decides scope routing and provisions a Honeycomb key; 0/0 children; last session 2026-09-09. DORMANT.

## hetzner-xubuntu-info/bootstrap-credentials-and-onboarding (hxi-vxsmdv)
Read through the repo's own wrapper (see Part 1); not in `inventory.json`.
- items:
  - N3 (move sessions, dispatcher and coordinator off the VPS) — `hxi-tyzxmh` "Migrate the coordinator and dispatcher seats to hetzner-xubuntu" (ready); `hxi-jhyvzd` "Shut down the coordinator and dispatcher sessions on the VPS"; `hxi-mkxqnt` "Drive the fleet from hetzner-xubuntu for seven consecutive days"; `hxi-3euehs` "Give hetzner-xubuntu the factory client the dispatcher seat launches runs with" (backlog); `hxi-gdrf4b` "Provision reconcile-runs on hetzner-xubuntu"; `hxi-wx53tb` (seat message channel to the vps); `hxi-4tnpwd` and `hxi-nrc4vv` (seat repo paths and checkouts); `hxi-xwhhtn` "Install a committed load guard ... every hetzner seat runs before heavy steps"; `hxi-bcaedi` "Apply livespec-dev-tooling's dev_host_memory_bounds to hetzner-xubuntu".
  - X (credentials) — `hxi-b77rdt` "Convert hetzner-xubuntu's interactive Claude sessions to the central credential push" (ready).
  - Y1 (host-proved lever) — `hxi-up5dud` "Keep the agent-session identity through hetzner-xubuntu's credential launcher so independent host replays can ..." (blocked).
- relevance: CORE for N3 (the epic's next_action reads "Move load off the vps"), though the plan slug and most children are host bootstrap.
- state: epic backlog; na=human (ref hxi-tyzxmh), finish seat-path repoint and orchestrator adopt, dog-food this plan's session on hetzner, then other seats, dispatcher, coordinator; 30/39 open (23 pending-approval, 4 blocked); last session 2026-11-13. LIVE.
- unrelated_open_children: 18 — `hxi-q3v2xk` (boot from either NVMe), `hxi-23pnf6` (firewall), `hxi-6cb6fb` (patch policy), `hxi-hiyqoq` (Arq restore proof), `hxi-jdhnk6` (backup secret policy).
- overlaps: dev-tooling `dev-host-test-gate-load` and `dev-host-disk-retention` (N3 on the VPS itself); livespec-overseer `overseer-5y7ebe`; livespec/livespec-ci-on-hetzner (same machine, superseded use).

## homelab/steady-state-loop-hardening (hl-nkuzaz per the plan file; LEDGER UNREAD)
- items: X — charter-only. The fix matrix covers a merged-green item routed back to `active` where no selector reads it, ready work idle for 26 hours, and a wrongly assumed full WIP slot. Research note 013 says the epic in the plan file (`hl-nkuzaz`) is closed and superseded by `hl-eufbpx`, and that fixes land upstream in the orchestrator and overseer, not here.
- relevance: PARTIAL (for homelab's own loop only).
- state: ledger unread; plan directory last committed 2026-09-06; anchor file names a superseded epic. DORMANT on the evidence available.
- overlaps: orchestrator `factory-idle-with-ready-work`, `run-lifecycle-false-verdicts` by slug; livespec-overseer/fleet-plumbing-and-dispatch-reliability (`overseer-jj44d4` is the same defect shape).

## homelab/change-safety-durability-and-out-of-band-assurance (hl-xowq4q; LEDGER UNREAD)
- items: none (charter: single-owner checks, restore drills, secret scanning). relevance: NONE. state: plan directory last committed 2026-09-06. DORMANT.

## homelab/fleet-substrate-boot-identity-and-network (hl-sft3pq; LEDGER UNREAD)
- items: none (Talos disk identity, site gateway, taints for the homelab cluster itself; it adds no CI or factory capacity). relevance: NONE. state: last committed 2026-09-06. DORMANT.

## homelab/phase-1-cost-account-and-identity-guardrails (hl-et4oae; LEDGER UNREAD)
- items: none. relevance: NONE. state: last committed 2026-09-06. DORMANT.

## homelab/shared-gitops-credential-bootstrap (hl-awyeat; LEDGER UNREAD)
- items: none directly (it supplies the AWS account that hetzner-xubuntu's credential launcher reads). relevance: NONE. state: last committed 2026-11-01; related homelab credential work merged 2026-11-10 to 11-13.
- overlaps: hetzner-xubuntu-info bootstrap plan (its client).

## openbrain/agent-memory-subsystem (README names ob-38cn; anchor file `unassigned`; LEDGER UNREAD)
- items: none. relevance: NONE. state: README says PARKED. DORMANT.

## openbrain/local-memory-archive (unassigned; LEDGER UNREAD)
- items: none. relevance: NONE. state: a reference archive of 47 snapshot files, not a work plan. DORMANT.

## Cross-plan duplicates and overlaps

1. **G1 has two plans and neither is moving.** livespec/github-request-budget-discipline (`livespec-httc`: contract, shared-budget item `livespec-j49m`, retrofit `livespec-umy2`) and livespec-driver-claude/github-rate-limit-guard-false-positives (`livespec-driver-claude-mbg4zg`: the guard's polling escape `-32a`). Both dormant since August/September. The budgeted client has zero production callers and the guard has a known polling escape, which matches the report's exhaustion. Orchestrator `dispatcher-run-watch-cost` looks like a third owner (by slug).
2. **Credential and quota availability (X) is spread over four overseer plans**: caam-quota-resets, caam-generic-limit-windows, central-credential-service, llm-provider-manager; plus `overseer-sozqxs` (quota spend) parented under herdr-overseer rather than caam-quota-resets, and `hxi-b77rdt` in hetzner-xubuntu-info. Orchestrator `anthropic-burn-mitigation`, `fabro-token-refresh`, `llm-provider-manager-consumer` appear to hold the consumer side.
3. **The Hetzner machine has two contradictory plans.** livespec/livespec-ci-on-hetzner (`livespec-h22nve`, CI runner, 3 children pending-approval, last worked 2026-08-11) versus hetzner-xubuntu-info/bootstrap-credentials-and-onboarding (`hxi-vxsmdv`, interactive workstation, live), whose research says the CI-node use is superseded.
4. **N3 has owners in three repos**: hetzner-xubuntu-info `hxi-vxsmdv` (move seats off the VPS), livespec-overseer `overseer-uzvcbn.23` and `overseer-5y7ebe` (memory floor, remote seats), and dev-tooling `dev-host-test-gate-load` (by slug).
5. **M1 consumer versus producer**: `overseer-fs4` (nothing consumes the failure category) sits in a dormant overseer plan while bd-ib-2h6cfl (populate the category) is the report's named item in the orchestrator.
6. **Dispatch-reliability defects (X) filed in overseer against orchestrator behaviour**: `overseer-cajdwp.10`, `overseer-jj44d4`, `overseer-1hv`, `overseer-7v5a73` in a plan with no next_action since 2026-09-06; homelab/steady-state-loop-hardening describes the same shapes; orchestrator `run-lifecycle-false-verdicts`, `factory-idle-with-ready-work`, `runaway-process-containment` look like the live owners (by slug).
7. **Console build telemetry (M2, M4)**: console/optimize-console-builds (`gqmtwa.5`, `u6sx`, `opdv`, `p5ci`) versus dev-tooling `console-factory-build-telemetry` and `console-factory-build-cache` (by slug).
8. **Session stall recovery**: livespec-overseer/session-obligation-recovery (`overseer-okf6bu`) is the daemon half of orchestrator `agent-session-stall-prevention` and `relay-delivery-and-progress-deadline`; held under a 2026-10-14 freeze.
9. **rop-railway-enforcement** exists in livespec, git-jsonl, runtime and dev-tooling, and **work-item-state-machine** in driver-claude, driver-codex and git-jsonl. None touches a report item; listed only as same-slug sets.
10. **`overseer-uzvcbn.12`** is listed as an open child of both herdr-overseer and overseer-validated-state-command.

Items with NO carrier in any in-scope plan: Y2, Y3, Y4, Y5, C1, C2, C3, N1, M3, M5 (C4, M2 and M4 only for console builds; Y1 only via `hxi-up5dud` and `overseer-cajdwp.12`).
