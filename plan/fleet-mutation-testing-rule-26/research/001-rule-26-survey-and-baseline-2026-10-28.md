## The maintainer's statement of what done means

10,000 tests is ridiculous. Commission a new plan around https://impatientprogramming.org/rules/#rule-26, utilizing the existing mutation testing. We previously set up mutation testing but I don't think it's run regularly. It should exist across at least all of the livespec repos. If it doesn't exist or is broken, we need to backfill and get it working. Then the definition of done is that this style of mutation-testing checks (per the link) are done and reported for every repo, and are hooked up through a `just` recipe (just to check that) that can be run on demand. Addition: metrics on IMPROVEMENT across ALL the repos, in both (1) exact test counts and (2) total test-suite runtime, as a before and after per repo and as a fleet total, measured the same way and reported in one table with the method stated.

## Definition of Done assertions derived from that statement

- In each of the twelve fleet repos livespec, livespec-orchestrator-beads-fabro, livespec-dev-tooling, livespec-runtime, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec-orchestrator-git-jsonl, livespec-overseer, livespec-console-beads-fabro, livespec-tdd-proof and dolt-server, a rule-26 mutation run is configured and working: it enumerates a non-zero set of mutants over that repo's first-party code, runs every test against them and exits with a real verdict, and every absent, no-op or broken setup found by the survey (0/0 baselines, missing mutmut configuration, unarmed or not-applicable pure_trees opt-outs, the livespec nested-layout failure) has been backfilled.
- Every one of those repos exposes the same on-demand recipe `just mutation-kill-matrix` that runs its mutation check and writes the report to a documented path, using a language-appropriate engine where the repo is not Python (cargo-mutants for Rust, a TypeScript engine for the extension, a shell-appropriate engine for dolt-server).
- Each report is in the style rule 26 prescribes: a test-by-mutant kill matrix that lists every surviving mutant and every test that catches no mutant that another test does not also catch, so redundant tests and missing obligations are both visible.
- A report from a real run of `just mutation-kill-matrix` has been produced for every one of those repos and recorded durably, stating mutants generated, mutants killed, survivors and redundant-test candidates per repo.
- `just mutation-kill-matrix` is on demand only: it is absent from the `just check` aggregate, the commit-time hooks and every required per-PR job, and the `just check` aggregate wall-clock in each repo is not increased by this plan.
- Before any test is removed, the exact collected test count and the total test-suite runtime of every repo were measured by one stated method on one host and recorded as the baseline, because no test-only runtime baseline exists in current evidence.
- After the tests the matrices prove redundant were removed, with no previously killed mutant left surviving, the exact test count and total test-suite runtime of every repo were re-measured by the same method on the same host.
- One table reports repo | tests before | tests after | delta | runtime before | runtime after | delta for every repo and as a fleet total, states the measurement method, and shows the fleet total test count and total runtime both lower than the baseline.

## Rule 26 - what "this style of mutation testing check" means

Source: https://impatientprogramming.org/rules/#rule-26 (fetched 2026-10-28).

Title: "Every test must prove it's worth keeping."

Quoted from the rule: "Not all code needs unit tests, because every test (unit or otherwise) has to prove that it's worth
keeping." and "Agents will happily write thousands of automated tests along with your code." and the selection criterion:
"keep a test only if it catches something no other test catches." The rule's figure is a KILL MATRIX of six tests against
eight mutants (code deliberately broken in small ways); its caption: "Take away tests 3 and 5 and every mutant shown is
still caught." (The page tool truncates quotes at 125 characters, so the quotes above are the exact fragments it
returned, not the whole paragraph.)

Operational meaning, as this plan reads it:

1. Generate mutants of the first-party code (small deliberate breakages).
2. Run EVERY automated test against EVERY mutant and record the full test-by-mutant kill matrix. A bare mutation SCORE
   (killed / total) is not the rule-26 artefact; the per-test matrix is.
3. A test earns its place only if it is the sole killer of at least one mutant (or otherwise catches something no other
   test catches). A test whose every kill is shared with another test is a redundancy candidate and is removed. A mutant no
   test kills (a survivor) is a missing obligation and is reported, not silently ignored.
