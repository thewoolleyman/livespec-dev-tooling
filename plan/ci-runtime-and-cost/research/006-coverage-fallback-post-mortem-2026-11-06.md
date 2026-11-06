# 006 — Post-mortem: the silent coverage-reuse fallback (2026-11-06)

Work item: livespec-dev-tooling-npysxq. Plan: ci-runtime-and-cost (livespec-dev-tooling-ib3oe3), Definition of Done
assertions 5 and 6. Written 2026-11-06 by the plan's own session on the maintainer's ruling, recorded verbatim in the
plan epic's scope event of 2026-11-06T05:48:01Z.

How this note is laid out:

1. Summary.
2. Measured cost: CI runner-minutes, then LLM tokens, with the queries that reproduce each figure.
3. Timeline and missed catch points.
4. Fleet sweep: every repository in the livespec fleet manifest.
5. Solutions: how each one was evaluated, which were adopted, and their carriers.
6. Corrections to the evidence pack.

Appendix A is the evidence pack both reviewers received, verbatim. Appendix B is the GPT-6-Astra review, verbatim, and
Appendix C is the Fable review, verbatim. The synthesis in sections 1-6 was written after both reviews were complete.

## 1. Summary

From commit 34f370e1 (livespec-dev-tooling-xluwqj, merged 2026-11-04T02:39:52Z as livespec-dev-tooling#3346) to the
first master run that reused again (run 42180192839, created 2026-11-06T07:20:11Z), every livespec-dev-tooling CI
run's `check-coverage` job re-ran the whole test suite. The job also passed green every time, so nothing failed.

- **What 34f370e1 changed.** It made the CI consumer require a provenance receipt that `ci.yml` never shipped.
- **A second defect.** The receipt was stamped before the per-file check's vanished-source rewrite changed `.coverage`.
  That made the receipt stale on any run whose tests left a vanished measured file.
- **The orchestrator.** The same class ran in livespec-orchestrator-beads-fabro from 2026-11-01T21:28:51Z to
  2026-11-04T11:53:59Z.
- **Cost.** Together about 23,900 runner-minutes above a report-only pass, almost all of it on the self-hosted k3s pool,
  plus about $109 of LLM spend on handling it.
- **The fixes.** livespec-dev-tooling-jerpfe (livespec-dev-tooling#3576) ships the receipt, and
  livespec-dev-tooling-x3lvve (livespec-dev-tooling#3587) stamps it last. Run 42186082097 proves both together on master.
  Its producer dropped 6 vanished files, its consumer reused in 0.8 min, and the data's sha256 `bd6285a2…1509` equals
  the receipt's digest.

**Root cause.** Both independent reviewers name the same root cause. The CI consumer's fallback is a designed GREEN
path, and no execution contract is enforced. A reuse failure therefore produces a correct verdict at about 15 times the
cost, with one log line as its only trace. The two defects above were only the triggers. Both reviewers also agree that
the two fixes restore the known handoff but leave the class open. At 775ca47c the consumer still has a green
full-suite branch. `test_check_coverage_reuse_stamp.py` still asserts that pytest RUNS under `GITHUB_ACTIONS=true` when
the receipt is missing. `ci.yml` still calls the fallback "slower, never wrong". No test reads `ci.yml` for the receipt
wiring.

## 2. Measured cost

### 2.1 CI runner-minutes (npysxq assertion 1)

"Waste" is time above a counterfactual report-only pass of 0.6 min per job; it is a MODELLED figure over measured
durations (Astra, Appendix B §5.3). Against the measured Nov 1-4 reuse median of 1.05 min the dev-tooling figure is lower
by about 190 min.

| Repository | Window | Jobs | Minutes | Waste | Runner split |
|---|---|---|---|---|---|
| livespec-dev-tooling | 34f370e1 merge 2026-11-04T02:39:52Z → creation of run 42180192839, 2026-11-06T07:20:11Z | 439 fallback `check-coverage` jobs | 8,671.3 | 8,409.3 | all self-hosted `livespec-dev-tooling-k3s`; 0 hosted |
| livespec-orchestrator-beads-fabro | 704a96ded via #4121, 2026-11-01T21:28:51Z → #4366, 2026-11-04T11:53:59Z | 941 fallback legs (553 nonroot, 388 root) | 16,034.8 | 15,470.2 | k3s 15,311.1 waste over 939 jobs; hosted 159.1 waste over 2 jobs (unbilled, public repo) |
| Total | about 4.8 repository-days (the two windows overlap by about 9 h) | 1,380 | 24,706.1 | 23,879.5 | k3s about 23,720; hosted about 159 |

The dev-tooling row is the pack's census (460 runs read, 419 fallback jobs, 8,263.3 min, 8,013.3 waste, to about
05:45Z) plus an extension this note made to reach the window end that npysxq assertion 1 names. The extension read the
`check-coverage` job of all 21 `ci.yml` runs created from 05:45:00Z to 07:20:11Z. 20 of those jobs fell back: 408.0 min
in total, 396.0 above 0.6 min, all on k3s. The one that reused, job 127763227768 at 0.52 min, belongs to jerpfe's own PR
run. Jobs 127768043985 and 127772870593 were checked by log: each prints the "ignoring existing .coverage without a
matching provenance marker" line and then runs 7,829-7,830 tests. If the pack's census ran past 05:45:31Z, run
42170297011 (15.92 min) is counted twice; that is a bound of 15.3 waste minutes. Not counted: PR-head runs after
07:20:11Z, until x3lvve merged at 08:12:55Z, whose producer rewrote the data.

Before the break, 3,074 dev-tooling consumer jobs (2026-09-06 to 2026-11-04) all reused. #3346's own pre-merge consumer
(job 126346804910, 14.67 min) is outside the window and adds 14.1 waste minutes.

What the waste cost: the k3s pool's capacity, of which dev-tooling has a ceiling of 12 runners, and the binding limit on
master CI. It also lengthened the coverage dependency chain by about 16-17 min per run. Its effect on whole-PR wall time
depends on the rest of the job graph and was not separately measured (Astra §5.7).

Queries that reproduce the figures (all `gh api --cache 1h`, owner `thewoolleyman`):

```text
# Runs in a window (repeat per repository; paginate):
gh api --cache 1h --paginate \
  "repos/thewoolleyman/<repo>/actions/workflows/ci.yml/runs?created=<from>..<to>&per_page=100" \
  --jq '.workflow_runs[]|[.id,.created_at,.event,.head_sha]|@tsv'
# Each run's consumer job, its runner label and duration (orchestrator: names "check-coverage (root|nonroot)"):
gh api --cache 1h "repos/thewoolleyman/<repo>/actions/runs/<run_id>/jobs?per_page=100&filter=latest" \
  --jq '.jobs[]|select(.name|startswith("check-coverage"))|[.id,.conclusion,.started_at,.completed_at,(.labels|join(","))]|@tsv'
# Which branch a job took:
gh api --cache 1h "repos/thewoolleyman/<repo>/actions/jobs/<job_id>/logs" | grep -E ':: check-coverage: |passed in'
# dev-tooling fallback line:  ":: check-coverage: ignoring existing .coverage without a matching provenance marker ..."
# orchestrator fallback line: "no canonical per-file verdict; running the suite"
# Minutes = completed_at - started_at; waste = minutes - 0.6 per fallback job; split on the labels column.
# Window boundaries: commits/<sha>/pulls for the merge times of #3346, #4121, #4366.
```

### 2.2 LLM tokens and spend (npysxq assertion 2)

| Component | Measured |
|---|---|
| Direct handling: sessions that diagnosed, measured, filed or fixed the class | $109.16 under rule R1 (floor R0 $45.87, ceiling R2 $386.41); 1,113 deduped responses. By seat: ci-runtime-and-cost $56.36 (+$8.36 subagents), legacy-coordinator-agent $32.29, legacy-dispatcher-agent $6.40, `claude -p` judges $2.73, implement-test-performance $2.58, expedited-incident-response-flag $0.26, kubernetes-sandbox-backend $0.17. No factory run worked on an incident item. |
| Token cost that scales with CI duration | None found ($0). The factory's pr, pr_route, verify_pr and publish_draft nodes are scripted with no agent turn. Of 229 seat CI watches, the 178 in the foreground hold one tool call, and the 51 in the background cost one wake each. Caches use a 1 h TTL. This is scoped to those surfaces only; seat ticks that re-poll are unmeasurable (below). |
| Research note 005's analysis runs | $27.14 in total, of which about $0.70 was about this defect, by share of non-blank lines |
| This note's two reviews | Not yet priced; they are in scope of the next spend read and add to R1 |

How to reproduce: scan the Claude transcripts (`~/.claude/projects/**/*.jsonl`) dated from 2026-11-04T02:39Z, deduped
by `message.id` with a uuid fallback (see `.ai/claude-transcript-usage-dedupe.md`). Price them with
`livespec_dev_tooling/llm_spend.py`, splitting 5 m and 1 h cache writes as `emit_spend.claude_cost` does.

The scan's keyword set is `jerpfe|x3lvve|npysxq|xevgsx|reuse-token|livespec-coverage-reuse-token|provenance marker|duplicate suite|coverage-reuse`.
The rules that turn matches into the three figures:

- **R1:** an assistant response counts from the first keyword in its turn. The keyword must appear in the prompt or the
  brief, or in the session's own text, thinking or tool input. A keyword seen only in tool output does not count,
  because the code contains these strings; it caused $51 of false positives in spot checks.
- **R0:** only responses whose own blocks carry a keyword.
- **R2:** whole keyword turns.

Cross-check: the same 37 sessions, 2026-11-04T02:39Z to 2026-11-06T07:00Z, total 9,564 responses and $957.74. Honeycomb
dataset `livespec/llm-spend`, queried through the MCP endpoint (COUNT and SUM of cost over those session ids and that
range), gives exactly 9,564 events and $957.74, and nine sessions match to the cent. llm-spend carries no incident tag,
so the cross-check validates dedupe and pricing, not attribution.

Costs that cannot be measured, and the surface each lacks:

1. Seat ticks that re-poll PR status: 746 checks without a watch. No record states each tick's purpose or links a poll to
   the CI duration of the PR it polled.
2. Local and factory-sandbox `just check` runs that also took the fallback: when x3lvve's rewrite fired, or a sandbox ran
   the pair serially. Nothing records which branch a local or sandbox consumer took.
3. Discovery before an incident id existed: there was no tag at discovery time.
4. llm-spend has no incident attribution field.

Reading: tokens were a small share of the cost here. The waste was CI capacity and wall time.

## 3. Timeline and missed catch points (npysxq assertion 3)

Appendix A §2 carries the full timestamped timeline with an evidence id on each row. Every row below is either a catch
point that row shows, or one the reviewers added.

| # | Catch point, and why it missed | Evidence |
|---|---|---|
| 1 | **The fallback is a green path.** `scripts/just/check-coverage.sh` returns success from either branch. `ci.yml` (about line 292) calls the fallback "slower, never wrong", and the orchestrator's `ci.yml` (about line 586) says the same. Nothing fails, alerts or counts it. Both reviewers rank this first. | dev-tooling jobs 126355763498 (first fallback, 11.22 min) and 127725260629 (7,791 tests in 921.67 s), both green |
| 2 | **34f370e1 changed the reuse contract without touching the workflow that feeds it.** `git show --stat 34f370e1 -- .github/workflows/ci.yml` is empty. It was a known, priced-at-zero acceptance, not an unseen side effect: the commit's own comment says "A downloaded artifact without its receipt falls back to normal measurement" (Fable). | commit 34f370e1 |
| 3 | **The same commit rewrote the test to endorse the fallback** (Astra). `test_github_actions_consumer_trusts_the_run_scoped_artifact` became `test_github_actions_consumer_rejects_unstamped_partial_artifact`, which asserts that pytest RUNS under `GITHUB_ACTIONS=true`. It is still in `tests/livespec_dev_tooling/test_check_coverage_reuse_stamp.py` at 775ca47c. | 34f370e1 diff |
| 4 | **The hand lane skipped the factory's review nodes.** 34f370e1 was a P1 carrier HAND-LANDED under the expedited-incident exception. livespec-dev-tooling#3346 had 0 reviews and was merged by `thewoolleyman-factory-bot[bot]`. It ran none of the factory's `dod_gate`, `review`, `proof_capture` or `proof_verify` nodes. Its commit and push gates and its PR CI did run. Its own pre-merge consumer fell back (14.67 min, fallback line) and passed. Both reviewers note that a reviewer would have had to price the comment in #2, so with #1 fixed this lane needs no reviewer for this class. | `gh api pulls/3346` (reviews: 0); job 126346804910 |
| 5 | **The first master run after it jumped from about 1-2 to about 11-19 min, and nothing alarmed.** No CI-runtime regression signal exists. A p50 alarm would also have missed the second defect, which hit a minority of runs (Astra). | jobs 126352561400 (2.32 min, last reuse) and 126355763498 (11.22 min) |
| 6 | **The orchestrator's identical class was fixed without a fleet sweep.** bd-ib-xevgsx was found and fixed on 2026-11-04 by this plan's seat, about 9 h after dev-tooling broke. No sweep of the same shape was filed. | livespec-orchestrator-beads-fabro#4366; transcript sessions 6c43b4fb, ee5317b5 |
| 7 | **The fix was filed into a lane that could not carry it.** livespec-dev-tooling-jerpfe was filed on 2026-11-04 at 23:48:56Z with the cause and a measured saving. It was queued in the factory lane, which cannot edit workflows, and left as a ready, low-priority carrier. | jerpfe `created_at` and its Context |
| 8 | **A measured, top-ranked fix stayed unlanded for about 30 h.** Research note 005 (livespec-dev-tooling#3490, merged 2026-11-05) named the cause and ranked its fix FIRST in both the Fable and the GPT-6-Astra report. The 2026-11-05T19:43Z recovery order put it THIRD, and the R301 dispatch freeze then held it. About 60% of the dev-tooling waste accrued after the cause was in the ledger (Fable). | research/005 §1.4, §M, Appendix B §1; plan scope event 2026-11-05 |
| 9 | **The coordinator first read the symptom as runner queueing.** Measurement showed jobs starting within 15-60 s; the tail was the serial pair re-running the suite. | coordinator message, 2026-11-06 ~05:3xZ |
| 10 | **The incident was mis-dated.** The start was taken from `git log -S` on the token string, which finds where the string first appeared, not where the behaviour changed. That date was then extrapolated about 2.5x to the maintainer. The mis-dating still sits in a committed file: `.livespec-workflow-edit-exemption` on master (from 70884cb7) says the suite re-ran "since the sc0z provenance gate (81defbb9, 2026-09-06)" (Fable). | jerpfe comment 05:38:36Z; `.livespec-workflow-edit-exemption` |
| 11 | **Two P1 CI changes collided, and only full-suite CI caught it.** z3wy33 and jerpfe each constrained the other's steps. Workflow-only commits take `scripts/just/check-pre-commit-doc-only.sh`, which runs no pytest. **Why the push gate also missed it is NOT established**: `check-pre-push.sh` intends to run the full aggregate unless a green token or cluster delegation applies, and neither reviewer could name the path that skipped `test_incident_ci_omission_wiring.py`. That open question is carried by solution S3. | job 127749278476: 1 failed / 7,824 passed |
| 12 | **A green PR proof covered only one of the two breakages.** jerpfe's proof run had no vanished file. The first master run after it still fell back: data hash fa620951… against receipt 0905399b…. | run 42178905676, job 127770178810 |
| 13 | **The producer's own vanished-source warning was never joined to the consumer's branch line.** Two warnings sat in two jobs of one run for two months (Fable M3). The producer also never checked its stamped receipt against the data immediately before upload (Fable M2). | producer logs, about 33% of 60 sampled |
| 14 | **Overseer's guard fails too late, on a log string.** livespec-overseer is the only repository whose CI fails a fallback, but it fails AFTER the duplicate suite has run (Astra). | livespec-overseer `ci.yml`, about lines 340-360 |
| 15 | **A red job is not a maintainer notification**, and the telemetry export runs outside `ci-green` with no missing-evidence check (Astra). | dev-tooling `ci.yml` `export-telemetry` |

## 4. Fleet sweep (npysxq assertion 4)

The sweep covers every repository named in `livespec/.livespec-fleet-manifest.jsonc` (22 repositories). It asks whether
any reuse, cache or dedup path in the repository's CI falls back to the full cost without failing.

The paths found are of two kinds:

- **MANDATORY reuse:** a consumer of an upstream producer in the same run, where a miss means a defect.
- **OPPORTUNISTIC caches:** a cold cache, where a miss is legitimate and a green rebuild is the right outcome.

The coverage pairs were read from each repository's latest default-branch consumer log on 2026-11-06. The other paths
were read from the workflows and scripts on each default branch by a read-only sweep agent (9 gh calls).

| Repository | Coverage producer/consumer pair | Does a fallback fail the job? | Evidence (job id: log line) | Other reuse, cache or dedup paths |
|---|---|---|---|---|
| livespec-dev-tooling | yes, receipt-gated since jerpfe + x3lvve | **no**: a green full-suite branch remains | 127791902358: ":: check-coverage: reading .coverage from check-per-file-coverage's clean run, provenance marker matches the current tracked tree (no duplicate suite run)"; the fallback is green in 126355763498 | uv `actions/cache`, buildx gha cache, `green_token` pre-push skip: opportunistic or local only |
| livespec-orchestrator-beads-fabro | yes (root/nonroot, canonical per-file verdict) | **no**: "no canonical per-file verdict; running the suite" is green | 127734055600: ":: check-coverage: reading the canonical per-file verdict"; the fallback is green in 124866358970 | pool uv/sccache, `green_token`: opportunistic or local only |
| livespec-overseer | yes, receipt-gated | **yes**, but only AFTER the duplicate suite has run | 127720337684: ":: check-coverage: reading current .coverage from matching provenance marker; no duplicate suite run"; `ci.yml` about lines 340-360 grep the log and exit 1 | `green_token`: local only |
| livespec | yes, bare `.coverage` | **no** | 127719149210: ":: check-coverage: reading existing .coverage (produced by check-per-file-coverage); no duplicate suite run" | uv `actions/cache` (hosted lane), `green_token`: opportunistic |
| livespec-driver-claude | yes, bare `.coverage` | **no** | 127718664258: the same "reading existing .coverage" line | `green_token`: local only |
| livespec-runtime | yes, bare `.coverage` | **no** | 127265574644: the same "reading existing .coverage" line | `green_token`: local only |
| livespec-orchestrator-git-jsonl | yes, bare `.coverage` | **no** | 127717862928: the same "reading existing .coverage" line | `green_token`: local only |
| livespec-driver-codex | reversed pair, bare `.coverage` | **no** | 127717995556: ":: check-per-file-coverage: reading .coverage from check-coverage's clean run (no duplicate suite run)" | `green_token`: local only |
| livespec-driver-pi | reversed pair, bare `.coverage` | **no** | 127717856078: the same reversed-pair line | `green_token`: local only |
| livespec-console-beads-fabro | none (cargo llvm-cov) | n/a | — | Fuzz-target seed: `seed-fuzz-target.sh` is "fail-soft and always exit 0" (`ci.yml` about lines 709-711). Job 126864631143 logs `seed-fuzz-target: MISS (toolchain key differs: seed nightly-1.100.0-nightly@cargo-fuzz-0.13.2, job nightly-1.101.0-nightly@cargo-fuzz-0.13.2)` and is green, so a stale seed builds cold on every run with no alert. Opportunistic, but a PERSISTENT miss is this class's shape |
| homelab | none | n/a | — | `deploy-record` artifact from apply to verify (`owner-deploy.yml` about lines 67-97): conditional by design. Verify runs without it only when apply did not run |
| openbrain | none | n/a | — | `setup-node` pnpm cache: opportunistic |
| resume | none | n/a | — | `setup-node`, plus a `hashFiles` gate on the Playwright step: opportunistic |
| dolt-server | none | n/a | `ci.yml` has no cache, artifact or reuse step | — |
| hetzner-xubuntu-info | none | n/a | `ci.yml`: `concurrency` and `ci-green` only | — |
| fabro-hosts, gmktec-xubuntu-info, hp-xubuntu-info, local-llm, otel-collector, poweredge-xubuntu-info, vps-info | no workflows | n/a | `gh api repos/thewoolleyman/<repo>/contents/.github/workflows` returns 404 | — |

Fleet-wide pool tiers: the k3s hook template (`ci-runner/k3s/phase2/arc/hook-pod-template.yaml`) gives every routed job
sccache and a warm uv seed, and both fail soft. Degradation shows only in the cache telemetry spans and in the six-hourly
`ci-cache-negative-tests.yml`. Neither of those fails a job or raises to the maintainer.

**The verdict for mandatory paths.** Eight repositories have a mandatory coverage-reuse path whose fallback does not fail
the job. One, livespec-overseer, fails it, but only after paying for the fallback. Both the orchestrator and dev-tooling
CI fell into this class this month. The six bare-`.coverage` repositories reuse today only because nothing has yet
required provenance of them: a change like 34f370e1 in any of them would put it into silent fallback.

## 5. Solutions (npysxq assertions 6 and 7)

### 5.1 How each candidate was evaluated

Each candidate is rated on four things:

- whether it PREVENTS, FIXES or RAISES TO THE MAINTAINER a recurrence of the class "a reuse, cache or dedup path that
  silently falls back to the full cost";
- whether any step relies on a person noticing;
- what it costs;
- what the two reviewers concluded (Appendices B §3 and C §3).

| Candidate | Effect | Relies on a person noticing? | Reviewers | Disposition |
|---|---|---|---|---|
| A. Fail-on-fallback: the reuse fallback becomes a failing verdict, not a green log line | PREVENTS | No | Both: adopt FIRST. Astra: the consumer must fail BEFORE it starts the suite, so overseer's after-the-fact grep is the right policy implemented too late. Fable: let the script itself refuse in CI, with no knob to unset. | **Adopted as S1, S2 and S6.** |
| B. Fleet-wide conformance check of producer and consumer artifact contracts | PREVENTS, at commit time, the missing-file and wiring breaks | No | Both: adopt. Repo-local tests now, the fleet check armed only after adoption. B alone cannot see a stale receipt; A catches that. | **Adopted, merged with E and I, as S3** (repo-local). The fleet arm is part of S6. |
| C. CI-runtime regression alarm in Honeycomb | RAISES | The alarm does not, if it is delivered, but a dashboard does | Both: secondary. Astra: a p50-tripling rule CANNOT see a minority fallback like the second defect, so explicit branch outcomes must lead. Fable: read durations from the GitHub jobs API, which is outside the shared ~100-queries/h Honeycomb budget. | **Adopted as S4's backstop**, sourced from the GitHub jobs API per job and runner label, using tail and absolute excess rather than p50 alone. Honeycomb carries the outcome span; it is not the alarm's source. |
| D. Waste reporting in the coordinator tick | RAISES only through a coordinator turn | **Yes**: it depends on a coordinator reading it, and narration is what failed at 05:3xZ | Both: reject as a primary control. | **Rejected as a control.** At most a channel that relays S4's deterministic output, never a measurement of its own. |
| E. Run the ci.yml-reading tests early when workflow or invoked scripts change | PREVENTS catch point 11 | No | Both: adopt. Fable verified that the doc-only pre-commit path runs no pytest. | **Adopted in S3.** |
| F. A reuse-contract change must touch its workflow | "Touch" proves nothing | Yes | Both: reject the touch rule. Verification is B. | **Rejected; covered by S3.** |
| G. Mechanical fleet sweep obligation | RAISES exposure; reduces latency (about 6-12 h of 51 h here) | Partly: deciding that a fix is "fleet-class" is a judgement | Fable: adopt later as a coordinator rule. Astra: adopt with applicability filtering, as one sweep with per-repo dispositions. | **Adopt later.** S6 performs this sweep for this class. The general rule is relayed to the coordinator for `.ai/coordinator-duties.md`. |
| H. Hand-lane review parity | Only mechanical parity is mechanical | Review: yes | Both: mechanical parity now, review parity secondary. With A in place, this class needs no reviewer. | **Adopted through S1/S2:** the consumer's refusal runs in every lane, so P1 hand-landing cannot waive it. Review parity is not adopted here. |
| I. A reuse proof covers every producer path that writes data after stamping | PREVENTS stale-receipt regressions | No, once it is a test | Both: adopt; x3lvve did this in substance. | **Adopted in S3** (a real-reporter fixture with a vanished source). |
| J. "Broken since X" claims cite a log before and after X | Prevents mis-reporting only | Yes (a reporting rule) | Both: adopt as a rule. | **Relayed to the coordinator** as a coordinator-duties rule. It is not a mechanical control of the class. |
| K. Structured reuse outcome, delivered alert, monitor health (added by both reviewers) | RAISES automatically, including a green but expensive fallback anywhere in the fleet | No, given a delivery receipt and a heartbeat | Both: adopt in the first set. Use a versioned outcome and reason (`reused`, `missing_receipt`, `data_digest_mismatch`, `tree_mismatch`, `producer_failed`), not a scraped log line. | **Adopted as S4.** |
| L. Executable incident ownership: lane-capability admission and age escalation (Astra) | PREVENTS silent abandonment of a detected regression; RAISES a blocked repair | No | Astra: adopt with K. Fable puts this under catch points 7-8. | **Adopted as S5.** |
| Local dispatcher parity (Fable's L) | PREVENTS the local and sandbox double suite | No | Fable: after A is proven in CI. | **Deferred into S6:** reconsidered after S1 proves the shape. |

**Mandatory reuse and opportunistic caches need different policies** (Astra). A coverage consumer whose upstream
producer succeeded must never fall back, so every miss there is an invariant violation (S1, S2, S6). A cold dependency
cache can legitimately miss. For those, S4 alerts on a declared budget being breached, or on a PERSISTENT miss such as
console's fuzz seed, not on every miss.

### 5.2 The adopted solutions and their carriers

The carrier ids are recorded on livespec-dev-tooling-npysxq and in the plan epic's carrier-map event for assertion 6,
which is written once the items are filed. That keeps this note free of ids that would otherwise need a second edit.

Adopt before arm (46c5dab): each repository adopts and proves its own consumer refusal, and only after that is a
fleet check armed. Every carrier's Definition of Done observes its solution against a DELIBERATELY INDUCED fallback.

| Id | Solution | Prevents, fixes or raises | Owning repository | Carrier |
|---|---|---|---|---|
| S1 | **The dev-tooling CI coverage consumer cannot start the suite.** In CI, `check-coverage` treats a missing or mismatched receipt or data as a named contract failure and exits non-zero BEFORE any pytest process. A standalone local run keeps measuring. The test that endorses the fallback (`test_github_actions_consumer_rejects_unstamped_partial_artifact`) is replaced, and `ci.yml`'s "slower, never wrong" doctrine is removed. | PREVENTS | livespec-dev-tooling | filed after this note merges |
| S2 | **The same refusal for the orchestrator's root/nonroot consumers** (the "no canonical per-file verdict; running the suite" branch). | PREVENTS | livespec-orchestrator-beads-fabro | filed after this note merges |
| S3 | **The handoff contract is tested, and tested early.** A test reads `ci.yml` and asserts that the producer uploads, and the consumer downloads, every file the consumer's reuse requires. A real-reporter fixture with a vanished source asserts that the receipt matches the FINAL bytes. The ci.yml-reading tests run at pre-commit whenever a workflow or a `scripts/just/*.sh` file is staged. First, it establishes why the push gate missed job 127749278476's failure. | PREVENTS | livespec-dev-tooling | filed after this note merges |
| S4 | **Reuse outcomes are recorded and delivered to the maintainer.** Each mandatory consumer emits a structured outcome. A scheduled fleet detector reads those outcomes and the GitHub job durations. It raises to the maintainer on any mandatory-consumer violation, on missing outcome evidence, or on a persistent opportunistic miss or duration excess, and it checks its own delivery and heartbeat. | RAISES | livespec-dev-tooling | filed after this note merges |
| S5 | **A detected regression cannot be lost in a lane that cannot carry it.** The admission valve already refuses a workflow-editing item and leaves it `ready` (orchestrator Scenario 48), which is exactly where jerpfe sat. The gap is escalation: an item refused for the attended-host route, and still `ready` past a committed age bound, is raised to the maintainer with its refusal reason and age, including while a dispatch freeze is in force. | PREVENTS loss; RAISES a blocked repair | livespec-orchestrator-beads-fabro | filed after this note merges |
| S6 | **Fleet rollout, then arming.** After S1 and S2 are proven, file and land the same refusal in livespec, livespec-driver-claude, livespec-runtime, livespec-orchestrator-git-jsonl, livespec-driver-codex and livespec-driver-pi. Move livespec-overseer's check ahead of the suite. Then arm a fleet conformance check that every mandatory coverage consumer refuses a fallback. Reconsider local dispatcher parity there. | PREVENTS, fleet-wide | livespec-dev-tooling | filed after this note merges |

Not adopted as mechanical controls, with the reason for each:

- **D:** it depends on a coordinator turn.
- **F:** a touch rule proves nothing.
- **Review parity:** it depends on a reviewer noticing.
- **G and J:** they are rules for people. They are relayed to the coordinator, and S6 performs the sweep G describes for
  this class.

## 6. Corrections to the evidence pack (Appendix A)

Both reviewers corrected the pack, and every correction below is accepted.

1. **"Nothing is extrapolated" overstates (Astra).** Job durations are measured, but "waste" subtracts a modelled 0.6 min
   or 1.05 min reuse duration, and the token attribution rests on rules R0-R2. §2 labels both accordingly.
2. **The window total was "about 4.8 days" (Astra).** That figure is 4.8 REPOSITORY-days of fallback across two
   overlapping windows, not the incident's elapsed time.
3. **The dev-tooling census stopped at about 05:45Z (Astra).** It is extended in §2.1 to the window end that npysxq
   assertion 1 names.
4. **"20 of 60" is a sample fraction (Astra),** not the exact residual rate.
5. **"About 16-17 minutes on every PR's critical path" is too categorical (Astra).** It lengthened the coverage
   dependency chain; whole-PR wall time was not separately measured.
6. **"Nothing else distinguishes them" (pack §1) is wrong (Fable).** Duration, the pytest banner and the per-file table
   all distinguish the two branches, which is why a duration backstop can work at all.
7. **34f370e1's workflow omission was a priced-at-zero acceptance, not an oversight (Fable).** The commit's own comment
   states the fallback.
8. **The second defect was latent, not independent, in activation (both).** 98a15fb5's rewrite was harmless while the
   receipt bound only the tree. 34f370e1's binding to the data bytes activated it: one commit opened both holes.
9. **The mis-dating survives in a committed file (Fable).** `.livespec-workflow-edit-exemption` on master repeats
   "since … 81defbb9, 2026-09-06". The file is overwritten by the next workflow-edit exemption, and this note is the
   correcting record.
10. **Overseer's guard is the right policy implemented too late (Astra).** It fails after the duplicate suite has run,
    and it keys on a log string.
11. **The fleet table needed a "does a fallback fail the job" column (Fable).** §4 adds it, and §4 also extends the sweep
    from 10 repositories to all 22 in the manifest.
12. **Catch point 10's push-gate mechanism is unestablished (both).** It is carried by S3.
13. **"56 ci.yml-reading test files" depends on definition.** Fable counted 62 files under `tests/` that mention
    `ci.yml`. S3 sizes the selection from its own enumeration.

## Appendix A — The evidence pack (verbatim)

Given unchanged to both reviewers. It was first stored as a comment on livespec-dev-tooling-npysxq at 2026-11-06T08:19:30Z, and it is reproduced here from that comment, starting at its title.

### Evidence pack: the silent coverage-reuse fallback (post-mortem livespec-dev-tooling-npysxq)

Prepared 2026-11-06 by plan ci-runtime-and-cost (livespec-dev-tooling-ib3oe3). Both independent reviewers receive this
same pack and the same question. Every figure below is MEASURED from GitHub job data, CI logs, git history, the beads
ledger, or Claude transcripts reconciled against the `llm-spend` Honeycomb dataset. Nothing is extrapolated.

#### 0. The maintainer's direction (verbatim, 2026-11-06 ~05:5xZ)

"This error and lack of reporting and visibility burned egregious amounts of tokens and time unnecessarily over many
weeks. Open a dedicated work item in ci-runtime-and-cost plan that does an exhaustive post mortem of this egregious
failure, with astra and fable agents offering reviews, and offers mechanical and systematic solutions so that such a
ridiculously expensive screw-up cannot happen again without being prevented, fixed or raised to my attention. This
needs to be in the definition of done for the plan."

The maintainer's "over many weeks" came from an early mis-dating; section 2 gives the measured window.

#### 1. The mechanism

The livespec fleet's repositories run a full test suite under coverage twice in CI: a per-file 100% gate and an
aggregate 100% gate. To avoid paying for the suite twice, they use a PRODUCER/CONSUMER pair.

In livespec-dev-tooling `.github/workflows/ci.yml`:
- Job `check-per-file-coverage` (the producer) runs `scripts/just/check-per-file-coverage.sh`. That script runs the
  full pytest suite with `--cov`, then runs `python -m livespec_dev_tooling.checks.per_file_coverage`, and uploads
  `.coverage` as artifact `coverage-data`.
- Job `check-coverage` (the consumer, `needs: [check-per-file-coverage]`) downloads the artifact and runs
  `scripts/just/check-coverage.sh`.
- The consumer has two branches:
  - REUSE: run `coverage report --fail-under=100` on the producer's data, taking about 0.6-1 min.
  - FALLBACK: run the whole suite again, taking about 15-20 min.
  - Either branch can PASS green. The consumer logs one line naming which branch it took, and nothing else
    distinguishes them.

The provenance receipt:
- Commit 81defbb9 (livespec-dev-tooling-sc0z, 2026-09-06) added a receipt, `.livespec-coverage-reuse-token`. It stops
  a stray `.coverage` left by a focused `pytest --cov` run from being reported as the suite's verdict.
- But 81defbb9 KEPT an unconditional reuse branch for GitHub Actions ("this workflow run's producer artifact"), so CI
  kept reusing.
- Commit 34f370e1 (livespec-dev-tooling-xluwqj, part of the P1 plan expedited-incident-response-flag) removed that
  GitHub Actions branch ("GITHUB_ACTIONS alone is not provenance") and bound the receipt to the data's sha256.
  It did NOT change ci.yml, so the receipt never reached the consumer job.
- From that commit on, every CI consumer logged ":: check-coverage: ignoring existing .coverage without a matching
  provenance marker (a focused pytest --cov run leaves one behind); running the clean suite", then re-ran the suite
  and passed green.

A second, independent defect behind the first:
- Even with the receipt shipped, the producer stamped it BEFORE running `per_file_coverage`.
- That check has a vanished-source rewrite (livespec-dev-tooling-5xh8, 98a15fb5, 2026-09-06): whenever a measured file
  has no source at report time, for example uv's transient interpreter-probe files under `/__w/_warm/uv/.tmp*/python/`,
  it erases and rewrites `.coverage`.
- So the receipt was stale on every such run. That is 20 of 60 sampled producer logs (33%).

#### 2. Timeline (UTC, with evidence ids)

| When | What | Evidence |
|---|---|---|
| 2026-08-17 | Producer/consumer chain added to dev-tooling ci.yml; consumer reuses | commit e42e57fc; jobs 96955257257, 100485507582 reuse, 0.85 min |
| 2026-09-06 | Provenance receipt added, CI reuse kept via the GITHUB_ACTIONS branch | commit 81defbb9 (sc0z); weekly sample jobs 101545415027 ... 114611490106 all print the reuse line |
| 2026-09-06 | Vanished-source rewrite added to per_file_coverage (a latent second defect) | commit 98a15fb5 (5xh8) |
| 2026-11-01 13:45 | ORCHESTRATOR repo: the same class begins on a PR branch, consumer logging "no canonical per-file verdict; running the suite" | livespec-orchestrator-beads-fabro job 124866358970; commit 704a96ded |
| 2026-11-01 21:28:51 | Orchestrator fallback reaches master | livespec-orchestrator-beads-fabro#4121 |
| 2026-11-04 02:12 | PR livespec-dev-tooling#3346 (34f370e1, xluwqj) opened, HAND-LANDED as a P1 carrier under the expedited-incident exception. It had 0 reviews and no factory dod_gate, review, proof_capture or proof_verify nodes. | `gh api pulls/3346`: reviews = 0 |
| 2026-11-04 02:24 | #3346's OWN pre-merge CI run already falls back: 14.67 min with the fallback line, and passes green | job 126346804910 |
| 2026-11-04 02:39:52 | #3346 merged by the factory bot (auto-merge) | merge of 34f370e1 |
| 2026-11-04 02:41:24 | Last dev-tooling reuse (a run on a head without 34f370e1), 2.32 min | job 126352561400 |
| 2026-11-04 02:50:44 | First dev-tooling fallback, 11.22 min | job 126355763498 |
| 2026-11-04 ~06:29-16:16 | The ci-runtime-and-cost seat finds and fixes the ORCHESTRATOR instance (bd-ib-xevgsx). No fleet-wide sweep for the same shape is filed. | transcript sessions 6c43b4fb, ee5317b5 |
| 2026-11-04 11:53:59 | Orchestrator fix merged; orchestrator reuses again | livespec-orchestrator-beads-fabro#4366; jobs 126555626953, 127734055600 |
| 2026-11-04 18:06 | implement-test-performance seat notices dev-tooling check-coverage re-running the suite | transcript session 89ab1866 |
| 2026-11-04 23:48:56 | livespec-dev-tooling-jerpfe filed by ci-runtime-and-cost (cause measured, saving ~39 runner-min per run), queued in the FACTORY lane although its own text says factory branches cannot edit workflows, so it must be hand-landed | jerpfe created_at; jerpfe Context |
| 2026-11-05 03:29 | All non-orchestrator factory launches held by an unrelated factory defect (commit_red script missing) | jerpfe comment 03:29:09Z |
| 2026-11-05 07:27-10:28 | Research note 005: an independent GPT-6-Astra report and a Fable report BOTH name the missing receipt as the cause and rank its fix FIRST | livespec-dev-tooling#3490, research/005 §1.4, §M, Appendix B §1 |
| 2026-11-05 15:10 | A docs-only PR's check-coverage re-runs the suite for 50 min; recorded on jerpfe | job 127301542527 |
| 2026-11-05 19:43 | The coordinator's recovery order puts jerpfe THIRD, behind livespec-dev-tooling-5y3luz and bd-ib-eq5ics | plan scope event |
| 2026-11-05 ~20:50 | Coordinator dispatch freeze R301 on: nothing launches unless it serves P1 | coordinator epic 6tgd2z |
| 2026-11-06 ~05:3x | The maintainer asks "Why is CI queuing on dev tooling?" The coordinator's first reading is runner queueing; measurement shows jobs start within 15-60 s, and the long tail is the serial pair re-running the suite | coordinator message |
| 2026-11-06 05:38 | ci-runtime-and-cost re-measures. It MIS-DATES the start to 81defbb9 (2026-09-06), from `git log -S` on the token string; the coordinator extrapolates about 58,000 runner-min to the maintainer | jerpfe comment 05:38:36Z |
| 2026-11-06 ~05:58 | Corrected to 34f370e1 by reading each commit's diff and quoting logs either side; the coordinator retracts | npysxq comments; ib3oe3 scope event 05:58:52Z |
| 2026-11-06 06:21:57 | z3wy33 (P1) merges a test requiring an incident guard on every coverage-member step | livespec-dev-tooling#3572 |
| 2026-11-06 06:42 | jerpfe's first PR CI run is RED: its two new receipt steps lack the guard z3wy33 just required. Neither the commit nor the push gate ran the ci.yml-reading tests; only full-suite CI caught it | job 127749278476: 1 failed / 7824 passed |
| 2026-11-06 07:08:24 | jerpfe merged (ships the receipt as an artifact) | livespec-dev-tooling#3576 |
| 2026-11-06 07:07 | jerpfe PR run reuses in 31 s; its producer logged no vanished file | job 127763227768 |
| 2026-11-06 07:27-07:43 | FIRST master run after jerpfe STILL falls back (16.2 min): the producer logged 6 vanished files, the data hashes to fa620951... but the receipt names 0905399b... | run 42178905676, job 127770178810 |
| 2026-11-06 07:39 | A clean master run reuses in 0.67 min | run 42180192839, job 127774291141 |
| 2026-11-06 07:43 | Second defect filed as livespec-dev-tooling-x3lvve | ledger |
| 2026-11-06 08:12:55 | x3lvve merged (stamp after the per-file check). Its PR run's producer logged 6 vanished files; data sha256 d81bf6e9... EQUALS the receipt, and the consumer reused in 0.4 min | livespec-dev-tooling#3587; run 42184143263, jobs 127780607500, 127786221682 |

#### 3. Measured cost

### 3.1 CI runner-minutes (waste = time above a 0.6 min report-only pass)

| Repository | Window | Runs read | Fallback jobs | Minutes | Waste |
|---|---|---|---|---|---|
| livespec-dev-tooling | 2026-11-04T02:39:52Z → 2026-11-06 ~05:45Z (about 51 h) | 460 of 460 | 419, all self-hosted k3s | 8,263.3 | 8,013.3 (7,826.7 against the measured 1.05 min reuse median) |
| livespec-orchestrator-beads-fabro | 2026-11-01T21:28:51Z → 2026-11-04T11:53:59Z | 611 | 941 legs (553 nonroot, 388 root) | 16,034.8 | 15,470.2 (k3s 15,311.1; hosted 159.1) |
| Total | about 4.8 days of fallback | | | about 24,300 | about 23,500 |

- Both repositories are PUBLIC, so the 2 hosted jobs (about 160 min) were not billed. The cost was the capacity of the
  self-hosted k3s pool: 12 runners for dev-tooling, whose ceiling was the binding limit on master CI. It was also the
  wall time on every PR's critical path, about 16-17 min per dev-tooling run.
- Before 34f370e1, 3,074 dev-tooling consumer jobs (2026-09-06 to 2026-11-04) all reused.
- Residual since jerpfe, until x3lvve: the runs whose producer rewrote the data (about 33%) still fell back.

### 3.2 LLM tokens

| Component | Measured |
|---|---|
| Direct handling (sessions that diagnosed, measured, filed or fixed the class), deduped by message.id, priced from livespec_dev_tooling/llm_spend.py | $109.16 under the primary rule (floor $45.87, ceiling $386.41). 1,113 responses. By seat: ci-runtime-and-cost $56.36 (+$8.36 subagents), legacy-coordinator-agent $32.29, legacy-dispatcher-agent $6.40, judges $2.73, implement-test-performance $2.58 |
| Token cost that scales with CI duration | $0. Factory PR/publish nodes are scripted (no agent turn); seat CI watches hold one tool call or wake once; caches have a 1 h TTL |
| Research note 005 analysis runs | $27.14 in total; about $0.70 by line share was about this defect |
| Cross-check | The same 37 sessions reconcile to the cent with llm-spend (9,564 events, $957.74). llm-spend carries no incident attribution |

Unmeasurable, with the missing surface for each: seat ticks re-polling PR status (no record of each tick's purpose);
sandbox and local `just check` re-runs from the vanished-source defect (no record of when it fired); discovery before
an id existed (no tag at discovery time).

#### 4. Fleet sweep (latest master consumer log per repository, 2026-11-06)

| Repository | Producer/consumer pair | Reusing now | Reuse condition |
|---|---|---|---|
| livespec | yes | yes (job 127719149210) | bare `.coverage` present, no provenance |
| livespec-orchestrator-beads-fabro | yes (root/nonroot) | yes since #4366 (job 127734055600) | canonical per-file verdict files shipped |
| livespec-overseer | yes | yes (job 127720337684) | ships the receipt AND its CI FAILS a job that takes the fallback |
| livespec-driver-claude | yes | yes (job 127718664258) | bare `.coverage` |
| livespec-runtime | yes | yes (job 127265574644) | bare `.coverage` |
| livespec-orchestrator-git-jsonl | yes | yes (job 127717862928) | bare `.coverage` |
| livespec-driver-codex | reversed pair | yes (job 127717995556) | bare `.coverage` |
| livespec-driver-pi | reversed pair | yes (job 127717856078) | bare `.coverage` |
| livespec-console-beads-fabro | no pair (cargo llvm-cov) | n/a | n/a |
| livespec-dev-tooling | yes | yes since jerpfe and x3lvve | receipt shipped and stamped after the rewrite |

Six repositories reuse a bare `.coverage` with no provenance check. A provenance change like 34f370e1 in any of them
would put it into silent fallback. Only livespec-overseer's CI turns a fallback into a red build.

#### 5. Missed catch points (each one is a place this could have been stopped)

1. The consumer's fallback is a GREEN path that writes one log line, so nothing fails, alerts, or counts it.
2. The change that caused it (34f370e1) altered a CI reuse contract without touching the workflow that feeds it. No
   check relates a script's reuse precondition to the files the workflow actually ships.
3. 34f370e1 was hand-landed as a P1 carrier under the expedited-incident exception: 0 reviews, and none of the
   factory's dod_gate, review, proof_capture or proof_verify nodes ran. Its own pre-merge CI run showed the fallback
   (14.67 min, fallback line) and passed.
4. The first master run after it went from about 1-2 min to about 11-19 min for this job, and nothing alarmed. No
   CI-runtime regression signal exists.
5. The orchestrator's identical class was found and fixed 2026-11-04 (xevgsx). No sweep of the same shape across the
   fleet was filed, though dev-tooling had broken about 9 h earlier.
6. jerpfe was filed with the cause and a measured saving on 2026-11-04 23:48Z, but queued in a factory lane that
   cannot edit workflows, so nothing could pick it up.
7. Research note 005 (2026-11-05) named the cause and ranked the fix first in BOTH independent reviews. The coordinator's
   recovery order ranked it third, and the dispatch freeze then held it. A measured, top-ranked, half-day fix stayed
   unlanded for about 30 h.
8. The coordinator's first reading of "why is CI queuing" was runner queueing.
9. The incident's own diagnosis mis-dated the cause (string first-appearance via `git log -S`, not behaviour change),
   and an extrapolation inflated the cost about 2.5x in a message to the maintainer.
10. Two P1 CI changes, z3wy33 and jerpfe, landed hours apart, each constraining the other's steps. Only a full-suite
    CI run surfaced it; the commit and push gates did not run the 56 ci.yml-reading test files (1,100 tests, 3m41s).
11. A green PR proof of jerpfe covered one of the TWO breakages. The vanished-source rewrite fired on about 33% of runs
    and was only found when the first master run fell back.

#### 6. Constraints any solution must respect (fleet rules)

- A solution must PREVENT, FIX, or RAISE TO THE MAINTAINER a recurrence of the class "a reuse, cache or dedup path that
  silently falls back to the full cost", with NO step relying on a person noticing.
- Adopt before arm: a conformance check armed before the repositories it judges have adopted the shape turns the fleet
  red. Commit 46c5dab did this to five repositories and was reverted. Per-repo adoption comes first, then the check.
- Do not weaken a gate. The provenance receipt exists to stop a focused run's leftover `.coverage` producing a false
  pass, so removing it is not acceptable.
- No forgeable carve-outs (subject-prefix exemptions, skip env vars). Stop-the-line for breakages: fix the root cause,
  do not route around it.
- The maintainer accepts the seat and model burn while the fleet stabilizes. Wasted CI capacity, and tokens spent on
  failures and rework, are what must be cut.
- Honeycomb queries run only through the MCP endpoint, about 100 queries per hour, shared. A recurring script must
  use a small fixed query set.

#### 7. Candidate solutions to evaluate (add others)

A. Fail-on-fallback: in every producer/consumer pair, a CI consumer that takes the fallback branch FAILS the job,
   making it a red build, not a green log line. The reuse precondition is asserted, and the receipt is shipped.
   livespec-overseer already does this. Adopt per repo, then arm a check.
B. A producer/consumer artifact-contract conformance check, fleet-wide: every file the consumer script requires for
   reuse must be uploaded by the producer job and downloaded by the consumer job.
C. A CI-runtime regression alarm in Honeycomb (or from GitHub job durations): a per-job duration step change, for
   example a consumer job's p50 tripling against its 7-day baseline, raises to the maintainer.
D. Coordinator-tick waste reporting: each coordinator tick reports measured CI waste and duplicate-work classes from
   data, not from narration.
E. A fast pre-push or pre-commit run of every ci.yml-reading test whenever ci.yml or a script it invokes changes.
F. A rule and check that a reuse/receipt contract change must touch, or be verified against, the workflow that feeds it.
G. A sweep obligation: when a defect class is fixed in one fleet repository, a sweep item for every other repository is
   filed mechanically.
H. Hand-lane review parity: a hand-landed P1 change gets the independent review the factory lane would have given, or
   at least a CI-runtime delta check, before merge.
I. Any reuse proof must cover every producer path that writes the data after stamping, not one green run.
J. "Broken since X" claims to the maintainer must cite a log before and a log after X.

#### 8. The question for each reviewer

Using ONLY this pack plus anything you verify yourself:
1. What is the root cause, and what are the contributing causes, ranked?
2. Which catch points in section 5 matter most? Which are missing?
3. For each candidate in section 7, and any you add: does it PREVENT, FIX, or RAISE TO THE MAINTAINER a recurrence of
   the class, and does any step rely on a person noticing? Give its cost, its order relative to the others under
   adopt-before-arm, and your recommendation (adopt, adopt later, or reject, with the reason).
4. A ranked, minimal set of mechanical solutions you would adopt first, each with a falsifiable proof that it works
   against a deliberately induced fallback.
5. Anything in this pack you believe is wrong.

## Appendix B — GPT-6-Astra review (verbatim)

Produced by `codex exec -m gpt-6-astra -s read-only -C /data/projects/livespec-dev-tooling` (codex session 01a1aff6-818c-7483-83da-ce37b50109f1, 2026-11-06 ~08:35-09:35Z). It was given only the shared prompt and the pack, and it was produced WITHOUT reading the Fable review, which ran at the same time in a separate process and was not shown to it. It was stored on livespec-dev-tooling-npysxq as a comment before this note was written. Its headings are demoted one level so this note keeps a single H2 outline; its text is otherwise unchanged.

### 1. Root cause and contributing causes, ranked

**The root cause was an unenforced execution contract: a CI job intended to consume completed work could silently replace consumption with another full execution and still satisfy the required checks.** Provenance validation correctly rejected unsuitable evidence; the system treated the resulting duplication as successful operation.

I independently inspected the dev-tooling checkout at `775ca47c`, historical diffs, relevant scripts and workflows, and selected GitHub job logs. I also inspected the orchestrator’s regression and repair and overseer’s fallback assertion. I did not read another review, run tests, modify files, or write externally. GitHub reads used the connector; I made zero `gh` calls.

The causes rank as follows:

1. **Successful fallback erased the distinction between correct results and correct execution.**  
   In [scripts/just/check-coverage.sh](/data/projects/livespec-dev-tooling/scripts/just/check-coverage.sh:63), either validated reuse or another successful pytest run returns success. `.github/workflows/ci.yml` passes that result into `ci-green`. The workflow even describes fallback as “slower, never wrong.” That expresses the defective acceptance criterion: coverage correctness mattered, but avoiding duplicate execution was unenforced. This remains true at inspected HEAD, after both repairs.

2. **`34f370e1` changed the consumer contract without updating its producer-to-consumer transport.**  
   I verified that [the commit](https://github.com/thewoolleyman/livespec-dev-tooling/commit/34f370e104cd86f2165a99bbecc18e7508b73a05) removed the `GITHUB_ACTIONS` reuse branch and required the receipt, while its workflow still transported only `.coverage`. By contrast, `81defbb9` explicitly retained CI reuse without transporting the receipt. The corrected November start is supported by code, not merely token-string history.

3. **Receipt creation preceded the final mutation of the certified data.**  
   `scripts/just/check-per-file-coverage.sh` stamped the receipt before `livespec_dev_tooling/checks/per_file_coverage.py` could call `_rewrite_without()`. Once `34f370e1` bound the receipt to data bytes, this ordering invalidated otherwise legitimate producer output. `775ca47c`, delivered through livespec-dev-tooling#3587, correctly moves stamping after that operation while preserving the per-file exit status.

4. **Tests protected provenance correctness while explicitly accepting the expensive CI behavior.**  
   This is stronger than “missing tests.” `34f370e1` changed `test_github_actions_consumer_trusts_the_run_scoped_artifact` into `test_github_actions_consumer_rejects_unstamped_partial_artifact`. The replacement asserts successful execution of pytest under `GITHUB_ACTIONS=true`. Those assertions remain in [test_check_coverage_reuse_stamp.py](/data/projects/livespec-dev-tooling/tests/livespec_dev_tooling/test_check_coverage_reuse_stamp.py:286). There was no complementary invariant that the designated CI consumer must never start pytest.

5. **Detection did not mechanically produce an executable repair or escalation.**  
   Taking the pack’s ledger chronology as supplied, `jerpfe` entered a lane incapable of performing its workflow edit, remained unresolved through prioritization and freezes, and required maintainer intervention. An identified ongoing regression was represented as ordinary queued work rather than an incident with an executable owner and escalation deadline.

6. **There was no automatic feedback across runs or repositories.**  
   The orchestrator exhibited the same contract-change/transport-mismatch pattern in `704a96ded`; `7574921c2` repaired transport. Neither the first expensive success nor that discovery forced a fleet applicability check.

7. **Review and change-selection weaknesses increased exposure.**  
   The pack’s hand-lane review gap and omitted workflow-reading tests matter, but neither explains the class alone. More review cannot substitute for an execution invariant. The orchestrator regression commit itself carries a `Factory-Run-Id`, so factory provenance is not evidence that this class is prevented.

The sampled execution evidence supports this chain:

| Evidence independently inspected | What it establishes |
|---|---|
| Dev-tooling job `126346804910` | Original PR consumer logged missing matching provenance, then passed **6,123 tests in 837.98 seconds**. |
| Dev-tooling job `126352561400` | A contemporaneous older head logged reuse of the workflow producer artifact. |
| Run `42178905676`, producer `127763830700`, consumer `127770178810` | Producer dropped six vanished files and uploaded the receipt; consumer nevertheless reran **7,829 tests**. Both consumer and `ci-green` succeeded. |
| Run `42184143263`, producer `127780607500`, consumer `127786221682` | Producer dropped six vanished files; repaired consumer logged reuse. |
| Orchestrator jobs `124866358970` and `127734055600` | Earlier “no canonical per-file verdict” fallback and later canonical-verdict reuse. |
| Dev-tooling job `127749278476` | The two receipt steps failed `test_committed_ci_yml_omits_only_through_the_released_aggregate`; **1 failed, 7,824 passed**. |

I did **not** independently reproduce the complete job census, artifact-content hashes, ledger/transcript chronology, review count, fleet-wide latest-run survey, or token attribution. Those remain pack-supplied evidence.

### 2. Most important catch points, and missing ones

The highest-value catch points in section 5 are:

1. **#1: reject fallback at the execution boundary.** This would have stopped every affected consumer before it duplicated the suite.
2. **#2 and #11: verify the complete handoff and final data state.** File transport and post-processing order are separate failure modes; both require coverage.
3. **#4: detect unexpected execution automatically.** This catches regressions outside the known artifact contract and provides independent confirmation after deployment.
4. **#6 and #7: prevent known incidents from becoming unexecutable backlog.** Discovery had already succeeded. More investigation or another ranking document would not solve the dispatch mismatch.
5. **#5: propagate the finding across applicable fleet members.** The orchestrator repair was an opportunity to catch dev-tooling without waiting for another user-visible symptom.
6. **#3 and #10: improve review parity and early test selection.** Valuable secondary defenses.
7. **#8 and #9: improve diagnostic and reporting accuracy.** These amplified response cost and damaged confidence; they did not cause duplicate execution.

Several catch points are missing or underspecified:

- **The existing tests endorsed fallback.** The required change is to distinguish a legitimate standalone measurement from a mandatory-reuse consumer, then test both contracts.
- **Overseer fails too late.** Its `.github/workflows/ci.yml` runs `just check-coverage`, captures its output, and only afterward greps for the reuse message. This prevents an expensive green result, but still pays for the duplicate suite. Adopt its invariant, not its implementation timing.
- **A red job is not guaranteed maintainer notification.** Required checks prevent merge; they do not establish delivery to the maintainer or resolution of a broken master. Notification needs its own verified path.
- **Missing telemetry must be a detectable condition.** Dev-tooling’s `export-telemetry` runs on pushes, after the checks, and is excluded from `ci-green`. Its script checks ingestion acceptance, but that does not detect an absent export job, absent branch-outcome fields, or a broken alert route.
- **A p50 alarm cannot reliably detect minority failures.** A fallback affecting roughly one-third of executions can leave p50 close to the healthy path.
- **The repair’s acceptance criterion lacked a forced rewrite case.** One successful warm-path PR run was insufficient. The first post-transport master run demonstrated this immediately.
- **Workflow files are executable inputs.** The pre-commit script classifies zero-Python changes as “doc-only.” That category includes workflow and shell changes. Conversely, pre-push advertises a full aggregate, so its actual historical execution path needs evidence before attributing its miss to the same classifier.
- **Completion lacked a fleet adoption inventory.** “Latest job reused” is not proof that missing, mismatched, or stale evidence will be rejected on the next run.

### 3. Evaluation of candidates A–J and additional controls

The costs below are qualitative implementation and operating costs, not measured delivery estimates.

Use this adoption order: **repair and demonstrate each repository’s handoff; enable that repository’s mandatory-consumer enforcement; then arm fleet conformance against adopted contracts.** Monitoring can collect evidence earlier without blocking unadopted repositories.

| Candidate | Effect and reliance on someone noticing | Cost and adoption order | Recommendation |
|---|---|---|---|
| **A. Fail-on-fallback** | **PREVENTS** duplicate execution only if it fails **before** launching the suite. Transport and stamping corrections **FIX** the present defects. A red result alone does not guarantee maintainer notification. | Low per pair; needs a distinct consume-only entry point and workflow wiring. Adopt after repairing that pair, before fleet enforcement. | **Adopt first, strengthened.** The CI consumer must have no full-suite branch. Preserve standalone measurement separately; no skip variable or subject-prefix exemption. |
| **B. Artifact-contract conformance** | **PREVENTS** missing-file and wiring regressions within its checked scope. Does not prove receipt freshness merely by finding matching filenames. No human noticing if required automatically. | Medium: declared inputs, artifact names, paths, hidden-file settings, matrix identity, dependencies and conditional execution. Arm per repository after adoption. | **Adopt.** Verify actual consumer acceptance of transported output as well as static wiring. Do not promise general inference from arbitrary shell code. |
| **C. Runtime regression alarm** | **RAISES TO THE MAINTAINER** if automatically delivered. A dashboard alone relies on noticing. Does not fix the defect. | Medium setup and ongoing baseline maintenance. Use existing duration data first; baseline refinement follows explicit outcome events. | **Adopt later as a secondary detector.** Reject p50-tripling as the sole rule. Include fallback counts/rates, tails, absolute excess duration and cumulative waste; separate execution from queue time. |
| **D. Coordinator-tick waste reporting** | Reporting alone neither prevents nor guarantees escalation. It depends on a coordinator interpreting and acting on each report. | Recurring query and agent-attention cost; overlaps C and the event monitor below. | **Reject as the primary control.** Adopt later only as a deterministic summary of existing measurements and unresolved alerts, without new per-seat polling. |
| **E. Early workflow-reading tests** | **PREVENTS** covered incompatibilities before expensive CI. No noticing dependency when enforced. Does not establish that the test expectations are correct. | Pack reports 3m41s for the set; I did not reproduce it. Add a smaller contract check first, then the broader selected set. | **Adopt.** Trigger on workflow, invoked scripts, receipt logic and reporting mutations. Keep a required CI equivalent; do not rely exclusively on local hooks or run the same selection redundantly at every stage. |
| **F. Contract change must touch or verify workflow** | “Must touch” proves nothing; a comment edit satisfies it. Actual verification can **PREVENT** mismatch. A prose rule relies on noticing. | Low incremental cost when implemented through B/E. | **Adopt verification; reject touch-count enforcement.** Bind evidence to the candidate tree and consumer contract. |
| **G. Mechanical fleet sweep** | **RAISES** possible exposure if findings reach an owner and escalation route. Filing items alone does not prevent or fix anything. | Medium inventory effort; low recurring cost with deduplication. Start discovery now, arm checks after per-repo adoption. | **Adopt with applicability filtering.** Create one tracked sweep with per-repository dispositions and repair items for affected pairs, rather than blindly creating work in every repository. |
| **H. Hand-lane review parity** | A required independent review can catch mistakes, but its substantive protection still depends on reviewer noticing. A mandatory execution-contract check is mechanical. | Review latency and agent cost; enforcing the same check across lanes is cheaper. | **Adopt mechanical parity now; review parity as secondary protection.** P1 transport must not waive the mandatory-consumer check. A duration comparison is not equivalent to review or semantic validation. |
| **I. Proof covers every producer mutation path** | **PREVENTS** known stale-receipt regressions when deterministic checks exercise those paths. A checklist alone relies on noticing. | Low-to-medium focused-test cost; a real workflow handoff probe adds modest CI work. Part of adoption before A/B are armed. | **Adopt first.** Cover unchanged data, vanished-source rewriting, invalid receipts, and failing producer/report verdicts. Stamp final output, then treat it as immutable. |
| **J. Before/after logs for onset claims** | Prevents unsupported incident reporting if mechanically required. It does **not** prevent, fix or alert on fallback itself. | Low; reporting-time requirement, independent of fleet rollout. | **Adopt.** Require commit relationship, run IDs, branch evidence, population and calculation. Logs bracket onset; they do not alone prove causation. |
| **K. Structured outcomes, delivered alerts and monitor health** | **RAISES TO THE MAINTAINER** automatically, including green expensive execution elsewhere in the fleet. Missing events and failed delivery are separate alerts. No dependence on someone opening logs. | Medium instrumentation and delivery work. Start with mandatory coverage consumers, then other reuse/cache/dedup paths. | **Adopt in the first set.** Emit a versioned outcome and reason, not a message to be scraped. |
| **L. Executable incident ownership and age escalation** | **PREVENTS** silent abandonment of detected regressions; **RAISES** unsupported routing, unresolved incidents and blocked repairs. It does not itself repair code. | Low-to-medium scheduler/ledger integration. Adopt alongside K. | **Adopt.** Validate lane capability, assign an owner, retain incident age across freezes, and escalate automatically when no permitted execution path exists. |

For K, record repository, commit, run/job/attempt, producer identity, expected execution mode, actual outcome, reason and duration. For example, distinguish `missing_receipt`, `data_digest_mismatch`, `tree_mismatch`, `producer_failed`, and `reused`.

**Mandatory reuse and opportunistic caching need different policies.** Every miss in a coverage consumer with a successful upstream producer is an invariant violation. A cold dependency cache can legitimately miss. Such paths need declared miss/work budgets and automatic escalation when exceeded, rather than universal fail-on-miss. Those policies must be reviewed configuration, not ad hoc bypasses.

A small shared query set is sufficient: for example, two fleet-wide queries every ten minutes—violations and missing expected evidence—would consume 12 queries/hour. That is a proposed allocation, subject to the shared budget; recurring Honeycomb queries must use MCP. Notifications need delivery receipts, deduplication, recovery events and an independent heartbeat check.

### 4. Ranked minimal mechanical solutions and falsifiable proofs

These are proposed acceptance tests. I did not execute them.

**1. Make the designated CI consumer incapable of starting the suite.**

Apply this first to dev-tooling’s `check-coverage` job and its equivalent fleet consumers, including the orchestrator’s UID variants and reversed producer/consumer pairs.

Keep the existing provenance protections. Preserve `70884cb7`/`721bd7f7` receipt transport and `775ca47c` stamping order. Add a consume-only operation whose invalid-input result is nonzero before pytest can run. Wire it through the required aggregate; do not implement it as a caller-controlled “strict mode” that can silently default off.

**Falsifiable proof:** starting with valid producer output, independently remove the receipt, remove the data, change a data byte, change the tree identity, and substitute another producer’s output. Every case must:

- Return a named contract failure.
- Start **zero** suite executions.
- Fail `check-coverage` and the required aggregate.
- Preserve coverage/report failures rather than translating them into success.

The valid control must reuse and pass. A controlled undercoverage case must still fail. Instrument command execution to establish the zero-pytest assertion; elapsed time or a log phrase alone is insufficient.

**2. Test the actual handoff and the final artifact, then enforce it on relevant changes.**

Use B, E, F and I as one control rather than four overlapping check systems.

In dev-tooling, cover `.github/workflows/ci.yml`, all three coverage shell scripts, `per_file_coverage.py`, and their contract tests. In the orchestrator, include `.coverage-gates/per-file.{status,log}` and the applicable UID workflows.

**Falsifiable proof:**

- Run the real producer processing against a small coverage fixture containing an existing source and a deliberately vanished transient source. Verify the rewrite occurs and the receipt matches the **final** bytes.
- Pass that output through the production upload/download path into a fresh consumer workspace. Verify reuse without another suite.
- Deliberately omit the receipt from transport: the required check must fail.
- Deliberately restore stamp-before-rewrite ordering: the receipt/consumer check must fail.
- Mutate artifact name, destination, matrix association and hidden-file handling: each mutation must be detected.
- Remove the required incident guard from a receipt step: the early workflow test selection must catch the exact failure seen in job `127749278476`.

A mocked `uv` test is useful for control flow, but it cannot be the entire proof. The existing rewrite regression test simulates mutation; complement it with the real reporter and real artifact boundary. Avoid a harness that reconstructs the handoff correctly while production remains wrong.

Adopt and prove each repository before including it in mandatory fleet conformance. Record the adopting commit and installed workflow revision.

**3. Deliver outcome violations automatically, with proof that the monitor itself works.**

Emit explicit reuse outcomes and alert on any mandatory-consumer violation. For other cache/dedup paths, alert on breaches of their declared budgets. Add duration-based detection as backup rather than the primary discriminator.

The observed [post-transport master failure](https://github.com/thewoolleyman/livespec-dev-tooling/actions/runs/42178905676/job/127770178810) is the essential replay case: successful job, successful uploads, invalid receipt, expensive execution.

**Falsifiable proof:** in a dedicated validation workflow, induce a missing receipt and verify the complete chain from outcome event to a maintainer-directed notification with a delivery receipt. A reasonable proposed acceptance target is delivery within ten minutes. Also:

- Inject a green expensive-fallback outcome from a controlled cache fixture; it must alert despite job success.
- Suppress the expected outcome event; monitoring must report missing evidence.
- Break notification delivery; an independent health path must report that failure.
- Repeat the same event; it must update/deduplicate the incident.
- Restore valid reuse; the system must emit recovery evidence.

This closes the gap between “a signal exists” and “the maintainer is automatically informed.” It does not require the maintainer to inspect dashboards or routine tick reports.

**4. Make unresolved incidents impossible to lose in an incompatible lane.**

Attach each violation to a deduplicated incident with an accountable owner, executable route and persistent age. Validate requested file changes against lane capabilities before admission. A workflow-changing item cannot remain accepted into a workflow-prohibited lane.

A dispatch freeze may restrict repair execution, but must not erase the incident or suspend reporting.

**Falsifiable proof:** submit a synthetic workflow-repair incident to the prohibited factory lane. The router must reject that assignment and select an authorized route or automatically notify the maintainer of the execution blocker. Then simulate a freeze and an unavailable owner. The incident must remain visible, retain its original detection time, and escalate without a coordinator turn.

Plan completion should require the adoption inventory, the deliberate-failure evidence above, and a verified notification route. One green latest run is insufficient.

### 5. What is wrong, overstated or insufficiently established in the pack

**The corrected technical diagnosis is substantially right.** My disagreements concern causality, strength of proof and measurement language.

1. **The September rewrite was not independently a stale-receipt defect at introduction.**  
   `98a15fb5` changed data bytes, but the earlier receipt did not bind those bytes and CI bypassed the receipt check. The stale-hash defect arose from the interaction with `34f370e1`. It is a second failure mode masked by missing transport, not evidence that this coverage-reuse incident existed since September.

2. **The overseer comparison needs an explicit qualification.**  
   It does reject an expensive green fallback, as claimed. It does so after running the duplicate suite and relies on matching a log string. It is useful precedent for the policy, not a complete implementation of prevention.

3. **“Nothing is extrapolated” overstates the cost evidence.**  
   Job durations can be directly measured. “Waste” subtracts a counterfactual reuse duration; the 0.6-minute and 1.05-minute alternatives are modeled baselines. Incident token attribution and the research-note line share also involve attribution rules. These are useful estimates, but should be labeled accordingly.

4. **The $0 duration-dependent token claim must remain narrowly scoped.**  
   Scripted factory nodes support zero agent inference cost for those nodes while CI runs. They do not prove zero incident-wide duration-dependent cost when repeated seat ticks and other handling are explicitly unmeasurable. The transcript/Honeycomb reconciliation validates session totals, not causal attribution to this defect.

5. **The measured cost window is not the complete incident window.**  
   The dev-tooling census stops around 05:45 on November 6; receipt transport merged at 07:08 and final stamping repair at 08:12. The headline total excludes later exposure unless separately counted. Also, “about 4.8 days” adds overlapping repository windows: it should be called approximately 4.8 **repository-days**, not elapsed incident duration.

6. **The 33% observation is a sample fraction.**  
   Twenty of sixty producer logs establishes that sample’s frequency, not the exact residual fallback fraction after `jerpfe`. The two producer logs I inspected verify that the rewrite occurred both before and after the final repair; they do not validate the census.

7. **“About 16–17 minutes on every PR’s critical path” is too categorical.**  
   Duplicate consumer time extends the coverage dependency chain. Its effect on whole-PR completion depends on competing jobs, overlap, failures and cancellation. The full wall-time claim needs workflow-DAG analysis, not consumer duration alone.

8. **The proposed p50-tripling alarm is inadequate for the demonstrated second defect.**  
   A minority fallback population can leave p50 healthy; a rolling baseline can eventually absorb a prolonged regression. Explicit branch outcomes and missing-evidence alarms are necessary.

9. **The pre-push miss needs a more precise explanation.**  
   I verified the CI failure and the pre-commit zero-Python classifier. However, `check-pre-push.sh` explicitly intends to run the full aggregate or reuse appropriate prior evidence. I have not verified which historical delegation, incident or token path omitted those tests. The pack establishes the miss as supplied evidence, but does not fully establish its mechanism.

10. **Review and prioritization claims need bounded conclusions.**  
    I accept from the pack that livespec-dev-tooling#3346 had no reviews and `jerpfe` waited in an unsuitable lane. That supports stronger mechanical parity and routing. It does not prove that an independent reviewer would have caught the defect, or that ranking the repair third was unjustified without the competing incidents’ evidence. The incompatible lane and absence of automatic escalation are failures regardless of that ranking.

The two landed repairs restore the known handoff. They do **not** yet establish the maintainer’s requested guarantee against silently expensive fallback: the inspected consumer still implements that behavior, and its tests still accept it.

## Appendix C — Fable review (verbatim)

Produced by a Claude subagent on model `fable` (2026-11-06 ~08:35-09:35Z). It was given only the shared prompt and the pack, and was told not to read any other file in the review directory. It was produced WITHOUT reading the GPT-6-Astra review, which was not yet written when it began. It was stored on livespec-dev-tooling-npysxq as a comment before this note was written. Its headings are demoted one level; its text is otherwise unchanged.

### Independent review: the silent coverage-reuse fallback (livespec-dev-tooling-npysxq)

Reviewer: Fable (independent, no role in the incident or its fixes). Read-only. 18 `gh` calls, all `--cache 1h`.

### What I verified myself, and what I took from the pack

Verified against git, the scripts, `ci.yml`, GitHub job metadata and job logs:

- `34f370e1` (xluwqj) removed the `GITHUB_ACTIONS` reuse branch from `scripts/just/check-coverage.sh`, bound the receipt to the `.coverage` sha256 in `scripts/just/coverage-reuse-id.sh`, and touched no file under `.github/workflows/` (`git show --stat 34f370e1 -- .github/workflows/ci.yml` is empty). Its new comment block says, verbatim: "A downloaded artifact without its receipt falls back to normal measurement."
- `81defbb9` (sc0z) added the receipt and kept the `GITHUB_ACTIONS` branch; `98a15fb5` (5xh8) added the vanished-source rewrite; `e42e57fc` added the producer/consumer chain to `ci.yml`.
- `70884cb7` + `721bd7f7` (jerpfe) added the `coverage-reuse-token` upload/download steps to `ci.yml` and changed nothing else except `.livespec-workflow-edit-exemption`; `775ca47c` (x3lvve) moved the stamp after `per_file_coverage` and added two harness tests.
- Jobs 126346804910 (PR #3346's own consumer: 02:24:39-02:39:19Z, 14.67 min, fallback line present, green), 126352561400 (2.32 min, last reuse), 126355763498 (11.22 min, first fallback), 127770178810 (head `721bd7f7`, 16.2 min, downloaded a 298-byte `coverage-reuse-token` and STILL printed the fallback line), 127786221682 (head `f7c6503d`, 28 s), 127301542527 (docs-only PR, 14:20:31-15:11:15Z, 50.7 min). Orchestrator jobs 124866358970 and 127734055600 exist with the stated times.
- PR #3346: 0 reviews, merged 2026-11-04T02:39:52Z by `thewoolleyman-factory-bot[bot]`, merge commit `34f370e1`.
- Job 127749278476 (jerpfe's red run): `1 failed, 7824 passed in 991.94s`; the failure is `tests/livespec_dev_tooling/test_incident_ci_omission_wiring.py::test_committed_ci_yml_omits_only_through_the_released_aggregate` in the `check-per-file-coverage` job.
- livespec-overseer's `ci.yml` consumer step greps its own log for the consume-once line and exits 1 otherwise (lines ~340-360); its provenance id is `github-run:<RUN_ID>:attempt:<ATTEMPT>` in CI. livespec-driver-claude (`dev-tooling/just/check-coverage.sh`) and livespec-runtime (`.github/scripts/check-coverage.sh`) reuse on a bare `-f .coverage`. livespec's consumer log 127719149210 prints "reading existing .coverage (produced by check-per-file-coverage)" with no provenance test.
- livespec-dev-tooling's `ci.yml` (line ~292) and livespec-orchestrator-beads-fabro's `ci.yml` (line ~586) both still say of the fallback: "slower, never wrong".
- No test under `tests/consumer/` or anywhere in `tests/` reads `ci.yml` for the string `coverage-reuse-token`; the only tests naming it are the script-harness tests (`test_check_coverage_reuse_stamp.py`, `test_incident_*`), which never open the workflow.
- The pre-commit path for a zero-`.py` staged tree is `scripts/just/check-pre-commit-doc-only.sh`, which runs no pytest at all. 62 files under `tests/` mention `ci.yml` (the pack says 56; a definitional difference, not a dispute).
- `.livespec-workflow-edit-exemption` on master (committed by `70884cb7`) carries a `ci_runtime=no-significant-increase` attestation that `check-no-workflow-edits.sh` parses as a declaration and compares against nothing measured.

Taken from the pack, not verified: the run counts and runner-minute totals in §3.1 (460/460 runs, 419 fallbacks, 8,013 waste minutes; orchestrator 15,470), the 3,074 pre-incident reusing jobs, the "20 of 60 producer logs" vanished-file rate, the token figures in §3.2, the transcript-sourced timeline rows, the ledger/coordinator rows (recovery order, R301 freeze), and the claim that the PUSH gate did not run the ci.yml-reading tests for jerpfe (I verified the commit gate; see §5 for the push gate).

---

### 1. Root cause and contributing causes, ranked

**Root cause (of the class, which is what the maintainer's direction is about): the consumer's fallback is a designed GREEN path with no asserted precondition.** `scripts/just/check-coverage.sh` treats "no reusable data" as a normal state and runs the suite; `ci.yml` documents this as "slower, never wrong". Nothing in the producer job, the consumer job, or the test suite asserts the contract "the producer ships what the consumer's reuse test requires". A contract break therefore produces a correct verdict at ~15x the cost, with one log line as the only trace. Every other cause below did damage only because this one made the damage silent. The same doctrine is in the orchestrator's `ci.yml` today, and six fleet repos reuse a bare `.coverage` with no contract to break yet.

Contributing causes, ranked by how much of the 51 h / ~8,000 runner-minutes each explains:

1. **The trigger: `34f370e1` changed the reuse precondition in a script and left the workflow shipping only `.coverage`.** This is not an unnoticed side effect. The commit's own comment states the consequence ("A downloaded artifact without its receipt falls back to normal measurement"), its own pre-merge consumer job (126346804910) took 14.67 min and printed the fallback line, and it merged with 0 reviews under the expedited exception. The author accepted a per-run 15-minute regression as the price of closing a focused-coverage false-pass hole, and the lane had no mechanism to price that acceptance.
2. **No test reads `ci.yml` for the receipt wiring — then or now.** The repo has 62 ci.yml-reading test files and two completeness checks (`check-ci-matrix-completeness`, `check-tool-backed-check-completeness`) that already parse the workflow, so this is an omission inside an existing capability, not a missing capability. jerpfe fixed the instance and added no guard; a later `ci.yml` refactor that drops the `coverage-reuse-token` steps would reproduce the incident with the same silence.
3. **The second defect (stamp-before-rewrite) was activated by the same commit.** `98a15fb5`'s rewrite was harmless while the receipt bound only the tree (`81defbb9`). `34f370e1` bound it to the data bytes and so made the receipt stale on every vanished-file run. The pack calls it "independent"; in mechanism yes, in activation no — one commit opened two holes, and the single-run jerpfe proof (job 127763227768, producer logged no vanished file) could not see the second. The local `just check` dispatcher runs the same pair, so roughly a third of local and sandbox aggregates since 2026-11-04 also ran the suite twice; the pack correctly lists this as unmeasured.
4. **No runtime signal of any kind.** A job that goes from 1-2 min to 11-19 min (and to 50 min on 127301542527) on every run for two days alarms nothing. The only runtime artefact in the whole system is the self-declared `ci_runtime=no-significant-increase` line in the exemption file, which `34f370e1` did not even need because it touched no workflow.
5. **Fix latency after diagnosis: ~30 h.** The cause was known at 2026-11-04 18:06 (observed) and 23:48 (filed with a measured saving), then sat in a factory lane that cannot edit workflows, was ranked third on 2026-11-05 19:43, and was frozen by R301. Roughly 60% of the dev-tooling waste minutes accrued after the cause was in the ledger.
6. **No fleet sweep after xevgsx (2026-11-04 11:53).** The orchestrator fix would have pointed at dev-tooling's identical pair within minutes; the actual notice came 6 h later and the filing 12 h later.
7. **Diagnosis quality (mis-dating via `git log -S`, 2.5x extrapolation).** Cost credibility and tokens, not runner-minutes. Real, but last.

### 2. Which catch points matter most, and which are missing

Of the pack's eleven, the ones that matter are the ones that would have made the rest unnecessary:

- **#1 (green fallback)** is the whole incident. Had the consumer failed on fallback, #3346's own CI run would have been red at 02:25Z on 2026-11-04 and the item would have cost one extra ci.yml step before merge. Every other point is a weaker substitute for this one.
- **#2 (no contract check between script precondition and workflow artifact)** is the commit-time version of #1. It is also the only one still MISSING today after both fixes.
- **#4 (no runtime regression signal)** is the second line, and the only one that catches classes nobody has foreseen (cache misses, image cold starts, a future reuse path). It is a RAISE, not a PREVENT.
- **#6 and #7 (fix parked in the wrong lane, then ranked third and frozen)** explain the largest share of minutes but are process latency; they only matter because #1 and #4 let the fire burn unseen while the queue was being argued.
- **#3 (hand-lane, 0 reviews)** matters less than it looks: a reviewer would have had to read "falls back to normal measurement" and price it. With #1 fixed, the lane does not need a reviewer for this class.
- **#10 (z3wy33 / jerpfe collision)** is a separate, cheap-to-fix hole (see E).
- **#5, #8, #9, #11** are real but secondary.

Missing catch points the pack does not list:

- **M1. The author's own text was a catch point.** `34f370e1` writes down the fallback in a comment and in `coverage-reuse-id.sh`. A rule that a hot-path script may not contain a designed fallback to the full cost without a job-level assertion would have fired on the diff itself.
- **M2. Producer-side asymmetry.** The producer's upload steps use `if-no-files-found: error`, so a MISSING receipt file fails loudly at the producer; a PRESENT-but-stale receipt, and a receipt the consumer never downloads, fail nowhere. The producer could have verified `coverage-reuse-id.sh` against its stamped receipt immediately before upload and caught x3lvve on 2026-11-04.
- **M3. The producer's own "vanished source" warning.** It fired on about a third of runs for two months and was never correlated with the consumer's branch line. Two warnings in two jobs of one run, never joined.
- **M4. The local dispatcher.** `just check` serializes the same pair and takes the same silent fallback; nobody measured host CPU burned there, and nothing in the aggregate's summary counts a fallback.
- **M5. The post-fix regression guard.** Catch point #2 is still open: no test asserts the `coverage-reuse-token` steps in `ci.yml`, and the "slower, never wrong" doctrine is still in both workflows.
- **M6. The exemption attestation.** `ci_runtime=no-significant-increase` is accepted as a string. A declaration that nothing measures is a catch point in name only.

### 3. Each candidate: prevent / fix / raise, human dependence, cost, order, recommendation

Order is under adopt-before-arm: "adopt" means per-repo change; "arm" means a fleet conformance check that turns red on a repo lacking the shape.

**A. Fail-on-fallback in every CI consumer.** PREVENTS the class (a fallback becomes a red build within a minute, not a green 16 min). No human in the loop. Cost: ~10 lines per repo; overseer has the template. Two design notes: (i) overseer couples to a log literal and guards the literal with a test; better is to have the script itself refuse: when `GITHUB_ACTIONS` is set, the fallback branch exits non-zero with a named cause (`check-coverage: refusing fallback in CI; the producer's receipt is missing or stale`). That uses `GITHUB_ACTIONS` to STRENGTHEN, which `34f370e1`'s "not provenance" objection does not touch, and adds no knob anyone can unset. (ii) Delete the "slower, never wrong" comments; they are the doctrine that produced the hole. Order: FIRST, in livespec-dev-tooling and livespec-orchestrator-beads-fabro now (both have live pairs with green fallback), then the six bare-reuse repos (their consumer has a "no .coverage ... running the suite" branch to assert on), then arm. **Adopt now.**

**B. Producer/consumer artifact-contract conformance check.** PREVENTS at commit time; complements A (A catches at CI, after push; B before). Cost: low as a repo-local pytest in `tests/consumer/` (assert the producer uploads `.coverage` and `.livespec-coverage-reuse-token` with `include-hidden-files: true` and `if-no-files-found: error`; the consumer downloads both before `just check-coverage`; the basename matches `reuse_stamp` in `check-coverage.sh`). Fleet-wide, moderate: needs each consumer script to declare its required files and a shared parser in the worktree pack. B alone misses the stale-receipt defect; A catches it. Order: repo-local test NOW in dev-tooling (it has none), fleet check after A is adopted everywhere. **Adopt the local test now; arm the fleet check later.**

**C. CI-runtime regression alarm.** RAISES to the maintainer; catches unforeseen classes. The last step is a human acting on an alert, which the constraints allow. Do it from GitHub job durations, not Honeycomb: the job API is free of the ~100/h budget and I used it for this review. Per repo and job name, 24 h median vs 7-day median, alert when >2x AND >5 min absolute, keyed by runner label (hosted vs k3s differ 3x legitimately). Cost: one scheduled script, ~10 API calls per repo per run. Risk: alert fatigue on shared runners; the median and absolute floor limit it. Order: independent of adopt-before-arm (it is monitoring, not a gate). **Adopt, second.**

**D. Coordinator-tick waste reporting.** RAISES, but costs a model turn per tick and is only as good as the data behind it. If it reads C's output it is C's delivery channel; if it narrates, it is what failed on 2026-11-06 05:3x. **Adopt later, only as C's channel; do not build separately.**

**E. Run the ci.yml-reading tests at pre-commit when `ci.yml` or a `scripts/just/*.sh` it invokes is staged.** PREVENTS catch point #10. I verified `check-pre-commit-doc-only.sh` runs no pytest for a zero-`.py` tree, so a workflow-only commit reaches CI with its 1,100 workflow tests unrun. Cost: ~4 min (pack figure) on the rare workflow commit. Not a carve-out: it adds a check. Order: now, dev-tooling only (other repos' hooks differ). **Adopt now.**

**F. Rule that a reuse/receipt change must touch or be verified against its workflow.** As a co-edit rule it is wrong-shaped (most script edits need no workflow edit, and a co-edit does not prove the contract). As "verified against" it IS B. **Reject as a rule; subsume into B.**

**G. Mechanical sweep obligation.** Reduces latency (~6-12 h of 51 h here). Classifying a fix as "fleet-class" is a human judgment, so it only partly removes the person; the mechanical part is: an item closed with a `fleet-class` label without sibling items or a recorded per-repo "n/a" is refused. Cost: ledger procedure plus a small check. **Adopt later, as a coordinator-duties rule first.**

**H. Hand-lane review parity / CI-runtime delta before merge.** The runtime delta is C applied at PR time: compare the PR's per-job durations with master's p50 and comment or label. Would have flagged #3346 (14.67 vs ~1-2 min). As a FAILING check it is flaky on shared runners; as a RAISE it depends on a person. With A in place it is redundant for this class. **Adopt later, low priority, as a PR comment fed by C's data.**

**I. Reuse proof must cover every producer path that writes data after stamping.** x3lvve did this in substance (stamp last; `test_receipt_survives_the_per_file_vanished_source_rewrite`). Make it a stated rule in the producer script header and add the producer-side pre-upload self-check (M2). A catches any residual. **Adopt; mostly done.**

**J. "Broken since X" claims cite a log before and after X.** Pure process, person-dependent, cheap, and it would have prevented the 2.5x message. **Adopt as a coordinator-duties rule.** Note the mis-dating survives in a committed file (§5).

Added candidates:

**K. Structured fallback/reuse record.** The consumer writes its branch to `$GITHUB_STEP_SUMMARY` and as a `::notice`/`::error`, and the `export-telemetry` job already in `ci.yml` attaches `coverage.reuse=true|false` to its span. Makes C's query a count of fallbacks, not an inference from duration. Cost: tiny. **Adopt with A.**

**L. Local dispatcher parity.** The `just check` dispatcher sets a producer-ran marker and the consumer refuses fallback when it is set, so the ~33% local double-suite case fails loudly too; a standalone `just check-coverage` keeps today's behaviour. Cost: small; some risk to local flows. **Adopt after A is proven in CI.**

### 4. Minimal ranked set to adopt first, each with a falsifiable proof against an induced fallback

1. **A + K in livespec-dev-tooling** (`scripts/just/check-coverage.sh`: fallback exits non-zero when `GITHUB_ACTIONS` is set; `ci.yml` consumer step records the branch; delete "slower, never wrong").
   Proof: on a branch, (a) delete the "Download the producer's provenance receipt" step → the consumer job must be RED within ~1 min with the named cause, never green at 16 min; (b) revert `775ca47c`'s ordering and add a test that imports then deletes a temp module so a vanished file is measured → RED, with the producer's pre-upload self-check (M2) naming the sha mismatch; (c) restore both → green in under 1 min with the reuse line, step summary `reuse=true`. The branch is discarded; the three outcomes are the proof.
2. **B-local: a pytest in `tests/consumer/` asserting the receipt wiring in `ci.yml`.**
   Proof: remove the receipt upload step on a branch → the test fails; with (3) below it fails at pre-commit, not in a 17-min CI run.
3. **E: `check-pre-commit-doc-only.sh` runs `pytest tests/consumer` (or the enumerated ci.yml-reading set) when any `.github/workflows/*` or `scripts/just/*.sh` path is staged.**
   Proof: stage the exact `ci.yml` diff of `70884cb7` (receipt steps without the incident guard) on top of `31773952` → pre-commit refuses with `test_committed_ci_yml_omits_only_through_the_released_aggregate`, reproducing job 127749278476's failure locally in ~4 min.
4. **C: scheduled job-duration regression alarm from the GitHub jobs API, per repo, per job name, per runner label.**
   Proof by replay: run it over stored durations for 2026-10-28 → 2026-11-06. It must fire for dev-tooling `check-coverage` in the 2026-11-04 03:00-06:00Z window and for orchestrator `check-coverage (nonroot)` after 2026-11-01 22:00Z, and clear after 2026-11-06 08:13Z; it must NOT fire on the orchestrator's hosted-vs-k3s lane move (bd-ib-uxv5al) when keyed by label. Two true alerts, zero false ones, is the pass.
5. **A rolled to livespec-orchestrator-beads-fabro and the six bare-reuse repos, then arm a fleet conformance check** (worktree pack) that every job downloading a coverage artifact also refuses fallback.
   Proof: the induced-fallback test (1a) per repo; then, only after all have adopted, the armed check goes red on a branch that strips the refusal from one repo and stays green on master everywhere.
6. **G and J as rules in `.ai/coordinator-duties.md`.** Proof is procedural: the next fleet-class fix shows sibling items filed in the same hour.

Items 1-3 are a half-day in one PR each; 4 is a day; 5 is a day of per-repo PRs plus the check.

### 5. What I believe is wrong or incomplete in the pack

- **"Nothing else distinguishes them" (§1) is overstated.** Job duration (0.6 vs 15-50 min), the pytest banner, and the per-file coverage table all distinguish the branches. That matters because duration is exactly the signal candidate C uses; the pack should not argue the fallback is undetectable while proposing to detect it.
- **The pack frames `34f370e1`'s workflow omission as an oversight.** The commit's own comment states the fallback consequence in words. This was a conscious acceptance under incident pressure, not something nobody saw, and catch point #3 should be stated that way: the lane let a known per-run regression through unpriced.
- **The second defect is not "independent" in activation.** It was latent and harmless under the tree-only receipt; `34f370e1`'s data-bytes binding activated it. One commit, two holes.
- **The mis-dating is still committed.** `.livespec-workflow-edit-exemption` on master (from `70884cb7`) says "Since the sc0z provenance gate (81defbb9, 2026-09-06) ... every CI run re-ran the suite." The pack says the error was retracted in comments; the durable record in git repeats it. The next exemption overwrites the file, so the stakes are low, but it contradicts candidate J.
- **Catch point #10 says the push gate did not run the ci.yml-reading tests, without saying why.** I verified the COMMIT gate (doc-only path, no pytest). `scripts/just/check-pre-push.sh` runs the full aggregate unless the green token matches the HEAD tree or the gate is delegated to the cluster, and both of those paths should have run `test_incident_ci_omission_wiring.py`. Either the push bypassed the aggregate through a path the pack has not named, or the test ran and the failure was not read. The mechanism needs stating before E is sized; if it is a gate bypass, it is a larger finding than the pack gives it.
- **§4 understates dev-tooling's status.** "Reusing now" is true for the instance; the class is open: the fallback is still green, the "slower, never wrong" comment is still in `ci.yml`, and no test guards the wiring jerpfe added. The table should carry a column for "fallback fails the job", with only livespec-overseer at yes.
- **Candidate C's framing.** Honeycomb is not needed; the GitHub jobs API carries the durations and is outside the ~100/h budget.
- **"56 ci.yml-reading test files"**: 62 files under `tests/` mention `ci.yml` by my count; the difference is definitional, not an error, but one number should be the one used for E's cost.
- Minor: jerpfe "merged 07:08:24" shipped two commits; the merged head is `721bd7f7`, which is also the head of the still-falling-back master run 127770178810. The timeline is consistent, but naming the head avoids a reader concluding jerpfe's first commit alone was the fix.
