# livespec-dev-tooling plans against the 2026-11-13 throughput report items

Source: inventory.json (mechanical dump), each plan's charter, open child titles, and `bd show` for caq7uh and wirn53. 37 plans (legacy-coordinator-agent excluded; throughput-track-organization has no entry in the dump). Child ids are short: prefix `livespec-dev-tooling-`.

Reading rule used: a child is listed under an item only when its title (or body, where read) says so. "charter-only" means the charter covers the item and no open child carries it. X is used for anything else that limits PRs merged green per hour.

## ci-cache-optimization (livespec-dev-tooling-7zozck)

- **relevance**: PARTIAL
- **items**:
  - C4:
    - zbu7jf [ready] Delegated gate Jobs fetch their tree through the node's git object seed as an alternate, falling back to a full fetch on any seed fault
  - N2:
    - e2gv6n [active] hp-xubuntu and gmktec-xubuntu CI nodes get the action-archive seed, the ghcr pull mirror and pre-pulled CI images that poweredge-xubuntu already has
    - n622ze [acceptance] Runner-only node hp-xubuntu: routed CI jobs resolve uv packages through a host-served source instead of running cold
  - X:
    - uqmdor [pending-approval] Petri factory sandboxes resolve locked Python packages through the in-cluster PyPI files proxy, so a PyPI timeout no longer fails run_prepare
    - ddcvyd [ready] The ARC container hook crashes with 'Converting circular structure to JSON' at job start, so the job dies before any check runs
    - dciyg5 [acceptance] Fleet ARC runner jobs check out against a seeded per-repository git object store (GIT_ALTERNATE_OBJECT_DIRECTORIES)
- **state**: epic backlog; next_action await (item:livespec-dev-tooling-m5m2dl): Await m5m2dl closed. uw6dqg and ktxuga are CLOSED (18:05Z, 18:09Z). Bullets 3 and 4 are observed. Bullet 1 is read from fabro fork-gates run 43472471910's ...; open/total children 10/19; updated 2026-11-13
- **note**: Purpose is CI job preparation time (caches), not a report item by name. zbu7jf shortens the delegated gate (C4). uqmdor is a factory run_prepare failure cause (PyPI timeout) and ddcvyd a CI job killed at start (X). e2gv6n/n622ze bring hp and gmktec CI nodes to poweredge parity (N2). dciyg5 is CI checkout time (X, CI duration).
- **unrelated_open_children**: 4:
  - gry6tq [ready] The CI-stack converge rolls the warm-uv-cache-populate DaemonSets when the warm-cache-budget ConfigMap data changes, so they stop 
  - m5m2dl [backlog] (BUG) The warm-cache populator never warms the thewoolleyman/fabro fork, so its ARC gate and carrier builds miss the shared compil
  - uyevam [acceptance] A compilation-cache warm build that the busy-pool guardrail keeps skipping is reported once it lags its repository's default branc
  - qyrmwe [ready] A seeded CI job's git object seed leaks to every git process in the job: scope the alternate to the checkout only
- **overlaps**: gmktec-pool-member-obligations hatvwq (uv warm cache missing on gmktec) duplicates e2gv6n/n622ze scope. gate-job-resources reuqym and zbu7jf both change how a gate Job fetches its tree.

## ci-pool-provisioning-leftovers (livespec-dev-tooling-fby3sx)

- **relevance**: NONE
- **items**: none
- **state**: epic backlog; next_action await (item:livespec-dev-tooling-y4umcc): Wait for livespec-dev-tooling-y4umcc to close: cut its revise for proposal delete-the-dead-phase-1 when the coordinator's dev-tooling revise queue reaches it (after dev-host-disk-retention #4265 and ci-cache #4257), ...; open/total children 3/13; updated 2026-11-13
- **note**: Ansible migration cleanup (dead artifacts, manual preconditions).
- **overlaps**: none noticed

## ci-runtime-and-cost (livespec-dev-tooling-ib3oe3)