4. Neighbouring rules on the same page: 19 (standards are enforced by machines; mutation gates are one such automated
   check), 20 (the Contract is made executable; the matrix catches tests that pass regardless of the code), 28 (a bug means
   the Contract lacked an obligation: add the test that kills the matching mutant, then fix), 29 (contract coverage is
   published), 27 (green merges itself).

Why this plan exists: the orchestrator repo's suite is now 11,672 collected tests; its red-green-replay suite-green leg
takes 40-60 min serially and overruns factory turn ceilings. Parallelism (xdist) is a separate in-flight fix and is NOT
this plan's scope. This plan attacks suite SIZE and QUALITY.

## Survey of existing mutation testing (2026-10-28, read-only)

The fleet set is the twelve repos the maintainer's coordinator named. No fleet manifest exists in livespec-dev-tooling
(searched; the only repo list is implicit in per-repo pin/dispatch workflows), so that list is the scope of record.

The shared check is `livespec_dev_tooling.checks.check_mutation` (mutmut 3.2.3, ratchet against `.mutmut-baseline.json`,
80% hard floor, RUN/SKIP lever `LIVESPEC_RUN_MUTATION`). Its slug `check-check-mutation` is a CANONICAL slug wired into
the `just check` aggregate of the repos that carry it, where it self-skips (exit 0) when the lever is unset. It reports a kill RATE only; it
has no per-test kill matrix, so even a perfectly working instance would not be rule-26 style.

| repo | tool | recipe | runs? | in CI? | notes |
|---|---|---|---|---|---|
| livespec | mutmut 3.2.3 (only repo with `[tool.mutmut]`: paths parse/ + validate/, runner `uv run pytest -x -q`) | `check-mutation`, `check-check-mutation` | NOT shown to work. Committed `.mutmut-baseline.json` is the 0/0 placeholder. Epic livespec-mutreal.1 (2026-07-19 diagnosis, not re-verified here) says `mutmut run` fails with ModuleNotFoundError inside the instrumented copy -> 0 mutants. Not executed (> 2 min). | release gate only: `release-gate-pre-tag` on release-please PRs and `release-tag.yml`, both with `LIVESPEC_RUN_MUTATION=true`; per-PR CI skips | `pure_trees = unarmed_until livespec-mutreal.1` |
| livespec-orchestrator-beads-fabro | mutmut 3.2.3 dependency only; no `[tool.mutmut]`, no baseline file | `check-check-mutation` | no (no-op) | ci.yml invokes the recipe with the lever unset, so it skips | `pure_trees = unarmed_until bd-ib-6qb2mc` |
| livespec-dev-tooling | mutmut 3.2.3 dependency only; no `[tool.mutmut]` | `check-check-mutation` | no. Baseline 0/0. A stale gitignored `mutants/` directory (May 2026) is left over from an old attempt | ci.yml invokes it, lever unset -> skip | `pure_trees = not_applicable` (flat library), so even armed it scans nothing |
| livespec-runtime | mutmut 3.2.3 dependency only; no `[tool.mutmut]` | `check-check-mutation` | no. Baseline 0/0 | ci.yml invokes it, lever unset -> skip | `pure_trees = not_applicable` |
| livespec-driver-claude | none (no mutmut dependency) | `check-check-mutation` (calls the shared module) | no-op | recipe in aggregate; no lever | `pure_trees = not_applicable` |
| livespec-driver-codex | none | `check-check-mutation` | no-op | ci.yml invokes it, lever unset | `pure_trees = not_applicable` |
| livespec-driver-pi | none (Python shell plus a TypeScript extension) | `check-check-mutation` | no-op | ci.yml invokes it, lever unset | TypeScript side has no mutation tooling at all (stryker is the natural candidate) |
| livespec-orchestrator-git-jsonl | mutmut 3.2.3 dependency only; no `[tool.mutmut]`, no baseline | `check-check-mutation` | no-op | recipe in aggregate | `pure_trees = unarmed_until livespec-mutreal.1` |
| livespec-overseer | none installed | `check-check-mutation` | `release-tag.yml` documents it as VERIFIED NO-OP: exits 0 in about a second on an explicitly empty `pure_trees` | release-tag.yml sets the lever, still no-op | `pure_trees = unarmed_until livespec-mutreal.1` |
| livespec-console-beads-fabro | cargo-mutants (Rust) | `check-mutants` (merge gate, `--in-diff`), nightly full sweep with fuzz (epic item 547r5w) | The only working setup. Local `mutants.out/` dated 2026-08-22. A full sweep of console-domain + console-application is 1456 mutants, at least 46 min (measured, recorded in the justfile) | yes: dedicated `check-mutants` CI job on PRs plus a nightly soak | per-mutant verdicts only, no per-test kill matrix; SPECIFICATION says `just check` MUST NOT include mutation runs |
| livespec-tdd-proof | none | none | n/a | ci.yml exists, no mutation | 5 tests |
| dolt-server | none | none | n/a | ci.yml exists, no mutation | shell-based tests (17 `*.test.sh`), no pytest, so the Python engine does not apply |

Summary of the state: mutation testing is NOT running anywhere in the Python fleet. Every `.mutmut-baseline.json` is a 0/0
placeholder, exactly one repo (livespec) has a `[tool.mutmut]` block, nine repos' `check-check-mutation` is a verified or
effective no-op, and the check that does exist cannot emit a kill matrix. The one genuinely working setup is the Rust
console repo's cargo-mutants gate. Nothing in the fleet implements rule 26's per-test matrix.

## Baseline (2026-10-28)

Test counts: exact `pytest --collect-only -q -p no:cacheprovider` totals taken on this host 2026-10-28 (parametrized cases
each count once). Console uses `cargo nextest list --workspace` lines containing `::` (an approximation of nextest's own
count; the baseline step should replace it with `cargo nextest list --message-format json`). dolt-server has no pytest
suite; its 17 shell test scripts have no per-test count, so its baseline step must define one.

Runtime: NO test-only runtime baseline is cheaply obtainable from existing evidence, so capturing it is the FIRST
Definition-of-Done step. The only existing evidence is whole `ci.yml` wall-clock (every gate, not just tests, queueing
included) of the latest successful master run, read from the GitHub Actions API on 2026-10-28. It is a proxy, not the
baseline.

| repo | tests (exact, collect-only) | latest green master `ci.yml` wall-clock (proxy) | run date (UTC) |
|---|---|---|---|
| livespec | 1741 | 2m51s | 2026-10-27 |
| livespec-orchestrator-beads-fabro | 11672 | 8m30s | 2026-10-27 |
| livespec-dev-tooling | 5520 | 9m21s | 2026-10-27 |
| livespec-runtime | 450 | 13m42s (includes queueing; the next two runs were under 2m) | 2026-10-27 |
| livespec-driver-claude | 2145 | 2m15s | 2026-10-27 |
| livespec-driver-codex | 729 | 2m06s | 2026-10-27 |
| livespec-driver-pi | 61 | 2m38s | 2026-10-27 |
| livespec-orchestrator-git-jsonl | 481 | 3m00s | 2026-10-27 |
| livespec-overseer | 3780 | 3m16s | 2026-10-27 |
| livespec-console-beads-fabro | 2079 (nextest list, approximate) | 5m24s | 2026-10-27 |
| livespec-tdd-proof | 5 | not captured | n/a |
| dolt-server | 17 shell scripts (no per-test count) | not captured | n/a |
| fleet total (pytest repos) | 26584 | n/a | |
| fleet total incl. console | 28663 | n/a | |

Note the coordinator's "about 10,244" orchestrator figure is stale: it collects 11,672 today. The orchestrator's red-green
replay suite-green leg (40-60 min serial, maintainer-reported) is the only existing test-only runtime evidence and is
orchestrator-specific.

## Prior art (ledger ids, all verified in the livespec-dev-tooling and livespec tenants, `--status all`)

- `livespec-mutreal` (livespec tenant, backlog): "Stand up functional mutation testing across the livespec family". The
  closest prior epic; untouched since 2026-07. This plan SUPERSEDES its intent and should cross-reference it, not adopt it
  (it is in a different tenant). Child `livespec-mutreal.1` (backlog): fix the livespec nested-layout mutmut bug and capture
  a real baseline.
- `livespec-8kip` (livespec tenant, backlog): check-mutation must emit a structured JSON fail-summary.
- Closed, in this tenant, all about the check's trustworthiness: `livespec-dev-tooling-q3r` (parse mutmut-3.x output, nested
  staging cwd), `-z45` (the check masked its own failure class), `-6j6` (z45 deleted the rc>=2 hard fail), `-y27` (rc=1 with
  a partial tally poisons the ratchet).