- **relevance**: CORE
- **items**:
  - C1:
    - s2esff [active] In CI, check-coverage refuses a missing or stale coverage receipt with a named failure before starting any test run
    - ljne5w [ready] Adopt the CI coverage-consumer refusal across the fleet, then arm a fleet check that no mandatory coverage consumer can start the suite
    - ool7pj [backlog] Write one structured reuse outcome from each CI run of check-coverage.sh to the step summary and the run's telemetry export
    - g3mnat [ready] Raise a maintainer notification from the scheduled detector when a mandatory coverage consumer records an outcome other than reused
    - v2b3yk [pending-approval] Raise a maintainer notification when a master CI run of the last 24 hours has a mandatory coverage consumer job with no recorded reuse outcome
    - zangru [pending-approval] Raise a maintainer notification naming the reuse-outcome detector when its last successful run is older than twice its schedule interval
    - 2xulmw [ready] The reuse-outcome detector delivers each maintainer notification to the dev host's ntfy topic and logs a delivery receipt
    - mbmqvy [ready] A push or PR that changes only declared capacity or config values runs schema validation only at pre-push and in CI
    - hmztez [ready] A commit that changes only declared capacity or config values runs schema validation only at pre-commit
    - symfx2 [active] No dev-tooling test asserts a committed capacity or config value literal
  - C2:
    - jd4qle [active] A delegated pre-commit that passes on its doc-only branch records full-suite green-token evidence, so the next push skips the whole suite
  - C4:
    - 5y3luz [ready] The flake-retry plugin decides retry eligibility once per test file and parses each module once, so collection stops dominating every pytest session
  - M4:
    - bt2cnw [ready] (BUG) The CI run-telemetry exporters post a skipped job's span with its end before its start, so Honeycomb github-ci reads a uint64-wrapped duration_m
    - k9mr [backlog] github-ci-export emits unexpanded matrix-leg spans (literal GitHub Actions ci.job.<matrix.target> expression) with a uint64-wrapped duration_ms
    - wnwwsl [ready] Every ci.job span export-ci-telemetry.sh sends carries ci.runner_name, so a CI job's duration joins to the k8s node that ran it
    - r6r3o2 [ready] The CI run-telemetry exporter names every failure path on stderr and degrades an unreadable check-coverage reuse outcome to unobserved instead of fail
    - 5ua57h [blocked] Every fleet member's CI exports its run telemetry through one exporter module that livespec-dev-tooling ships, so a change to the exporter lands in on
    - wza24d [pending-approval] Raise a maintainer notification when a CI job's 24-hour p90 duration doubles its 7-day baseline by more than 5 minutes for the same runner label
  - N2:
    - mtvxde [ready] ARC runner pods are spread across CI nodes by free churn slots, so gmktec-xubuntu's 12 slots are used instead of being scored last behind its factory 
    - 6e5pyj [ready] Each CI pool node's churn slots and per-job test parallelism are derived together from one CPU budget, so a full node never runs more test workers tha
    - 2aelab [ready] livespec-orchestrator-k3s and livespec-runtime-k3s carry recorded maxRunners exceptions (24 and 10), so their jobs stop queueing at the rule ceiling w
    - lzkzwb [acceptance] Master-push CI runs on its own scale set with a reserved non-lendable Kueue slice, so it no longer queues behind pull-request CI
    - 5wewi2 [ready] CI runs of work items in top-ranked plans take PR-lane and master-lane admission priority from a priorities record, on every fleet repository (phase 1
    - samgg2 [blocked] A high-band CI workload preempts a running normal-band workload when its lane is full, and the preempted job is re-run automatically (phase 2)
  - X:
    - 227glz [pending-approval] A pull request whose newest CI run is a zero-job ghost queued over 15 minutes is closed and reopened once for a fresh run on the same head
    - vrpwyw [pending-approval] A CI run GitHub leaves queued with no jobs for more than 30 minutes is replaced by one fresh run on the same head, so a pull request's required checks
    - cetyrq [blocked] A CI job that fails at Set up job on a codeload 429 is re-run automatically with growing backoff
    - ybnep5 [ready] A fleet CI run that GitHub fails at job creation with an "Internal server error" is re-run automatically with incremental backoff, at most three times
    - khlrw3 [active] A CI job that fails at "Initialize containers" on a registry network error is re-run once automatically, before any test runs, in every fleet reposito
    - 73qw6g [active] The CI infrastructure re-run reconciler imports its vendored structlog, so it runs under the reusable workflow's bare PYTHONPATH instead of crashing o
    - fc4dzb [pending-approval] Self-hosted CI git fetches from github.com are anonymous, so when GitHub 401s the homelab NAT egress every uv git source, sibling clone and core fetch
    - vfofyj [ready] livespec-overseer's master ruleset requires its ci-green aggregate gate, so a red pull request cannot auto-merge
    - qzw2gf [active] livespec-dev-tooling's ci.yml keeps the in-progress master push run and only the newest pending one, never dropping a release or expedited run
    - xtofr3 [blocked] just check refuses a master-push concurrency group in a repository whose workflows call the master-health reconciler
    - aplxhg [blocked] Coalesce releases into a scheduled window so the release and pin-bump CI cascade stops costing 34% of fleet k3s CI time
    - 7crrkb [backlog] A bump to a livespec-dev-tooling tag opens before ghcr.io serves that tag's sandbox image, so any bump path but the release fan-out reds on ErrImagePu
    - hqbbff [pending-approval] The runner-scheduler fail-open reconciler fails open when the ci-runner-scheduler Lease's renewTime is stale while its pods read Ready
    - 2yne2h [pending-approval] The master-health reconciler opens its revert through revertPullRequest, whose commits are UNSIGNED, so its revert of a culprit that touched product .
    - c7efqa [pending-approval] docs/server-side-revert-exemption.md says GitHub signs every commit its API creates, but revertPullRequest and the REST contents API mint UNSIGNED com
    - jkwzwv [ready] The ARC runner version pin is bumped before GitHub stops serving it, so a deprecated runner never kills in-flight CI jobs across the pool
    - hnynfm [pending-approval] The crates proxy serves the fleet's pinned GitHub release assets from a committed manifest, so CI does not depend on a live release download
    - ehnjlt [pending-approval] An expedited incident's incident-ci job is admitted ahead of ordinary PR traffic in the livespec-dev-tooling runner pool
    - onk27y [pending-approval] incident-ci and check-metadata route on CI_INCIDENT_RUNNER_LABELS, so the tailnet observer stays reachable while non-coverage CI runs on hosted runner
  - Y3:
    - mpv6bp [ready] The generated heading-coverage debt register merges without textual conflict when two branches change different rows
    - oim422 [backlog] Every workflow-editing PR rewrites the single .livespec-workflow-edit-exemption file, so any two in flight conflict
- **state**: epic backlog; next_action await (item:bd-ib-voazyv): Await bd-ib-voazyv (S3, the dev-host breakage-pass timer) closed: S1 bd-ib-v6rkls and S2 bd-ib-y3hgmv go through the factory first, then this seat hand-lands S3; pgbr52 was ...; open/total children 58/75; updated 2026-11-13
- **note**: Charter: cut CI runtime and cost, starting with the doubled root/nonroot coverage legs (C1). The C1 carriers are the coverage-receipt reuse chain (CI consumers refuse to start the suite; reuse outcome recorded and alerted) plus config-only changes running schema validation only. jd4qle is a C2 correctness bug (doc-only pre-commit evidence lets the next push skip the suite). mpv6bp/oim422 remove two guaranteed textual conflicts between in-flight branches (Y3). X children are infra auto-reruns, ghost runs, anonymous-fetch 401, master-push lane, release cascade (aplxhg: 34% of fleet CI time), red-master revert signing. This plan has become a catch-all: 58 open children.
- **unrelated_open_children**: 13:
  - apluqn [pending-approval] A release-please pull request that changes anything beyond its release-owned version lines and changelog fails a required pre-merg
  - 6pozr5 [blocked] The interim release guard ships as a tested livespec_dev_tooling module with a committed user unit
  - hnbn7z [pending-approval] Every repository tracking .livespec-workflow-edit-exemption pins a pack release that reads .livespec-workflow-edit-exemptions/
  - hyeteu [pending-approval] check-no-workflow-edits admits an inherited exemption whose only change is a mode bit or a rename
  - fsle5g [blocked] check-ci-single-container-image enforces one image version per consumer workflow, with a layered flavor allowed only off the gate 
- **overlaps**: C1 with implement-test-performance and rgr-touched-test-scope; C2 jd4qle with implement-test-performance yud7rc; N2 6e5pyj/mtvxde/2aelab with gate-job-resources wirn53; red master 2yne2h/c7efqa/xtofr3/qzw2gf with red-master-self-healing; M4 5ua57h with rop-railway-enforcement 8o8e.23 (exporter exists in four versions); bt2cnw and k9mr both describe the uint64-wrapped duration_ms.

## codex-implement-cost-per-run (livespec-dev-tooling-vspttc)

- **relevance**: NONE
- **items**: none
- **state**: epic backlog; next_action await (item:bd-ib-ch44wn): Await bd-ib-ch44wn closing, then restore the m3nfnh References heading; relays 1a/1b and any gpt-6.1-terra re-trial (which must first prove the model is accepted) remain on ...; open/total children 0/0; updated 2026-11-06. **DORMANT?** no update since 2026-11-06
- **note**: Cost per Codex implement run, not throughput. Charter says it must not duplicate implement-test-performance. Adjacent to C4/Y5 only through its drivers (turns per run, re-entries per item; note 003 redispatch carry-forward). No children in this tenant; waits on orchestrator bd-ib-ch44wn.
- **overlaps**: orchestrator anthropic-burn-mitigation, factory-context-per-turn-reduction.

## console-factory-build-cache (livespec-dev-tooling-3u3gm2)

- **relevance**: NONE
- **items**: none
- **state**: epic closed; next_action human: implement 3u3gm2.1 — the python-rust-agent Dockerfile change that runs `cargo fetch` of the console lockfile into the image CARGO_HOME at build, plus measure the image-size ...; open/total children 0/2; updated 2026-09-12. **DORMANT?** no update since 2026-09-12, next_action=human
- **note**: Epic CLOSED 2026-09-12, 0 open children; plan directory not archived.
- **overlaps**: none noticed

## console-factory-build-telemetry (livespec-dev-tooling-bfvbsw)

- **relevance**: PARTIAL
- **items**:
  - M2:
    - bfvbsw.1 [blocked] Verify factory cargo-phase spans reach github-ci from a real console run, then report on the console epic and dispose 2er6nc
- **state**: epic backlog; next_action none: Record this plan's next action; the migration found none to seed from.; open/total children 1/1; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=none
- **note**: Factory cargo build/check/test stage spans for console runs only: stage timing in the factory (M2, console slice). One blocked verification child.
- **unrelated_open_children**: 0
- **overlaps**: console optimize-console-builds (livespec-console-beads-fabro-gqmtwa) is the parent programme; orchestrator factory-run-correlation-observability (bd-ib-qfv9) owns run identity on spans.

## delegated-commit-time-gates (livespec-dev-tooling-2fekp6)

- **relevance**: CORE
- **items**:
  - N3:
    - sewnfp [acceptance] Suite-green replay leg obtains its suite run from a gate Job over the staged tree, falling back to a local run on no verdict (slice 3 of 3)
  - C4: charter-only
- **state**: epic backlog; next_action None; open/total children 1/1; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=None
- **note**: Charter: commit-time Red/Green/suite-green legs run as cluster gate Jobs, not on the VPS (N3; also shortens the commit leg, C4). Last slice sewnfp is at acceptance.
- **unrelated_open_children**: 0
- **overlaps**: dev-host-test-gate-load (same goal for the pre-commit aggregate, janitor, ad-hoc runs); rgr-touched-test-scope was opened from the same maintainer statement.

## dev-host-disk-retention (livespec-dev-tooling-qgwxo4)

- **relevance**: PARTIAL
- **items**:
  - N3:
    - 7tfa3x [ready] Dev host /tmp refills about 13 GiB in 9 h and the session-scratch leg runs only daily; add a scratch-and-pytest-only retention timer every 2 h
    - 64ik6g [ready] A SIGKILLed check runner leaks its covns-* coverage namespace directories in the system temp dir, and nothing reclaims them (4.5G on the dev host /tmp
    - hlyayb [ready] The red-green-replay revert check leaves a gpg-agent daemon running per verification after removing its temporary GNUPGHOME; each orphan keeps a dead 
- **state**: epic active; next_action await (item:livespec-dev-tooling-4rcuxp): Run the STANDING TRIPWIRE before every livespec-dev-host-retention.timer firing (next 2026-11-10T23:28:13Z) until livespec-dev-tooling-ovnrsv is applied; land the hermetic retention-test fix (chore/retention-tests-hermetic-state-dir) through the coordinator grade; file ...; open/total children 8/14; updated 2026-11-10
- **note**: Dev host disk (/tmp, uv cache), not CPU. The three carriers are dev-host pressure produced by gates and sessions: /tmp refill, leaked coverage namespaces from killed check runners, orphan gpg-agents per revert check. A full /tmp stops sessions and local gates.
- **unrelated_open_children**: 5:
  - mrbvgm [ready] test_local_gate_concurrency_limit pins the dev_hosts slot limit to a literal; assert a positive whole number instead
  - kvmjvm [pending-approval] The dev host capacity alert publishes anonymously and shares the host IP's 250-message ntfy quota, so on 2026-11-11 every /tmp ale
  - ng6ka4 [ready] The dev host retention bulk-dump cap re-walks the whole dump directory for every file it removes, so on a large tree one pass outl
  - umy3ry [ready] Dev host retention's uv-cache ownership walk never completes on the dev host (5.3M entries, 29 min full walk vs a 300 s budget) an
  - pxqxti [ready] Dev host retention trusts an empty live-session set from a scan that could read no process environment at all (xargs 123 when ever
- **overlaps**: dev-host-test-gate-load (moving gates off the host removes the source of 64ik6g and most of 7tfa3x).

## dev-host-test-gate-load (livespec-dev-tooling-6vuiwe)

- **relevance**: CORE
- **items**:
  - N2:
    - gvo7fa [acceptance] Gate admission cannot see runner CPU load because runner pods request no CPU, so gates keep landing on a saturated node
  - N3:
    - ie7fas [active] The delegated gate client polls its gate Job with a kubectl get every 10 s for the whole wait; block on a watch of the Job's terminal condition instea
    - cvef23 [active] The agent guard runs a foreground pytest of an ansible-playbook-driving test module on the dev host, because no gate-Job-only declaration exists
    - ctmtfg [ready] (BUG) A delegated gate Job's own check-pre-push prints the host-fallback warning, so a host log falsely claims its delegated push gated locally
    - 5lhafp [ready] A stalled gate run's kill misses a descendant that started its own session, which outlives the gate and spins for hours
  - Y2:
    - q4ahay [ready] A gate run the stall bound ends leaves no record of which process was hung, so a silent stall cannot be localized after the kill
  - Y4:
    - fmprfr [ready] (BUG) test_aggregate_completeness pins the check aggregate's member count as a literal, so every new check refuses the next push until the number is b
    - wj45qt [ready] A gate Job's `pytest --cov=<pkg>` passes the whole suite, then fails combining branch with statement coverage data
  - M3: charter-only
- **state**: epic backlog; next_action await (item:livespec-dev-tooling-ie7fas): Await ie7fas CLOSED: its FRESH relaunch from master (reference rider naming 1e48c86e9 and the _await_terminal re-arm fix) is active on ticket …1702 after the coordinator's ...; open/total children 9/69; updated 2026-11-13
- **note**: Charter: routine test and gate load leaves the VPS (N3). gvo7fa makes gate admission see runner CPU (N2). q4ahay/5lhafp are stalled-gate kills (Y2 evidence and a runaway that spins for hours). fmprfr and wj45qt are gate failures with no code defect (Y4). Research note 010-gate-wall-time holds gate duration measurements but no child records durations on gate outcome events (M3 charter-only).
- **unrelated_open_children**: 1:
  - 6cgj2e [ready] A CLI that defaults its state directory to a live host path lets any caller that omits the flag write live host state, as the flak
- **overlaps**: delegated-commit-time-gates sewnfp; implement-test-performance (charter assertion on which gates run as Jobs); gate-job-resources wirn53 with gvo7fa; kubernetes-observability exx6f5.

## dev-tooling-backlog-drain (livespec-dev-tooling-kcoslm)

- **relevance**: NONE
- **items**: none
- **state**: epic backlog; next_action human: Ceiling raised and MERGED (PR #2327: dispatcher.node_timeouts implement=14400/review_fix=7200/fix=janitor=3600). The gate-heavy keep class (s1ic/u3f6bw/go7a/xam/izbq/uw3h) is UNBLOCKED. A herdr resume: resume gate-heavy drain dispatch, re-evaluating formerly node-timeout-blocked ...; open/total children 0/1; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=human
- **note**: Generic backlog drain through the factory; 0 open children. Touches X only in the sense that it feeds the factory.
- **overlaps**: none noticed

## expedited-incident-hardening (livespec-dev-tooling-dh3hub)

- **relevance**: PARTIAL
- **items**:
  - X:
    - rs6o3q [active] livespec-dev-tooling tests bound waits on threads, processes, barriers and events with short wall-clock timeouts, so a loaded runner can fail them wit
    - dqndbz [pending-approval] test_exact_concurrent_reservation_survives_restart_and_conflicting_bytes bounds its two reserve threads with 3-second wall-clock waits, so a loaded ru
    - ek36t5 [ready] The claim-token race drill releases its two writers by two serial go-FIFO writes against one named instant, so a release write later than the lead plu
    - okij46 [blocked] Arm the master-health reconciler in livespec-dev-tooling
    - j2rdde [pending-approval] An incident repair touching .github/workflows is always refused: the host hook has no way to accept scoped workflow authorization
- **state**: epic backlog; next_action await (item:livespec-dev-tooling-fx32ej): Await livespec-dev-tooling-fx32ej closing (the only dispatchable ready child, in legacy-dispatcher-agent's lane). Meanwhile, drive v212 livespec-dev-tooling#4530 (rgiufy) through the coordinator's grade to merge; then rewrite rgiufy's ...; open/total children 13/20; updated 2026-11-13
- **note**: Successor plan for incident-path hardening. rs6o3q/dqndbz/ek36t5 are load-sensitive wall-clock test waits (flaky under contention). okij46 arms the master-health reconciler in this repo (red master). j2rdde: an incident repair touching workflows is always refused.
- **unrelated_open_children**: 8:
  - xazlro [ready] test_incident_observer_role.py pins the reset-failed handler's committed YAML values instead of proving its behaviour
  - rgiufy [active] Incident focused-changes reads bypass the isolated git view, misclassify symlinked modules, explain submodules opaquely, and leave
  - fx32ej [active] The conflict sweep has no global attempts bound, an operator /reconcile skips its back-off, and nothing documents clearing quarant
  - 7axsxq [ready] The expedited matrix call-site check trusts reusable-check-matrix at any ref, and a YAML constructor error crashes it (hlxbsv note
  - io6hyk [blocked] No verb closes a drill incident chain, so a drill item stays at reverting or repayment-owed forever
- **overlaps**: fleet-flaky-tests owns flaky tests (rs6o3q, dqndbz, ek36t5 belong there by its charter); red-master-self-healing owns the reconciler (okij46).

## expedited-incident-response-flag (livespec-dev-tooling-bqnzcm)

- **relevance**: PARTIAL
- **items**:
  - X:
    - g734nf [pending-approval] ci-green fails a green run when its jobs read lags GitHub: a needed leg that completed seconds earlier reads in_progress and ci-green fails closed on 
    - lr3tfv [pending-approval] check-branch-protection-alignment refuses a whole commit or push when one forge answer omits a ruleset's bypass_actors, instead of retrying the transi
    - xdt4ue [acceptance] The incident-ci entrance runs its selected members in parallel without the pyright warm-up, so two pyright members race a cold install and one type-ch
    - eqtyyr [pending-approval] incident-label-ci re-runs a CI run whose event payload predates the incident block, so check-red-green-replay can never admit the expedited commit on 
    - 3u5rzz [pending-approval] An expedited pull request's incident-ci is refused whenever the default branch moves between the attempt's genesis and the armed run, so the incident 
    - 7qb2bs [pending-approval] The orchestrator's fast incident gate check-codex-skill-picker depends on the host's codex install and fails deterministically on the incident host, s
    - m5cpnl [ready] A pin-bump PR whose base gains a new pin-bearing line after the rewrite merges with that line still on the old pin
- **state**: epic backlog; next_action await (item:livespec-dev-tooling-xdt4ue): Land release 1.207.1 (#4552), shepherd livespec's bot pin bump to it, drive livespec-57r6qo/#3199 to USABLE; xdt4ue's repayment waits on orchestrator bd-ib-ah5t7i.; open/total children 34/123; updated 2026-11-13
- **note**: Charter: incidents block the factory because fixes go through the slow path; a fast lane (X: red master / production defect recovery time). Open children are mostly audit and adoption residue. Throughput carriers: g734nf (ci-green fails a green run on a lagging jobs read), lr3tfv (a transient forge read refuses a whole commit or push), xdt4ue (pyright race), eqtyyr/3u5rzz/7qb2bs (incident path unavailable), m5cpnl (pin-bump merges with a stale pin).
- **unrelated_open_children**: 27:
  - bqnzcm.4 [pending-approval] An expedited pull request's CI runs and their omitted members are not recorded on the incident work item
  - bqnzcm.3.1 [blocked] livespec-dev-tooling's own 36 incident fleet rows are unclassified, so the pilot repository is not on the audit's ready list
  - bqnzcm.3 [backlog] The incident fleet inventory is incomplete: about 560 of 814 audited surface rows are still unclassified, so no consumer is ready 
  - bqnzcm.2 [ready] Operators cannot inspect an incident's full history by its work-item id: read-history returns only the current attempt and the exp
  - h73ok4 [pending-approval] The pyright warm-up runs in the caller's working directory and inherits the incident credentials the members are denied
- **overlaps**: expedited-incident-hardening (its own successor); red-master-self-healing; ci-runtime-and-cost ehnjlt and onk27y carry incident-CI routing for this plan; fleet-flaky-tests awaits this epic closing.

## factory-spend-accuracy (livespec-dev-tooling-fwq26r)

- **relevance**: NONE
- **items**: none
- **state**: epic backlog; next_action human: Owner: scope where factory cache splits, run outcome and fallback can be measured, record the carrier map, and start the host-only assertions 5 and 6.; open/total children 0/0; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=human
- **note**: Spend measurement (cache splits, run outcome on spend events). Run outcome on spend events is near M1 but it is outcome, not a failure category. No children.
- **overlaps**: orchestrator bd-ib-2h6cfl (M1) is the named owner of the failure category.

## fleet-bare-metal-rebuild-proof (livespec-dev-tooling-jqbc3t)

- **relevance**: NONE
- **items**: none
- **state**: epic backlog; next_action None; open/total children 4/4; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=None
- **note**: Rebuild-from-bare-metal proof for pool hosts.
- **overlaps**: none noticed

## fleet-flaky-tests (livespec-dev-tooling-zwveqp)

- **relevance**: CORE
- **items**:
  - X:
    - i4prpx [blocked] root-fix: tests/livespec_dev_tooling/test_check_target_runner.py::test_outcomes_keep_run_order_status_output_and_stdin_closed
    - hzhw6y [ready] Two incident observer route tests fail on a starved runner because a 15-second git bound in the inverse helpers decides their verdict
    - gokm2v [ready] The gate renderer's own exit-test suite still flakes on a loaded runner after its readiness fixes, and the failing case is not recorded
    - vzfxlg [active] The incident recovery principal's tests can see a 'pending' recovery outcome on a loaded runner (test_principal_refuses_a_request_that_is_not_the_exac
    - oszlos [active] test_competing_invalidations_have_one_winner decides pass or fail on a 3 s barrier wait, so a slow second worker breaks the barrier under load
    - qohfro [active] The detached gate runner exposes when a tick saw no new progress, so a renewal test needs no wall-clock quiet pause
    - lshpdf [active] The flake-retry filer files a fresh root-fix item from the same unconsumed retry record every time the previous root-fix item for that node id closes
    - h77qmw [active] Nothing runs the flake-retry filer, and CI does not deliver its records, so a flake the retry absorbs files no root-fix item
    - ljea46 [pending-approval] Consumer CI delivers no flake-retry records: add a shared publish-flake-retries action and one additive step per consumer
    - k3lpwj [pending-approval] The flake-retry closure retries tests whose repository path is built through getattr, an aliased request, a fixture imported from another test module,
    - d4siza [pending-approval] The flake-retry plugin reads a top-level changed directory such as config/ as matching an identical bare string in a test's closure, even a git argume
    - n3dr3z [pending-approval] Any .livespec.jsonc edit marks every test touched through the conftest that reads it, so a config-value-only change withholds every flake retry
    - ln77b6 [pending-approval] The flake-retry plugin's per-test touched withhold prints no marker, so a correctly withheld retry is indistinguishable from the plugin not running
    - o4hkgh [ready] A delegated gate Job rewrites uv.lock through the PyPI proxy in its working tree, so the flake-retry plugin withholds every in-place retry as a non-ve
    - bxnqo7 [ready] The flake-retry shallow-lock fix reaches no consumer until a release, and its CI cause is still inferred
    - wc23r2 [ready] Propose how the flake-retry closure treats a Path.cwd() or pytest rootpath base, which the Untouched-test retry clause neither roots nor excludes
    - p34aap [active] The delegated pre-commit gate publishes a merge as a single-parent commit, so a hand merge of master that brings in newly registered TODO rows is refu
  - Y2:
    - h2i4u2 [active] Factory janitors kill the suite-green leg at its 900-second stall window on a passing tree, and the kill does not say which tests were still running
  - Y4:
    - dpkz32 [blocked] A test loop statement over the ambient environment covers its body line only when the host sets a matching variable, so per-file coverage passes in th
    - e34ks3 [pending-approval] A timed wait loop in coverage-measured test code covers its sleep line only when the wait is slow, so per-file coverage flakes with load; no check req
- **state**: epic backlog; next_action await (epic:livespec-dev-tooling-bqnzcm): Await epic livespec-dev-tooling-bqnzcm closed, as a precondition only. FIRST resume (on hetzner-xubuntu, /home/ubuntu/workspace/livespec-dev-tooling) into a self-paced /loop (about 20-30 min), then work handoff 69's OPEN ...; open/total children 24/61; updated 2026-11-13
- **note**: Charter: root-fix every known flaky test (X). h2i4u2: factory janitors kill the suite-green leg at its 900 s stall window on a passing tree (Y2). dpkz32/e34ks3: per-file coverage passes or fails with host environment or load (Y4). The flake-retry plugin children (k3lpwj, d4siza, n3dr3z, ln77b6, o4hkgh, wc23r2, bxnqo7) decide when an in-place retry is given.
- **unrelated_open_children**: 4:
  - ehug6z [acceptance] The two reused-pre-commit-evidence pre-push scenarios have no integration-tier test, and their TODO rows' owner livespec-dev-tooli
  - wc6sxv [blocked] Re-own every heading-coverage TODO row whose work_item is closed (57 closed owners, 122 rows in this repository)
  - 7w4wca [active] The pipefail reader sweep catches only N = 1 readers, while its clause names grep -m N, head -n N and head -c N
  - ljmpht [ready] Inline pipefail shell in composite actions and workflows escapes the reader sweep, and bump-pin-rewrite's gitlink guard can miss
- **overlaps**: expedited-incident-hardening rs6o3q, dqndbz, ek36t5 and expedited-incident-response-flag xdt4ue are flaky-test fixes outside this plan; ci-runtime-and-cost 5y3luz changes the same flake-retry plugin; fleet-heading-coverage-convergence owns the TODO rows wc6sxv re-owns.

## fleet-heading-coverage-convergence (livespec-dev-tooling-0bse)

- **relevance**: NONE
- **items**: none
- **state**: epic backlog; next_action human: Maintainer: state in your own words what DONE means for this plan (proposed: charter D9 scoped to the frozen set per the 10-19 ruling R1) ...; open/total children 11/19; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=human
- **note**: Heading-coverage debt burn-down; adds tests rather than removing them.
- **overlaps**: fleet-flaky-tests wc6sxv.

## fleet-mutation-testing-rule-26 (livespec-dev-tooling-oi2two)

- **relevance**: CORE
- **items**:
  - C3:
    - mrahu4 [pending-approval] Rule-26 runtime adoption: on-demand recipe and first exhaustive report
    - dya4ta [ready] Rule-26 diagnostic elapsed budget and durable job-only stop
    - rl6tqt [ready] Rule-26 diagnostic manifest selection and partial report
    - 46y4en [pending-approval] Rule-26 pruning tool: remove redundancy candidates one at a time, never a cited or unmeasured test
    - dkgwsm [acceptance] Rule-26 kill-matrix engine: pure code, parallel, incremental and scheduled (fast enough for the orchestrator)
    - fqnbtd [blocked] Rule-26 slice 1: kill-matrix feasibility and first report for livespec-orchestrator-beads-fabro
- **state**: epic backlog; next_action impl (livespec-dev-tooling-fqnbtd): Complete fqnbtd under RULE26-DAY-RESCOPE-20261113: verify existing proposal-push gate 20261113T082112Z-501916 and cache-Green gate 20261113T082124Z-505717 after adoption of merged root fix 785e0b96, finish proposal and he7huy PRs/review/merge/cleanup, ...; open/total children 6/15; updated 2026-11-13
- **note**: Charter: kill-matrix mutation testing and test-suite shrink (C3). 46y4en is the pruning tool; dya4ta/rl6tqt are the elapsed budget and manifest sampling that ration the matrix; fqnbtd is the first report (blocked).
- **unrelated_open_children**: 0
- **overlaps**: mutation-testing-keystone (cross-tenant epic livespec-mutreal); implement-test-performance charter assertion "make the suite faster".

## gate-job-resources (livespec-dev-tooling-ukoeah)

- **relevance**: CORE
- **items**:
  - N1:
    - caq7uh [pending-approval] The gamingpc gate reproduction route is retired, and the converge deletes its Kueue queue, flavor and local queue
  - N2:
    - wirn53 [pending-approval] One committed per-node CPU budget sets the gate request, the gate lane quotas, the churn slots and the factory pod budgets on every pool node
  - X:
    - reuqym [pending-approval] A gate Job fetches livespec core and its cross-repo siblings from the in-cluster git-gates mirror instead of anonymous github.com
  - C4: charter-only
- **state**: epic backlog; next_action await (item:livespec-dev-tooling-wirn53): Await wirn53 (the one per-node CPU budget change) closed: get the coordinator's joint regrade of livespec-dev-tooling#4565 and #4567 and the maintainer's factory-budget choice (cut to ...; open/total children 3/13; updated 2026-11-13
- **note**: Charter: per-repository gate Job resources and one per-node CPU budget across gates, factory, CI and system (N2), plus gate parallelism (C4, measured in note 003; no open child). caq7uh retires the gamingpc gate REPRODUCTION route only; gamingpc's real gate lane is live at 5 cpu. reuqym moves gate fetches off anonymous github.com.
- **unrelated_open_children**: 0
- **overlaps**: ci-runtime-and-cost 6e5pyj (churn slots and test parallelism from one CPU budget) is the same budget as wirn53; gmktec-factory-placement zsbvp3 (fleet cap from factory_pod_budget); gmktec-pool-member-obligations z7nfhx (soak the provisional Kueue numbers); radar-and-deterministic-admission 7exa37.

## gmktec-factory-placement (livespec-dev-tooling-me5aqz)

- **relevance**: PARTIAL
- **items**:
  - N2:
    - zsbvp3 [pending-approval] Derive the dispatcher's fleet cap from the sum of committed factory_pod_budget values
- **state**: epic backlog; next_action proof (capture:livespec-dev-tooling-me5aqz): Capture the plan Proof of Done record for livespec-dev-tooling-me5aqz.; open/total children 6/16; updated 2026-11-13
- **note**: Factory cutover to gmktec is done; next action is the plan proof capture. zsbvp3 derives the dispatcher fleet cap from committed factory pod budgets (N2 / dispatcher width). The other five children are orchestrator release canary and roll mechanics.
- **unrelated_open_children**: 5:
  - gpo5cp [ready] Every SessionStart plugin reconcile on the dev host leaves an existing orchestrator install record unchanged
  - zpqvnr [ready] A canary clone adopts a published orchestrator release tag ahead of the release branch without moving it
  - jfnmnb [ready] A new orchestrator release's canary executes every rendered workflow input command once in a factory pod before the release branch
  - tv7obt [ready] An operator can roll a fleet clone's orchestrator install back to a named earlier release through one committed recipe, so a faile
  - 7upzav [acceptance] A fleet clone's session reconcile moves its installed orchestrator build with no roll step, so the orchestrator plugin must move o
- **overlaps**: gate-job-resources wirn53; orchestrator kubernetes-sandbox-backend and legacy-dispatcher-agent.

## gmktec-pool-member-obligations (livespec-dev-tooling-frei6s)

- **relevance**: CORE
- **items**:
  - M4:
    - xnie [backlog] R5 precondition: gmktec has no collector on its own cni0 gateway, so every cache span from a gmktec job would be dropped the moment the node is untain
  - N2:
    - z7nfhx [backlog] Soak-test the pool's provisional Kueue numbers: gmktec-xubuntu's 12 churn slots and the gates queue's 15 CPU / 24 GiB
    - a2kwn3 [backlog] gmktec-xubuntu has no runner scale set of its own, so no job can be routed to it by name
    - hatvwq [backlog] The uv warm-cache populator runs only on poweredge-xubuntu, so CI jobs on gmktec-xubuntu install packages with no warm cache
- **state**: epic backlog; next_action None; open/total children 4/4; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=None
- **note**: gmktec as a full pool member: soak its 12 churn slots and the gates queue, its own scale set, its warm cache (N2); xnie: cache spans from gmktec jobs are dropped (CI telemetry gap).
- **unrelated_open_children**: 0
- **overlaps**: ci-cache-optimization e2gv6n/n622ze (hatvwq); gate-job-resources wirn53 (z7nfhx); ci-runtime-and-cost mtvxde (use gmktec's 12 slots).

## homelab-k8s-worker-nodes (livespec-dev-tooling-ko26ez)

- **relevance**: CORE
- **items**:
  - N2:
    - u45iv6 [ready] A departed homelab worker's lanes leave admission automatically, and a gate Job whose pod dies with the node is retried, not failed
    - p4cv4l [ready] homelab worker: departure-safe, self-rejoining laptop worker with stable networking agents
    - t5ervh [backlog] homelab worker: join macbook-air-homelab-worker identically, then re-converge macbook-m4-max
    - qotekb [active] homelab worker join: join-worker.sh records the pod-span collector endpoint from the node's current CNI bridge, so a rejoin with a new pod CIDR needs 
- **state**: epic backlog; next_action await (item:livespec-dev-tooling-p4cv4l): Apply the worker image repin by the coordinator's un-enroll, replace, re-enroll procedure once livespec-dev-tooling#4548 merges, get zfgtin's re-dispatch outcome from the dispatcher, read the drill's ...; open/total children 6/29; updated 2026-11-13
- **note**: New capacity: M4 Max worker, then CI and factory dogfood (N2). Open children make the laptop worker departure-safe so gates requeue, and join the MacBook Air.
- **unrelated_open_children**: 2:
  - 6yxdxu [pending-approval] The k3s agent restart play does not refuse a node for an ARC AutoscalingListener pod, so an agent restart needs no hand step to mo
  - ew6bot [ready] ci_pool nodes: a node-level cri-containerd.apparmor.d lets default-profile containers signal their own children on kernel 7.0.0-43
- **overlaps**: gate-job-resources wirn53 names the homelab workers in the CPU budget; kubernetes-observability 7nvfjk (dead-man triggers for the M4); orchestrator kubernetes-sandbox-backend (factory pods on these nodes).

## implement-test-performance (livespec-dev-tooling-sv6m5p)

- **relevance**: CORE
- **items**:
  - C2:
    - yud7rc [active] One library command gives every consumer's pre-push gate the same-tree delegated pre-commit verdict
  - X:
    - mlhzau [pending-approval] The bump-pin reconcile inserts a slug the consumer waives under canonical_check_waivers into its `just check` aggregate and ci.yml, so every bump to a
  - C1: charter-only
  - C4: charter-only
  - Y5: charter-only
- **state**: epic backlog; next_action await (item:bd-ib-vy75ws): Wait for plan carrier bd-ib-vy75ws to close in livespec-orchestrator-beads-fabro. Run 01M7AFVCPSK2GT0W2SWXP3258Z ended at 16:12Z: its stall watchdog cancelled it after turn 1 spent its time ...; open/total children 3/33; updated 2026-11-13
- **note**: Charter: Red/Green legs run only changed tests and the whole suite runs once before final (C1), suite faster (C4), no run ending partial with Red committed apart from its implementation (Y5). The C1 carrier is CROSS-TENANT: orchestrator bd-ib-vy75ws (blocked/needs-human after a stall-watchdog cancel) is what the plan awaits; no open child in this tenant carries C1. yud7rc is the same-tree verdict reuse for pre-push (C2). mlhzau: every pin bump to a repo with waivers goes red.
- **unrelated_open_children**: 1:
  - rdgzpi [acceptance] cross_repo_public_api declares the seven livespec_dev_tooling.config functions fleet consumers import today, so dev_tooling_import
- **overlaps**: rgr-touched-test-scope (C1, same lever at the commit hook); ci-runtime-and-cost C1 chain and jd4qle; orchestrator sandbox-commit-gate-follow-ups (bd-ib-3goerg, "pays for the full aggregate once"), sandbox-commit-gate-ceiling (bd-ib-qy5wol), checkpoint-commit-hook-failures (bd-ib-hcwmnq, Y5), stall-watchdog-false-kills (bd-ib-laf735).

## k3s-embedded-etcd-datastore (livespec-dev-tooling-qql3lo)

- **relevance**: NONE
- **items**: none
- **state**: epic ready; next_action None; open/total children 2/2; updated 2026-11-11. **DORMANT?** next_action=None
- **note**: k3s datastore migration and secrets hardening. Reliability of the pool server, no report item.
- **overlaps**: none noticed

## kubernetes-observability (livespec-dev-tooling-s2aqob)

- **relevance**: PARTIAL
- **items**:
  - M3:
    - 2mp63s [backlog] Gate placement and Kueue admission stay queryable in Honeycomb after the Workload object is gone
  - M4:
    - ja7bv4 [ready] The k8s-node-load board's pod CPU panel sums the per-pod usage gauge, which over-weights short-lived pods and reads 15-49% high
  - N1:
    - 7nvfjk [ready] k8s node dead-man triggers exist only for poweredge, gmktec and hp, so gamingpc-xubuntu or the M4 going silent fires nothing
  - N2:
    - y5ewfc [ready] The churn-slot quota gauges sum every flavor of a ClusterQueue, so a queue with an arm64 overflow flavor no longer reads 0
  - N3:
    - exx6f5 [pending-approval] Dev-host no-data triggers: a dev host that stops exporting metrics fires nothing
  - M2: charter-only
- **state**: epic backlog; next_action await (item:livespec-dev-tooling-7nvfjk): Await livespec-dev-tooling-7nvfjk closed (per-node k8s dead-man triggers for every listed node; A5/A6 carrier). It is TICKETED …1802 by legacy-dispatcher-agent, as is y5ewfc (A4) …1801; rz23sl ...; open/total children 5/13; updated 2026-11-13
- **note**: Purpose is cluster-management observability. ja7bv4 is the pod CPU panel overcount the report names (M4). 2mp63s keeps gate placement and Kueue admission queryable (M3-adjacent: gate records, not durations). Charter assertion 2 gives per-pod CPU with node and namespace including factory namespaces, which is the raw data for M2, but nothing attributes it to repository or stage.
- **unrelated_open_children**: 0
- **overlaps**: ci-runtime-and-cost wnwwsl (joins CI job to node); radar-and-deterministic-admission z6yf2a (dev host metrics) with exx6f5; orchestrator factory-run-correlation-observability (bd-ib-qfv9) for M2.

## mutation-testing-keystone (unassigned)

- **relevance**: PARTIAL
- **items**:
  - C3: charter-only
- **state**: epic None; next_action None; open/total children 0/0; updated unknown. **DORMANT?** no epic in this tenant, next_action=None
- **note**: No epic in this tenant: anchored cross-tenant to livespec-mutreal; handoff says the thread belongs in livespec and should move there. Makes mutation testing real in livespec; overlaps C3 only as the mutation-testing subject.
- **unrelated_open_children**: 0
- **overlaps**: fleet-mutation-testing-rule-26.

## pin-autodiscovery-format-coverage (livespec-dev-tooling-ikeggh)

- **relevance**: NONE
- **items**: none
- **state**: epic closed; next_action human: the maintainer confirms the accept IN THE ACTING; open/total children 0/2; updated 2026-09-12. **DORMANT?** no update since 2026-09-12, next_action=human
- **note**: Epic CLOSED 2026-09-12, 0 open children; plan directory not archived.
- **overlaps**: none noticed

## pure-trees-role-key-scope (unassigned)

- **relevance**: NONE
- **items**: none
- **state**: epic None; next_action None; open/total children 0/0; updated unknown. **DORMANT?** no epic in this tenant, next_action=None
- **note**: No epic recorded in inventory (handoff names livespec-dev-tooling-8zv3); ROP pure_trees scope.
- **overlaps**: rop-railway-enforcement.

## radar-and-deterministic-admission (livespec-dev-tooling-w7ley3)

- **relevance**: PARTIAL
- **items**:
  - M5:
    - rzefod [pending-approval] Scheduler inputs Honeycomb board generated from the query specs, with a read-only drift check
  - N2:
    - hvfc6c [pending-approval] Radar admission function: pure, every ready target decided, placement rules, hysteresis, shadow-mode decision log
    - 7exa37 [ready] Radar admission inventory and thresholds files, with throughput-named caps
  - N3:
    - z6yf2a [ready] Dev host collector also exports its host metrics to the livespec metrics dataset (otel-collector config + dev-host converge)
- **state**: epic backlog; next_action impl (livespec-dev-tooling-22wpdk): Let the factory RESUME livespec-dev-tooling-22wpdk onto draft PR livespec-dev-tooling#3804 (run 3, the last: proof capture for factory_captured assertions 1-7 only, after the 16:36-16:38Z DoD fix ...; open/total children 7/12; updated 2026-11-09
- **note**: A typed priorities array and a Honeycomb-fed admission function with placement rules. hvfc6c/7exa37 decide where ready work is placed and carry "throughput-named caps" (N2, and dispatcher-idle X). z6yf2a exports dev host metrics (N3 measurement). rzefod generates a "scheduler inputs" Honeycomb board: a board applier, not the throughput metric (M5-adjacent only).
- **unrelated_open_children**: 3:
  - 3xeqvg [ready] Radar Honeycomb reader: MCP transport, tick cache, endpoint override and the flagged fallback snapshot
  - k3dpo2 [pending-approval] Radar Honeycomb contract test and the published required-columns file
  - 22wpdk [ready] Radar load entry point and ledger-resolving validation: ids resolve and are open, no item under a listed plan, plan directories ex
- **overlaps**: gate-job-resources wirn53 (caps); orchestrator dispatch-control-plane (bd-ib-k6dqwc) and factory-idle-with-ready-work (bd-ib-opbzv3); ci-runtime-and-cost 5wewi2 (CI admission priority from a priorities record).

## red-master-self-healing (livespec-dev-tooling-zcp5vb)

- **relevance**: CORE
- **items**:
  - X:
    - tig7vu [blocked] The master-health reconciler re-runs a cancelled master gating run before naming a culprit, and never names one from an unverdicted commit (option A)
    - 7uq5ri [ready] The master-health reconciler closes a server-side revert it did not open as superseded whenever GitHub CI is green, so a revert of a cluster-gate-only
    - myltix [blocked] Commit the reusable master-health reconciler workflow that every fleet shim calls
    - reslr6 [pending-approval] Arm the workflow-master-health-reconcile conformance row (missing and drifted shims fail) after fleet adoption
    - bznobs [pending-approval] Master-health reconciler: name the revert-blocked-by-gate-defect shape when a revert fails the same check that turned the branch red
    - yilv6p [pending-approval] Scheduled drill that proves the master-health revert path end to end on a throwaway branch
    - 4xrhck [pending-approval] Watch the watcher: report a master red longer than the threshold with no revert pull request in flight
- **state**: epic backlog; next_action human (livespec-dev-tooling-dw7dzd): Maintainer sets approval:workflow-edit on livespec-dev-tooling-dw7dzd; on restart re-arm the joqff6 hp slot launcher at +300 and the label watch.; open/total children 9/20; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=human
- **note**: Charter: red master reverts or fixes forward automatically (X). tig7vu is "option A" (re-run a cancelled master run before naming a culprit).
- **unrelated_open_children**: 2:
  - luist2 [pending-approval] Guard: every gating check judges the pull request's tree, never the canonical ref (general rule; 543kob is its first instance)
  - dxe742 [backlog] wire-fleet-member's branch-protection PUT test asserts a hand-listed subset of fields, so a field the spec adds later can be omitt
- **overlaps**: ci-runtime-and-cost 2yne2h, c7efqa, xtofr3, qzw2gf; expedited-incident-hardening okij46 (arming in this repo); stale-base-merge-options (compares against this baseline and directs option A here); expedited-incident-response-flag.

## rgr-cycle-agent-efficiency (unassigned)

- **relevance**: CORE
- **items**:
  - C4: charter-only
- **state**: epic None; next_action None; open/total children 0/0; updated unknown. **DORMANT?** no epic in this tenant, next_action=None
- **note**: No epic; a single 2026-08-17 proposal on RGR cycle latency written against old item livespec-dev-tooling-e60. C4 by subject, but stale.
- **unrelated_open_children**: 0
- **overlaps**: implement-test-performance supersedes it in practice.

## rgr-touched-test-scope (livespec-dev-tooling-5yyjqk)

- **relevance**: CORE
- **items**:
  - C1: charter-only
- **state**: epic backlog; next_action None; open/total children 0/0; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=None
- **note**: Charter: a single-test-file commit runs only that test in its suite-green leg (C1, at the commit hook). No children ever filed.
- **unrelated_open_children**: 0
- **overlaps**: implement-test-performance (Red/Green legs run changed tests only) and its relay bd-ib-vy75ws; delegated-commit-time-gates (same maintainer statement).

## rop-railway-enforcement (livespec-dev-tooling-8o8e)

- **relevance**: NONE
- **items**: none
- **state**: epic backlog; next_action human: No session-startable child disposition remains (see entry 61): plan waits on arming ratification + downstream jtrt/qx2l/8zv3 closure (or the 5asgvm gate fix), and still owes ...; open/total children 16/31; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=human
- **note**: ROP railway arming. Only tangent: 8o8e.23 (export-ci-telemetry.sh in four versions) is the M4 exporter-duplication problem.
- **overlaps**: ci-runtime-and-cost 5ua57h covers 8o8e.23; livespec, livespec-runtime and git-jsonl each have their own rop-railway-enforcement plan.

## software-factory-gap-map (livespec-dev-tooling-oft4bu)

- **relevance**: PARTIAL
- **items**:
  - N3: charter-only
  - X: charter-only
- **state**: epic backlog; next_action human: Maintainer to declare the brainstorm done; then open a seat named software-factory-gap-map to prepare options and a recommendation.; open/total children 0/0; updated 2026-11-12. **DORMANT?** next_action=human
- **note**: Brainstorm-stage plan. Charter assertion 4: the dispatcher runs from a host other than vmi3006760 (N3); shared state and messaging for seats and dispatcher (X, dispatcher availability). No children.
- **unrelated_open_children**: 0
- **overlaps**: orchestrator dispatch-control-plane (bd-ib-k6dqwc) and legacy-dispatcher-agent (bd-ib-ynnykl); overseer central-credential-service.

## spend-purpose-attribution (livespec-dev-tooling-vf3bqf)

- **relevance**: NONE
- **items**: none
- **state**: epic backlog; next_action human: Owner: scope the claude -p launchers and the seat-to-plan map, record the carrier map, and start the host-only assertion 5.; open/total children 0/0; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=human
- **note**: Spend attribution by purpose and plan. No children.
- **overlaps**: none noticed

## stale-base-merge-options (livespec-dev-tooling-xowhol)

- **relevance**: CORE
- **items**:
  - X: charter-only
  - C1: charter-only
- **state**: epic backlog; next_action human: Do note 005 Phase 1 steps 1-6 now (no halt needed): the maintainer sets the livespec-ai org settings and creates the org fleet App and ...; open/total children 0/0; updated 2026-11-13. **DORMANT?** next_action=human
- **note**: Charter: options for stale-base merges (the cause of semantically-conflicting merges turning master red: X). Its current next action is a fleet move to a GitHub organization to use GitHub's own merge queue. That is in direct tension with C1 as the report states it ("one full coverage run guarding master, NOT GitHub merge queue"). The maintainer has not chosen a direction (note 003). Related to Y3 only by name: Y3 is the in-run rebase conflict, this is the post-merge semantic conflict.
- **unrelated_open_children**: 0
- **overlaps**: red-master-self-healing (the decided baseline; tig7vu is the option A it directs there); ci-runtime-and-cost qzw2gf (master-push run coalescing); orchestrator publish-draft-green-work-loss (bd-ib-acrr56) and pr-refresh-reproof-relevance (bd-ib-ku7phe) own the Y3 side.

## token-spend-analysis (livespec-dev-tooling-6lv7ze)

- **relevance**: PARTIAL
- **items**:
  - M3:
    - 3su2nx [blocked] Factory turn spans carry tool-open seconds and tool-call count, so idle-turn and gate-wait spend are one Honeycomb query each
  - C4: charter-only
- **state**: epic active; next_action human: Plan stays OPEN by maintainer ruling 2026-10-31 (do not archive). It holds three deferrals; reconsider the iznup7 consumer half when bd-ib-h23kbx closes. Plan proof verified ...; open/total children 2/10; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=human
- **note**: Held open by maintainer ruling with deferrals. 3su2nx: factory turn spans carry tool-open seconds, so gate-wait time inside a turn is one query (measurement for C4/M3; blocked).
- **unrelated_open_children**: 1:
  - n277mo [ready] llm-spend's spend.account is inferred from caam's timeline or selection, never read from the credential that sent the response, so
- **overlaps**: implement-test-performance; orchestrator factory-run-correlation-observability.

## version-lockstep-release-race (livespec-dev-tooling-zbkur6)

- **relevance**: PARTIAL
- **items**:
  - X: charter-only
- **state**: epic backlog; next_action None; open/total children 0/1; updated 2026-11-06. **DORMANT?** no update since 2026-11-06, next_action=None
- **note**: A janitor or gate run on a checkout between a release commit and its tag fails a version test (a false red: X). 1 child, closed; nothing open. Looks finished but not proved or archived.
- **unrelated_open_children**: 0
- **overlaps**: fleet-flaky-tests (same class: red with no defect).

## Cross-plan duplicates and overlaps

Child ids are `livespec-dev-tooling-<id>` unless a tenant prefix is shown.

- **C1** (suite once per change): implement-test-performance (charter; carrier is cross-tenant bd-ib-vy75ws), rgr-touched-test-scope (charter-only, no children), ci-runtime-and-cost (s2esff, ljne5w, ool7pj, g3mnat, v2b3yk, zangru, 2xulmw, mbmqvy, hmztez, symfx2). Outside this repo: orchestrator sandbox-commit-gate-follow-ups (bd-ib-3goerg). stale-base-merge-options pulls the opposite way (GitHub merge queue through an organization move) and the report's C1 says "NOT GitHub merge queue".
- **C2** (verdict reuse per tree): implement-test-performance yud7rc; ci-runtime-and-cost jd4qle (bug in the reuse evidence); fleet-flaky-tests ehug6z (the missing tests for the reused-pre-commit-evidence scenarios).
- **C3** (shrink suite, ration mutation): fleet-mutation-testing-rule-26 (all six children) and mutation-testing-keystone (cross-tenant livespec-mutreal, no children here). implement-test-performance's "make the suite faster" assertion is the same goal from the runtime side.
- **C4** (turn and gate duration): implement-test-performance (charter), rgr-cycle-agent-efficiency (stale proposal, no epic), delegated-commit-time-gates (charter), gate-job-resources (gate parallelism, charter), ci-runtime-and-cost 5y3luz, ci-cache-optimization zbu7jf, token-spend-analysis 3su2nx (measurement).
- **N1** (gamingpc idle): no plan owns it. Only gate-job-resources caq7uh (retires the reproduction lane) and kubernetes-observability 7nvfjk (dead-man trigger) touch gamingpc.
- **N2** (capacity and per-node budget): gate-job-resources wirn53; ci-runtime-and-cost 6e5pyj, mtvxde, 2aelab, lzkzwb, 5wewi2, samgg2; gmktec-pool-member-obligations z7nfhx, a2kwn3, hatvwq; gmktec-factory-placement zsbvp3; homelab-k8s-worker-nodes u45iv6, p4cv4l, t5ervh, qotekb; radar-and-deterministic-admission hvfc6c, 7exa37; dev-host-test-gate-load gvo7fa; kubernetes-observability y5ewfc; ci-cache-optimization e2gv6n, n622ze. Closest to true duplicates: wirn53 vs 6e5pyj (one per-node CPU budget deriving churn slots), and hatvwq vs e2gv6n/n622ze (warm caches on gmktec).
- **N3** (dev host pressure): dev-host-test-gate-load ie7fas, cvef23, ctmtfg, 5lhafp; delegated-commit-time-gates sewnfp; dev-host-disk-retention 7tfa3x, 64ik6g, hlyayb; radar-and-deterministic-admission z6yf2a; kubernetes-observability exx6f5; software-factory-gap-map (charter-only: dispatcher off vmi3006760). Outside this repo: orchestrator dispatch-control-plane (bd-ib-k6dqwc).
- **M3** (gate durations on gate events): no carrier. Nearest: kubernetes-observability 2mp63s, token-spend-analysis 3su2nx, dev-host-test-gate-load q4ahay and research note 010.
- **M4** (CI runs and durations): ci-runtime-and-cost bt2cnw and k9mr (both the uint64-wrapped duration_ms: likely one defect filed twice), wnwwsl, r6r3o2, 5ua57h, wza24d; kubernetes-observability ja7bv4; gmktec-pool-member-obligations xnie; rop-railway-enforcement 8o8e.23 (same exporter duplication as 5ua57h).
- **M2** (factory CPU by repo and stage): no carrier. kubernetes-observability (charter-only raw pod CPU), console-factory-build-telemetry bfvbsw.1 (console stage spans). Outside: orchestrator factory-run-correlation-observability (bd-ib-qfv9).
- **Y2** (timeouts in refresh and gate steps): fleet-flaky-tests h2i4u2; dev-host-test-gate-load q4ahay. Outside: orchestrator sandbox-commit-gate-ceiling (bd-ib-qy5wol), stall-watchdog-false-kills (bd-ib-laf735), factory-run-wall-budget (bd-ib-hqt3s5).
- **Y3** (rebase conflicts): ci-runtime-and-cost mpv6bp, oim422 (two files every branch rewrites). Outside: orchestrator publish-draft-green-work-loss (bd-ib-acrr56), pr-refresh-reproof-relevance (bd-ib-ku7phe).
- **Y4** (gate check failures in runs): dev-host-test-gate-load fmprfr, wj45qt; fleet-flaky-tests dpkz32, e34ks3. A scattered family of "test pins a committed literal" items sits in four plans: fmprfr (dev-host-test-gate-load), mrbvgm (dev-host-disk-retention), xazlro (expedited-incident-hardening), egyvwa (expedited-incident-response-flag), with symfx2 (ci-runtime-and-cost) as the general rule.
- **Y5**: implement-test-performance charter-only. Outside: orchestrator checkpoint-commit-hook-failures (bd-ib-hcwmnq), factory-test-first-enforcement (bd-ib-q622ls).
- **X: red master**: red-master-self-healing (tig7vu, 7uq5ri, myltix, reslr6, bznobs, yilv6p, 4xrhck); ci-runtime-and-cost 2yne2h, c7efqa, xtofr3, qzw2gf; expedited-incident-hardening okij46; stale-base-merge-options (charter); expedited-incident-response-flag (charter).
- **X: flaky tests**: fleet-flaky-tests (17 children); expedited-incident-hardening rs6o3q, dqndbz, ek36t5; expedited-incident-response-flag xdt4ue.
- **X: CI infra failures and fetches**: ci-runtime-and-cost 227glz and vrpwyw (both replace a zero-job ghost run: 15 min close/reopen vs 30 min fresh run, likely overlapping), cetyrq, ybnep5, khlrw3, fc4dzb; gate-job-resources reuqym and ci-cache-optimization zbu7jf (both change the gate Job's fetch source); ci-cache-optimization uqmdor, ddcvyd.
- **No dev-tooling plan or child carries**: Y1, M1 (owner named in the report: bd-ib-2h6cfl), M5 (radar rzefod is a different board), G1 (livespec has an unassigned plan `github-request-budget-discipline`; orchestrator `dispatcher-run-watch-cost` bd-ib-k7ymgx; driver-claude `github-rate-limit-guard-false-positives`).