- Open, in this tenant, blocking arming of the role key: `livespec-dev-tooling-8zv3` (pure_trees is a shared role key with
  five consumers), `livespec-dev-tooling-8o8e.30`.
- Live plan `plan/mutation-testing-keystone/` (this repo; anchor `unassigned`, ledger anchor cross-tenant to
  livespec-mutreal.1). It records the livespec layout defect and the total=0-passes defect and says to move it to the
  livespec repo. This plan does not touch it; its child work is absorbed by DoD assertion 1 for `livespec` and the
  disposition (supersede, close or move) is the first child of this plan's carrier map.
- Console tenant: items `txtzn5.10` (check-mutants merge gate) and `547r5w` (nightly soak).

## Decisions taken at creation (no maintainer picker; defaults chosen)

1. Recipe name is `just mutation-kill-matrix`, identical in every repo. Rationale: any `check-*` recipe is policed by
   the canonical-slug enforcement and would be pulled into the `just check` aggregate, which the maintainer forbids (DoD
   assertion 5); `check-mutation` already exists in livespec as the release-gate score check with different semantics;
   the name states that the artefact is the rule-26 kill matrix, not a score. It writes its report under `tmp/` (or a
   repo-declared path) and does not gate.
2. Engine per ecosystem: mutmut for Python repos (already pinned at 3.2.3), cargo-mutants for the Rust console repo, and a
   language-appropriate engine for the TypeScript extension (stryker) and the shell-only repo (dolt-server). The shared
   per-test attribution layer lives in livespec-dev-tooling (this repo) and the per-repo adoption is thin. For the Python
   path the likely mechanism is running mutmut with a per-test runner (or pytest per-test selection against each mutant)
   to build the matrix, since mutmut reports only per-mutant status. Design child decides.
3. Pruning is in scope. The maintainer's complaint is the suite size and the added requirement is a before/after
   improvement table, so tests the matrix proves redundant are removed (with the kill set preserved) and the table
   reports the result. Removal must not leave any previously-killed mutant surviving.
4. Plan assertions carry the plan skill's default proof mode `host_captured` (a plan has no factory-captured leg; no factory
   run executes against an epic). None is `human_attested`.
5. The existing no-op `check-check-mutation` behaviours (total=0 passes, unarmed opt-outs) are not left as a substitute:
   assertion 1 requires each repo to enumerate a non-zero mutant set.
6. No children are filed at creation (the plan prose files children only after a scoping event; none is recorded yet).

## Carrier map (proposed, not filed)

Plan assertion ordinals refer to the epic's Definition of Done.

- C0 baseline capture (assertion 6): one shared recipe/script and a per-repo first run recording exact test count and
  test-only runtime by one method, before any other change.
- C1 shared kill-matrix engine and report format in livespec-dev-tooling, plus the `mutation-kill-matrix` recipe template
  and its guard that the recipe is absent from the `check` aggregate (assertions 2, 3, 5).
- C2 per-repo adoption, one child per repo, twelve in all: livespec (also fixes the layout defect), orchestrator-beads-fabro,
  dev-tooling, runtime, driver-claude, driver-codex, driver-pi (Python plus TypeScript), orchestrator-git-jsonl, overseer,
  console-beads-fabro (cargo-mutants plus per-test attribution), tdd-proof, dolt-server (assertions 1, 2, 4).
- C3 pruning children, one per repo, filed only after that repo's first report (assertion 7).
- C4 the single improvement table and its method note (assertion 8), plan-level proof.
- C5 disposition of `plan/mutation-testing-keystone` and of `livespec-mutreal` / `livespec-mutreal.1` / `livespec-8kip`.

Suggested order: C0, C1, C2 for livespec-orchestrator-beads-fabro first (largest suite, the motivating case), then the other
repos, C3, C4.

## Reading order for a resuming session

This note first, then `plan/mutation-testing-keystone/handoff.md`, then `livespec_dev_tooling/checks/check_mutation.py`
docstring, then the console `check-mutants` recipe in `livespec-console-beads-fabro/justfile` as the one working reference.
