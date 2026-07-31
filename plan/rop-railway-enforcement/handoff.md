# rop-railway-enforcement — arm the check that was never armed, then remediate six repos

**Ledger anchor:** epic `livespec-dev-tooling-8o8e`

**Thread:** `plan/rop-railway-enforcement/` in **livespec-dev-tooling**
(`https://github.com/thewoolleyman/livespec-dev-tooling/blob/master/plan/rop-railway-enforcement/handoff.md`)

**Supervised thread.** A supervisor session (`rop-railway-enforcement-supervisor`) drives this
worker and owns `supervisor-handoff.md` — that file is the ROLE charter, this one is the LIVE
RECORD, and **the ledger is authoritative over both**. Every live-state claim below expires in
minutes; re-derive before acting:

```bash
cd /data/projects/livespec-dev-tooling && /usr/local/bin/with-livespec-env.sh -- bd show livespec-dev-tooling-8o8e.1
```

---

## 🔴🔴 THIS THREAD BROKE THE FLEET'S RELEASE FAN-OUT FOR SEVEN HOURS, AND EVERY GREEN LIGHT STAYED GREEN

**2026-07-30. First-class finding, given its own heading because a merged PR body is not a
work queue and this is the epic's own subject arriving inside the epic's own remediation.**

**WHAT HAPPENED.** `vzwa`'s conversion commit `89296e0` added a BARE
`from returns.unsafe import unsafe_perform_io` to
`cross_repo/ci_yaml_canonical_reconcile.py` — no `_VENDOR_DIR` preamble. `returns` is
VENDORED, not installed, so a bare import resolves only if some EARLIER import in the same
process already put `_vendor/` on `sys.path`. That module is a `python -m` **ENTRY POINT** in
the reusable bump-pin workflow, where nothing runs first. Every consumer's pin bump died on
`ModuleNotFoundError: No module named 'returns'`. **SEVEN of eight members sat at `v1.8.4`
while this repo released through `v1.12.0`.** Fixed by **PR #930** (`e9c2f5e`, released
`v1.12.1`), which fixes the CLASS: a test sweeps the whole first-party tree by `rglob`, and
it caught a second latent instance (`checks/_ci_matrix_parse.py`).

**⛔ THE PART THAT MATTERS MORE THAN THE BUG: dev-tooling's OWN CI WAS GREEN THE ENTIRE TIME,
and so was every member's.** A green signal that means nothing is the defect this thread
exists to close, and this thread shipped one. `just check` passed 64/64 on the commit that
broke the fleet, because the failing environment — being the process entry point — is the one
environment no unit test exercises. **A test suite has always imported something else first.**

**IT IS THE THIRD AXIS, EXACTLY** (`zu85` / `dx8l`): *"CAN this module import `returns` at
all, in EVERY environment it executes in?"* This file already records that question as binding
on every remaining conversion. It was not asked of this one. **A perfect answer to the railway
question does not answer it** — and being right about the failure semantics is what made the
change feel finished.

**✅ AND A CLAIM I MADE IS RETRACTED, because it changes the recovery.** I wrote in `#930`'s
commit and PR body that the breakage was **SELF-LOCKING** — that a member running the reusable
workflow from its own stale pin could never receive the fix. **That is FALSE.** The reusable
workflow's `Checkout livespec-dev-tooling support modules` step carries **NO `ref:`**, so it
takes dev-tooling's **DEFAULT BRANCH**. The failing code was master's, and the fix was live to
the next dispatch with no per-member unlock. The recovery was a fresh dispatch, not a rescue.
**That no-`ref:` is its own standing hazard and the real lesson:** a workflow pinned at a tag
executes **UNPINNED** support modules, so one master-only regression breaks every member's
fan-out instantly — which is exactly what happened.

**✅ REPAIRED AT THE CONSUMED END, per `dx8l` doctrine — a pin moving on the forge, not a
green run.** A re-run is refused by the workflow itself ("a rerun always builds the original
event SHA"); the sanctioned recovery is a fresh `sibling-released` dispatch, which the error
message prescribes. Measured after dispatching:

| member | pin |
|---|---|
| `livespec`, `livespec-driver-claude`, `livespec-driver-codex`, `livespec-orchestrator-git-jsonl`, `livespec-console-beads-fabro` | **v1.12.1** |
| `livespec-runtime` | **v1.12.0** (bumped from the earlier dispatch; PR #399 merged) |
| `livespec-orchestrator-beads-fabro`, `livespec-overseer` | bump PRs **#1186** / **#409** OPEN, **zero failing checks**, merging under their own CI |

**🔴 AND THE LOUDER FINDING — `livespec-dev-tooling-0j3i` (P0). WHY NOTHING TOLD US.**
MEASURED by RUNNING the three pin-currency rows against all nine live members, not inferred.
**The rows FIRED. Every time. On every stale member.** `uses-pin-currency` reported the exact
file and the exact stale ref (`…reusable-bump-pin-from-dispatch.yml current v1.8.4 latest
release v1.12.1`) continuously. **All three are registered via `_warning_committed_file_row`,
so every finding is `severity=warning`** — it fails no run and gates no PR. **The detection was
never the gap; a correct, continuously-firing signal reached nobody for seven hours.** That is
`2j2l`'s class one turn out: `2j2l` is a row that CANNOT SEE a bad state, this is a row that
sees it perfectly and cannot make anyone care. **AND SEPARATELY, NO ROW COVERS THE PIN THAT
DECIDED ANYTHING:** the three specs cover `.livespec.jsonc` `compat.pinned`, workflow `uses:`
refs, and fabro image tags — **zero hits for `pyproject`**, so
`[tool.uv.sources] livespec-dev-tooling tag`, the pin that governs which dev-tooling a member
actually RUNS, is measured by nothing. `dev-tooling-pin` asserts that pin EXISTS, never that it
is CURRENT. **The two pins moved in lockstep only because the bump rewrites both — precisely
when the fan-out breaks, that correlation is not guaranteed, and only the uncovered one
decides what runs.** Do not "fix" this by making the rows errors everywhere: they warn because
a sibling's stall should not red an unrelated repo's PRs, which is a real reason. `0j3i`
records the lane-scoped shape instead.

---

## ▶️ START HERE — where the work actually is

> **COLD START, IN ORDER.** This file is all a fresh session inherits.
>
> 1. Re-derive live state — everything below ages in minutes:
>    `cd /data/projects/livespec-dev-tooling && /usr/local/bin/with-livespec-env.sh -- bd show livespec-dev-tooling-8o8e`
>    (the EPIC — `8o8e.1` is CLOSED and is a record, not a work item)
> 2. **NOTHING IS MID-FLIGHT — re-verified at the 2026-07-31 session wrap-up.** No worktree of
>    this thread's is open in ANY of the six repos it has touched (`livespec-dev-tooling`,
>    `livespec`, both Drivers, both orchestrators), no PR of its own is unmerged, and no
>    background job is running. There is no half-finished edit and no un-amended Red commit to
>    find. Several FOREIGN worktrees exist in those repos; **reap none of them, and ENUMERATE
>    with `git worktree list` rather than trusting any count — including this sentence's
>    absence of one.**
>
>    **THE SEVEN PRs THAT SESSION LANDED, all merged:** **#941** (the triage record), **#942**
>    (`8o8e.3`, the re-export blind spot), **#946** (`8o8e.4`, CHECK-FIX), **#949** (DECLARE),
>    **#950** (the table self-consistency sweep). **CLOSED:** `8o8e.3`, `8o8e.4`. **OPEN and
>    deliberately OFF the arming queue:** `8o8e.2` (P1), `8o8e.5` (P2), `8o8e.6` (P2).
>
>    **AND THE 2026-07-31 CONVERT SESSION: PR #952, MERGED — master `c35ea9e` + `87fd400`.**
>    Two Red→Green pairs, both carrying both trailer sets (verified on the forge AFTER a fetch,
>    post-rebase). Offenders **70 → 61**. Nothing of it is open; its worktree is removed and its
>    branch deleted. Recorded in **#955** (`cb81910`).
>
>    **AND THE 2026-07-31 `2j2l` INVESTIGATION SESSION — NOTHING OF IT IS IN CODE.** Verified at
>    its wrap-up: `git worktree list` shows only the primary plus **five FOREIGN worktrees**
>    (`cap-test-parallelism`, `ci-concurrency-group`, `docs/archive-fleet-plan-lifecycle-thread`,
>    `fix-except-check-breadth-aware`, `fix/generated-block-comment-syntax`) — **REAP NONE OF
>    THEM**, and enumerate rather than trusting that list. The only OPEN PR in this repo is
>    **#285**, which is FOREIGN. No background job is running. Its entire output is the
>    investigation block in §"START HERE" — a reading and a measurement, no code.
>    **Version note:** the `v1.0.0` figures in steps 3–4 are the HISTORICAL `8o8e.1` discharge
>    evidence. dev-tooling has released well past it since; **do not read any step below as
>    current pin state — re-derive the pin from the forge if you need it.**
> 3. **ALL FOUR PHASES HAVE LANDED, AND THE SPEC IS RATIFIED.** Phase 3 + `oitd`
>    (`606f17b`, `34c05c1`), spec v033 (`0500155`), `pj3j` (`c0c0472`), Phase 4 (`b36e0b8`).
> 4. **✅ `8o8e.1` IS CLOSED — the precondition is DISCHARGED with per-repo evidence.** The
>    fan-out completed: **`v1.0.0` is tagged and CONTAINS `b36e0b8`**, and all eight siblings
>    both DECLARE `tag = "v1.0.0"` and RESOLVE `livespec-dev-tooling==1.0.0` at rev
>    `20227edb…` in their `uv.lock`. **Eighteen pieces of evidence** — see the discharge
>    section below. Merged, released AND consumed.
> 5. **🟢 AUTHORITY IS GRANTED. THERE IS AUTHORIZED WORK QUEUED. DO NOT STAND BY.** Earlier
>    revisions of this file told a cold start to stand by because everything was
>    maintainer-gated. **That is now FALSE and is the single most dangerous stale line this
>    file has ever carried.** Maintainer ruling 2026-07-29, verbatim in substance: *"Do the
>    proposed change, the revise, the grooming, the implementation, and everything
>    autonomously. Just get this work done unless you have an absolutely, truly blocking
>    question for me."* And on step 6: *"Remediate dev-tooling's 59, then arm, then fan out."*
>    The grant is **not repo-scoped** — a cross-repo propose-change into `livespec` was filed
>    and accepted under it (v177). **`5ror`, `clkf`, `fwcwxv`, `pj3j` and `livespec-i04f` are
>    all CLOSED.** The spec lifecycle is NOT waived — changes still go through
>    propose-change → revise as OPERATIONS — but the accept/reject decision is delegated.
> 6. **▶️▶️ `721o` IS CLOSED AND MERGED. THE CRITERION IS LIVE, AND IT REPORTS **9**, NOT 0.
>    "RATIFIED-RULE VIOLATIONS ARE ZERO" IS RETRACTED — read step 6e before planning
>    anything.** Measured on master `0788e93` with the shipped check: **25 dropped + 6 kept
>    + 3 ADDED = 9**.
>
>    **✅ `9sl0`, `rvw3`, `q5lb` AND `vzwa` ARE ALL CLOSED. 🎯🎯 THE TWO NUMBERS AGREE AT
>    **ZERO**.** Re-measured on MERGED master `89296e0` with the shipped code, never inherited:
>    universe **150**, v178 public **167**, member-1 exempt **382**, member-2 exempt **1**
>    (0 rejected, the two member sets verified DISJOINT), **0 offenders** — and the ratified rule
>    considers **0** a violation. **The remediation half of step 6 is DONE.** `vzwa` took four
>    PRs, consumer-first: livespec **#1847** (dual-shape read), **#908** (the incremental gate
>    selects `*_edges.py` siblings), **#913** (ci-matrix tests clear the ambient severity var),
>    **#905** (the conversion). ~~Arming now waits on `5cai` and the `995m` known-gap statement,
>    and on NOTHING in the count.~~ **SUPERSEDED — `5cai` IS REGISTERED (#934). Arming now waits
>    on the `995m` known-gap statement ALONE.~~ **SUPERSEDED AGAIN, 2026-07-31 — ARMING IS
>    BLOCKED ON `qndn` (P0), WHICH IS NOW THE FIRST GATE. Read the ⛔ block immediately below
>    before planning anything.**
>
>    **🔺🔺 THE META-FINDING, AND IT OUTRANKS THE 75: THE ANSWER WAS ALREADY IN THIS FILE, WRITTEN
>    CORRECTLY, AND NOBODY READ IT AGAINST THE GATE IT BLOCKED.** §"THE THREE UNDECLARED
>    CONSUMPTIONS" states it almost verbatim — *"this check skips `_`-prefixed FILES wholesale,
>    while v178 clause 0 disqualifies only a `_`-prefixed NAME — so the file-level skip is wider
>    than the ratified rule, and a cross-repo consumer is reaching through it"* — and it NAMES the
>    two consumers, one of them a beads-fabro HOOK (the `dx8l` blast-radius shape). **Both are
>    confirmed in the 75.** So the blocker sat in this thread's own handoff, true and specific,
>    from before the arming attempt, and was never connected to the precondition it invalidated
>    until a MEASUREMENT forced the join.
>
>    **THIS IS THIS THREAD'S SIGNATURE DEFECT IN A NEW PLACE, and it is worth more than the 75.**
>    Every prior instance was a FALSE record — a stale count, a ratified paragraph contradicted by
>    measurement, a status field that lied. **This one is a TRUE record nobody re-read against the
>    current question.** A finding filed as an OBSERVATION, and never re-asked as a PRECONDITION,
>    is how a known defect survives an epic built to close it. **Practical consequence for whoever
>    reads this next: before accepting ANY precondition as discharged, grep this file for the
>    surface it depends on. The answer to the next gate is more likely already written here than
>    not** — and this file is long enough that "I read it" and "I read it against this question"
>    are different claims.
>
>    **🔺🔺 AND THE THIRD VARIANT, FOUND 2026-07-31 AND WORSE THAN BOTH: A FALSE CLAIM THAT
>    CARRIES AN INSTRUCTION. CLOSING THE ITEM DOES NOT DISARM IT.** The three variants now
>    stand as: (1) a FALSE record someone might quote; (2) a TRUE record nobody re-read against
>    the current question (above); (3) **a false record that DIRECTS the next reader to ACT.**
>
>    The instance: `0j3i` claimed "no row covers the `pyproject` dependency pin" — FALSE
>    (`assert_dev_tooling_pin` → `_freshness_outcome` covers it for currency). `vt61` then
>    propagated that claim **with an action attached**: *"That is a fourth `PinCurrencySpec`, and
>    it is independent of this ruling; do not let one close the other."* So the false statement
>    was not inert — **it recruited the next reader into BUILDING A DUPLICATE ROW over an
>    already-covered surface**, and the "do not let one close the other" clause was specifically
>    engineered to survive the other item being resolved.
>
>    **THE STANDING RULE THIS PRODUCES, and it is sharper than the one we had: WHEN YOU RETRACT
>    A CLAIM, DO NOT ONLY GREP FOR THE CLAIM — GREP FOR INSTRUCTIONS DERIVED FROM IT.** Including
>    in items you are about to CLOSE: `vt61` was closed as discharged by v039 the same hour, and
>    a closed item with a live instruction in it still gets read. Both retractions were written
>    into its body BEFORE the close for exactly that reason. **A close is not a disarm.**
>
>    **⛔⛔⛔ ARMING IS BLOCKED. `livespec-dev-tooling-qndn` (P0) IS THE FIRST GATE, AND IT WAS
>    FOUND BY MEASURING BEFORE COMMITTING. ~~THE NEXT ACTION IS THE TRIAGE OF 75 FUNCTIONS~~ —
>    AUTHORIZED STANDING WORK, NOT A NEW DECISION.**
>
>    **✅✅ THE TRIAGE IS DONE AND THREE REMEDIATION STEPS HAVE LANDED —
>    `plan/rop-railway-enforcement/qndn-75-triage.md`. READ THAT FILE BEFORE PLANNING
>    ANYTHING; it carries all 75 by name with the evidence that convicted each.**
>
>    **▶️▶️ COLD START, THE ONLY THING YOU NEED FROM THIS BLOCK: the NEXT ACTION is
>    ▶️ THE REMAINING **23** CONVERT — the walker family is DONE.** ~~THE SEVEN PIN WALKERS AS
>    ONE FAMILY~~ — **✅ LANDED 2026-07-31, PR #962, master `96fc2a3`. Offenders 61 → 53,
>    re-verified on MERGED master. `2j2l` and `xhbp` are CLOSED.** Read the block below before
>    the next conversion: it carries three things the family cost that WILL recur.
>
>    ---
>
>    ## ✅ THE PIN-WALKER FAMILY LANDED — AND IT COST THREE THINGS WORTH MORE THAN THE 8
>
>    **PR #962, master `96fc2a3`, ONE Red→Green pair carrying both trailer sets (verified on the
>    FORGE after a fetch). Full suite 2271 passed. `2j2l` + `xhbp` CLOSED with evidence.**
>
>    **THE MEASUREMENT: 61 → 53**, exactly the eight family functions, nothing else moved.
>    Re-verified on MERGED master: universe **156** (was 155 — the +1 is the new
>    `fleet/_pin_walk_failure.py` sibling), offenders **53**. Measured at both ends with
>    `_find_offenders`, never through `main()`.
>
>    **1. 🔴 AN IMPORTED TYPE ALIAS IS NOT A SAFE ANNOTATION, AND ONLY THE COUNT TELLS YOU.**
>    Three of the eight did NOT drop on the first measurement (61 → 56, not 53). The three
>    single-file walkers were annotated with `PinWalkResult` **imported** from the sibling
>    module; the four directory-scan walkers used the SAME alias **defined locally** and dropped
>    fine. `_is_railway_compliant` matches the annotation's TERMINAL NAME and **cannot resolve an
>    alias across a module boundary**. This is the `memoized_snapshot` CHECK-FIX class the triage
>    already records, arriving in the RELAXING direction — the code was conformant and the check
>    said otherwise. ⛔ **For the remaining 23: annotate with the explicit `IOResult[...]` at any
>    cross-module boundary, and NEVER accept a conversion as done without re-running the count.**
>    A partially-credited conversion looks exactly like a finished one in the diff.
>
>    **2. ⛔ TWO HOOK FAILURES ARE STRUCTURAL AND WILL RECUR — budget them, do not route around.**
>    `check-file-lloc`: `_rows_pin_currency.py` hit **265 against the 250 HARD ceiling** because
>    the conversion added a renderer. Fixed by extracting `fleet/_pin_walk_failure.py`, the same
>    private-sibling split as `_ci_matrix_parse`. **Budget one module split per conversion that
>    adds a branch to an already-large file** — this is the LLOC analogue of the PLR0911
>    six-return cap units 1–2 paid. `check-per-file-coverage`: five uncovered lines, ALL of them
>    the new failure short-circuits. **Every converted call site adds a line no existing test
>    reaches**; the Green-leg `*_edges.py` sibling is not optional.
>
>    **3. 🔴🔴 A COVERAGE TRAP THAT WOULD HAVE PASSED WHILE PROVING NOTHING — TWICE OVER.**
>    Both halves are the epic's own subject in the test suite, and both were found by measuring
>    rather than by reasoning:
>
>    - **`walk_github_workflow_container_image`'s failure branch is UNREACHABLE through
>      `discover`.** `discover` stops at the FIRST failure, and TWO walkers read the same
>      `.github/workflows/*.yml` — so an unreadable workflow file ALWAYS fails at
>      `walk_github_workflow_uses` first. A test driving the composed entry point would look
>      thorough and leave that line uncovered forever. **Exercise each walker at its OWN seam
>      when the composed caller short-circuits.**
>    - **A `chmod 000` fixture is a LIE when the suite runs as root** — every read succeeds, the
>      assertion never fires, the test passes proving nothing. Used **invalid UTF-8 bytes**
>      instead, which fail identically for every user. This is the SAME shape as the `PATH`-shim
>      fixture recorded under CONVERT units 1–2, and as the `_scan` measurement trap: **a
>      fixture that cannot fail is a green that means nothing, inside the epic that exists to
>      remove them.** Ask of every new fixture: *if the behavior regressed right now, would this
>      assertion fire?*
>
>    **🔺🔺 THE GENERAL FORM, AND IT IS A CLASS WITH FOUR MEMBERS RATHER THAN AN ANECDOTE —
>    STATE IT ONCE AND APPLY IT TO EVERY INSTRUMENT THIS THREAD BUILDS:**
>
>    > **AN INSTRUMENT THAT CANNOT PRODUCE A NEGATIVE RESULT HAS NOT PRODUCED A POSITIVE ONE.**
>
>    Four instances, all in THIS epic, all reporting CLEAN while reading nothing:
>
>    | instrument | why it could not fail |
>    |---|---|
>    | `chmod 000` fixture | every read succeeds when the suite runs as **root** |
>    | `PATH`-shim fixture (CONVERT units 1–2) | shim dir was **appended** to `PATH`, so real `git` answered |
>    | `_scan` / `main()` offender harness | `pure_trees` is `not_applicable` → **iterates zero files** |
>    | supervisor's ledger sweep (brief 62) | `for id in $ids` in **zsh** does not word-split → **one** bogus iteration, 0 bytes read, "clean across 94 items" |
>
>    **⛔ AND THE CATCH WAS A POSITIVE CONTROL IN EVERY SINGLE CASE — NEVER REVIEW, NEVER
>    READING THE CODE AGAIN.** Each was found by asserting the instrument could detect a
>    condition KNOWN to be present (a term known ubiquitous in the corpus; a count known
>    non-zero; a behavior known broken) and watching it report nothing. **Review cannot catch
>    this class**, because the instrument's code reads correctly — the defect is in what it was
>    pointed at, not what it does. **So: before trusting any negative result, feed the
>    instrument something it MUST flag.** One command, every time.
>
>    The operational form for a fixture stays as above — *if the behavior regressed right now,
>    would this assertion fire?* — and it is the same question asked of a measurement harness as
>    *would this count move if the thing I am counting appeared?*
>
>    **▶️ THE ANSWER-vs-FAILURE CALLS THIS FAMILY MADE, since the same question recurs 23 more
>    times.** An absent file, an absent directory, an empty `glob`, a parsed document that is not
>    an object, a `.vendor.jsonc` with no `libraries` array, and a Dockerfile with no `ARG` line
>    are all **ANSWERS** — the ratified missing-file tolerance, unchanged. Only failing to obtain
>    bytes, and failing to parse bytes we HAVE, are failures. **The one non-obvious call: a
>    `[tool.uv.sources]` block that EXISTS and yields no entry IS unparseable**, because that
>    block exists solely to hold pins — contrast the codex-acp Dockerfile, whose shape is not
>    this format's to adjudicate. That asymmetry is the reusable test: *does this container exist
>    SOLELY to hold the thing I could not find?*
>
>    **⚠️ ONE HONEST GAP IN THE COMMIT.** The body was written at RED per the ritual and amended
>    `--no-edit` to preserve the trailers, so it PREDATES the LLOC split and the edges file. Both
>    are described in PR #962's body instead. The commit is correct about the behavior and
>    incomplete about the mechanics; redoing the pair to fold them in would have cost more than
>    the accuracy gained. **Budget the split and the edges file INTO the Red-time body next
>    time** — they are now predictable rather than surprising.
>
>    **⏭️ WHAT THIS DID NOT CLOSE: `0j3i`.** Its escalation predicate and `published_at` plumbing
>    live at the ROW layer and never depended on the walkers — the negative result brief 61
>    accepted. It is still open and still owes code.
>
>    ---
>
>    **~~▶️ THE SEVEN PIN WALKERS AS ONE FAMILY~~ — `read_pin_text` + 7 walkers + `discover`'s
>    composition + relocating `PinFileUnreadable`, 8 of the 40 CONVERT. ✅ DONE (#962).**
>    ~~fire a fresh `sibling-released` dispatch for `livespec` v0.21.1~~ · ~~THEN the batched
>    `2j2l` + `xhbp` + `vt61` ratification~~ — **✅ BOTH LANDED 2026-07-31; see the block
>    immediately below.** ~~the git probes then the RGR trailers~~ — **✅ BOTH LANDED, PR #952,
>    master `c35ea9e` + `87fd400`.**
>
>    **⛔⛔⛔ READ THIS BEFORE MEASURING ANYTHING. THE OBVIOUS HARNESS REPORTS `0` AND READS AS
>    SUCCESS — AND IT WOULD CONVICT YOU OF THIS EPIC'S OWN FOUNDING DEFECT WHILE YOU REMEDIATE
>    IT.** `pure_trees` in this repo is `{ not_applicable = "flat-layout library has no
>    pure-module subtree" }`. So `role_trees()` returns **EMPTY**, `_scan` iterates **ZERO
>    FILES**, and **`main()` reports `0` offenders REGARDLESS OF WHAT THE CODE SAYS.** That is
>    not a passing check — **THAT IS THE UNARMED STATE, `8o8e`'s founding condition, and it is
>    lying in wait for the person doing `8o8e`'s own remediation.** A remediation harness built
>    on `_scan` or on `main()` will report `0` before your change and `0` after it, and you will
>    read that as "nothing broke".
>
>    **✅ THE ARMED MEASUREMENT — iterate `resolve_check_universe()`'s 155 files and call
>    `_find_offenders` PER FILE, never through `_scan` and never through `main()`.** Supply
>    `public` / `no_expected_failure_mode` exactly as `_scan` builds them
>    (`repo_local_public_names | declared_public_names`, then
>    `functions_without_expected_failure_mode | declared_absence_names`), and toggle
>    `rel_path.name.startswith("_")` to get both variants. **RE-MEASURE AT BOTH ENDS OF EVERY
>    CONVERSION with that harness** — the standing never-inherit-a-count rule is unchanged, but
>    the instrument it names is not `main()`.
>
>    **📏 BASELINE, measured on master `26a6b05` with the shipped analyses, NOT inherited:
>    universe **155** · offenders CARRYING the `_`-prefixed-FILE skip **0** · offenders DROPPING
>    it **61** · **all EIGHT family functions confirmed present in the 61** (triage rows 17–24).
>    ▶️ TARGET AFTER THIS UNIT: **53**.**
>
>    **⛔ THE FAMILY IS ATOMIC — IT IS ONE UNIT, NOT SEVEN, AND THE TRIAGE'S "do this one FIRST"
>    MEANS FIRST *WITHIN* IT.** Converting `read_pin_text` breaks **all seven callers
>    simultaneously**, so there is no partial landing and no intermediate green. Do NOT begin it
>    on thin context: an atomic change across two modules plus the row layer, begun and
>    abandoned, is how a dirty worktree or an un-amended Red commit happens, and this thread has
>    paid for both. Stopping clean BEFORE starting is the correct answer; stopping halfway is
>    not.
>
>    **▶️ THE SETTLED DESIGN IS ON `livespec-dev-tooling-2j2l`, NOT RESTATED HERE — read it
>    before writing any code.** It carries, with the reasoning: the `pin_walk` parameter on
>    `read_pin_text` and why the `.alt(replace(...))` alternative is worse; **TWO DISCRIMINATED
>    failure types** (`PinFileUnreadable` → `RowSkip`, `PinFileUnparseable` → `RowFinding`) —
>    **a single failure type CANNOT express v039's two bullets**, which is the whole `2j2l`/`xhbp`
>    fix; the three `unrecognized` emit sites and `_records_for`'s silent drop dying TOGETHER;
>    `discover` aborting on either failure on its existing partial-walk rationale; the
>    relocate-and-re-export that avoids the import cycle; and the ANSWER-vs-FAILURE call for this
>    family (`is_file` / `is_dir` / an empty `glob` are all **ANSWERS**, not failures).
>
>    **📌 AND A NEW ITEM THIS THREAD OWNS BUT DOES NOT GATE ON: `livespec-dev-tooling-e01t`
>    (P1).** All EIGHT `SKILL.md` bindings in `livespec-driver-claude` resolve livespec core via
>    `entries[0]` of `installed_plugins.json` — *whichever project on the host installed core
>    first* — instead of the entry whose `projectPath` matches. **Its gate: it blocks NOTHING on
>    the arming path and breaks EVERY `/livespec:revise` and `/livespec:propose-change` from this
>    repo, so the gate is THE NEXT SPEC RATIFICATION THIS THREAD NEEDS** — already paid by hand
>    once, to land v039.
>
>    ---
>
>    ## ✅✅ THE FAN-OUT IS REPAIRED AND v039 IS RATIFIED — AND THE ORDERING PAID FOR ITSELF WITH A FINDING
>
>    **2026-07-31. Both halves landed in one session. Every number below was measured on the
>    forge or by running the shipped sweep, never inherited.**
>
>    **✅ REMEDIATION FIRST, exactly as `v034` carve-out 1 required.** A fresh
>    `sibling-released` dispatch for `livespec` v0.21.1 was fired at all SEVEN stale siblings
>    (the form the reusable workflow's own rerun-refusal error message prescribes:
>    `gh api repos/<owner>/<member>/dispatches -f event_type=sibling-released -f
>    'client_payload[source_repo]=livespec' …`). All seven runs succeeded, all seven bump PRs
>    opened (dev-tooling **#957**, driver-claude **#355**, driver-codex **#335**, beads-fabro
>    **#1193**, git-jsonl **#476**, overseer **#431**, runtime **#405**), and **ALL SEVEN
>    MERGED under their own CI**. Re-measured after: **`compat.pinned` is `v0.21.1` in 8 of 8
>    siblings.** The 2026-07-30 outage has no remaining tail.
>
>    **✅ THEN THE RATIFICATION — `v039`, PR #958, master `40b65f3` + `29c7e2b`.** Filed and
>    ratified as ONE PR (the #854 pattern: a `file` commit then a `ratify` commit). Disposition
>    was **`modify`**, not accept — see below. `2j2l`, `xhbp` and `vt61` are answered by it.
>
>    **WHAT v039 ACTUALLY SAYS, since the titles still mislead.** It changes NO severity: the
>    lane scoping (`ctx.filter_consuming_preflight`) already existed and is kept verbatim. It
>    partitions staleness EXHAUSTIVELY — *fired-and-could-not-land* (open bump PR, escalates at
>    ANY age, unchanged) and **NEVER-FIRED** (no bump PR, escalates once the release ages past a
>    **two-hour settle window**, read from `published_at` on the `releases/latest` payload both
>    readers already fetch for `tag_name`, so no new API call and no local clock). And it
>    separates a can't-**RECOGNIZE** (ratified tolerance, kept) from a can't-**PARSE** of a
>    known-format file, which must be a distinct typed outcome a consumer cannot silently drop.
>    **No lever, no env var, no opt-out key** — the settle window is a ratified CONSTANT
>    precisely so it cannot become the opt-out by another name.
>
>    **⚠️ IT WAS A `modify`, AND THE REASON GENERALIZES TO EVERY FUTURE PROPOSE-CHANGE IN THIS
>    THREAD.** The proposal targeted `contracts.md` alone while introducing observable behavior,
>    which the revise prose's **Behavior-implies-Gherkin split makes MALFORMED**. Three
>    `scenarios.md` entries were co-edited in atomically (never-fired past the window,
>    never-fired INSIDE it, can't-parse), each naming the evaluating CONTEXT so the lane scoping
>    is ASSERTED rather than implied, plus three paired `tests/heading-coverage.json` entries at
>    `test: TODO` with tier-acknowledging reasons (the `scenarios.md` integration-tier rule).
>    **`contracts.md` adds/renames/removes no H2, so it needed no coverage co-edit** — the
>    registry tracks H2 headings only. Budget this co-edit into every behavioral proposal.
>
>    **🔺 AND THE INTENT-PRESERVATION CHECK PRODUCED THE STRONGEST ARGUMENT IN THE CHANGE, so do
>    not skip it as ceremony.** Running it surfaced that **`livespec-dh9r` — the design record
>    this section's escalation comes FROM — was itself an incident measured with "open bump PRs
>    fleet-wide: 0"**, which is precisely the state its own escalation cannot see. The record
>    that motivated the persisting-gap rule was an instance the rule could not detect. That went
>    into the ratified text as the supporting evidence, and it is better evidence than anything
>    the proposal reasoned its way to.
>
>    **🔴 THE FINDING THE ORDERING BOUGHT — `livespec-dev-tooling-ve7w` (P1), FILED, NOT STARTED.**
>    The live sweep re-run after remediation (`members: 9`, **`blind_rows: 0`**, exit **passed**)
>    shows **ONE** member that newly escalates under v039 — **not the eight this file warned
>    about**, because the re-dispatch removed the incident first. It is **`livespec` ITSELF**:
>    its own `.livespec.jsonc` `compat.pinned` sits at **`v0.20.2`** against latest **`v0.21.1`**
>    — TWO releases stale — with **ZERO open bump PRs in livespec**, verified on the forge.
>
>    **AND IT CANNOT SELF-HEAL, WHICH IS WHY IT IS P1 RATHER THAN A STALE PIN.** The fan-out
>    EXCLUDES the publishing repo from its own dispatch matrix by ratified contract, and livespec
>    publishes every livespec release — so no `sibling-released` dispatch ever reaches it and the
>    rewrite path never runs against its own file. `reusable-pin-freshness.yml` is the ratified
>    safety net for exactly this class and has not opened a PR across at least two releases;
>    **whether the shim is unwired in livespec or the walk skips a self-referential pin is
>    UNDIAGNOSED — measure it, do not assume which.** ⛔ Do NOT "fix" it by hand-editing the pin:
>    that repairs one release and leaves the mechanism broken. **This is the NEVER-FIRED class in
>    its purest and most permanent form, found by the predicate the same session ratified it.**
>
>    **Two other live rows, both correctly classified and NEITHER a v039 consequence:**
>    `livespec-driver-codex` carries a dev-tooling `v1.13.2 → v1.13.3` **persisting gap with open
>    bump PR #334** across `dev-tooling-pin` / `uses-pin-currency` / `fabro-pin-currency` — that
>    is the FIRED class, already escalating under the PRE-v039 rule, untouched by this change.
>
>    **⏭️ WHAT v039 DOES NOT DO: the CODE. Nothing is flipped.** The predicate, the settle
>    window, and the can't-parse carrier are ratified text only. The flip lands with the walker
>    family below — and the remediate-then-flip precondition is now DISCHARGED, so the next
>    session may implement without re-running the fan-out. **Re-run the live sweep at both ends
>    of that unit anyway**, per this thread's standing never-inherit-a-count rule.
>
>    **NOTHING OF THIS SESSION IS OPEN.** PR #958 merged, worktree reaped, branch deleted,
>    primary checkout clean on master `29c7e2b`. The five FOREIGN worktrees persist — **REAP
>    NONE, and ENUMERATE with `git worktree list` rather than trusting this sentence.**
>
>    ---
>
>    ## 🔴🔴 THE 2j2l INVESTIGATION IS DONE AND IT INVERTS THE ITEM. READ THIS WHOLE BLOCK BEFORE FILING ANYTHING.
>
>    **Measured 2026-07-31 on master `cb81910` by READING THE CODE AND RUNNING THE LIVE FLEET
>    SWEEP, not from the items' own text. TWO OF `0j3i`'s CLAIMS ARE FALSE, and supervisor
>    brief 59 repeated one of them — so the items and the brief must both be read against the
>    code before any of it is quoted.**
>
>    **RETRACTION 1 — "all three rows are registered via `_warning_committed_file_row`, so
>    every finding is `severity=warning`" is FALSE.** `_warning_committed_file_row`
>    (`fleet/_contract_rows.py:87`) and `_manual_committed_file_row` (`:97`) are
>    BEHAVIOURALLY IDENTICAL — neither sets severity; they differ only in the hint string and
>    `applies_to`. Severity comes entirely from each row's own `RowFinding(severity=...)`, and
>    `_rows_pin_currency._pin_currency_outcome` DOES escalate:
>    `severity="error" if ctx.filter_consuming_preflight else "warning"`. **The lane-scoped
>    escalation `vt61` recommends and brief 59 endorses ALREADY EXISTS, is wired, and matches
>    the ratified text.** ⚠️ The helper's NAME asserts a property it does not implement — this
>    epic's own subject, inside the fleet contract table. Worth its own item.
>
>    **RETRACTION 2 — "NO row covers `[tool.uv.sources] livespec-dev-tooling tag`;
>    `dev-tooling-pin` asserts that pin EXISTS, never that it is CURRENT" is FALSE.**
>    `assert_dev_tooling_pin` → `_freshness_outcome` (`fleet/_rows_files.py:177`) compares the
>    pin to the latest release and escalates on a persisting gap identically to the three
>    currency rows. **The deciding pin IS covered for currency.** The narrower half `0j3i`
>    also stated is TRUE and is what misled it — zero hits for `pyproject` in
>    `_rows_pin_currency.py` — because the coverage lives in `_rows_files.py`. The ratified
>    §"Pin-currency severity policy" already names it as one of FOUR evaluated formats.
>
>    **▶️▶️ SO THE HOLE IS THE ESCALATION *PREDICATE*, NOT THE SEVERITY — and this is what the
>    propose-change must say.** All four rows escalate only on
>    `persisting_bump_pr_number(...) is not None` — **stale AND a bump PR for the latest
>    release is ALREADY OPEN** ("the mechanism fired and could not land"). Measured in the
>    workflow: the module that broke the 2026-07-30 fan-out runs at
>    `.github/actions/bump-pin-rewrite/action.yml:364`; **`Open auto-merge PR` is at line 463,
>    four steps later.** A failure there means **NO PR IS EVER OPENED** — so the outage's state
>    was *stale with NO open bump PR*, which the ratified policy classifies as **"normal
>    operation — the minutes-long window between a release and its bump PR merging."**
>
>    **Nothing could have stopped, and NOT because the severity was mis-set: the condition
>    never entered the escalating class at all.** The predicate has no TIME and no
>    RELEASE-DISTANCE component, and it names only the "fired and failed" failure mode while
>    the outage was "NEVER FIRED" — the worse of the two, and the two are exhaustive given
>    staleness. **A propose-change that only makes a can't-PARSE a finding (2j2l's title) would
>    leave this untouched**, which is exactly brief 59's warning arriving with a mechanism.
>
>    **✅✅ RESOLVED 2026-07-31 — THIS TABLE IS A HISTORICAL RECORD, NOT LIVE STATE. DO NOT ACT
>    ON IT.** The `livespec` v0.21.1 fan-out was re-dispatched to all seven stale siblings, all
>    seven bump PRs merged, and **`compat.pinned` is `v0.21.1` in 8 of 8** — re-measured on the
>    forge. The rows below are kept because they are the evidence that convicted the predicate,
>    and deleting them would delete the reasoning behind v039. **Every "today" in them is
>    2026-07-31T06:30Z.**
>
>    **⛔⛔ AS MEASURED THEN — THE 2026-07-30 OUTAGE'S UNREPAIRED TAIL.** PR #930 fixed the class
>    and the prior session re-dispatched — **but only for the DEV-TOOLING release fan-out. The
>    `livespec` v0.21.1 fan-out was never re-fired.**
>
>    | measured 2026-07-31T06:30Z | |
>    |---|---|
>    | `livespec` v0.21.1 published | 2026-07-30T14:04:25Z (~16h earlier) |
>    | its fan-out to `livespec-runtime` | run **`30550180299`** → **`ModuleNotFoundError: No module named 'returns'`** |
>    | bump PR opened | **NONE**, in any member |
>    | `.livespec.jsonc` `compat.pinned` today | still **v0.21.0** in **8 of 9** members |
>    | what the row does | reports it **correctly and continuously**, at `warning` |
>    | what the sweep exits | **`passed`**, `blind_rows: 0` |
>
>    `livespec` has published NO release since, so nothing supersedes it. The walker was run
>    against a fetched `livespec-runtime` `.livespec.jsonc` and DOES emit
>    `source_repo: "livespec"` for both compat records, and the bump action DOES rewrite
>    `livespec_jsonc_compat_pinned` (`action.yml:147/162) — **so a fresh dispatch WILL fix it.**
>
>    **⛔ THEREFORE, REMEDIATE-THEN-FLIP, AND THE MEASUREMENT IS ALREADY DONE (brief 59 item 3):
>    if escalation is ratified on "stale with no bump PR past a settle window", EIGHT OF NINE
>    MEMBERS GO RED TODAY** — from an unrepaired incident, not a policy defect. **Re-dispatch
>    FIRST, flip SECOND** (v034 carve-out 1). Do NOT file the propose-change's escalation half
>    without re-running the live sweep afterwards.
>
>    **✅ DONE, AND THE ORDERING WAS WORTH ITS COST — the post-remediation sweep found ONE
>    escalating member, not eight, and the one is REAL: `ve7w`, livespec's own structurally
>    unbumpable self-pin. Had the flip gone first, that finding would have been indistinguishable
>    from seven repair-pending siblings and almost certainly lost. THE PRECONDITION IS
>    DISCHARGED; the next session implements without re-dispatching.**
>
>    **▶️ AND THE DATA A SETTLE-WINDOW PREDICATE NEEDS IS ALREADY FETCHED AND DISCARDED.**
>    `_rows_pin_currency._latest_release_tag` calls
>    `ctx.api_object(path="repos/<owner>/<repo>/releases/latest")` and reads ONLY `tag_name`;
>    the same payload carries **`published_at`** (verified against the live API). So a
>    release-age component needs NO new API call and stays stateless — the release's own
>    publish time, not a local clock. **That is the `unrecognized`-sentinel shape again: the
>    value is in hand and thrown away.**
>
>    **THE RECOMMENDED PROPOSE-CHANGE CONTENT, so it is not re-derived:** (a) a can't-PARSE is
>    a FINDING, not silence — `contracts.md:525` already says an unrecognized format produces
>    no record plus an ANNOTATION, so the spec's own carrier never created the fail-open, which
>    discharges `xhbp`; and (b) **the escalation predicate must partition staleness
>    EXHAUSTIVELY** — a stale pin either has an open bump PR for the latest release (fired,
>    could not land — escalates today) or has none (**never fired**, which is currently read as
>    normal operation and is the worse case). Scope (b) by RELEASE AGE from `published_at`, and
>    keep the EXISTING lane scoping (`ctx.filter_consuming_preflight`) rather than inventing
>    one. **⛔ Do NOT make the rows errors everywhere** — a sibling's stall must not red an
>    unrelated repo's PRs — and **⛔ do NOT add a severity lever or opt-out key** (`vt61`'s
>    named third option; every dodge this sweep found was an emptiness that meant yes).
>
>    **~~NOTHING OF THIS INVESTIGATION IS COMMITTED IN CODE~~ — SUPERSEDED. Its RECOMMENDED
>    CONTENT above was filed and ratified verbatim in substance as `v039` (PR #958), and the
>    remediation it demanded is complete. What remains uncommitted is the CODE: no walker is
>    converted, no predicate is flipped, no settle window is implemented.**
>
>    ---
>
>    **⛔ SUPERVISOR BRIEF 58 MOVED THE RATIFICATION FROM THE TAIL TO NEXT, and the reason is
>    arithmetic rather than preference:** when one walker looked blocked it could sit at the
>    end; now that `2j2l` gates **SEVEN of the 40 CONVERT** — nearly a fifth of the remaining
>    conversion work — deferring it piles those seven against the end of the epic, and a batch
>    that large arriving last is where sequencing mistakes get made under pressure. The brief
>    also RETRACTS its own brief-57 instruction ("do the seven other walkers first,
>    `read_pin_text` leading"): it had inherited §7's ordering and passed it on without asking
>    what the sentinel's footprint actually was.
>
>    **THE DENOMINATOR, and quote it with its composition or not at all** (supervisor brief 52
>    constraint 2 — after remediation "0 offenders" and "0 because the remainder was declared"
>    are indistinguishable, and that indistinguishability is this epic's subject):
>
>    | class | n | landed? |
>    |---|---|---|
>    | CHECK-FIX | **3** | ✅ **#946** — the machinery convicted conformant code |
>    | CONVERT | **40** | 🟡 **17 of 40 landed** — 9 (#952) + the 8-walker family (#962); **23 remain** |
>    | DECLARE | **2** | ✅ **#949** |
>    | COUPLED | **1** | ⏳ follows `open_bump_prs_for` |
>    | TYPE-SLICE | **23** | ⏳ the `RowOutcome` family, ONE decision |
>    | OPEN | **6** | ⏳ not settled by the triage |
>
>    **3 + 40 + 2 + 1 + 23 + 6 = 75. Offenders measured 75 → 70 → 64 → 61, re-derived at BOTH
>    ENDS of each unit and never inherited. ONLY TWO OF 75 ARE BOUGHT BY DECLARATION**, and both
>    carry a callers' reading. DECLARE went 4 → 2 UNDER READING — moving AWAY from exemption,
>    the direction this thread's negative results have historically erred toward.
>
>    **✅ CONVERT UNITS 1 AND 2, LANDED 2026-07-31 (PR #952). 70 → 61, and NOTHING ELSE MOVED.**
>    Universe 155 · `_`-FILES 65 · v178 public 182 → 183 · member-1 exempt 404 → 408 · member-2
>    3 · DISJOINT · `supervisor_entry_files` 33 · **0 stale / 0 rejected**. No declaration was
>    added and no `__all__` narrowed: the count fell because nine functions converted.
>
>    - **`_primary_checkout_git_probes` (6) → 70 → 64.** The four `bool` probes returned False
>      both for "git says no" and "git never answered", and `is_git_repo_at_all` is THE
>      discriminator between "not a repo" (skip, exit 0) and a bare-flag regression — so a
>      broken environment routed to SKIP. `git_common_dir` / `work_tree_root` used `check=True`
>      with docstrings ADVERTISING the raise. The parent gained `git_probe_failed` (exit 4, NOT
>      the skip) carrying probe + argv + cwd.
>    - **`_red_green_replay_trailers` (3) → 64 → 61.** `head_red_awaiting_green` picks WHICH LEG
>      of the commit ritual runs; a failed read produced empty stdout → "no Red trailer" → the
>      SUITE-GREEN leg → `TDD-Suite-Green-*` stamped onto what may be a Green amend. **A
>      fail-WRONG, not a fail-closed** — the sharpest instance in the epic so far.
>
>    **▶️ THE RULE THE TWO UNITS ESTABLISH FOR THE REMAINING 31, and it is the substance rather
>    than the type change: AN INVOCATION THAT COMPLETES AND ANSWERS IS A SUCCESS WHATEVER IT
>    ANSWERS.** `git rev-parse --git-dir` exiting non-zero means "not a repository"; `git config
>    --get <key>` exiting 1 means the key is UNSET; an absent trailer is empty. All ANSWERS. Only
>    the command failing to answer AT ALL is a `Failure`. Deciding that per call site is most of
>    the work in each conversion; the type change is the cheap part.
>
>    **🔴🔴 AND THE ONE THAT NEARLY SHIPPED A REGRESSION — A TIGHTENING THAT WOULD HAVE REFUSED
>    A NEW REPO'S FIRST COMMIT.** `git log -1` exits **128** in a repository with **no commits**.
>    Reading every non-zero exit as a failure — the obvious conversion — would make the
>    commit-msg hook REFUSE the first commit of any fresh member repo, because `just bootstrap`
>    installs these hooks BEFORE that commit exists. `head_red_awaiting_green` therefore resolves
>    HEAD first (`git rev-parse --verify --quiet HEAD`; exit **1** = unborn = an ANSWER) and the
>    case is pinned by the FIRST test in the mirror file as a guard against re-tightening.
>    **Generalize it: every remaining conversion must ask which non-zero exits are ANSWERS before
>    deciding which are failures. "Convert" is not "treat every non-zero as a Failure", and this
>    thread's negative results have historically erred toward over-exemption — this is the same
>    error running the OTHER way, and it is just as available.**
>
>    **▶️ SAY THE DIRECTION EXPLICITLY, because a reader who has absorbed "we always err toward
>    exemption" will not be looking for it (supervisor brief 59): THIS IS THE FIRST TIME THIS
>    THREAD'S ERROR HAS RUN IN THE TIGHTENING DIRECTION.** Every prior instance — the 1-of-6, the
>    2-of-4, the hand-simulated fixpoint, the `_`-FILE skip itself — ran toward EXEMPTION. This
>    one ran the other way and was equally available.
>
>    **▶️▶️ AND IT IS THE EXACT MIRROR OF THE `DECLARE` QUESTION, WHICH MAKES IT CHEAP TO ASK 31
>    MORE TIMES. Run every remaining candidate through the PAIR:**
>
>    | class | the question | the artifact |
>    |---|---|---|
>    | **DECLARE** | is this `None` an **ABSENCE** or a **FAILURE**? | an `X \| None` return |
>    | **CONVERT** | is this non-zero exit / empty result an **ANSWER** or a **FAILURE**? | an exit code, an empty string, an empty list |
>
>    **Same question, opposite artifact.** The `_UNSET_KEY_RESOLVES_TO` constant in
>    `_primary_checkout_git_probes` was that instinct already: the literal was NAMED precisely
>    because `False` was ALSO what a failed read used to return, and naming it is what kept the
>    two apart. Reach for that spelling whenever a converted function has a literal that means
>    two things.
>
>    **⚠️ FOUR MECHANICAL COSTS THE TWO UNITS PAID, all cheap to re-pay and all certain to recur
>    across the remaining 31 — re-derive none of them.**
>
>    1. **⛔ `git commit --amend -F <file>` DESTROYS THE `TDD-Red-*` TRAILERS.** The message file
>       REPLACES the whole message, the hook then adds only Green trailers, and the commit lands
>       with a Green-without-Red shape that `_commit_violates` rejects — `just check` was green
>       at the time, because HEAD when it ran was still the Red commit. **Use `--amend --no-edit`
>       at Green and write the FINAL body at the RED commit.** I hit this on unit 1 and redid the
>       pair rather than hand-patching trailers back in: the evidence would all have been
>       genuine, and the commit would still have read as a pair that was never verified as one.
>    2. **PLR0911 CAPS A FUNCTION AT SIX RETURNS, and every converted call site adds one.**
>       `main()` in both callers had to split (`_inspect_work_tree` / `_inspect_installed_state`;
>       `_dispatch_impl_staged`). Budget one function split per ~3 conversions in a single
>       caller, and prefer `.map()` over `if isinstance(...)` where the transform is TOTAL — it
>       adds no branch and no coverage obligation.
>    3. **GREEN-LEG TESTS GO IN A `*_edges.py` SIBLING AND MUST CALL `main()` IN-PROCESS.**
>       `check-tests-no-subprocess-spawn` fails a NEW file that spawns Python;
>       `subprocess_spawn_allowlist` is explicitly a list to migrate AWAY from, so a new file
>       must not join it. `monkeypatch.chdir` + `monkeypatch.setenv` + `capsys` + `rc = main()`.
>    4. **RED MODE TAKES EXACTLY ONE STAGED TEST FILE**, so a unit touching several modules is
>       still ONE pair: the mirror test is the Red file, and every other test file lands at the
>       Green amend.
>
>    **⚠️ AND ONE FIXTURE FACT, found by measuring rather than assuming: a `git` shim with an
>    unresolvable interpreter does NOT raise if a real git sits later on `PATH`.** `execve` fails
>    with `ENOENT` and `subprocess`'s own PATH search reads that as "not here" and CONTINUES. The
>    shim dir must be the WHOLE PATH. The first version of that fixture appended
>    `os.environ["PATH"]`, the check ran to completion against the real git, and the test would
>    have passed while proving nothing — a green that means nothing, inside the epic that exists
>    to remove them.
>
>    **⛔⛔ TWO CORRECTIONS TO THIS THREAD'S OWN TRIAGE, BOTH FOUND BY MEASURING AFTER SHIPPING,
>    AND THE SECOND CHANGES HOW YOU MUST READ §2 OF THE TRIAGE FILE.**
>
>    **(1) CHECK-FIX WAS 4 AND IS 3.** After #946 the repo went 75 → 72, not 71.
>    `extract_created_worktree_paths` did NOT drop and never would have: verified on UNMODIFIED
>    master it was **DOUBLY CONVICTED** — the `Path(raw)` false positive AND clause (d), since
>    both its callees carry a `try`. **THE METHOD FLAW MATTERS MORE THAN THE COUNT: the triage
>    classifier assigns ONE conviction basis per function — it tests LOCAL first and STOPS — so
>    §2's LOCAL / TRANSITIVE / CLAUSE-(e) split is a partition of FIRST-FOUND basis, NOT of all
>    bases.** Never re-derive anything from §2 that assumes a function has only one. That
>    function is now OPEN.
>
>    **(2) DECLARE WAS 4 AND IS 2, and the reading caught a contradiction INSIDE the table.**
>    `impl_plugin_name` (4 conditions on its `None`) and `named_plugin_connection` (6+) were
>    read and moved to CONVERT; both row callers turn the `None` into a `RowFinding` and
>    `_rows_baseline`'s docstring says "which link BROKE". **`connection_block` had ALREADY been
>    disposed CONVERT on exactly that ground while `named_plugin_connection`, same module and
>    same shape, had DECLARE.**
>
>    **▶️ THE RULE FOR `total_absence_returns`, BOTH HALVES — counting alone is NOT sufficient
>    and an earlier revision of `pyproject.toml` said it was.** (1) Count distinct MEANINGS, not
>    syntactic `return None` sites, and FOLLOW a callee that itself collapses — `resolve_owner`
>    has ONE return expression and THREE meanings. More than one → CONVERT. (2) If exactly one,
>    ask **WHOSE failure the callers report**: "I cannot verify this" → the FUNCTION failed →
>    CONVERT; "the thing I INSPECTED is non-conformant", or pure control flow → DECLARE.
>    **Part 2 decides every one-condition case**, which is the only population that key admits.
>    Both halves are now in `pyproject.toml` above the key. The whole `X | None` population was
>    swept against this and NO verdict is wrong (**#950**).
>
>    **⛔ AND A CLEAN `rejected_declarations` RUN IS NOT VALIDATION.**
>    `_declared_absence_returns._split` yields only UNRESOLVED and NOT_ABSENCE_SHAPED; neither
>    asks whether the `None` is really an absence, and the reason is parsed for PRESENCE, never
>    truth. Run it per new entry anyway — `ueni` makes it unreachable in this repo until the
>    arming commit — but never cite "0 rejected" as evidence a disposition is right.
>
>    **✅ UNBLOCKED 2026-07-31 — `2j2l` IS ANSWERED BY `v039` (PR #958), SO THE PIN-WALKER FAMILY
>    IS NOW THE NEXT UNIT. Everything below still governs HOW to do it; only the "blocked" verdict
>    is retired.** v039 ratifies the semantics the conversion must realize: a can't-PARSE is a
>    distinct typed outcome a consumer cannot silently drop, and a pin-currency row may not pass
>    on a format it did not evaluate. ⛔ **The forbidden shortcut below is now MORE live, not
>    less** — with the semantics ratified, moving the sentinel would be non-conformance with
>    ratified text rather than merely a tidy that misses the point.
>
>    **~~⛔⛔⛔ DO NOT START CONVERT WITH `read_pin_text`. THE WHOLE PIN-WALKER FAMILY IS BLOCKED
>    ON `2j2l`~~, AND AN EARLIER PLAN — INCLUDING A SUPERVISOR BRIEF — SAID TO START THERE.**
>    Measured on master `302abd6`, not inferred:
>
>    - **The `unrecognized` sentinel is emitted at THREE sites, all three single-file walkers**
>      (`_pin_single_file_formats.py:80` `walk_livespec_jsonc`, `:192` `walk_pyproject_toml`,
>      `:216` `walk_vendor_jsonc`). The brief assumed ONE entangled walker; it is three of the
>      seven in `pin_autodiscovery._WALKS`.
>    - **`read_pin_text` is THE shared reader for all seven**, so converting it forces all seven
>      to adapt. **The family cannot be split**: a split leaves `discover` composing TWO return
>      shapes over ONE `_WALKS` table — converted walkers returning `IOResult`, unconverted ones
>      still raising into its `except OSError` arm. `discover` was itself converted (`9sl0`
>      conversion 3) precisely to stop a partial walk being indistinguishable from a complete
>      one; two composition paths for one table would reopen that.
>    - **⛔ AND THE FORBIDDEN SHORTCUT, named so it cannot return as a clever tidy:** converting
>      a single-file walker to `IOResult` while leaving `_rows_pin_currency._records_for`'s
>      silent drop of the `unrecognized` record intact is **MOVING the sentinel, not removing
>      it** — which `vzwa` refused by name.
>
>    **THE UNIT, when `2j2l` is answered:** `read_pin_text` + 7 walkers + `discover`'s
>    composition + relocating `PinFileUnreadable` (it lives in `pin_autodiscovery.py`, which
>    imports the walkers, so they cannot name it without a cycle — move it to
>    `_pin_directory_scan_formats.py` and re-export). **8 of the 40 CONVERT.**
>
>    **✅ EXECUTED — this recommendation is now HISTORY, ratified as `v039` (PR #958). Kept
>    because the ratified text tracks it closely and a reader diffing the two will understand
>    both faster; the one substantive change is that v039 ALSO partitions staleness
>    exhaustively, which this paragraph did not yet know to ask for.**
>
>    **▶️ THE RECOMMENDATION ALREADY MADE, so nobody re-derives it:** batch `2j2l` + `xhbp` +
>    `vt61` into ONE propose-change (`vt61` already records that `2j2l` and `0j3i` are one
>    question twice). Content: **a can't-PARSE is a FINDING, LANE-SCOPED** — error in the lane
>    that owns the pin, warning elsewhere, which is `0j3i`'s recorded shape and preserves the
>    reason the rows warn. That also discharges `xhbp`, since `contracts.md:525` ALREADY says an
>    unrecognized format produces NO RECORD plus an annotation — the spec's own carrier never
>    created the fail-open. **The supervisor ruled this is NOT a maintainer valve and NOT to be
>    stalled on** (brief 57): the charter's "a severity lever is out of bounds" clause forbids a
>    lever used to WEAKEN, and making a can't-PARSE stop reading as PASS is STRENGTHENING a
>    fail-open — squarely inside standing authority. File and ratify through
>    propose-change → revise as OPERATIONS.
>
>    **🔴 AND THE RESULT THAT OUTRANKS THE COUNT: FOUR OF THE 75 ARE THE CHECK BEING WRONG,
>    AND THEY ARE THE EXACT MIRROR OF THE SKIP.** (Read as THREE — see correction (1) above.) The `_`-FILE skip is non-conformance with the
>    ratified rule in the RELAXING direction; these four are non-conformance in the TIGHTENING
>    direction, by the same standard — so the commit that drops a too-wide relaxation must not
>    carry a too-wide conviction. **`memoized_snapshot` IS ALREADY ON THE RAILWAY**
>    (`SnapshotResult = IOResult[TreeSnapshot, SnapshotUnavailable]`); `_is_railway_compliant`
>    matches the annotation's TERMINAL NAME and **a type ALIAS defeats that match**. The other
>    three are `io.StringIO` (an IN-MEMORY buffer) and `Path(raw)` (a value CONSTRUCTION) read
>    as I/O boundaries because `io` and `pathlib` sit in `_IO_MODULES` at MODULE granularity.
>    **Arming without these fixes reports violations against conformant code** — the false-
>    positive risk the charter names by name. **⛔ It is 4 of 75, each isolated by measurement;
>    70 STAND. A fifth member needs the same evidence, not a resemblance** — and
>    `preflight_credential` is deliberately NOT in the class though it looks like it, because a
>    bare call to an injected parameter is DOCUMENTED doubt and doubt disqualifies BY DESIGN.
>
>    **▶️ AND THE SKELETON'S "35 TRANSITIVE" SPLITS 24 + 11.** Eleven are convicted by clause
>    (e) ALONE — clean body, clean callees, `X | None` — which is precisely the population
>    member 2's `total_absence_returns` key exists to sort, and FOUR of them are declarations
>    rather than code. Folding them into "transitive" hid that.
>
>    **🔴 TWO FINDINGS THE TRIAGE ITSELF PRODUCED, filed, and the first is this epic's own
>    subject in the fleet outcome type.** **`RowSkip` CARRIES TWO MEANINGS AND THE TWO LANES
>    READ IT OPPOSITE WAYS** — central (`_lanes.py:173`) reads "not evaluable" and feeds
>    **`blind_rows`**, which reds master; local (`local_reconcile.py:94`) reads "not applicable"
>    and logs `info`. The central lane ALREADY has a correct spelling for inapplicability
>    (`RowPass` + the excluded-note prefix) and two rows do not use it. **That is
>    `pure_trees = []` in the type both engines share, and `blind_rows` is the number `5cai`'s
>    health was just declared to rest on.** Second: **the justfile `check:` parser exists FOUR
>    times**, and the copies say they keep agreement by copying — the `livespec-i04f` shape.
>
>    **▶️ DROPPING THE SKIP CREATES A DECLARATION OBLIGATION — do not let it sink.**
>    `resolve_owner` and `discover_fixtures` are absent from `cross_repo_public_api` on the
>    stated ground that "declaring them would assert a scope this check does not actually
>    apply". **The moment the skip drops that ground EXPIRES**, and both entries are owed in
>    the same change. **AND RUN THE DECLARATION DETECTORS PER NEW ENTRY AS YOU AUTHOR IT** —
>    `ueni` makes `stale_declarations` / `rejected_declarations` structurally unreachable in
>    this repo (they sit behind `main()`'s `pure_trees` gate), so member 2 bound 1's REJECTING
>    gate first becomes reachable **in the arming commit itself** — the one commit that must
>    not go red.
>
>    **🔴🔴 THE THIRD AXIS WAS RUN WITH THE SHIPPED `5cai` ORACLE, NOT GREPPED — AND IT
>    CONTRADICTED THIS REPO'S OWN `pyproject.toml`. THE RECORD WAS RIGHT AND THE ROW IS
>    BLIND.** Same denominator as the pre-registration run: 9 roster / **9 READ** / 0
>    unavailable / 0 unparsed / **58 edges**. Of the 75 it finds **ONE**:
>    `fleet/_context.py::resolve_owner` ← beads-fabro's `.claude-plugin/hooks/codex_yolo_gate.py`
>    (the `dx8l` hook). It finds **ZERO** for `discover_fixtures` — yet reading the nine
>    tarballs the oracle had already fetched shows **all four siblings genuinely consume it**,
>    each via `from livespec_dev_tooling.testing import cli_e2e` then
>    `cli_e2e.discover_fixtures(...)`. **MECHANISM, at `_public_api_graph.py:263` —
>    `if name not in functions[defining]: continue`.** `discover_fixtures` is IMPORTED into
>    `cli_e2e.py` and re-exported, not DEFINED there, so the correctly-resolved reach is
>    **SILENTLY DROPPED** and never re-resolved to `_cli_e2e_discovery.py`; no edge reaches
>    EITHER file. `test_workflow_full_round_trip`, which IS defined in `cli_e2e.py`, is seen
>    from all four — which isolates the re-export as the cause.
>    **⛔ GATE: this blocks `5cai`'s OWN completeness claim, NOT arming.** Its
>    `error_findings: 0` is quotable only over consumptions the oracle can see. **And it
>    retro-scopes the `wdn7`/`nkkv` TWENTY** — that denominator silently excluded every
>    re-exported consumption fleet-wide. The drop is a bare `continue` with no record, unlike
>    `unparsed`, which this same graph deliberately carries in-band.
>
>    **🔴 AND `RowSkip` CARRIES TWO MEANINGS IN CODE THAT IS REGISTERED AND GATING TODAY.**
>    Central (`_lanes.py:173`) reads it "not evaluable" and feeds **`blind_rows`**, which reds
>    master with no lever or opt-out; local (`local_reconcile.py:94`) reads it "not applicable"
>    and logs `info`. `assert_tenant_connection_consistency` — registered as
>    `beads-tenant-connection-consistency` — returns it for two INAPPLICABILITIES
>    (`_rows_beads.py:68`, `:73`). **If the beads-backed population among applicable members
>    ever reaches zero, that row goes blind and fails every central run fleet-wide for a
>    condition that is not a failure.** `blind_rows: 0` today is contingent on one applicable
>    member still evaluating. **⛔ GATE: NONE — and that is the point. Do NOT couple this to
>    the 23-function TYPE-SLICE** (an earlier draft did; supervisor brief 53 corrected it, and
>    the correction is accepted). The targeted fix needs no new type:
>    `RowPass(note=_EXCLUDED_NOTE_PREFIX + reason)`, which `_lanes.py:188` already renders.
>
>    **THE TWO NUMBERS DO NOT AGREE, AND THE WHOLE DIFFERENCE IS ONE LINE.** Measured on master
>    `7f2abfd` with the shipped analyses over the shipped `resolve_check_universe()` — universe
>    **155**, v178 public **182**, v179 member-1 exempt **390**, member-2 **1** (DISJOINT), 33
>    `supervisor_entry_files`, 0 stale and 0 rejected declarations:
>
>    | arming variant | offenders |
>    |---|---|
>    | CARRIES `_scan`'s `_`-prefixed-**FILE** skip | **0** |
>    | DROPS it | **75** |
>
>    The entire delta is `if py_file.name.startswith("_"): continue` at
>    `public_api_result_typed.py:310`. Nothing else moves.
>
>    **⛔ WHY ARMING WITH THE SKIP IS FORBIDDEN: IT HIDES 65 OF 155 FILES — 42% OF THE UNIVERSE.**
>    Arming while carrying it arms a check that structurally cannot see 42% of the universe it was
>    just migrated onto. **That is `pure_trees = []` in its final costume, at the last step of the
>    epic that exists to remove it** — the epic would close by committing its own founding defect.
>    And the skip is WIDER THAN THE RATIFIED RULE: v178 clause 0 disqualifies a `_`-prefixed
>    **NAME**, never a **FILE**. This repo's own `pyproject.toml` comment already says so and names
>    two cross-repo consumers reaching through it — `fleet/_context.py::resolve_owner` (beads-fabro's
>    `codex_yolo_gate.py` hook) and `testing/_cli_e2e_discovery.py::discover_fixtures` (four
>    siblings). **BOTH ARE IN THE 75.**
>
>    **⛔ AND DROPPING THE SKIP FIRST IS ALSO FORBIDDEN** — it turns this repo's own `just check`
>    RED at 75 and lefthook then blocks the very commit that would fix it. That is THE ORDERING
>    TRAP, in the place `8o8e` originally named it.
>
>    **⛔ AND DROPPING THE SKIP IS *FIDELITY*, NOT A TIGHTENING — say it in those words, because it
>    changes what KIND of decision this is.** v178 clause 0 disqualifies a `_`-prefixed **NAME**;
>    `_scan` skips a `_`-prefixed **FILE**. A check enforcing something WIDER than its own ratified
>    rule is not a stricter check — it is a **NON-CONFORMANT** one, in the RELAXING direction. This
>    is the exact mirror of PR #748, where wiring the spec's own stated exemptions IN was fidelity
>    rather than softening. **So "should we tighten?" is the WRONG QUESTION and must be refused if
>    it comes up: the check has been out of conformance with its ratified rule, and the 75 is what
>    conformance COSTS.** That framing also disposes of the temptation to ratify the skip after the
>    fact (supervisor brief 51).
>
>    **✅ THE RULING (supervisor brief 50), so nobody re-asks it: REMEDIATE-THEN-FLIP under v034
>    carve-out 1.** Read and triage the 75 per function the way the original 59 were → THEN drop the
>    skip → THEN arm. **This is authorized standing work; an item boundary is a place to REPORT, not
>    to WAIT.**
>
>    **THE 75 ARE NOT ARTIFACTS — established by READING, not assumed.** I did NOT read all 75 and
>    do not claim they are all genuine; that reading IS the work. What is established:
>    `resolve_owner(*, cwd) -> str | None` is a genuine violation — its `None` collapses THREE
>    distinct failures (no origin remote, `git remote get-url` failing, a non-github remote) into
>    one sentinel, and it reaches `subprocess` through `_origin_remote_match`, so member 1 does not
>    exempt it and clause (e) refuses `X | None` outright.
>
>    **▶️ IS THIS `995m`'s PREDICATE? NO — MEASURED, AND IT DOES NOT SHRINK THE JOB.**
>    `qndn` is a FILENAME predicate inside `_scan`'s own loop, and the 65 files ARE in
>    `resolve_check_universe()`'s output — this ONE check discards them. `995m` is `is_generated`, a
>    CONTENT predicate matching `@generated`, applied by the universe resolver itself (`config.py`
>    verified ABSENT from the universe). Upstream vs downstream, 8 checks vs 1. **Fixing
>    `is_generated` reclassifies NONE of the 65. The triage stands at 75.**
>
>    **▶️ THE TRIAGE SKELETON — mechanical, on `7f2abfd`. NONE OF IT IS A DISPOSITION.**
>
>    **⛔ CORRECTED BY MEASUREMENT: THE "35 TRANSITIVE" BELOW IS 24 + 11, AND THE 35 IS THE
>    NUMBER A COLD START WOULD OTHERWISE INHERIT.** Eleven of it are convicted by clause (e)
>    ALONE — clean body, clean callees, `X | None`, no I/O anywhere in the reachable graph —
>    which is precisely the population v179 member 2's `total_absence_returns` key exists to
>    sort, and FOUR of them are DECLARATIONS rather than code. Folding them into "transitive"
>    hid that. Read the corrected split in `qndn-75-triage.md` §2.
>
>    | by signature shape | n |   | by conviction clause | n |
>    |---|---|---|---|---|
>    | `X \| None` | **15** |   | **LOCAL** (a/b/c — own body raises, tries, reaches I/O) | **40** |
>    | `raise` / `try` | **6** |   | ~~TRANSITIVE (d)~~ → **24 TRANSITIVE + 11 CLAUSE-(e)-ONLY** | ~~35~~ |
>    | supervisor-shaped | **0** |   | | |
>    | total-looking signature | **54** |   | | |
>
>    **⚠️ THE 35 TRANSITIVE ARE THE DANGEROUS CLASS AND MUST NOT BE HAND-READ.** They are the
>    `canonical_check_slugs` / `world_gate_check_slugs` shape exactly: every clause a body-only
>    reading can check PASSES, and the only one that fails needs a fixpoint. This thread's hand
>    judgement has been wrong 1-of-6 and then 2-of-4 on precisely this class, **both times toward
>    EXEMPTION**. Run the analysis per function; never simulate it. And `tag_version_component` sat
>    in the STRONGEST convict class and was still not a conversion — so **read every function this
>    classification CONVICTS, not only the ones it acquits.**
>
>    **SUGGESTED FIRST UNIT:** the **15** `X | None`. That class splits cleanly into member-2
>    `total_absence_returns` DECLARATIONS versus genuine conversions, so it tells you how much of
>    the 75 is declaration rather than code before any conversion is attempted.
>
>    **THE THREE METHOD CONSTRAINTS BIND EVERY CANDIDATE, all already paid for:** (1) is the `None`
>    a real failure or a legitimate ABSENCE? (2) **CAN this module import `returns` in EVERY
>    environment it executes in?** — unasked once, and it cost a fleet-wide fan-out outage on
>    2026-07-30. (3) does any SIBLING import this symbol? if so consumer wiring lands FIRST,
>    dual-shape, in the consuming repo (`dx8l`).
>
>    **⛔ WHAT MUST NOT HAPPEN: do not narrow an `__all__`, adjust the universe, or add a
>    declaration to make 75 become 0.** This thread has retracted 245, 282, 43, 40-of-46, "class C
>    is empty", "exposure is zero", and its own 0 that was really 2 — every one caught by
>    RE-DERIVING. A surprise on the first real scan is the most valuable finding available and the
>    most tempting to tidy away, because it is the only thing between here and a finished epic.
>
>    **AND THE OLD ZERO IS NOT RETRACTED.** The count agreeing at zero was TRUE of the universe as
>    it was then defined; that universe was smaller than anyone knew. It was honestly measured
>    against a universe with a hole in it — which is `995m`'s own "a gate whose arming precondition
>    was verified against a universe with a hole in it", now recurring ONE LEVEL UP.
>
>    **⛔ KEEP `qndn` AND `995m` SEPARATE, and the next reader's instinct will be to merge them.**
>    `995m` is an ACCEPTED known gap whose written statement covers ONE file. `qndn` is 65 files and
>    was never decided by anyone. Folding them together would launder 65 undecided files through a
>    ratification they never received — the declaration-that-means-consent pattern.
>
>    **🎯🎯 `5cai` IS CLOSED. THE ROW IS REGISTERED AND VERIFIED GATING ON MASTER CI. THE ONLY
>    THING LEFT BEFORE ARMING IS THE `995m` KNOWN-GAP STATEMENT.** PR **#934** → master
>    **`6f38105`**, two Red/Green pairs (`ba65383` the roster wiring, `6f38105` the registration).
>
>    **THE ZERO, WITH ITS DENOMINATOR — quote it this way or not at all.** A bare "0 findings" and
>    "0 because I read nothing" are indistinguishable, and that indistinguishability is this
>    epic's entire subject:
>
>    | | |
>    |---|---|
>    | roster members | 9 |
>    | members **READ** (tarball + config) | **9** |
>    | members SKIPPED | **0** |
>    | files UNPARSED | **0** |
>    | cross-member edges **EXAMINED** | **58** |
>    | declarations fleet-wide | 24 |
>    | verdicts | **9 PASS / 0 SKIP / 0 FINDING** |
>
>    The SAME denominator the pre-registration run used, when it found TWENTY.
>
>    **✅ VERIFIED GATING ON MASTER CI, NOT MERELY MERGED.** The post-merge run reports
>    `{"own_failing_rows": [], "error_findings": 0, "blind_rows": 0, "out_of_vantage_rows": 3}`.
>    **`blind_rows: 0` IS THE LOAD-BEARING NUMBER, not `error_findings: 0`.** Had the roster
>    wiring been absent, the newly-registered row would have skipped for EVERY member,
>    `blind_rows` would be ≥1, and the run would have FAILED. So the row was **EVALUATED**, not
>    merely present — which is the exact distinction this epic exists to enforce, finally applied
>    to its own last slice. **A future check of this row's health should read `blind_rows`, not
>    the exit code.**
>
>    **🔴 AND REGISTRATION WAS NOT THE SIX-LINE FOLLOW-UP THIS FILE PROMISED — building it found a
>    SECOND wiring hole.** `FleetContext.members` carries the fleet roster and its docstring said
>    the central engine populates it "once the manifest resolves". **NOTHING DID** — frozen
>    dataclass built in `main()` BEFORE the manifest is fetched, no construction site passing a
>    roster, no `dataclasses.replace` anywhere. The field held its `()` default for every run
>    either engine had ever made. **It surfaced only because a row finally needed it:** no row
>    asked for the roster until this one, so an unpopulated field broke nothing and READ AS WIRED,
>    its docstring stating an intention as a fact. **It would not have under-enforced quietly** —
>    an empty roster yields the named skip, and a row blind for every applicable member is already
>    an error, so registering as-is would have failed every run forever. Fixed in
>    `run_member_rows`, the one function holding BOTH the context and the manifest;
>    `dataclasses.replace` rather than a fresh construction, because the memo caches are mutable
>    dicts carried BY REFERENCE and a rebuild re-spends the manifest's ~35 API reads.
>
>    **⚠️ TWO THINGS THE REBUILD PAID FOR, both cheap to re-pay and both likely to recur.**
>    (1) **A PROBE MUST ASSERT THE ROSTER IS USABLE, NOT MERELY PRESENT.** The first version
>    asserted only on the member list; its canned downloader was then never invoked and
>    `check-per-file-coverage` failed on the dead fixture — the honest signal that the test proved
>    less than it claimed. The probe now snapshots EVERY member's tree. (2) **THE BYTE-IDENTITY
>    RULE COST A FULL PAIR REBUILD AGAIN**, for the reason recorded below: the fixture change
>    belonged in pair 1's test file, was written after pair 1 was committed, and a Red-recorded
>    file cannot be amended. **Write the fixture the LATER pair needs into the EARLIER pair's test
>    file, or plan to rebuild.**
>
>    **(history, and the wrap-up entry it superseded is gone: nothing of this thread's is open)
>    ✅✅✅ `wdn7` AND `nkkv` ARE BOTH CLOSED. THE TWENTY ARE ZERO.** `wdn7` = dev-tooling's nine
>    (#929, `91e3bec`): declared, and each file earned a REASONED `supervisor_entry_files` entry,
>    taking the ratified-rule count **0 → 9 → 0** measured at each end. `nkkv` = livespec-runtime's
>    eleven (that repo's #398, `67bc22d`): declared, raising ITS armed count **24 → 27**, +3 and
>    zero removed — `parse_cross_repo_manifest`, `lane_of`, `is_item_ready`, filed as
>    **`vojo`**, NOT converted (they are `dx8l`-shaped, consumer wiring first).
>
>    **(superseded) ALL THREE `5cai` SLICES ARE LANDED AND ON MASTER. THE ROW EXISTS, IS TESTED,
>    AND IS DELIBERATELY NOT REGISTERED. THE NEXT ACTION IS THE REMEDIATION — `wdn7` THEN `nkkv`
>    — NOT THE ROW.** Merged: the tarball primitive (`c24e8d4`, v1.10.0), the oracle (`df04359`
>    + `846c97c`, v1.11.0), the oracle correction (`56379a3`) and the row itself (`e20c3ab`),
>    with the measured record at `plan/rop-railway-enforcement/5cai-fleet-measurement.md`
>    (`eeffe60`). **READ THAT FILE BEFORE PLANNING ANYTHING** — it carries both offender lists.
>
>    **▶️ THE ROW WAS MEASURED AGAINST THE LIVE FLEET BEFORE REGISTRATION, AND IT CONVICTS TWO
>    MEMBERS ON TWENTY GENUINE UNDECLARED CONSUMPTIONS.** Nine members read, **0 skipped, 0
>    unparsed**: `livespec-dev-tooling` **9** (`checks/*.py::main`, 12 sites) and
>    `livespec-runtime` **11** (product imports, 23 sites); the other seven are clean.
>    **REGISTERING TODAY IS MECHANICALLY IMPOSSIBLE, not merely unwise** — dev-tooling's own
>    failing row makes `own_failing_rows` non-empty, so the REGISTERING PR's OWN CI fails and it
>    cannot land; and livespec-runtime's would leave this repo's PRs green while breaking the
>    scheduled sweep and the RELEASE FAN-OUT PREFLIGHT fleet-wide. Hence REMEDIATE-THEN-FLIP
>    (v034 carve-out 1). **The severity was NOT softened — the row is `error` and inert, which is
>    the Phase 3 shape, and registration is a six-line follow-up.**
>
>    **⛔⛔ THE ONE RESOLUTION THAT IS FORBIDDEN, and it is the newest costume of this epic's own
>    subject: DO NOT UNDER-DECLARE `cross_repo_public_api` TO KEEP THE COUNT AT ZERO.** Declaring
>    dev-tooling's 9 makes them public for `public_api_result_typed`, taking the ratified-rule
>    count from **0 to 9** unless each file also earns a REASONED `supervisor_entry_files` entry.
>    Omitting a genuinely-consumed name to protect that number is `pure_trees = []` in a new
>    costume — and `5cai` would convict this repo for exactly that, which is the row working on
>    its own author. **If the honest resolution leaves the count non-zero, ARMING WAITS and the
>    gate gets restated.** A delayed arming is acceptable; a clean number bought by an incomplete
>    declaration is not.
>
>    **AND THE 9 ARE CLAUSE-2 SYMBOL IMPORTS, NOT CLAUSE-3 PROCESS ENTRY POINTS — THE QUESTION
>    IS ANSWERED, NOT OPEN.** Established by READING both consumers, which do
>    `from livespec_dev_tooling.checks import (...)` and then `assert wrapper_shape.main() == 0`
>    **IN-PROCESS**, asserting on the return value. beads-fabro's file also carries
>    `assert "python -m ...wrapper_shape" in justfile` — a STRING assertion ABOUT the justfile,
>    not an invocation, and the only place the process form appears at all. **So this is NOT the
>    known `main() -> int` exemption-scoped-to-a-LOCATION spec defect and must not be filed as
>    it.** The count going 0 → 9 would be nine genuine clause-2 consumptions, not one old spec
>    defect reaching code.
>
>    **▶️ THE TWENTY, BY NAME — a count without its members cannot be re-derived, and this
>    thread has retracted six numbers for exactly that reason.** Measured with the SHIPPED
>    oracle against the LIVE fleet BEFORE registration; nine members read, 0 skipped, 0
>    unparsed. Full record with consumer sites: `5cai-fleet-measurement.md`.
>
>    `livespec-dev-tooling` — **9**, every one `checks/<slug>.py::main`: `all_declared`,
>    `assert_never_exhaustiveness`, `keyword_only_args`, `main_guard`, `no_inheritance`,
>    `no_lloc_soft_warnings`, `no_write_direct`, `private_calls`, `wrapper_shape` (12 sites,
>    consumed by beads-fabro's and livespec-runtime's test trees).
>
>    `livespec-runtime` — **11**, and it declares NOTHING: `credentials.py::decide_credentials`,
>    `credentials.py::wrapper_launch_failure`, `cross_repo/types.py::parse_cross_repo_manifest`,
>    `work_items/lifecycle.py::is_item_ready`, `work_items/lifecycle.py::lane_of`,
>    `work_items/rank.py::key_between`, `work_items/rank.py::n_keys_between`,
>    `work_items/reduce.py::materialize_work_items`, `work_items/reduce.py::random_id_suffix`,
>    `work_items/reduce.py::reduce_work_item_heads`,
>    `work_items/reduce.py::work_item_record_identity` (23 sites). **These are PRODUCT imports
>    (clause 1)** from `store.py`, `_ids.py`, `bin/_bootstrap.py` and `commands/*.py` in two
>    orchestrators and in `livespec` itself — so a conversion there is the `dx8l` shape exactly:
>    consumer wiring lands FIRST, dual-shape, in the consuming repo.
>
>    **▶️ WHERE SLICE 3 STANDS, AND THE BYTE-IDENTITY LESSON PAID FOR AGAIN.** Branch
>    `feat/fleet-public-api-row`, merged as **#924**, worktree reaped. The Red/Green pair was
>    REBUILT mid-flight: `c672161` was superseded by `d589e71` because **`check-per-file-coverage`
>    counts TEST files too**, and a deliberately-never-called guard function in the Red-recorded
>    test was one uncovered line. The Red-recorded test file is byte-identity-bound, so fixing it
>    forced a full rebuild of the pair from master — **there is no amend path**. Expect this
>    whenever a test carries a "this must never run" assertion; make it an assertion about a
>    RECORDED call instead of a raising stub.
>
>    **📐 THE APP INSTALLATION POOL, MEASURED — nobody on this thread had this number before.**
>    Installation **131208965**, across the window that reset at 16:48:24Z, which spans TWO
>    releases (v1.10.0 at 15:55, v1.11.0 at 16:43):
>
>    | time (UTC) | used | remaining |
>    |---|---|---|
>    | 16:35:54 | 303 | 4697 |
>    | 16:38:48 | 330 | 4670 |
>    | 16:43:16 | 434 | 4566 |
>    | **16:46:16** | **532** | **4468** ← window peak |
>    | 16:48:24 | *reset* | |
>    | 16:49:19 | 0 | 5000 |
>    | 17:04:35 | 77 | 4923 |
>
>    **Peak 532 of 5000 — 10.6%. The pool never approached exhaustion**, and an independent
>    sample of the SAME window found SIX green `check-fleet-conformance` runs (15:53Z–16:44Z,
>    four of them 40–50 min downstream of v1.10.0). **The two measurements AGREE, and
>    release-correlation weakens.** So cumulative core exhaustion is unlikely to be `mmqe`'s
>    mechanism, and a **SECONDARY rate limit** (burst/concurrency) fits what the core-pool story
>    cannot: **it does not move `used`**, which is why every retrospective look at the counter
>    found nothing. **Falsifiable cheaply — capture the response HEADERS on the next instance**
>    (`Retry-After` / "exceeded a secondary rate limit" vs `x-ratelimit-remaining: 0`), not
>    another window. One window is one window; this is a number, not a verdict. The probe is
>    recorded in `5cai-fleet-measurement.md` (app JWT → installation token → `GET /rate_limit`,
>    which does not itself consume quota — two consecutive reads showed 303 → 303).
>
>    **(history, kept because the tarball reasoning still binds any future central row)** The
>    naive build calls
>    `FleetContext.file_text()` once per file — **~653 GitHub API reads per run against a
>    5000/hr installation pool that is SHARED across all nine repos' automation.** Across a
>    nine-PR release fan-out that is ~5877 reads, **1.2× the entire hourly budget**, so it would
>    not merely be slow: it would ship a new central row that reds master on release day — this
>    epic's own defect, authored by the fix for it. One tarball per member is **9 reads** (81
>    across a fan-out), and this thread has already used that route twice. `FleetContext` has NO
>    tarball method, so `5cai` is THREE slices: the primitive (`IOResult`, ref-pinned, memoized,
>    named skip on failure), then the consumption oracle reusing
>    `checks/_public_api_consumption`'s MODULE-QUALIFIED resolution (a bare-name oracle is
>    measured wrong), then the row **plus its REGISTRATION in `OBLIGATION_ROWS`** — registration
>    is the step that makes it run, and Phase 3 proved an unregistered row is walked by neither
>    engine. The row must carry the guard warning and the static blind spot in its OWN OUTPUT,
>    not in a docstring, and must report PER MEMBER rather than an aggregate.
>
>    **(superseded, kept because the 2 was quoted for a day)** THE TWO NUMBERS AGREE AT 2.
>    Re-measured on merged master `2df1515` with the shipped code, never inherited: universe
>    **149**, v178 public **167**, member-1 exempt **381**, member-2 exempt **1** (0 rejected,
>    the two member sets verified DISJOINT), **2 offenders** — and the ratified rule considers
>    exactly those **2** a violation.
>
>    **⛔⛔ AGREEMENT AT 2 IS NOT PERMISSION TO ARM, AND THIS IS THE SINGLE EASIEST LINE IN THIS
>    FILE TO MISREAD.** The gate was always "the two numbers agree" AND "the number is zero".
>    Agreement means the check is now HONEST; it does not mean the repo is clean. **Arming at 2
>    reds dev-tooling on its own gate and lefthook then blocks the very commit that fixes it.**
>    The 2 are `canonical_check_slugs` and `world_gate_check_slugs` — **`vzwa`**.
>    ~~THE NEXT ACTION IS `vzwa`, THEN `5cai`, THEN ARM.~~ **SUPERSEDED — `vzwa` LANDED. The
>    next action is `5cai`.** This line is struck rather than deleted because the paragraph
>    above it is the still-correct explanation of why agreement alone is not permission to arm;
>    a cold start greps for "NEXT ACTION" and must not find this one live.
>
>    **🔴 TWO DIFFERENT ZEROS, AND CONFLATING THEM WOULD UNDO THE WHOLE LESSON.** An earlier
>    revision claimed the ratified-rule count was 0 on the strength of a HAND reading of six
>    functions; `rvw3`'s fixpoint shipped and disagreed, and that 0 was RETRACTED as false —
>    the count was 2. **Today's 0 is a DIFFERENT zero: it is MEASURED with the shipped
>    analyses on merged master, after `q5lb` and `vzwa` actually removed the offenders.** The
>    retracted 0 was a simulation of a fixpoint; this one is the fixpoint's own answer. **Do
>    not cite the earlier retraction as doubt about the current count, and do not cite the
>    current count as vindication of the hand reading.**
>
>    **▶️ WHY THE COUNT ROSE 0 → 2 — ANSWERED, AND THE ANSWER IS "THE SIMULATION WAS WRONG".**
>    Asked by supervisor brief 33, which named the two admissible answers: (a) the BASIS
>    changed, so the figures were never comparable; or (b) the implementation genuinely convicts
>    functions the hand simulation exempted. **It is (b), and the basis did NOT change.**
>    Re-derived on master `55c4206` with the shipped `_find_offenders` over the shipped
>    `resolve_check_universe()` — universe **149**, v178 public **164**, member-1 exempt **377**,
>    **3 offenders** — never inherited:
>
>    | function | hand simulation | shipped fixpoint |
>    |---|---|---|
>    | `canonical_check_slugs` | member-1 EXEMPT | **CONVICTED** — clause (d), 1 hop |
>    | `world_gate_check_slugs` | member-1 EXEMPT | **CONVICTED** — clause (d), 2 hops |
>    | `parse_open_bump_prs` | member-1 exempt | exempt ✅ |
>    | `denotes_same_release` | member-1 exempt | exempt ✅ |
>
>    **THE HAND SIMULATION NAMED FOUR MEMBER-1 EXEMPTIONS AND GOT TWO OF THEM WRONG. Those two
>    ARE the 0 → 2 delta, exactly — there is no other component.** `tag_version_component` is
>    NOT part of it: it was counted exempt under member 2 in BOTH figures, and it is still the
>    entire difference between the check's **3** and the rule's **2**, because member 2 is
>    ratified and not yet implemented (that is `q5lb`).
>
>    **WHY THE SIMULATION WAS WRONG, in one sentence: it read the BODIES and clause (d) is not
>    about the body.** Verified by reading `canonical_checks.py`, not by re-reading the ledger:
>    `_discover_slugs` calls `pkgutil.iter_modules([str(package_path)])` — a filesystem walk, so
>    clause (c) disqualifies it locally; `canonical_check_slugs`'s entire body is
>    `return _discover_slugs(package_path=_CHECKS_PACKAGE_DIR)`; `world_gate_check_slugs` calls
>    `canonical_check_slugs`. All three of (a) no `raise`, (b) no `try`, (e) return is
>    `tuple[str, ...]` and not `X | None` hold for both — **every clause a body-only reading can
>    check passes, and the only clause that fails is the only one that requires a fixpoint.**
>
>    **⚠️ AND THE ERROR RATE IS THE RESULT WORTH CARRYING, not the delta.** Hand judgement was
>    **2 of 4 wrong** on the population it was MOST confident about — worse than the
>    `classify_role_key_declarations` precedent (6c), which was 1 of 6. Two independent hand
>    readings of clause (d), months apart, both erred in the SAME direction: toward exemption.
>    **A hand simulation of a fixpoint is not a measurement of it**, and this is the third time
>    this thread has paid for treating one as such. No count for a sibling repo may be quoted
>    from a hand reading of clause (d) — run the analysis.
> 6k. **✅ `q5lb` IS CLOSED — v179 MEMBER 2 SHIPPED, AND THE TWO NUMBERS AGREE AT 2.** Three
>    slices, all merged: **#891** SPECIFICATION **v037** (the `total_absence_returns` role-key
>    bullet), **#892** the loader (bound 2) + `checks/_declared_absence_returns` (bounds 1+3),
>    **#895** wired into the check + `tag_version_component` declared. The check went **3 → 2**.
>
>    | bound | what | where it landed |
>    |---|---|---|
>    | 1 | structural gate — only `X \| None` is declarable | `_declared_absence_returns`, **hard fail** |
>    | 2 | a written reason is REQUIRED | the config loader, `ConfigParseError` |
>    | 3 | staleness detector, **hard fail not warning** | `_declared_absence_returns` |
>    | 4 | counted per-repo AND fleet-wide | **NOT DONE — it is `5cai`'s** |
>
>    **THE POLARITY IS THE THING A LATER EDITOR WILL GET WRONG, and it is written into the
>    ratified text three times for that reason.** `cross_repo_public_api` is TIGHTENING-ONLY and
>    says so three times in its own bullet; **this key REMOVES functions from the rule's scope**,
>    so that argument is NOT available to it and v037 says so by name. **An EMPTY declaration is
>    the STRICT end of this key** — the opposite polarity from the five union role keys, where
>    empty was the blinding value. Carrying the reassuring "tightening-only" wording across
>    because the two keys are otherwise parallel would be a false statement of exactly the kind
>    this epic exists to remove.
>
>    **BOUND 1 REJECTS; IT DOES NOT SKIP.** Quietly ignoring a declared entry whose function is
>    not `X | None` would satisfy the letter of the gate while making the mis-declaration
>    invisible. Both wrong readings are foreclosed BY NAME in the ratified bullet ("neither
>    silently ignored nor accepted") because each is individually plausible.
>
>    **AND THE LOADER DELIBERATELY DOES NOT ENFORCE BOUND 1.** The gate needs the declared
>    file's SOURCE; the loader parses TOML and is imported by every check, so making it read
>    `.py` files would buy a new I/O dependency for no gain. Bounds 1 and 3 are ONE detector
>    where the universe already is. **A successful parse is HALF the gate**, and
>    `_parse_total_absence_returns`'s docstring says so.
>
>    **TWO FINDINGS FILED, and the first is this epic's subject one level down:**
>    - **`livespec-dev-tooling-ueni` (P1) — BOTH declaration keys' HARD-FAILING staleness gates
>      are UNREACHABLE in this repo.** They sit BEHIND the `pure_trees` role-absence gate in
>      `main()`, and dev-tooling declares `pure_trees = { not_applicable = … }`, so `main()`
>      returns before reading a single declaration. **This repo's five declared entries — four
>      `cross_repo_public_api` plus `tag_version_component` — are verified by fixture tests and
>      by NOTHING ELSE.** Same for the four `unarmed_until` members. Not a defect in either
>      detector (both are correct and tested), which is what makes it easy to miss. **The fix is
>      a reorder with SIBLING BLAST RADIUS** — measure all nine members' declarations first, fix
>      any stale entry in its own repo, then reorder. `dx8l` shape.
>    - **`livespec-dev-tooling-k76y` (P1) — `5cai`'s naive build is ~653 GitHub API calls per
>      run.** See 6l.
>
>    **THREE PROCESS FACTS PAID FOR HERE, all cheap to re-pay and easy to avoid:**
>    - **RED MODE REQUIRES EXACTLY ONE STAGED TEST FILE.** `just check-pre-commit` gates on
>      `test_count -eq 1 && impl_count -eq 0`; TWO staged test files fall through to the FULL
>      aggregate, where the Red leg's stubbed impl fails `check-per-file-coverage` and
>      `check-lint`. **A multi-module slice is several Red→Green PAIRS, not one pair with several
>      test files.** Two pairs in one PR is fine and is what #892 did.
>    - **A FRESH WORKTREE NEEDS `just install-worktree-pack`** before `just check` passes —
>      `check-primary-checkout-commit-refuse-hook-installed` fails `worktree_pack_absent`
>      otherwise. Doc-only commits never hit it, so it first appears on the first commit staging
>      a `.py`, several commits into a session.
>    - **🔴 AND THE RE-MEASURE SCRIPT WENT STALE MID-PASS, which is the one worth carrying.** It
>      applied member 1 ALONE, bypassing `_scan`'s union, and reported **3** where the shipped
>      check reports **2**. A measurement that UNDER-applies a ratified exemption reads as "the
>      repo is dirtier than it is" — **it would have restored the very number this pass
>      retracted.** Mirror `_scan`, never approximate it.
> 6m. **✅ `vzwa` IS CLOSED AND THE REPO MEASURES ZERO. Two PRs, consumer-first.**
>    **livespec #1847** landed the dual-shape READ in all three cross-repo consumers; the
>    dev-tooling PR then converted `canonical_check_slugs` and `world_gate_check_slugs` to
>    `IOResult`. Consumer wiring FIRST, so the pin is free to move in either direction —
>    including a REVERT, which a sequenced fix would not survive (`dx8l`'s cost).
>
>    **THE CONVERSION WAS NEVER THE POINT — REMOVING THE SENTINEL WAS.**
>    `pkgutil.iter_modules` on a MISSING directory yields no entries rather than raising, so the
>    old surface returned an EMPTY TUPLE and every consumer read it as "this repo has no
>    canonical checks" — a PASS. **Typing it `IOResult` while still returning `IOSuccess(())`
>    for an empty walk would have MOVED the sentinel rather than removed it.** So an empty walk
>    is `ChecksPackageUnreadable` on the FAILURE track, and that track is genuinely inhabited:
>    `canonical_checks.py` ships INSIDE the same installed package as `checks/`, so zero modules
>    means a broken install, never a repo with no checks.
>
>    **⛔ THE DODGE, REFUSED BY NAME IN THE DOCSTRING SO IT CANNOT RETURN AS A CLEVER TIDY.**
>    Hoisting the walk to a module-level constant (`_SLUGS = _discover_slugs(...)` at import
>    time) would make the function MECHANICALLY TOTAL — clauses (c) and (d) analyse function
>    bodies and callees, and a module-level assignment is in neither. The check would go GREEN
>    and the result would be STRICTLY WORSE: the I/O moves where the analysis cannot see it, the
>    failure becomes implicit again, and an import-time empty walk is MORE invisible than a
>    call-time one.
>
>    **BOTH FUNCTIONS CONVERTED IN ONE PAIR, and the arithmetic is why.** Clause (d) couples
>    them — `world_gate_check_slugs` is two hops from the walk — so a split PR would have
>    measured **2 → 2** and read as a FAILED conversion. The outer function FORWARDS the failure
>    rather than re-wrapping it: it adds no failure mode of its own, and two error types for one
>    condition make a caller distinguish two things that are one thing.
>
>    **AND THE COST LANDED WHERE PREDICTED: the coverage, not the typing.** All SEVEN in-repo
>    call sites use `unsafe_perform_io(...unwrap())`, fail-closed, and added **ZERO** uncovered
>    lines — every one of the six touched modules stayed at 100%. The `#846` precedent is what
>    makes that legitimate: the failure means the installed `checks/` package is unreadable,
>    which is not a reachable state for a check running out of that same package, so a `match`
>    arm could never be covered under a 100%-per-file gate. **`value_or(())` was refused at every
>    site** — it is the fail-open the commit removes. Only `main()`'s new diagnostic branch needed
>    a test, and it went in a `*_edges.py` sibling because the Red file is byte-identity-bound.
>
>    **🔴 TWO TRAPS PAID FOR HERE, both cheap to re-pay:**
>    - **MY OWN CALL-SITE SURVEY WAS INCOMPLETE, AND I RECORDED IT AS COMPLETE.** It said "every
>      in-repo call site, enumerated" and listed 6; there were **7**. The seventh
>      (`checks/_ci_matrix_parse.py:145`) was cut off by a `head -20` on the grep that produced
>      the list. **`check-types` caught it, not review.** This thread's own "read the callee, do
>      not match the name" lesson recurring as "do not trust a TRUNCATED view" — inside the
>      inventory written to prevent re-derivation. Re-run any survey without a pager limit.
>    - **A `@dataclass` BREAKS EVERY TEST THAT LOADS THE MODULE VIA `spec_from_file_location`
>      WITHOUT REGISTERING IT IN `sys.modules`.** Under `from __future__ import annotations`,
>      `dataclasses` resolves field annotations through `sys.modules[cls.__module__]`; for an
>      unregistered module that is `None` and the decorator dies with `'NoneType' object has no
>      attribute '__dict__'` — **at import, so the traceback names the import and not the
>      cause.** It broke 16 pre-existing tests in one file. The fix is one line
>      (`sys.modules[spec.name] = module`). Expect this in every sibling whose tests use that
>      loader idiom, which is most of them.
> 6l. **📐 THREE SIBLINGS RE-MEASURED, AND 6e's "UNKNOWN IN BOTH DIRECTIONS" IS NOW CONFIRMED
>    RATHER THAN FEARED — ONE REPO GOES UP.** Taken 2026-07-30 from each repo's FORGE MASTER
>    TARBALL, so no shared clone was touched, with the shipped post-v178/v179 criterion and each
>    repo's own `pyproject.toml`. **The stale 223/282 figures are now replaceable for three
>    repos.**
>
>    | repo | recorded | PRE-v178 re-run today | v178 | **v178+v179 = what the check reports** | tightening ADDED |
>    |---|---|---|---|---|---|
>    | `livespec-orchestrator-beads-fabro` | 58 | 55 | 19 | **17** | **0** |
>    | `livespec-overseer` | 56 | 55 | **80** ⬆️ | **53** | **26** |
>    | `livespec` | 35 | 11 | 8 | **6** | **0** |
>
>    **THE METHOD VALIDATES ITSELF ON TWO OF THREE: the PRE-v178 oracle re-run today reproduces
>    the recorded figure within 3** (55 vs 58; 55 vs 56). `livespec`'s 11 vs 35 is NOT a
>    disagreement — that repo has been actively converting (68 of 129 modules import `returns`),
>    so the gap is real remediation since the figure was taken.
>
>    **🔴 `livespec-overseer` GOES UP UNDER v178 — 55 → 80 — AND THE CAUSE IS NOT 26 NEW GENUINE
>    VIOLATIONS. Filed as `livespec-dev-tooling-oip9` (P1).** That repo keeps **49 `test_*.py`
>    files INSIDE its product package** (`overseer/test_supervisor.py`, …), not under `tests/`,
>    and declares no `tests_tree_prefix`, so the default `"tests/"` matches none of them and
>    `resolve_check_universe()` classifies all 49 as first-party PRODUCT code. v178 clause 1 then
>    makes a function public when non-test first-party code imports it across a module boundary —
>    and `overseer/test_supervisor_builders.py` is imported by its sibling `overseer/test_*.py`
>    files, all inside the universe. **So 24 of the 26 added offenders are TEST-BUILDER HELPERS.**
>    The other 2 are real (`supervisor.build_supervisor`, `supervisor.run_daemon`).
>
>    | `livespec-overseer` universe | pre-v178 | v178 | v178+v179 | added |
>    |---|---|---|---|---|
>    | as `resolve_check_universe()` sees it (84 files) | 55 | 80 | **53** | 26 |
>    | co-located `test_*.py` EXCLUDED (35 files) | 49 | 43 | **33** | **2** |
>
>    **BOTH NUMBERS ARE TRUE AND THEY ANSWER DIFFERENT QUESTIONS.** **53** is what the ARMED
>    CHECK WOULD REPORT there today — the work someone must actually clear. **33** is the count
>    over genuinely-product code. The 20-offender gap is a UNIVERSE-CLASSIFICATION issue in that
>    repo, not a railway issue, and a fan-out planned from the raw 80 would budget conversion
>    work for 24 test builders. **NO SIBLING FIGURE MAY BE QUOTED WITHOUT SAYING WHICH UNIVERSE
>    IT WAS MEASURED OVER** — these two differ by 38% and both are correct.
>
>    **⛔ AND DO NOT "FIX" THIS BY MAKING `test_*.py` A TEST BASENAME FLEET-WIDE.** `oip9` records
>    three non-equivalent readings; the cheap one is a one-line `tests_tree_prefix` correction in
>    that repo. Changing `resolve_check_universe()` would shrink several universes at once, and a
>    universe that shrinks is a check that inspects LESS — the relaxing direction.
>
>    **🔎 AND THE RATIFIED-RULE COUNT FOR ALL THREE IS UNMEASURED, DELIBERATELY.** 7 of
>    beads-fabro's 17 are `main` — the v177 member-4 shape wanting a `supervisor_entry_files`
>    DECLARATION rather than a conversion — so its ratified-rule count is materially BELOW 17.
>    **That number is NOT stated here**, because establishing it needs the per-function reading
>    and this file's own newest standing constraint forbids hand-simulating the answer. The
>    figures above are what the CHECK reports. Keep the two labelled apart, exactly as 6d does
>    for this repo.
>
>    **AND THE FLEET SHAPE VARIES FAR MORE THAN ANY RATIO PREDICTS**, so do not scale by
>    first-party count: beads-fabro dropped 36 of 55 because it declares `commands_trees` and 4
>    `supervisor_entry_files`; overseer declares NO `commands_trees` and 1 supervisor file and
>    dropped 1. **Flat-layout members are where v178 bites hardest — which is dev-tooling's own
>    shape.** Six repos remain unmeasured.
>
>    **✅ NOTHING OF THIS THREAD'S IS OPEN, re-verified at the 2026-07-31 wrap-up.** Every PR it
>    opened is MERGED (adding **#929, #930, #933, #934, #937**, plus livespec-runtime **#398**),
>    every worktree of its own is REAPED, and no branch of its own remains. **The arming attempt
>    was measured, NOT committed, and its worktree reaped — see the ⛔⛔⛔ block above.**
>    **FIVE items were filed on 2026-07-31 and none is started:** **`qndn`** (P0, the arming
>    blocker), **`0j3i`** (P0, pin-currency rows fire at warning severity and escalate to nobody;
>    no row covers the `pyproject.toml` dependency pin), **`vt61`** (P1, ratify a Pin-currency
>    severity policy — `2j2l` and `0j3i` are one question twice), **`vojo`** (P1, livespec-runtime's
>    three convictions from the `nkkv` declaration), and the fan-out regression recorded under its
>    own heading at the top of this file. **The prior revision's warning about an
>    open `5cai-register-public-api-row` worktree is RETIRED — that branch was abandoned on stale
>    master, reaped, and rebuilt from scratch as `feat/5cai-register-row`.** FOREIGN worktrees
>    exist under `~/.worktrees/livespec-dev-tooling/`; **ENUMERATE with `git worktree list` rather
>    than trusting any count, including this sentence's absence of one**, and reap NONE.
>
>    **▶️ COLD-START ORIENTATION — the items this thread still owns, all FILED, none started.**
>    Nothing is mid-flight, verified at wrap-up 2026-07-30 (second wrap-up of the day): every
>    PR this thread opened is MERGED (#867, #870, #874, #880, #883, #886, #890, #891, #892,
>    #895, #898, #905, #906, #908, #913, #914, **#919, #921, #924, #926**, plus livespec #1834
>    and #1847), the primary checkout is clean on `master` **`e8769ad`** (released **v1.12.0**),
>    every worktree of this thread's is REAPED, and no branch of its own is open.
>    **FIVE FOREIGN worktrees exist under `~/.worktrees/livespec-dev-tooling/` — reap NONE of
>    them, and ENUMERATE with `git worktree list` rather than trusting that count, including
>    when it is this file's own.** In dependency order:
>
>    | id | what | gates arming? |
>    |---|---|---|
>    | ~~`9sl0`~~ | ~~the 3 genuine violations~~ | **✅ CLOSED — #867, #870, #874** |
>    | ~~`rvw3`~~ | ~~v179 member 1, the clause-(d) fixpoint~~ | **✅ CLOSED — #880, #883, #886** |
>    | ~~`q5lb`~~ | ~~v179 member 2, the `total_absence_returns` key~~ | **✅ CLOSED — #891, #892, #895** |
>    | ~~`vzwa`~~ | ~~the 2 genuine violations~~ | **✅ CLOSED — livespec #1847 + dev-tooling PR. The count is ZERO** |
>    | ~~`5cai`~~ | ~~the CENTRAL-vantage conformance row~~ | **✅ ALL THREE SLICES LANDED — #919, #921, #924. The row is BUILT and deliberately UNREGISTERED** |
>    | ~~`wdn7`~~ | ~~dev-tooling's 9 undeclared `checks/*.py::main`~~ | **✅ CLOSED — #929. Count 0 → 9 → 0, measured at each end** |
>    | ~~`nkkv`~~ | ~~livespec-runtime's 11, cross-repo~~ | **✅ CLOSED — livespec-runtime #398. Its armed count 24 → 27; the +3 are `vojo`** |
>    | ~~REGISTER~~ | ~~the row into `OBLIGATION_ROWS`~~ | **✅ DONE — #934. Registered, and VERIFIED EVALUATED on master CI via `blind_rows: 0`** |
>    | **`qndn`** | **the 75 — ✅ TRIAGED (`qndn-75-triage.md`); CHECK-FIX + DECLARE + 17 of 40 CONVERT LANDED (70 → 61 → 53); 23 CONVERT remain, then drop the `_`-FILE skip, then arm** | **YES — THE FIRST GATE. Next step is the remaining 23 CONVERT.** |
>    | `8o8e.2` | `RowSkip` two meanings, LIVE in a registered central row | **NO — and that is the point. Off the queue; fix on its own timetable.** |
>    | `8o8e.5` / `8o8e.6` | `find_ruff_backstop_gaps` fails OPEN · the justfile parser exists 4× | **NO.** Off the queue. |
>    | ~~`2j2l` + `xhbp` + `vt61`~~ | ~~the pin-currency severity policy~~ | **✅ RATIFIED AS v039 — PR #958. The fan-out was re-dispatched FIRST (8/8 at v0.21.1). Code NOT flipped; that is the walker family.** |
>    | **`ve7w`** | **livespec's OWN `compat.pinned` is STRUCTURALLY unbumpable — the publisher is excluded from its own fan-out; 2 releases stale, zero bump PRs ever** | **NO — filed 2026-07-31 by the post-remediation sweep. The one member v039 newly escalates.** |
>    | **`0yfo`** → `995m` | decompose `config.py`, then flip the `@generated` predicate | the SECOND gate — via 6f's known-gap statement |
>
>    **Three NEW items were filed by this work. `vzwa` IS an arming blocker; the other two are
>    NOT** — but the first of those is this epic's own subject in the central sweep, so do not
>    let it sink: **`2j2l`** (P1, the pin-currency row reads an UNPARSEABLE pin file as PASS)
>    and **`xhbp`** (P2, the spec/impl divergence that created it). See 6h. **Do not treat a P1
>    as a gate it is not** — 2j2l needs a §"Pin-currency severity policy" decision and arming
>    does not wait on it (supervisor brief 32).
>
>    - **Both rulings are RATIFIED**: livespec **v178** (public = CONSUMED ACROSS A BOUNDARY,
>      PR #1826 → `d230c9ff`) and **v179** (the rule reaches functions that HAVE an expected
>      failure mode, PR #1827). **No spec change BLOCKS arming** — but one is owed and PENDING:
>      v178's "exposure of the tightening half: ZERO" paragraph is FALSE, and the correction is
>      filed-not-ratified (see 6e). The earlier "no spec work remains" reading is retired.
>    - **`zu85` CLOSED** (#832), **class B CLOSED** (#835, nine reasoned
>      `supervisor_entry_files` entries), **`u4ij` CLOSED** — all three conversions landed:
>      #841 `classify_role_key_declarations`, #846 `select_runner`, #849
>      `test_workflow_full_round_trip`.
>    - **All FOUR sibling dual-shape wirings are merged and green on the forge** — #329, #309,
>      #1141, #450. Conversion 3's precondition is discharged and spent.
>    - **Track C is DONE.** Ratified as **v035** on master (PR #824 → `703c5a6`).
>    - **THE P0 IS CLOSED.** `dx8l` — see step 6a. Nothing is owed on it.
> 6d. **⛔⛔ TWO NUMBERS. THEY NOW AGREE AT 2 — AND THAT IS STILL NOT PERMISSION TO ARM.**
>    Both v179 members are implemented, so the check and the ratified rule finally answer the
>    same question the same way. **The gate was always BOTH conditions: the numbers agree AND
>    the number is zero.** Arming at a non-zero agreed count turns dev-tooling RED ON ITS OWN
>    GATE, and lefthook then blocks the very commit that fixes it. **Arm only when both numbers
>    agree AT ZERO, and state both explicitly in the arming commit.**
>
>    **THE PATH IS NOW EXACTLY ONE STEP — measured at each end, not projected:**
>
>    | after | check reports | ratified rule |
>    |---|---|---|
>    | ~~`721o`~~ (history) | ~~9~~ | ~~3~~ |
>    | ~~`9sl0`~~ (history) | ~~7~~ | ~~0, RETRACTED — see 6i~~ |
>    | ~~`rvw3`~~ (history) | ~~3~~ | ~~2~~ |
>    | ~~`q5lb` landed~~ | ~~2~~ | ~~2~~ |
>    | **today, `vzwa` landed** | **0** | **0** — they AGREE AT ZERO |
>
>    **THE COUNT IS NO LONGER A GATE.** ~~`5cai` AND THE `995m` STATEMENT ARE.~~ **SUPERSEDED —
>    `5cai` IS REGISTERED AND GATING (#934).~~ ~~THE `995m` KNOWN-GAP STATEMENT IS THE ONLY
>    REMAINING ARMING GATE.~~ **BOTH SUPERSEDED — `qndn` (P0) IS NOW THE FIRST ARMING GATE; the
>    `995m` statement is the second.** Every row above was
>    measured at both ends, never projected — including the `9sl0` row, which is a RETRACTION.
>
>    **The first three rows are kept rather than deleted because the `9sl0` row is a RETRACTION**
>    — that 0 was a hand simulation and the shipped fixpoint disagreed. Deleting the row would
>    delete the evidence for this file's strongest standing constraint.
> 6i. **✅ `rvw3` IS CLOSED — AND ITS MECHANISM CONTRADICTED THIS FILE. THE RATIFIED-RULE
>    COUNT IS 2, NOT 0.** Three slices, all merged: **#880** extracted the import-resolution
>    graph, **#883** built the member-1 analysis, **#886** wired it into the check. The check
>    went **7 → 3**.
>
>    **`rvw3`'s OWN LEDGER said member 1 "is expected to clear five", naming
>    `canonical_check_slugs` and `world_gate_check_slugs`. The fixpoint disqualifies BOTH.**
>    Traced, not asserted:
>
>    | function | own body | final | why |
>    |---|---|---|---|
>    | `_discover_slugs` | **disqualified** | disqualified | calls `pkgutil.iter_modules` — a filesystem walk |
>    | `canonical_check_slugs` | clean | **disqualified** | its ONLY callee is `_discover_slugs` |
>    | `world_gate_check_slugs` | clean | **disqualified** | calls `canonical_check_slugs` — TWO hops |
>
>    **Both bodies are clean, which is exactly why the hand reading missed them.** This is the
>    `classify_role_key_declarations` defect (6c) recurring INSIDE the list written to record
>    it — the third time this thread's own lesson has recurred inside its own fix. **Filed as
>    `livespec-dev-tooling-vzwa` (P1), untriaged, and it is an ARMING BLOCKER.**
>
>    **⚠️ `vzwa` IS NOT A TYPE CHANGE.** `pkgutil.iter_modules` on a MISSING directory yields no
>    entries rather than raising, so `canonical_check_slugs()` returns an EMPTY tuple and every
>    consumer reads that as "this repo has no canonical checks" — which PASSES. Typing it
>    `IOResult` without deciding what an empty walk MEANS moves the sentinel instead of removing
>    it. The likely better answer is RESTRUCTURE (inject the slug set, the #841 precedent), but
>    `canonical_check_slugs` is consumed by `livespec` PRODUCT code, so a signature change is a
>    `dx8l`-shaped fan-out and the consumer wiring lands FIRST, dual-shape.
>
>    **CLAUSE (d)'s VALUE, MEASURED AT REPO SCALE — quote this, not the anecdote.** Over **845**
>    top-level functions: **310** disqualified by their own body, **394** after the fixpoint —
>    **+84 TRANSITIVE**. Eighty-four functions reach I/O one or more calls away with a clean
>    body of their own.
>
>    **THREE BUGS THE FIXTURES CAUGHT, all of which the fan-out will meet eight more times:**
>    (1) `ast.unparse` renders a union WITH SPACES (`str | None`), so an unstripped membership
>    test missed EVERY `X | None` return — silently exempting the exact shape clause (e) exists
>    to refuse, and making member 2's key unnecessary; (2) `module_aliases` binds every
>    `import X`, first-party or not, so treating any bound base as first-party made
>    `pkgutil.iter_modules(...)` resolve to an EMPTY edge set and report no I/O at all — **the
>    repo measurement was briefly RIGHT FOR THE WRONG REASON**, and only a fixture caught it;
>    (3) a first-party callee under a declared `io_trees` resolved to an ordinary edge, so the
>    tree's CONTENTS decided and a declared boundary stopped being one.
>
>    **AND FIVE EXISTING FIXTURES WERE PASSING FOR THE WRONG REASON.** Every one a total
>    `def compute(*, x: int) -> int: return x`, across three test files. Two `@safe` decorator
>    cases would have gone green **WITHOUT THE DECORATOR BRANCH EVER RUNNING** — caught by
>    COVERAGE, not by review. All now raise, each carrying a docstring saying why, because the
>    next editor's instinct on seeing a raise in a fixture is to delete it. **Expect this when
>    wiring member 1 into any sibling: it does not only change the count, it exposes every test
>    whose fixture was never in scope for what it claimed to test.**
> 6h. **✅ `9sl0` IS DISCHARGED — the three conversions, and what each one actually taught.**
>
>    | function | disposition | PR | check | ratified rule |
>    |---|---|---|---|---|
>    | `holds_app_class_credential` | **RESTRUCTURE** — inject the token | #867 | 9 → 9 | 3 → 2 |
>    | `fetch_manifest` | **CONVERT** → `Result[Manifest, ManifestUnavailable]` | #870 | 9 → 8 | 2 → 1 |
>    | `discover` | **CONVERT** → `IOResult[list[...], PinFileUnreadable]` | #874 | 8 → 7 | 1 → **0** |
>
>    Re-measured after EACH, never only at the end. The offender SET changed as predicted and
>    **nothing relocated** — the `#841` hazard did not recur.
>
>    - **`Result` vs `IOResult` was decided by the SEAM, not by the word "I/O".** `fetch_manifest`
>      reaches the network through the injected `ctx.file_text`, so it is not itself a boundary →
>      `Result`. `discover`'s seven walkers call `read_text` / `glob` DIRECTLY → `IOResult`, with
>      the `unsafe_perform_io` discipline at every call site. **That is the same distinction that
>      separates `fetch_manifest`'s conviction (clause (e)) from the clause-(c) reading that would
>      wrongly convict `holds_app_class_credential`.** Carry it into the fan-out.
>    - **A DELIBERATE NON-CHOICE worth not undoing:** conversion 1 has NO shared
>      `effective_gh_token(*, environ: Mapping[str, str])` helper. It would have stated the
>      env-pair precedence once, and it would have been "total" only because the environment
>      arrived as an ARGUMENT — a syntactic totality, which is this thread's own subject. The
>      one-line read is written out at each of the two `main()` boundaries instead.
>    - **CONVERSION 3'S RED TEST CAUGHT THE IMPL BEING WEAKER THAN ITS OWN DOCSTRING.** The first
>      implementation named the walk ROOT when the exception carried no filename
>      (`UnicodeDecodeError` has none). The test asserted the FILE and failed. **The fix was to
>      strengthen the impl, not weaken the assertion**: one shared `read_pin_text` re-raises a
>      decode failure as `OSError(EILSEQ, …, path)`. `discover`'s catch is then a SINGLE `OSError`
>      arm on purpose — a `UnicodeDecodeError` arm would look more thorough and be strictly worse,
>      because a walker bypassing the shared reader would then fail QUIETLY into the weaker
>      diagnostic instead of loudly.
>    - **🔴 AND CI CAUGHT A TEST THAT WAS TRUE ONLY ON A DEVELOPER MACHINE.** The second Red test
>      made a file unreadable with `chmod(0o000)`. **That denies nothing to root, and CI runs as
>      root inside the sandbox container**, so it passed locally and failed in CI. Replaced with a
>      DIRECTORY named `ci.yml` — globbed like a file, raises `IsADirectoryError`, uid-independent.
>      **A `skipif` would have been the wrong fix**: it leaves the branch unexercised in the only
>      environment that gates merges. Because the corrected file was the Red-RECORDED one, the
>      byte-identity rule forced a full rebuild of the pair from master; there is no amend path.
>    - **⚠️ AND A PROCESS TRAP PAID FOR IN THAT REBUILD, worth its own line.** `git diff master
>      HEAD` is the WRONG way to save a branch's work when master has moved: it silently includes
>      a REVERSAL of every commit master gained. Master shipped 1.3.2 mid-session, and the saved
>      patch would have reverted the release, a pin bump and an unrelated fleet feature. **Diff
>      against the FORK POINT** (`git diff <base> <tip>`), and read `git status` after applying a
>      saved patch — the extra paths are the tell.
>
>    **TWO FINDINGS FILED FROM THE MANDATED CONSUMER READ — and the read is why they exist.**
>    `9sl0` said "READ `_rows_pin_currency.py` FIRST — it may depend on the sentinel row". It does
>    not. It does something worse:
>
>    - **`livespec-dev-tooling-2j2l` (P1) — the pin-currency row reads an UNPARSEABLE pin file as
>      PASS.** `_records_for` filters records by `pin_format`, the sentinel's is `"unrecognized"`,
>      so it is **silently DROPPED** → zero records → `_stale_pins` returns `()` → `RowPass()`.
>      **MEASURED:** a truncated `.livespec.jsonc` and NO `.livespec.jsonc` at all are
>      indistinguishable to the row, and both are GREEN. **This is `8o8e`'s own subject — a check
>      reporting green over something it could not read — inside the CENTRAL FLEET SWEEP**, the
>      vantage this epic keeps pointing at as the one that sees what repo-local checks cannot.
>      Fixing it needs a §"Pin-currency severity policy" decision: that policy covers a
>      can't-READ ("not a violation") and says nothing about a can't-PARSE, so the row has no
>      ratified instruction for this input and its current answer is neither of the two the
>      policy contemplates.
>    - **`livespec-dev-tooling-xhbp` (P2) — spec/impl divergence that CREATED 2j2l.**
>      `contracts.md` line 525 says an unrecognized format "produces NO RECORD and a workflow
>      annotation"; the walk emits an in-band sentinel record and a `log.warning`. **The spec's
>      carrier would not have created a fail-open** — an annotation is not something a row can
>      silently drop. Decide it together with 2j2l; they are the same question at two levels.
>
>    **What conversion 3 DID fix there:** a can't-read now yields `RowSkip` — ratified as "a
>    can't-read is not a violation" — where before it propagated as an uncaught raise and killed
>    the whole nine-member sweep partway through one member. A skip is not free either: a row that
>    skips for EVERY applicable member is BLIND, already error severity here.
> 6e. **🔴 THE TIGHTENING HALF HAS TEETH HERE, AND v178's OWN RATIFIED TEXT SAYS IT DOES NOT.
>    This is the most important result of the `721o` session and it MUST NOT be smoothed.**
>    Implementing v178 dropped 25 offenders and ADDED **3** that the `__all__` proxy never
>    looked at, because they appear in no `__all__` and are imported by another first-party
>    module:
>
>    | function | why it is public | v179 status |
>    |---|---|---|
>    | `fleet/fleet_conformance.py:187 fetch_manifest` | imported by `wire_fleet_member.py` + `fleet_conformance_admin.py` | **REACHES THE NETWORK — not exempt by member 1. Likely a genuine conversion.** |
>    | `fleet/fleet_conformance.py:152 holds_app_class_credential` | imported by `fleet_conformance_admin.py` | reads the environment — triage it |
>    | `cross_repo/pin_autodiscovery.py:126 discover` | imported by `fleet/_rows_pin_currency.py` | walks the filesystem — triage it |
>
>    **livespec v178 records "MEASURED EXPOSURE OF THE TIGHTENING HALF AT RATIFICATION: ZERO
>    … the 11 imported-but-undeclared names were all SUBMODULES."** That measurement is FALSE
>    for this repo, and it was ratified into the spec as a reassurance. Correcting it is a
>    `livespec` propose-change and SHOULD be filed — a ratified clause that under-sells its
>    own reach is the mirror image of one that over-sells it, and this thread has spent its
>    life on the second kind.
>
>    **CONSEQUENCE FOR THE FAN-OUT: the other repos' counts are UNKNOWN IN BOTH DIRECTIONS.**
>    Say it in those words. Every prior estimate — **223, 282, and any ratio derived from this
>    repo** — assumed v178 only ever REMOVES. It also ADDS. **A sibling can come out HIGHER
>    than its pre-v178 figure.** "Unknown" is now the honest word in both directions, not just
>    upward, and no figure may be quoted without a post-v178 re-measurement of that repo.
>
>    **✅ THE CORRECTION IS FILED — `livespec` PR #1834, MERGED to `livespec` master.**
>    **⛔ MERGED ≠ RATIFIED, and conflating them here would be this thread's core defect at the
>    process level.** #1834 lands a PENDING proposed change under
>    `livespec/SPECIFICATION/proposed_changes/`; **v178's false paragraph is STILL IN THE
>    RATIFIED TEXT** and stays there until a `livespec` revise pass consumes it. Do NOT cite
>    the correction as ratified, and do NOT quote v178's "exposure: ZERO" as authority in the
>    meantime — it is filed-as-wrong, not yet fixed.
>    **Whoever runs that revise inherits a decision this thread declined**: that repo's
>    `proposed_changes/` also held TWO pending changes from other work
>    (`github-app-request-budget.md`, `owned-heading-coverage-todos.md`), and a revise consumes
>    one decision PER FILE — so revising means adjudicating both. They are not this thread's to
>    judge. Either their owners revise, or a maintainer rules. It requires the
>    ratified text to carry the measured number, the named functions, the network-reaching
>    detail, and the both-directions consequence — and to record the figure as WRONG WHEN
>    WRITTEN rather than superseded, because **a clause's exposure cannot be measured before
>    the clause is mechanized**. That reasoning is the part that generalizes to every future
>    clause ratified ahead of its mechanization.
> 6f. **🐛 `livespec-dev-tooling-995m` (P1, filed) — `config.py` EXCLUDES ITSELF from every
>    check universe.** `is_generated` treats any `#` line containing `@generated` as the
>    sentinel, and `config.py` carries two such lines DESCRIBING the sentinel mechanism. So
>    the module that implements the marker excludes itself, and the eight applies-to-all
>    checks that derive from `resolve_check_universe()` never inspect the fleet's
>    most-consumed module (~1300 lines, imported by every check and four sibling repos).
>    `tests/livespec_dev_tooling/test_config.py` and
>    `tests/livespec_dev_tooling/checks/test_no_fmt_directives.py` are excluded the same way.
>    **This is this epic's own subject occurring inside the universe resolver the epic routes
>    everything through**, and it is SILENT — nothing logs "skipped as generated".
>
>    **⛔⛔ IT IS AN ACCEPTED KNOWN GAP, AND ARMING DOES NOT COVER `config.py`. Say so in the
>    arming commit.** The one-line predicate fix was written, tested and MEASURED, and then
>    deliberately NOT LANDED — because the moment `config.py` enters the universe it fails two
>    checks:
>
>    | check | finding |
>    |---|---|
>    | `check-file-lloc` | `config.py` is **560 LLOC** against a **250 hard ceiling** — 2.24× over |
>    | `check-keyword-only-args` | `config.py:210 assert_never` is missing the `*` separator |
>
>    So landing the fix alone turns this repo RED ON ITS OWN GATE and lefthook blocks the very
>    commit that fixes it — **the ordering trap in a third spelling**. The sequence is
>    REMEDIATE-THEN-FLIP, which is this repo's own ratified doctrine (v034 carve-out 1):
>    decompose `config.py` first (**`livespec-dev-tooling-0yfo`**, filed, with the seam and two
>    binding constraints), verifying green by applying the predicate change LOCALLY WITHOUT
>    COMMITTING; then flip. The predicate diff and its three known-good tests are recorded on
>    `995m` so nobody re-derives them.
>
>    **BLAST RADIUS OF THE FIX IS ZERO, and that is measured against FORGE masters, not clones.**
>    All eight siblings: `beads-fabro` keeps its 2 exclusions, `livespec-runtime` keeps its 1,
>    every other repo is 0 before and after. Only dev-tooling changes, reclaiming exactly its 3
>    self-referential false positives. **No consumer wiring is needed — this is not a `dx8l`
>    shape.**
>
>    **🔴 AND A SECOND FINDING, which is the more troubling one.** `check-file-lloc`'s own
>    docstring records that retiring its legacy severity classifier was "gated on every governed
>    repo satisfying the ceiling first … verified before the flip: all eight". **That
>    verification was taken THROUGH THIS HOLE** — `config.py` was invisible to the universe when
>    it ran, and `config.py` is 560 LLOC. The precondition for arming that gate was satisfied by
>    a measurement that could not see the largest offender in the repo that ships the check.
>    **A gate whose ARMING PRECONDITION was verified against a universe with a hole in it** is
>    this epic's subject one level up, and it is the reason 995m is a blocker rather than a
>    parallel finding.
> 6g. **✅ THE 3 ARE TRIAGED — `livespec-dev-tooling-9sl0`. The ratified-rule count is 3, NOT 0.**
>    **9 reported = 5 member-1 exempt + 1 member-2 declared + 3 GENUINE VIOLATIONS.** Each was
>    established by reading the body AND its callees:
>
>    - **`fetch_manifest` → CONVERT. The brief's premise was right about the verdict and wrong
>      about the reason, and the difference is load-bearing.** Its network reach is through an
>      INJECTED seam (`ctx.file_text`), so clause (c) is NOT what convicts it. Clause (e)
>      disqualifies `X | None` outright, and the failure track is genuinely INHABITED — by TWO
>      failures collapsed into one sentinel (`could not fetch` vs `fetched but unparseable`),
>      distinguished today only by a side effect. **A clause-(c) reading would also convict
>      `holds_app_class_credential`, which must NOT be converted.**
>      **⛔ BOOBY-TRAPPED AT BOTH CALL SITES** (`wire_fleet_member.py:169`,
>      `fleet_conformance_admin.py:230` — both `if manifest is None`). Both in THIS repo, so no
>      cross-repo wiring, but dual-shape consumer wiring still lands FIRST.
>    - **`holds_app_class_credential` → RESTRUCTURE, do NOT convert.** Clause (c) disqualifies
>      it (reads `GH_TOKEN`/`GITHUB_TOKEN`), but it HAS NO FAILURE MODE: an absent variable
>      yields `""` yields `False`. A `Result` would carry an uninhabited failure track — the
>      outcome v179's own rationale forbids. **This is a MEASURED FALSE POSITIVE of clause (c)**,
>      a syntactic proxy that an unfailing env read defeats. Inject the token; the caller is
>      already a boundary. Precedent: `classify_role_key_declarations` (#841).
>    - **`discover` → CONVERT, design first.** Clause (d) disqualifies it (seven `walk_*`
>      callees touch the filesystem). It already models failure OFF-RAILWAY AND LOSSILY: a parse
>      failure becomes a SENTINEL RECORD (`pin_format="unrecognized"`) in the same list as
>      successes, so "no pins" and "unparseable file" are indistinguishable to a caller. **Read
>      `fleet/_rows_pin_currency.py` first** — it may depend on the sentinel row.
> 6a. **✅ `livespec-dev-tooling-dx8l` — CLOSED, and its LESSON is now a hard precondition.**
>    Slice 2 broke `livespec-orchestrator-beads-fabro`'s master (its `codex_yolo_gate` hook
>    imports `parse_manifest`). Repaired doctrine-exact per livespec `.ai/ci-gate-discipline.md`
>    — server-side revert to the last green pin (#1134 → `cf1b7a8`), consumer wiring second
>    (#1136 → `8af024c`), pin re-landed third (#1138 → `bc23b0d3`). **Verified from the FORGE:
>    beads-fabro master `bc23b0d3`, pin `v1.0.5`, CI SUCCESS** — repaired at the CONSUMED end,
>    not merely merged. No gate weakened, none bypassed. **Do not re-open; do not re-file.**
>    The durable output is §"THE THIRD AXIS", which BINDS every remaining conversion.
> 6b. **🔴 THE GATE IS NO LONGER "ZERO OFFENDERS". IT IS "NO OFFENDER THE RATIFIED RULE CALLS A
>    VIOLATION", AND TODAY THAT NUMBER IS 3.** Both rulings landed: livespec **v178** (public =
>    CONSUMED ACROSS A BOUNDARY) and **v179** (the rule reaches functions that HAVE an expected
>    failure mode). **26 + 4 + 1 + 3 = 34.** Say which number you are measuring against in every
>    status claim — "34" is what the check reports, "3" is what the rule considers wrong, and
>    only the second is the gate. See §"THE GATE IS 3".
> 6c. **⛔ TWO CLAIMS FROM THE PREVIOUS PASS ARE RETRACTED. The commit that introduced them is on
>    master with "class C is EMPTY" IN ITS OWN TITLE — do not inherit it.**
>    - **"Class C is EMPTY" is FALSE. Class C is THREE.** It rested on reading
>      `test_workflow_full_round_trip`'s raise as the pytest COLLECTION protocol. That does not
>      survive checking how the four siblings actually call it: they alias it to a
>      non-`test_`-prefixed name **specifically to keep pytest from collecting it** and invoke it
>      from a wrapper. So its raise is an ORDINARY domain raise and a conversion is owed.
>    - **"Exactly 6 total functions" is FALSE. It is 4 mechanical + 1 declared.**
>      `classify_role_key_declarations` was read BY HAND as total — no raise, no try, no I/O in
>      its own body — and it calls `layout_dependent_check_slugs`, which walks the filesystem.
>      **Hand judgement got 1 of 6 wrong; the mechanical fixpoint caught it.** That single result
>      is why v179's member 1 is COMPUTED rather than DECLARED, and it is written into the
>      ratified text as the reason clause (d) is load-bearing.
> 7. **⛔⛔ THE ARMING GATE IS THREE ORDINARY CONVERSIONS, ONE OF WHICH NEEDS FOUR SIBLING
>    WIRINGS FIRST. READ THIS BEFORE PLANNING ANYTHING.** Step 6 is at **34** as the check
>    reports it (measured on master with the class-B declarations applied). Composition,
>    measured per function with MODULE-QUALIFIED import resolution:
>
>    | class | n | path to zero |
>    |---|---|---|
>    | **PUBLIC — product import** (v178 clause 1) | **7** | none convert; see below |
>    | **PUBLIC — cross-repo test harness** (v178 clause 2) | **1** | `test_workflow_full_round_trip` — MUST NOT convert |
>    | **NOT PUBLIC API** by ratified v178 | **26** | the criterion removes them once IMPLEMENTED |
>
>    **7 + 1 + 26 = 34, exactly.** So the criterion shrinks the unresolved population from
>    **30 to 8**, and of those 8 every single one was read and **none has a genuine failure
>    track**. Arming therefore still needs ONE ruling — what the Result-return rule requires of
>    a function with no failure mode — but the population it applies to is ~6, not 30, and the
>    conversion track that was supposed to shrink it is EXHAUSTED.
> 7a. **⚠️ THE 46/40 FIGURES IN OLDER SECTIONS BELOW ARE SUPERSEDED, AND ONE OF THEM WAS
>    MEASURED WRONG.** The "40 of 46 are not public API" figure came from a BARE-NAME oracle.
>    Re-measured with module-qualified resolution, it over-credited at least one function:
>    `merged_branch_sweep.fetch_manifest` was scored PUBLIC with two consumers, but **both
>    consumers import a DIFFERENT `fetch_manifest`** — there are two functions of that name
>    (`fleet/fleet_conformance.py:187` and `fleet/merged_branch_sweep.py:94`), and the offender
>    has ZERO consumers. **That is this thread's own "read the callee, do not match the name"
>    lesson recurring INSIDE the measurement built to apply it.** Any future oracle MUST
>    resolve an import to its DEFINING MODULE. Do not re-derive the old numbers.
> 8. **🔑 THE CRITERION IS RATIFIED — livespec v178, `d230c9ff`.** `__all__` membership no
>    longer defines public API. A function is public when CONSUMED ACROSS A BOUNDARY, measured
>    FLEET-WIDE, in four enumerated forms. See §"v178 — THE CRITERION" for what it costs and
>    what it does NOT do. **It is ratified but NOT IMPLEMENTED** — two impl commitments are
>    declared, and until the repo-local half ships, the check still reports 34.
> 9. **⛔ `zu85` — the START-HERE target this file used to name is UNCONVERTIBLE.** Four of
>    the 46 offenders live in `otel_step_timer.py`, and that file **cannot import the railway
>    at all**: `docker/fabro-sandbox/base/Dockerfile:106` COPYs it ALONE to
>    `/usr/local/bin/livespec-step-timer`, its `Dockerfile.dockerignore` allowlists only that
>    one file into the build context, and it runs on the base image's system python3 BEFORE
>    the first `uv sync`. The house vendor-path idiom would resolve to `/usr/local/_vendor`
>    and `ImportError` at import time, breaking **every dispatched Fabro prepare step**. So
>    dev-tooling cannot reach measured ZERO by converting, and arming is blocked on an
>    exemption that does not exist today. **The handoff previously named
>    `otel_step_timer.parse_argv` as the START-HERE target, "already READ and verified
>    genuine" — the failure-semantics reading was RIGHT and the deployment reading was never
>    done.** Do not retry it. Full record and the do-not-do-this-instead warning are on
>    `zu85`.
> 10. **DO NOT ARM until dev-tooling measures ZERO**, and do NOT start the other five repos'
>    223 — fan-out follows arming. The ordering trap is unchanged and is the oldest constraint
>    on this thread: this repo runs the check on ITSELF, so arming early turns its own
>    `just check` red and lefthook then blocks the very commit that would fix it. **And per
>    steps 7–9 above, ZERO is not reachable by conversion at all** — ~39 remain after every
>    convertible offender is converted. `zu85` does not relax the gate and neither does the
>    `__all__` finding: if the floor is non-zero, arming needs a ruling on what the gate MEANS,
>    not an early arm.
> 9. **`8o8e.1` being CLOSED is not the epic.** `check-public-api-result-typed` still scans
>    ZERO files in every flat-layout repo — it is still `pure_trees`-scoped, and NOTHING landed
>    so far has changed that. **Re-verified 2026-07-29 by reading the code, not the record:**
>    `public_api_result_typed.py` still resolves its universe as
>    `role_trees(role=config.pure_trees)` behind a `role_absence_exit_code` gate, and this repo
>    declares `pure_trees = { not_applicable = … }`, so the check gates out before scanning
>    anything. Every reduction from 59 → 47 lowered what arming WILL report; it did not arm
>    anything. See the ⛔ paragraph immediately below.
>
>    **⚠️ AND "RE-DERIVE" MEANS READ THE ARTIFACT, NOT THE STATUS FIELD.** A 2026-07-28 cold
>    start found TWO ledger statuses that were FALSE — `pj3j` read `BACKLOG` and `fwcwxv` read
>    `blocked`/`needs-human` while both had verifiably landed (`c0c0472`, `0500155`). The
>    staleness pointed the dangerous way: `fwcwxv` read as "a maintainer still owes a
>    propose-change" for a change already RATIFIED, three lines from this file's own "Do NOT
>    re-file it." **A status is a claim like any other.** Read the commit, the file, the
>    `history/vNNN/` directory.


The open item is the EPIC, **`livespec-dev-tooling-8o8e`**. Its child **`8o8e.1` is CLOSED** —
its ledger notes carry the full record (the role-key classification, the maintainer ruling, the
union design, the release mechanism, the Phase 1 proof, the Phase 3 exercise evidence and the
eighteen-piece discharge), and it is far more detailed than this file. **Read it for the record,
never for the next action.**

**ALL FOUR PHASES HAVE LANDED and the spec is ratified at v033. All eight repos measure ZERO
`LegacyAmbiguousEmpty`, Phase 3 makes that keep being true, and Phase 4 (`v1.0.0`) makes the
ambiguous spelling unloadable in every consumer.**

**⛔ THAT IS NOT AN ARMED RAILWAY, AND THE DIFFERENCE IS THIS THREAD'S ENTIRE SUBJECT.**
`check-public-api-result-typed` is STILL `pure_trees`-scoped, so it still scans **zero files** in
every flat-layout repo — legitimately and honestly now, and still zero. Phases 2, 3 and 4 made the
SCHEMA honest, made it STAY honest, and made the ambiguous spelling unloadable; none of them made
any check scan anything. Arming means migrating
that check off `pure_trees` onto `resolve_check_universe()` — `8o8e`'s own **step 6, NOT STARTED**.

**AND IT IS NOW MEASURED, NOT ASSERTED.** On 2026-07-28, every repo's live `pyproject.toml` was
loaded through the shipped loader and `config.pure_trees` resolved through the shipped
`role_trees()` accessor — the same call `public_api_result_typed.py:186` makes. **All eight
repos yield an EMPTY tree list. Fleet total scan roots: 0.** Four `UnarmedUntil`
(`livespec`, `livespec-orchestrator-beads-fabro`, `livespec-orchestrator-git-jsonl`,
`livespec-overseer`) and four `NotApplicable` (`livespec-dev-tooling`, `livespec-driver-claude`,
`livespec-driver-codex`, `livespec-runtime`). The thread's central claim is a measurement.

**RE-DERIVED INDEPENDENTLY LATER THE SAME DAY, and it reproduces EXACTLY.** All NINE members'
live `pyproject.toml` re-fetched from the forge and re-loaded: four `UnarmedUntil`, four
`NotApplicable`, plus `livespec-console-beads-fabro` reporting `Undeclared` — **fleet total scan
roots: 0**, and no member REJECTED by the loader. Two things make the re-run worth more than a
repeat: it was taken through a loader first proven **behaviorally identical to the released
`v1.0.0`** every sibling actually consumes (the `v1.0.0..master` diff of `config.py` is
comment-only, verified line by line), and all eight siblings were re-confirmed to declare
`tag = "v1.0.0"`. So the measurement is against the loader the fleet RUNS, not merely the one this
repo has checked out. `public_api_result_typed.py:186` still reads
`role_trees(role=config.pure_trees)`: **step 6 is NOT STARTED, and that is verified rather than
inherited.**

### ✅ AUTHORITY CHANGED 2026-07-29 — step 6 IS AUTHORIZED, and Piece 1 is DONE

Maintainer ruling: do the propose-change, revise, grooming and implementation autonomously; on step
6, **"remediate dev-tooling's 59, then arm, then fan out."** The items this file previously listed
as human-gated are no longer parked on a maintainer. **The spec lifecycle is NOT waived** — changes
still go through propose-change and revise as OPERATIONS — but the accept/reject decision at revise
is delegated to this thread.

**PIECE 1 IS COMPLETE: `5ror` and `clkf` are RATIFIED as v034 and both are CLOSED.** Batched into
ONE propose-change/revise cycle because both target `contracts.md` and are the same class. Filed
`c3a1915`, ratified `3a7d8d8` (PR #807). Details on the closed items; the two things most likely to
be undone by a later editor are recorded in §"What v034 preserved" below.

### 🛡️ WHAT v034 PRESERVED — three carve-outs a later editor is most likely to undo

Recorded here because each was a deliberate NON-change inside a change, and none of them is
self-evident from reading the ratified text alone:

1. **The harden-first ordering clause SURVIVED the retirement of the regime it governed.** "A
   rejecting loader MUST NOT land before every consumer has migrated" is the GENERAL rule for
   future required-key schema changes; the `[]`-on-union-keys transition was one application of
   it. Deleting the rule alongside its occasion was the obvious tidy and would have discarded the
   constraint that made this whole epic land safely.
2. **§"Clean role keys retain `[]`" is untouched.** A bare `[]` remains legitimate for
   `source_trees`, `io_trees`, `commands_trees`, `supervisor_entry_files`, `covered_trees` — for
   those, emptiness removes exemptions rather than files, so it makes the consuming check STRICTER.
   "Declared-empty is retired" MUST NOT be generalized.
3. **The v0.54.12 deviation record is retained as HISTORY, not deleted as embarrassment.** It now
   reads as "that was the regime then in force" plus an explicit statement that it is NOT a
   standing licence. The paragraph's purpose was always to record a deviation rather than smooth
   it over; correcting its justification without deleting the record is the whole trick.

**And the scenario was REWRITTEN, not deleted** — the behavior (a consumer declaring a union key as
a bare `[]`/`""`) still exists and is still load-bearing; only its outcome changed from WARN to
hard failure. No other scenario covers that input: the neighbouring one governs a blessed variant
NAME with an empty payload, which is a different input. The line `And the emptiness MUST NOT be
reported as a sanctioned opt-out` was carried over verbatim — it is the invariant the union exists
to enforce, and it survives the change in outcome.

### 🚦 STEP 6 PROGRESS — **59 → 46**, and the cross-repo blocker is CLEARED

| landed | effect |
|---|---|
| **#809** underscore rule (`b49c744`) | **59 → 53** |
| **#812** ROP slice 1 (`8751a69`) | **53 → 51** |
| **livespec #1821** — spec **v177** (`7acee70a`) | ratifies the exemption set; unblocks the next row |
| **#816** honor `supervisor_entry_files` (`537ec6a`) | **51 → 48** |
| **#821** ROP slice 2 — `parse_manifest` (`2ff79a5`, released `v1.0.4`) | **48 → 47** (20 files → 19) |
| **#826** ROP slice 3 — `filter_siblings`, the hand-rolled Either (`bcbe035`) | **47 → 46** |

**RE-MEASURED 2026-07-29 on master at `bcbe035`, not inherited:** universe **145**, **19** files,
**46** offenders — the shipped `public_api_result_typed._find_offenders` run over the
shipped `resolve_check_universe()` with this repo's real config. The 48 it started from
reproduced exactly first, so the delta is measured at both ends.

**⛔ THE FLOOR IS ~39, NOT 43 AND NOT 0.** An earlier revision of this file said "the
conversion floor is 43" — **wrong, and retracted.** Only **4** of the 46 have a real failure
track (~7 after the triage's I/O reading); 8 are `main()` supervisors wanting a DECLARATION, 4
are `zu85`'s, and **30 are genuinely TOTAL functions with no path to zero today**. See
START-HERE steps 7–9.

### ⚖️ `zu85` OPTIONS — COMPARED AND RECOMMENDED, NOTHING IMPLEMENTED. Awaiting a ruling.

Produced under supervisor brief 22, which asked for a worked comparison rather than a stop. The
full version with costs is on the `zu85` item; the decision content is here.

**RECOMMENDATION: option (a). It needs NO spec change, and that is MEASURED.** Probing the
SHIPPED `_find_offenders` against `otel_step_timer.py`, varying only `__all__` and the
declaration:

| variant | offenders |
|---|---|
| today | **4** |
| `__all__` narrowed to `main` + the two constants | **1** |
| that, plus the file declared in `supervisor_entry_files` | **0** |

- **(a) NARROW THE PUBLIC SURFACE — RECOMMENDED. No split is required, and that is the
  surprise.** The brief's hypothesis (a shim's public surface reduces to exempt shapes) is
  right, but the mechanism is simpler: the problem was never the CODE's placement. None of
  `parse_argv`, `build_trace_payload`, `run` is imported by any other first-party module — they
  are internal helpers of a baked CLI, exported so unit tests can reach them. **EXPRESSES an
  existing reality rather than weakening the rule.** Same premise `#809` was ratified on.
  **A split would make it WORSE:** the shim must be self-contained (single-file `COPY`,
  single-file dockerignore allowlist), so logic cannot move out — a split yields either a broken
  image or a second forked copy, which is `qv3k`'s hazard and this fleet already has eight.
  **THE HONEST RISK:** narrowing `__all__` purely to silence a check IS the `io_trees`
  hook-tree dodge this epic refused. What makes it legitimate here is an ORACLE, not an
  assertion — "is this name imported across a first-party module boundary?" — which is
  mechanically answerable and was answered. If (a) is adopted the narrowing MUST be justified
  per name against that oracle, never wholesale.
- **(b) A FIFTH RATIFIED EXEMPTION — do NOT adopt, and it is unnecessary.** It is **genuinely
  new in kind**, stated plainly: v177's four members all describe SUPERVISOR shapes; this would
  describe a DEPLOYMENT fact. It also creates a class nothing mechanically verifies — `m50u`'s
  finding that a blessed payload nobody checks is "a comment with better syntax highlighting".
  Spending a widening on a problem a ratified mechanism already solves is the expensive
  direction. Recommend only if (a) is rejected on the honesty ground above.
- **(c) CHANGE THE BUILD — do NOT adopt. It DOES violate the constraint that created the
  module.** The module is stdlib-only because it runs before the first `uv sync`, in BASE, on
  the base image's system python3. Vendoring `returns` onto that interpreter's path puts the
  fleet's ROP library into every consumer's base image, widens the dockerignore allowlist from
  one file to a tree (whose stated purpose is a tiny hermetic context), grows the layer CI pulls
  every run, and lets a `vendor_update` break the image. It buys railway-typing four functions
  in one CLI wrapper. The cost/benefit is inverted.
- **(e) THE OPTION NOT ON THE LIST, AND IT OUTRANKS ALL FOUR** — see the section below.

### 🔑 THE `__all__` FINDING — `zu85` is a 4-of-46 instance of a 40-of-46 problem

Measured while testing option (a), and it reframes the remediation. **Of the 46 current
offenders, 40 are exported in `__all__` but imported by NO other first-party module. Only 6
cross a module boundary.**

The check's premise — "public API = named in `__all__`" — is **false for this repo at scale**,
not in one module. `#809` corrected the `_`-prefixed spelling of exactly this defect (the 6
`check_mutation.py` cases); **the un-prefixed spelling was left standing and is 40.**
`check-all-declared` does NOT force it: it requires a well-formed `__all__`, not that every
top-level function appear in one, so narrowing is compliant today.

**CAVEAT, so the number is not over-read:** "not imported" is not "not used". `main` is reached
via `python -m`, not by import, and the probe is a static regex over first-party sources plus the
test tree. **40 is an UPPER BOUND on the mis-flagged set**, and each name still needs the
per-function reading the triage's own lesson demands. It is NOT a licence to bulk-narrow 40
`__all__` entries — that would be the bulk-declaration hazard one level over.

**Why it matters more than the count:** the D class of 30 genuinely-total functions has no path
to zero today, and conversion is the wrong answer for it by the triage's own ruling. If most of
D is not public API, the D class largely dissolves and the arming gate becomes reachable. **That
is the next thing to establish, and it is the critical path — not `zu85`.**

### 🔴 THE THIRD AXIS, PAID FOR IN A RED SIBLING MASTER — grep the eight repos BEFORE converting

**Slice 2 broke `livespec-orchestrator-beads-fabro` and turned its master RED.** Filed as
**`livespec-dev-tooling-dx8l`** (P0). Read that item before converting anything else.

`parse_manifest` moving to `Result` broke `codex_yolo_gate.py:104`, a HOOK in that repo which
imports it. **The blast radius of an API change is only knowable at the CONSUMED end, and the
auto-merge bump fan-out delivers "consumed" within minutes without anyone deciding.**

**THE FAILURE MODE IS A BOOBY TRAP AND DESERVES ITS OWN NAME.** The consumer did
`if manifest is None`. Against a `Result` that is permanently False, so the guard did not FAIL —
**it silently STOPPED BEING A GUARD**, and control flowed into `manifest.owner` on a `Success`,
raising an uncaught `AttributeError`. *A `None`-check does not survive a `Result` migration by
breaking loudly; it survives by no longer checking anything.* And the consequence direction was
the bad one: the refresh path crashed instead of returning 0, leaving an access-gating marker
**STALE rather than failing closed**. **Fail-stale on an access gate is strictly worse than
fail-closed.**

**THE PRECONDITION, now binding on every remaining conversion here and on the other five repos'
223:** before converting any public function, **grep all eight siblings for it**. This is the
mechanical form of `.ai/ci-gate-discipline.md` step 3 — *consumer wiring lands BEFORE the
dependency that assumes it* — which is exactly what slice 2 did backwards.

**AND IT CORRECTS THE `__all__` ORACLE.** The boundary oracle asked "imported by another
first-party module?" scoped to **THIS repo**. The siblings import symbols from this library **29
times fleet-wide** (vs 65–68 `python -m` targets per repo, so module execution still dominates —
the premise survives, the SCOPE was wrong). **A repo-local oracle would have classified
`parse_manifest` as non-public: the exact function whose conversion broke a sibling.** The
public-API criterion MUST therefore be **fleet-wide**, as a requirement and not a nicety — a
criterion right about 40 functions and wrong about the 29 that cross repo boundaries is worse
than none, because it is confidently wrong exactly where the blast radius is largest.

| repo | symbol imports | notable |
|---|---|---|
| `livespec` | 9 | 3 in PRODUCT code (`canonical_check_slugs`) |
| `livespec-orchestrator-beads-fabro` | 10 | **a HOOK importing `parse_manifest` + `resolve_owner`** |
| `livespec-driver-claude` / `-codex` | 3 each | `install_no_shadow_ledger`, `testing.cli_e2e` |
| `livespec-orchestrator-git-jsonl` | 3 | `config.iter_first_party_py_files` |
| `livespec-runtime` | 1 | `checks` |
| `livespec-overseer`, `livespec-console-beads-fabro` | 0 | — |

### 🧭 THE MISSING AXIS — the method constraint `zu85` added, binding on the fan-out

The step-6 triage classified all 59 offenders by FAILURE SEMANTICS and never asked a second,
independent question. Both are required:

1. **Does this function have a real failure track?** — the triage asked this well.
2. **CAN this module import `returns` at all, in every environment it executes in?** — never
   asked, and a perfect answer to (1) is worthless when (2) is no.
3. **Does any of the eight SIBLINGS import this symbol?** — never asked either, and it cost a
   red sibling master (`dx8l`). If yes, the consumer is wired FIRST, in that sibling, and the
   conversion lands only after.

**Binding on the other five repos' 223**, where a module executed outside its package's
dependency environment is MORE likely rather than less: the Drivers and orchestrators ship hook
entry points, and hook bodies are installed as foreign content into repos that do not carry the
vendored tree. Add this beside "read the callee, do not match the name".

### 🔒 THE SWEEP THAT BOUNDED `zu85` — it is ONE file, and that was measured too

Finding a deployment constraint that forbids conversion raises the obvious question of how
many other offenders carry one. **Measured, so nobody re-measures it:** all 20
offender-bearing modules were checked for a standalone/stdlib-only deployment constraint.
`otel_step_timer.py` is the ONLY one — it is the sole `COPY` of a first-party `.py`
anywhere under `docker/`, and the sole module whose docstring declares STDLIB ONLY. So the
blocker costs exactly 4 offenders and **nothing else in Track B is affected**. Recorded
because the cheap wrong response to `zu85` is to treat every remaining conversion as
suspect.

**THE GENERALIZABLE LESSON, and it binds the other five repos' 223.** The step-6 triage
classified all 59 by FAILURE SEMANTICS — does this `None` model a failure? — and never
asked whether the module can import `returns` at all. Those are independent questions and
the triage only ever asked the first. **For the fan-out, ask both**: a module that is
deployed standalone, vendored into another artifact, or executed outside the package cannot
be converted no matter how genuine its failure track is.

### ✅ THE CROSS-REPO SPEC CHANGE LANDED — livespec **v177**, and `i04f` is RESOLVED

Authority was granted 2026-07-29 to file and accept in the `livespec` repo. Done, under that
repo's OWN worktree→PR→merge protocol (read from its `AGENTS.md`, not dev-tooling's).

**`livespec-i04f` is discharged.** The Result-return rule was stated TWICE with incompatible
exemption sets — §"ROP composition" CLOSED it ("exempts only such supervisors"), §"Typechecker rule
set" OPENED it with `e.g.` **and** added `build_parser`. Resolved by taking the second's CONTENT
with the first's DISCIPLINE. **The set is now stated ONCE**, in §"ROP composition", and the
typechecker section CITES it — because restating a normative set in two places is what produced the
defect, and two copies would drift again.

**The `e.g.` was the sharper half.** An open-ended list in a NORMATIVE exemption clause is the same
ambiguity class this fleet spent an epic removing from the role-key schema, where a value meaning
"whatever the reader needs" silently disarmed six checks.

**The ratified set has exactly four members**: `main() -> int` under `commands/*.py` or
`doctor/run_static.py`; `build_parser() -> ArgumentParser` under `commands/**.py`; any function
annotated `None`; and **a supervisor entry point in a file declared in `supervisor_entry_files`**.

### ⚖️ WHY MEMBER 4 IS NOT A WIDENING — and what it DOES cost

Three things went into the RATIFIED TEXT rather than only a rationale, because each is the kind a
later editor drops:

- It admits the **SAME category** through a different mechanism and creates **NO new class** of
  exempt function.
- **A per-file declaration is STRICTER than a directory glob.** `commands/*.py` exempts every
  present and future file with nobody deciding anything; `supervisor_entry_files` names each file,
  and **a repo that has not spoken gets nothing**.
- **The cost is real and recorded**: flat-layout consumers gain an exemption they cannot express
  today, so the fleet-wide count of exempt functions WILL rise, and each claim must carry a written
  reason rather than arriving by inheritance from a directory name.

Member 4 is also **BOUNDED** — it exempts supervisor ENTRY POINTS in a declared file, never every
function in it. Both properties are pinned by test in #816.

### ⛔ DO NOT BULK-DECLARE THE REMAINING NINE SUPERVISORS

#816 exempted only the **3** `main()`s already declared. Nine remain, and declaring them is NOT a
formality: **`supervisor_entry_files` grants FOUR exemptions per file**, not one — this repo's own
`pyproject.toml` comment says so and lists them (`no_write_direct`, `supervisor_discipline`,
`no_except_outside_io`, `partition_completeness`). Bulk-declaring nine files to silence ONE check
would hand each a stdout-write, `sys.exit`-confinement and broad-catch exemption it may not
warrant. **Each needs the same per-file judgement the triage applied to functions** — which is the
triage's own lesson arriving one level up, in the declarations rather than the code.

### 🚦 (superseded) STEP 6 PROGRESS — 59 → 51, and the blocker is a DIFFERENT REPO'S SPEC

| landed | effect |
|---|---|
| **#809** underscore rule (`b49c744`) | **59 → 53.** A `_`-prefixed name is not public API even inside `__all__`. |
| **#812** ROP slice 1 (`8751a69`) | **53 → 51.** Two of `fabro_image_pin_rewrite`'s three `X \| None` returns converted. |

### ⛔ THE RULE THIS CHECK ENFORCES IS NOT IN THIS REPO'S SPEC — verify before planning anything

**`livespec-dev-tooling/SPECIFICATION/` never states the Result-return rule at all.** Measured:
zero hits for `Result[_, _]` or "public function". The normative rule lives in
**`livespec/SPECIFICATION/non-functional-requirements.md`**, and it is stated **TWICE with
INCOMPATIBLE exemption sets**:

- **line 655** — "…unless the function is a supervisor at a deliberate side-effect boundary
  (`main() -> int` in `commands/*.py` and `doctor/run_static.py`, or any function returning
  `None`). **The rule exempts only such supervisors.**"
- **line 695** — the same sentence **plus** "OR the `build_parser() -> ArgumentParser` factory in
  `commands/**.py`".

That contradiction is **`livespec-i04f`**, already filed and listed here as carried-forward. The
repo's own test file for this check has documented it for some time.

**CONSEQUENCE: widening the supervisor exemption is a `livespec`-REPO spec change, not a
dev-tooling one.** Line 655 is explicitly CLOSED ("exempts only such supervisors"), so honoring
`supervisor_entry_files` in dev-tooling's check ALONE would ship an exemption the ratified rule
does not grant — which is precisely the `io_trees` hook-tree dodge this epic REFUSED, "an
unratified exemption invented in config rather than argued in the spec". **It was deliberately not
implemented for that reason.**

### 🔑 THE `supervisor_entry_files` LEVER IS REAL, AND STRONGER THAN IT LOOKED

Verified rather than taken. `supervisor_entry_files` is consumed by **FOUR** checks —
`no_except_outside_io`, `no_write_direct`, `supervisor_discipline`, `partition_completeness` — and
**`public_api_result_typed` is the ONLY one of the five that never asks the repo.** So the
Result-return check and the except-position check already disagree about what a supervisor is.

**3 of the 12 `main()` offenders are ALREADY declared** (`canonical_checks.py`,
`cross_repo/bump_pr_supersession.py`, `fleet/merged_branch_sweep.py`), so honoring the key exempts
them with no new declaration at all; the other 9 would need an explicit, reasoned entry. That is
the epic's own idiom — an ACTIVE per-file declaration, verbose and greppable, where a repo that has
not spoken still gets nothing.

**AND THIS REPO'S OWN SPEC UNDER-REPORTS IT.** `contracts.md:217` says `supervisor_entry_files` is
"Consumed by `no_except_outside_io`" — **one of four**. Meanwhile `pyproject.toml`'s comment
correctly says "Adding a path here grants it FOUR separate exemptions" and lists them. **The
staleness is INVERTED from this thread's usual direction**: here the config comment is right and
the ratified spec is wrong. Correcting that bullet is a dev-tooling propose-change and is
independent of the livespec one.

### 🔧 TWO MEASUREMENTS THAT CORRECT THE RECORD

- **`returns` IS vendored in `livespec-dev-tooling`** (`livespec_dev_tooling/_vendor/returns`), so
  conversion needs no vendoring prerequisite. The `8o8e` epic description's table saying this repo
  does NOT vendor it is **STALE**. Zero first-party imports, though — "vendoring is not usage"
  still holds exactly as the epic says.
- **`Optional`-as-optional is NOT a failure track, and one of three in the strongest class was
  not a conversion.** `tag_version_component() -> str | None` returns `None` because a tag HAS no
  version component — a legitimate absence. Converting it would force every caller to unwrap a
  `Failure` for an ordinary answer. **The "hand-rolled failure track" class must still be read per
  function**, or the triage's own lesson gets re-lost one level down.

### 🧭 METHOD CONSTRAINT FOR THE FAN-OUT — read EVERY function, including the convicted ones

**The strongest form of this rule, and the one to carry hardest.** `tag_version_component` was in
the STRONGEST convert class — a hand-rolled `X | None` failure track — and it was **still not a
conversion**: its `None` means the tag HAS no version component, a legitimate absence. Wrapping it
would force every caller to unwrap a `Failure` for an ordinary answer.

**That is the triage's own lesson recurring INSIDE the triage's own output**, which is exactly how
this thread's defect propagates: a classification convicts a set, the set is then treated as
settled, and the reading stops. **Read every function the classification convicted, not only the
ones it acquitted.** One of three in the strongest class was innocent.

### 🧭 AND: read the callee, do not match the name

Binding on the other five repos' 223, not just on this pass. Matching call NAMES flagged ten
"total" functions as touching I/O; reading them showed most hits were `dict.get` / `settings.get`
and **only three were real** (`subprocess.run`, an injected runner seam, `Path.is_file`). The
shortcut errs toward **over-conversion**, which is the expensive direction — it manufactures
`Result` types whose failure track is uninhabited and sells it as progress.

### 🔬 STEP 6 TRIAGE — the 59 are triaged. **Only ~15 are genuine conversions. DO NOT convert 59.**

The maintainer's sequence is remediate → arm → fan out, but this file's own measurement said it
could not settle whether each offender is a genuine violation. **It is now settled, per function.**
Reproduced exactly — 59 offenders in 21 files — by running the SHIPPED
`public_api_result_typed._find_offenders` over the git-derived universe `resolve_check_universe()`
returns, with this repo's real config (`commands_trees` is **empty**, which is load-bearing below).

| # | class | verdict |
|---|---|---|
| **6** | **private name in `__all__`** | **NOT a violation — the check over-reaches.** All six are in `checks/check_mutation.py`, whose `__all__` contains ONLY `_`-prefixed helpers and does not even list `main`. `__all__` there exposes privates for testing; it is not a public-API declaration. The spec's rule is "every **public** function's return annotation"; a `_`-prefixed name is private by this repo's own convention. The check equates `__all__` membership with publicness, and for this module that equation is simply false. |
| **12** | **`main() -> int` supervisor** | **NOT a conversion — needs a stated exemption or a declared location.** The spec exempts exactly this shape, but scopes it to `commands/*.py` and `doctor/run_static.py`. dev-tooling declares NO `commands_trees` and its supervisors sit flat at `livespec_dev_tooling/*.py` and `checks/*.py`. The check is faithfully implementing the spec — its own docstring says the scoping "is load-bearing, not decoration" — so the gap is in the SPEC's location-scoping, not the check. |
| **7** | **exit-code returner** | **Mostly the same family.** `install_hooks`, `install_neutral_hook_body`, `install_pack`, `run`, `run_tdd_commit`, `run_from_settings` are supervisor BODIES returning an exit code, each called by an exempt-shaped `main()`. `ordinal_distance() -> int` is the odd one out — pure arithmetic, no failure mode. |
| **6** | **hand-rolled failure track `X \| None`** | **CONVERT — the strongest candidates.** These already model failure; they just model it off-railway. `tag_version_component`, `rewrite_layered_docker_tag`, `rewrite_pin_in_text` (fabro), `parse_manifest`, `fetch_manifest`, `parse_argv`. |
| **1** | **hand-rolled Either** | **CONVERT.** `fleet/dispatch_matrix_filter.filter_siblings() -> FilterOutcome \| FilterError` is literally an Either encoded by hand. |
| **3** | **explicit `raise` / `try`** | **CONVERT.** `parse_manifest` (also `\| None`), `select_runner`, `test_workflow_full_round_trip`. |
| **~3** | **real I/O, unhandled** | **CONVERT to `IOResult`.** `fleet/ensure_plugins.subprocess_runner` (`subprocess.run`), `testing/cli_e2e.run_workflow` (injected runner seam), `checks/required_role_keys_declared.layout_dependent_check_slugs` (`is_file`). |
| **~22** | **genuinely total pure** | **DO NOT CONVERT.** Plain value in, plain value out; no raise, no try, no `None` failure return, no I/O. `Result` on a total function carries no information — the failure track would be uninhabited. Wrapping them satisfies the letter of "every public function" and defeats its purpose. |

**Counts sum to 59** (the 6 `\| None` include `parse_manifest`, which also has a `try`, so the
conversion set is the UNION, not the sum: **~15 distinct functions**).

**⚠️ A HEURISTIC IN THIS TRIAGE WAS WRONG ONCE AND IS CORRECTED HERE.** A first pass flagged ten of
the "total" functions as touching I/O by matching call names. Reading them showed most hits were
`dict.get` / `settings.get`, not I/O. **Only three are real.** Recorded because the same
name-matching shortcut would mis-triage the other five repos' 223 in the same direction — toward
over-conversion, which is the expensive direction to be wrong in.

**THE TWO STRUCTURAL FINDINGS, which matter more than the counts.** Both say the remaining 41
non-conversions need a SPEC decision, not code:

1. **The `main()` exemption is granted to a LOCATION, and the enforcement suite has no such
   location.** Either dev-tooling declares a commands tree (fabricating a layout it does not have),
   or the spec's exemption is restated to name the shape rather than the directory. **This is a
   propose-change, and it must land BEFORE arming** — otherwise arming reddens 19 functions the
   spec already means to exempt.
2. **`__all__` is overloaded in this repo**, and the check's "public API = named in `__all__`"
   premise is false wherever `__all__` is used to expose privates for testing.

**SEQUENCE, REVISED BY THE TRIAGE:** spec change for the two structural classes → convert ~15 in
slices (each its own Red-Green-Replay pair and its own PR) → re-measure → arm → fan out. **Arming
still MUST NOT precede dev-tooling reaching zero**: the ordering trap is unchanged, this repo runs
the check on itself, and lefthook would block the very commit that fixes it.

### 📐 STEP 6's BLAST RADIUS — RE-MEASURED 2026-07-28. **282, not 245.** Read-only; nothing armed.

The loader has stopped moving, so this is the first moment the number can be trusted — which is
exactly the precondition this file has carried from the beginning.

**Method:** `master` TARBALLS from the forge (no local clone touched — several are shared). The
universe uses the SHIPPED `config.filter_first_party_py`, the same predicate
`resolve_check_universe()` calls. Offenders use the SHIPPED
`public_api_result_typed._find_offenders`, so **PR #748's PATH-SCOPED exemptions apply as
IMPLEMENTED**, not as the old table assumed. Each repo's own `pyproject.toml` supplies
`tests_tree_prefix`, `commands_trees` and `neutral_hook_body_path`.

| repo | universe | files | OFFENDERS | `commands_trees` |
|---|---|---|---|---|
| `livespec-dev-tooling` | 145 | 21 | **59** | NONE |
| `livespec-orchestrator-beads-fabro` | 184 | 25 | **58** | declared |
| `livespec-overseer` | 84 | 11 | **56** | NONE |
| `livespec-runtime` | 31 | 20 | **46** | NONE |
| `livespec` | 129 | 17 | **35** | declared |
| `livespec-orchestrator-git-jsonl` | 49 | 17 | **28** | declared |
| `livespec-driver-claude` | 6 | 0 | **0** | NONE |
| `livespec-driver-codex` | 7 | 0 | **0** | NONE |
| `livespec-console-beads-fabro` | 0 | 0 | **0** | zero-Python |
| **FLEET TOTAL** | **635** | **111** | **282** | |

**THE STALE 245 IS RECONCILED, NOT MERELY REPLACED.** 35 of the 282 are `main` / `build_parser` in
a location the spec does NOT exempt. Read the exemption as unscoped — granted to a NAME rather than
a LOCATION — and the total falls to **247, within two of the recorded 245.** So the old figure was
not wrong arithmetic; it was computed under the wrong reading, and this identifies which.
Understated by **+37**, as this file warned.

**Correction to this file's own estimate:** it said the scoping meant 245 "subtracted 75
main()/build_parser() hits fleet-wide". The measured delta is **35, not 75**. Direction right,
magnitude wrong; do not restore 75.

**What it cannot settle:** whether every offender is a genuine violation (some may want a
spec-stated exemption rather than a conversion — per-function judgement, not measurement); whether
each is reachable public API (the rule is "top-level function named in `__all__`"); and the
ORDERING TRAP, which still binds — `livespec-dev-tooling` runs this check on ITSELF, so arming
turns its own `just check` red and lefthook blocks the very commit that would fix it.
**Remediating dev-tooling is a PRECONDITION of arming, not a follow-up**, and at 59 offenders in
21 files it is the largest single piece. **Nothing here says step 6 should proceed — it says what
it would cost.**

**AND PHASE 3 SHARPENED THAT, RATHER THAN SOFTENING IT.** Four repos now declare
`pure_trees = { not_applicable = "…" }` **honestly and correctly**, which means arming the railway
in those four **cannot come from `pure_trees` at all** — there is no tree there to widen. Step 6 is
not "fill in the empty key later"; it is a different universe source. A reader who sees Phase 3
green and infers the railway is close to armed has inverted the finding.

**Phase 3 is LANDED and REGISTERED — PR #779 → `606f17b`.** The conformance row that turns the
eight-repo measurement below into a standing guarantee is merged AND wired into `OBLIGATION_ROWS`,
which is the only step that makes it run. It was parked unregistered for hours on purpose: an
unregistered row is walked by neither engine. `livespec-dev-tooling-oitd` (PR #776 → `34c05c1`)
decomposed the table to make room and is **CLOSED**.

**Phase 4 MUST NOT start.** It cannot land until the filed spec change (PR #773 -> `f58e7d03`,
now on master as a PENDING proposed change) is ACCEPTED by a maintainer, or the spec actively
contradicts the implementation the day it ships.

### State as of 2026-07-28 (RE-DERIVE — this ages in minutes)

| thing | state |
|---|---|
| `livespec-dev-tooling` master | re-derive; was `606f17b` at wrap-up |
| `oitd` — obligation-table decomposition (PR #776) | **merged `34c05c1`, item CLOSED.** `_contract_rows.py` 246 → 183 → **195** with the Phase 3 row registered |
| Phase 3 — conformance row + registration (PR #779) | **merged `606f17b`.** Two commits: the row (`8dc8027`) and its REGISTRATION (`606f17b`) |
| Phase 0 — commit-pairs coupling break (PR #755) | **merged `5f82dbe`, RELEASED in `v0.56.7`** |
| Phase 1 — accepting loader (PR #759) | **merged `8a61df6`, RELEASED in `v0.57.0`** (verified: `git tag --contains 8a61df6` → `v0.57.0`) |
| Sibling consumption | **ALL SEVEN carry `v0.57.0`** — the pin gate is fully open; #296 merged after a re-run. **RE-DERIVE per repo.** |
| Piece B — `livespec-driver-claude` prose (PR #317) | **merged `e8c8847`** |
| Slice 3 — `livespec` values + prose (PR #1814) | **merged `6454b2cc`** — fleet's first `unarmed_until` |
| Piece 1 — spec propose-change (PR #773) | **SUPERSEDED BY EVENTS — this row described the FILED state and was left standing after ratification.** It is now RATIFIED: `SPECIFICATION/history/v033/` exists, `proposed_changes/` is drained to `README.md` only (the change was CONSUMED by revise), and `contracts.md` carries the four-variant regime. Ratified at `0500155`, which `git merge-base --is-ancestor 0500155 b36e0b8` confirms landed BEFORE Phase 4. `fwcwxv` is **CLOSED**. Do NOT re-file the propose-change. |
| Slice 4 — `livespec-runtime` values + prose (PR #366) | **merged `408388c`** — fleet's first two `convention_not_adopted` |

**MERGED ≠ RELEASED ≠ CONSUMED.** Keep the three separate in every status claim. Conflating them
re-creates this thread's core defect — a green signal that means nothing — at the process level.

### ✅ FLEET PROGRESS — 8 of 8 DONE. **FLEET TOTAL: 0.** This is HALF the closure-precondition evidence.

Measured on the **FORGE** after every merge, loading each repo's `pyproject.toml` through
`master`'s union loader. This is a SCHEMA measurement under one loader — deliberately, so only the
config varies. Each repo's own suite was ALSO run green under its OWN pinned loader, which is the
part the precondition demands.

**Re-verified by the LANDED Phase 3 row on 2026-07-28**, against the live nine-member manifest from
both the central CI sweep and a direct per-repo run: eight members EVALUATED and passed, and
`livespec-console-beads-fabro` (no `[tool.livespec_dev_tooling]` block) returned a NAMED
`excluded-with-reason` rather than a silent skip. So this table is no longer a snapshot someone has
to re-take — but see the 🛑 CLOSURE PRECONDITION section: it is the half about DECLARING correctly,
not the half about REJECTING the ambiguous spelling.

| repo | legacy | the blessed variants it now carries | own suite |
|---|---|---|---|
| `livespec` | **0** | `pure_trees`=**UnarmedUntil**, `neutral_hook_body_path`=NotApplicable | 73/73 |
| `livespec-dev-tooling` | **0** | 3× NotApplicable | 64/64 |
| `livespec-driver-claude` | **0** | 2× NotApplicable, `target_dirs`=SupersededBy | 64/64 CI |
| `livespec-driver-codex` | **0** | 2× NotApplicable, `target_dirs`=SupersededBy | exit 0 / 66 |
| `livespec-orchestrator-beads-fabro` | **0** | 2× NotApplicable, `pure_trees`=**UnarmedUntil** | 72/72 |
| `livespec-orchestrator-git-jsonl` | **0** | 2× NotApplicable, `pure_trees`=**UnarmedUntil**, 2× SupersededBy | 65/65 |
| `livespec-overseer` | **0** | 2× NotApplicable, `pure_trees`=**UnarmedUntil**, 2× ConventionNotAdopted | 62/62 |
| `livespec-runtime` | **0** | 3× NotApplicable, 2× ConventionNotAdopted | 62/62 |

**29 → 0 (repo, key) pairs.** All four blessed spellings are exercised by real repos.

PRs: Piece A `8b5ab7f` · Piece B #317 · livespec #1814 · runtime #366 · beads-fabro #1081 ·
overseer #223 · git-jsonl #438 · driver-codex #297. One PR per repo, never batched.

### 🔑 THE `pure_trees` SPLIT — the same key, and FOUR repos got the OPPOSITE answer correctly

**This is the result most likely to be "tidied" by a later reader.** `pure_trees` is
`UnarmedUntil` in four repos and `NotApplicable` in four. The discriminator is **whether that
repo's OWN ratified `constraints.md` asserts an obligation the key gates** — NOT whether a `pure/`
directory exists:

- **`unarmed_until`** — `livespec` + `livespec-overseer` (`livespec-mutreal.1`),
  `livespec-orchestrator-git-jsonl` (`livespec-mutreal.1`),
  `livespec-orchestrator-beads-fabro` (`bd-ib-6qb2mc`). Both orchestrators ratify "property-based
  test coverage on pure modules" AND wire `check-pbt-coverage-pure-modules` into `just check` — so
  the concept applies, the check is wired, and it was scanning zero. `not_applicable` would have
  been **factually false**.
- **`not_applicable`** — `livespec-dev-tooling`, `livespec-driver-claude`, `livespec-driver-codex`,
  `livespec-runtime`. Checked, not assumed: `livespec-driver-codex`'s `constraints.md` carries NO
  coverage-on-pure-modules clause, so nothing there is deferred.

Two repos with no `pure/` directory got opposite answers, correctly. **Do not collapse them.**

### `bd-ib-6qb2mc` — the id filed so `unarmed_until` could be honest

`livespec-orchestrator-beads-fabro`'s `pure_trees` was the one key in the fleet its own comments did
not determine (it had none). Ruled `unarmed_until`, with the id filed rather than invented, through
the orchestrator `capture-work-item` operation. It routed to **`blocked` / `needs-human`** via
intake DoR — correct rather than a formality: verifying the RESULT is mechanical, but deciding
WHICH modules are pure is an architectural judgement.

It carries the `constraints.md:26` citation, the `8858c90` history, the measured armed control
(23 files / 33 offenders — **arming proof, NOT its blast radius**), and an explicit
**do-not-close-by-declaring-`not_applicable`** warning: if the repo genuinely has no pure layer, the
CONSTRAINT must be amended through the spec lifecycle FIRST.

### ✅ THE PIN GATE IS FULLY OPEN — every repo carries `v0.57.0`

`livespec-driver-codex` was never blocked by a defect. #296 failed on a PyPI download timeout
(`Failed to download ruff==0.8.6 ... operation timed out`) during dependency INSTALL, with 62 of 64
checks passing and `ci-green` failing only because that job did. A `gh run rerun --failed` landed
it. Keep the lesson: *"gated on a flake" and "gated on an incompatibility" deserve different
answers* — the record asserted the second for hours without anyone reading the log.

### ✅ PROSE — ALL EIGHT REPOS CLEAN. And **a grep would have missed FIVE of the second sites.**

Phase 2's definition of done was VALUES **and** PROSE, and both are now done fleet-wide. The
durable finding is about how the prose sites were found.

The retired wording — *"declare it explicitly empty ... Declared-empty is the sanctioned, VISIBLE
opt-out: the gating check no-ops and says so in a structured info event"* — was only the
**copy-paste family**. **Every repo migrated after Piece B also carried a SECOND stale sentence
phrased differently, and the grep would have caught none of them. Five for five:**

- `livespec` — "A role core LACKS **is declared explicitly empty (list `[]`, scalar `""`) with a
  reason**". *Repo had been classified prose-CLEAN by the grep.*
- `livespec-runtime` — the same shape in its e9j Wave-1 note.
- `livespec-overseer` — "Still empty, and NOT an oversight" AND "Declared-empty: these roles remain
  unarmed". *Also classified prose-CLEAN by the grep.*
- `livespec-orchestrator-git-jsonl` — the strongest case: the header argued the backfill was
  "provably behavior-neutral" because "each key below resolves to the SAME empty/none Config as
  omission does". **That equivalence WAS the defect, stated as a virtue.** Correcting it was a
  reversal, not a touch-up.
- `livespec-driver-codex` — claimed the remaining heavy role keys "stay deliberately OMITTED" while
  `io_trees`/`commands_trees`/`covered_trees` are all declared twenty lines below. **Already
  inaccurate before this epic touched it.**

**CONSEQUENCE FOR PHASE 3's COMPANION CHECK — do not oversell it.** A literal-string check for the
retired wording is cheap and worth building, but it would have caught **ZERO of those five**, and
**two of the repos it must catch were scored CLEAN by exactly that grep**. Build it; never describe
it as closing the prose gap. The measured evidence is that the second site is the COMMON case and
it is not searchable.

### ⚠️ ONE TERSE COMMENT CAN COVER TWO MEANINGS — and `livespec-overseer` proved it

Its four keys shared ONE line: *"Declared-empty: these roles remain unarmed."* That single word
covered a genuine `not_applicable` pair (no dataclasses tree; not a Driver, so no neutral hook body)
**and** a genuine `convention_not_adopted` pair (`tests/` has NO `tests/overseer/` mirror tree at
all, so arming `source_tree_prefixes` would redden `tests_mirror_pairing`; no per-directory
CLAUDE.md layout for `claude_md_coverage` to walk). Inheriting the shared word would have produced
two wrong declarations. **A single reason comment spanning several keys is a smell, not a
convenience.**

### 🔺 THE RATIFIED SPEC ITSELF IS STALE — FILED as `livespec-dev-tooling-fwcwxv`

`livespec-dev-tooling/SPECIFICATION/contracts.md` §"Consumer configuration schema" **lines 243 and
245** still define declared-empty as "the sanctioned, VISIBLE opt-out" logging an `info` event, and
still names only "two sanctioned outs". Every clause is now wrong for the five union keys: it is
`LegacyAmbiguousEmpty`, it WARNs, Phase 4 makes it a hard error, and there are five spellings.

**Deliberately NOT fixed.** Spec changes go through `/livespec:propose-change` and the revise
lifecycle — a direct edit would be an out-of-band spec edit, which `doctor-out-of-band-edits`
exists to catch. Bypassing that to fix a prose bug would be worse than the bug.

The proposed change must also add what the spec currently does not say at all: the CLEAN keys keep
`[]` as a LEGITIMATE spelling, because for them empty makes the check STRICTER rather than blinder.
That distinction is the thing most likely to be lost in a rewrite.

**Sequence it BEFORE Phase 4**, which would otherwise make the spec actively contradict the
implementation. It does NOT block the remaining Phase 2 migrations.

**TRACKED as `livespec-dev-tooling-fwcwxv`** — status `blocked`, `blocked-reason:needs-human`,
depends on `8o8e.1`. That routing is deliberate: a spec propose-change is accepted or rejected by a
maintainer, so it is NOT autonomously verifiable and must not sit in the factory's `ready` lane.
The item carries the exact line numbers (188, 211/213/215/217, 221), the before-Phase-4 constraint,
the CLEAN-keys-keep-`[]` trap, and one downstream docstring
(`tests/livespec_dev_tooling/checks/test_hook_trees_not_io_exempt.py:140`) to reword AFTER
ratification.

Deliberately NOT in that item's scope:
`tests/livespec_dev_tooling/checks/test_config_driven_checks.py:150`, which is a comment
identifying the retired wording AS retired — a correct reference, not an instruction. Do not
"fix" it; doing so deletes the explanation of why the wording changed.

### ⚠️ ROLE-LEVEL LESSON — do not amend an open PR once its checks are green

Measured the hard way on #765: it merged mid-amend, its branch auto-deleted, and the amend went
**local-only**. The force-push FAILING is what surfaced it — nothing succeeding would have. A silent
local-only amend is how a durable record quietly reverts.

**Once checks are green, open a FRESH PR off the new master rather than amending.** Amending races
auto-merge, and the race is invisible when you win it.

### ⛔ (RETRACTED) `u4ij` IS CLOSED — "RATIFIED-RULE VIOLATIONS ARE ZERO" WAS TRUE OF THE OLD SCOPE ONLY

**The 31 → 0 arithmetic below is correct for the population the `__all__` proxy could see, and
that population was NOT the ratified one.** Implementing v178 (`721o`, merged) added 3
offenders the proxy never looked at, so the ratified-rule count is no longer known to be 0 —
see START-HERE 6e. The three conversions `u4ij` landed are still landed; what is retracted is
the CONCLUSION drawn from the count, not the work.

**25 + 5 + 1 + 0 = 31**, measured on master `244306b` with the shipped `_find_offenders` over the
shipped `resolve_check_universe()`, module-qualified oracle, v179 fixpoint.

| conversion | PR | how |
|---|---|---|
| `classify_role_key_declarations` | #841 | **RESTRUCTURED**, not converted — injection removed the I/O |
| `select_runner` | #846 | `Result[CliRunner, HarnessSelectionError]` |
| `test_workflow_full_round_trip` | #849 | `Result[WorkflowResult, WorkflowFailedError]` |

### ⛔⛔ TWO NUMBERS, AND ARMING DEPENDS ON THEM AGREEING — READ BEFORE ARMING

- **31** — what the check reports today. Neither ruling is IMPLEMENTED, so it still counts every
  `__all__` member and every total function.
- **0** — what the ratified rule (v178 + v179) considers a violation.

**⛔ ARMING NOW WOULD TURN dev-tooling RED ON ITS OWN GATE.** The armed check would report **31**
violations against a rule that recognizes **0**. `721o`, `5cai` and v179's two members are
exactly what closes that gap. **ARM ONLY AFTER THEM, and only when BOTH numbers agree — say so
explicitly in the arming commit.**

### ✅ ALL FOUR SIBLING DUAL-SHAPE WIRINGS ARE MERGED AND GREEN ON THE FORGE

**Conversion 3's precondition is DISCHARGED. `test_workflow_full_round_trip` is now safe to
convert.** Verified per repo from the forge — merged AND master CI `success`, not merely merged:

| repo | PR | master CI |
|---|---|---|
| `livespec-driver-claude` | #329 | ✅ success |
| `livespec-driver-codex` | #309 | ✅ success |
| `livespec-orchestrator-beads-fabro` | #1141 | ✅ success |
| `livespec-orchestrator-git-jsonl` | #450 | ✅ success |

**EACH IS DUAL-SHAPE, SO THE PIN CAN MOVE IN EITHER DIRECTION.** `_round_trip_result` accepts a
bare `WorkflowResult` (today's pin) OR a `Result` (post-conversion). The wiring is correct
before, during and after the conversion, and **a later REVERT of the dev-tooling pin cannot
re-break it either** — which a sequenced fix would not survive.

**AND EACH IS PROVEN AGAINST BOTH SHAPES, NOT ASSUMED — three tests per repo.** Wiring for a
shape nothing exercises is how the silent pass ships. The load-bearing one asserts the `Success`
unwraps **TO ITS VALUE** (`is result`, then reads `.discovered_skills`), because *asserting the
call succeeded is exactly what the silent-pass bug also satisfies.*

**⛔ WHY THE ORDER WAS NON-NEGOTIABLE, measured rather than argued:** `bool(Failure(...))` is
**True** and a `Failure` carries no `.passed`. So the pre-existing wrappers would NOT have
raised against the new shape — they would have **stopped checking**, and four sibling suites
would have gone GREEN on a broken round trip. `dx8l`'s failure mode aimed at a test gate, times
four.

### 🎯 THE GATE IS 2 — conversion 1 of 3 has LANDED (PR #841)

**25 + 5 + 1 + 2 = 33.** Re-measured on master at `70c2eb6`, not inherited.

`classify_role_key_declarations` is cleared. The two that remain are BOTH in
`livespec_dev_tooling/testing/cli_e2e.py`:

1. **`select_runner`** — local, no sibling consumers (grepped). **READ ITS ONE PRODUCT CALL
   SITE BEFORE CONVERTING:** `checks/plugin_resolution.py` gates on the harness mode
   (`if mode != _HARNESS_REAL: return 0`) BEFORE calling, so the `ValueError` is
   **UNREACHABLE from product code**. A `Result` there would have an uninhabited failure
   track at that call site — use `.unwrap()` (fail-closed, no dead branch) rather than a
   match, because this repo enforces **100% per-file coverage** and an unreachable
   failure branch cannot be covered.
2. **`test_workflow_full_round_trip`** — **FOUR SIBLING WIRINGS FIRST.** Not paperwork:
   convert first and all four consuming suites go silently green.

### 🕳️ THE FAIL-OPEN TRAP HAS THREE SPELLINGS, ALL HIT IN ONE SITTING (PR #841)

Recorded because the fan-out will meet every one of them, and NONE fails loudly. In
`required_role_keys_declared`, an empty slug set reads as *"no layout-dependent checks
wired"* → an EXCLUSION → a **PASS**. So any unwrap that degrades to `()` turns an I/O
error silently green:

1. **`value_or(())`** — the natural default. Silently green.
2. **`frozenset(result.unwrap())`** — **`IOResult.unwrap()` returns `IO[T]`, NOT `T`**, and
   `frozenset(IO(("a","b")))` **SUCCEEDS**, yielding a set holding the TUPLE. Every slug
   comparison then misses. Caught only by an existing behavioural test.
3. **`case IOSuccess(slugs)`** in a `match` — binds the inner `Result`, not the `IO`.
   Caught by `check-types`.

**`unsafe_perform_io(x.unwrap())` is the correct form.** All three wrong spellings produce
a plausible value rather than an error — the booby-trap class in a new costume: the failure
does not surface, it just **stops being checked**.

**AND THE CONVERSION MOVED THE VIOLATION BEFORE IT REMOVED IT.** Injecting the slug set
made `classify_role_key_declarations` total, and thereby made `layout_dependent_check_slugs`
PUBLIC (a new cross-module import), so the violation RELOCATED onto the function that
actually does the I/O. That is the rule working — the I/O got typed where it happens — but
**expect a conversion to change the offender SET, not just shrink it.** Re-measure after
every one.

### 🎯 (superseded) THE GATE WAS 3 — the exact arithmetic, and what each number is measured against

**26 + 4 + 1 + 3 = 34.** Measured on master with the shipped `_find_offenders` over the shipped
`resolve_check_universe()`, this repo's real config, class-B declarations applied, and a
MODULE-QUALIFIED consumption oracle.

| bucket | n | authority |
|---|---|---|
| removed — **not public API** | **26** | ratified **v178** |
| removed — **mechanically no failure mode** | **4** | ratified **v179** member 1 |
| removed — **declared legitimate absence** | **1** | ratified **v179** member 2 (`tag_version_component`) |
| **REMAINING VIOLATIONS** | **3** | — |

**TWO NUMBERS, AND CONFLATING THEM RE-CREATES THIS THREAD'S DEFECT.** **34** is what the check
reports today, because neither ruling is IMPLEMENTED yet. **3** is what the ratified rule
considers wrong. **The gate is 3.** `livespec-dev-tooling-u4ij` carries all three.

**THE 4 MECHANICAL:** `canonical_check_slugs`, `world_gate_check_slugs`, `parse_open_bump_prs`,
`denotes_same_release`. **THE 1 DECLARED:** `tag_version_component`.

**THE 3 VIOLATIONS — all ORDINARY CONVERSIONS, none an exemption candidate:**

1. **`classify_role_key_declarations` → `IOResult`.** Reaches the filesystem TRANSITIVELY via
   `layout_dependent_check_slugs`. Zero siblings; no cross-repo wiring needed.
2. **`select_runner` → convert.** Raises `ValueError` under a `mock` selector, and
   `checks/plugin_resolution.py:470` calls it with `injected_runner=None`, so the raise is
   reachable from PRODUCT code under a legitimate environment. Zero siblings.
3. **`test_workflow_full_round_trip` → convert, but ONLY AFTER FOUR SIBLING WIRINGS.**
   **⛔ THIS IS THE `dx8l` SHAPE AND WORSE.** All four consuming repos CALL it from a wrapper
   test. Convert first and each wrapper receives a `Failure`, does not raise, and **four sibling
   suites go SILENTLY GREEN while the round trip is broken.** A test that stops failing is
   fail-stale aimed at a gate.

### 🔑 v179 — THE RULE REACHES FUNCTIONS THAT *HAVE* AN EXPECTED FAILURE MODE

Ratified 2026-07-29 into `livespec` (PR #1827). Two members, **no third mechanism and no
per-function judgement at check time** — a rule needing one is a triage, and this thread has been
there.

- **MEMBER 1 — MECHANICAL, RECOMPUTED EVERY RUN.** No `raise`, no `try`, no I/O boundary call,
  **every first-party callee likewise as a FIXPOINT**, and the return is not `X | None`.
  Conservative in the DISQUALIFYING direction: an unresolved callee or any doubt demands a
  `Result`. **It stores no claim, so it CANNOT ERODE** — add a raise or an I/O call and the rule
  re-arms at that commit. **And it cannot become a dumping ground, because there is nothing to
  add to**: membership is a function of the code, not of a list.
- **MEMBER 2 — DECLARED, and it is the half that CAN decay.** An `X | None` return whose `None`
  is a legitimate ABSENCE, declared per function with a reason in `total_absence_returns`.
  Bounded four ways: a structural gate (only `X | None` can be declared at all), a required
  reason, a **HARD-FAILING staleness detector** so a declaration cannot outlive its subject, and
  a counted fleet-wide total so growth is measured rather than capped by an uncalibratable
  number. **One residual is UNGUARDED and the ratified text says so:** a declared `None` shifting
  from absence to failure while keeping its shape fires no detector.

**⛔ CLAUSE (d) IS LOAD-BEARING — an implementation that inspects only a function's own body is
WRONG.** That is not caution, it is the measured result: hand judgement called
`classify_role_key_declarations` total and the fixpoint disqualified it on a callee's
filesystem walk.

**FIDELITY *AND* A NARROWING, both in the ratified text.** Fidelity, because the railway carries
EXPECTED failures and a `Result` over a total function has an uninhabited failure track whose
dead unwraps hide the live ones. A narrowing, because "every public function" is the core
obligation of the ROP regime — and this is the **SECOND scoping in two revisions**, after v178
scoped which functions are public. Read them together.

**IT EXEMPTS NOTHING THAT RAISES.** A raise disqualifies under clause (a) whether it is
domain-meaningful, a framework's protocol, or a report of a caller's wiring mistake.

### 🔁 THE INVERTED HEURISTIC — carry this verbatim into the fan-out

**"An explicit `raise` is the strongest signal to convert" is plausible and EXACTLY BACKWARDS.**
The triage ranked the explicit-raise class as its strongest; it is its weakest. Three worked
examples, each a different way a raise is load-bearing:

- **`test_workflow_full_round_trip` — the raise reaches a FOREIGN framework.** Convert it without
  wiring the four consumers first and a FAILING round trip reads as a PASS in four sibling repos.
- **`run_workflow` — the raise IS a fail-CLOSED gate** (`CoverageGateError`). Converting a
  fail-closed raise into a `Failure` return is `dx8l`'s fail-stale inversion aimed at a gate
  instead of a marker.
- **`select_runner` — the raise reports a CALLER'S WIRING BUG.** Bugs propagate; the railway
  never carried them.

**Ask what the raise IS before converting it.** In all three, converting makes the failure
QUIETER — which is the wrong direction, and the direction this whole epic exists to reverse.

### 🛠️ TWO PROCESS TRAPS — REMEDIES, NOT WARNINGS

1. **Green amend: use `git commit --amend --no-edit`. NEVER `-F` or `-m`.** A message file
   **discards the `TDD-Red-*` trailers** the Red leg recorded. The commit-msg hook reads Red
   state from the PARENT commit, so it PASSES at amend time and the commit only fails later at
   `check-red-green-replay` on PUSH — a delayed failure whose cause is three steps back. **There
   is no repair in place; the pair must be rebuilt from master.**
2. **Invoke `.claude-plugin/scripts/bin/<command>.py`, NEVER `python -m livespec.commands.<cmd>`.**
   Those modules have **no `__main__` guard**, so `python -m` imports them and **exits 0 having
   done nothing** — no output, no file, no error. Filed as `livespec-dev-tooling-ganj`, because a
   lifecycle command that silently no-ops is this thread's signature shape occurring inside the
   spec lifecycle's own tooling, not a gotcha to memorize.

### 📊 BRIEF 25 — WHAT LANDED, WITH THE ARITHMETIC STATED EXACTLY

| item | state | effect |
|---|---|---|
| 1. `zu85` option (a) — narrow `__all__` | **MERGED** PR #832, released `v1.0.6` | **46 → 43** |
| 2. Fleet-wide public-API criterion | **RATIFIED** livespec **v178**, PR #1826 → `d230c9ff` | shrinks the unresolved set 30 → ~6 |
| 3. Class B — nine reasoned declarations | PR **#835** (re-derive merge state) | **43 → 34** |
| 4. Class C — the conversions | **EMPTY.** Every candidate read; every one a NON-conversion | **0** |
| 5. Re-measure, then arm | **NOT ARMED**, correctly — the floor is not zero | — |

**THE NUMBER THE ARMING GATE IS DEFINED AGAINST: 34 today; 8 once v178's repo-local half is
implemented; and ZERO is still not reachable**, because all 8 are public-and-total.

### 🔑 v178 — THE CRITERION. Ratified 2026-07-29 into `livespec`, and it is the load-bearing result

`livespec/SPECIFICATION/non-functional-requirements.md` §"ROP composition". A top-level function
is PUBLIC API for the Result-return rule **only when CONSUMED ACROSS A BOUNDARY**, measured
**FLEET-WIDE**, in four forms: (1) product import, in this repo across a module boundary or in any
sibling; (2) **cross-repo TEST import**; (3) process entry point (`python -m`, console script,
baked binary); (4) a live non-Python distributed surface. Clause 0 preserves the ratified
`_`-prefix rule rather than deleting it alongside its own generalization.

**WHY CLAUSE 2 EXISTS, and it is the constraint most likely to be "simplified" away.** A rule
saying "imported only by tests → not public" would have acquitted
`livespec_dev_tooling/testing/cli_e2e.py` — **the most explicitly consumer-facing surface in the
repo**, consumed from the test trees of FOUR siblings, one of which documents itself as "a
CONSUMER" in its own module docstring. The line belongs at the **REPO** boundary, not the
`tests/` boundary. A same-repo test importer is scaffolding; another repo's test suite is a
consumer whose green gates break.

**THE ANTI-GAMING HALF, and its honest measurement.** The criterion is `__all__`-INDEPENDENT in
the tightening direction: a consumed function is public **whether or not** it appears in
`__all__`, so deleting a line is not an escape. **Measured exposure of that half TODAY: ZERO** —
no top-level function is consumed-but-undeclared fleet-wide; the 11 imported-but-undeclared names
are all SUBMODULES, every one from test code. It is a guard against future gaming, not a
correction of present state, and it turned nothing red. **Do not quote it as having teeth it does
not yet have.**

**IT IS BOTH A WEAKENING AND AN EXPRESSION, and the ratified text says so.** It expresses reality
for the names it removes; it also **materially shrinks enforcement scope — 26 of 34 in this repo
alone** — which is a real reduction, not a reclassification. The `__all__`-independent clause and
the central-vantage row strengthen it back in the direction that matters.

**ENFORCEMENT IS SPLIT AND NEITHER HALF SUFFICES — this is the part to implement.** A repo-local
check **structurally CANNOT see a sibling's import**, so a fleet-wide claim enforced only locally
would assert a guarantee nothing computes. Two impl commitments are declared:
`public-api-consumed-criterion-check` (repo-local) and
`public-api-fleet-consumption-conformance-row` (**central vantage — the half that would have
caught `parse_manifest` BEFORE its conversion**).

**KNOWN BLIND SPOT, ratified rather than discovered later:** the oracle is STATIC and cannot see
`getattr` / `importlib` / string dispatch. A cross-repo dynamic reach MUST be declared.

### ⛔ CLASS C IS EMPTY — every candidate was READ, and every one is a NON-conversion

Brief 25 item 4 gated each conversion on the sibling grep. Doing the reading dissolved the track.
**This is the triage's own lesson landing for the fourth time: read every function the
classification CONVICTED.**

| candidate | verdict |
|---|---|
| `merged_branch_sweep.fetch_manifest` | **NOT PUBLIC.** Zero consumers — the two `if manifest is None` guards belong to the OTHER `fetch_manifest` (`fleet_conformance.py:187`). The name-match fooled the first measurement. |
| `cli_e2e.test_workflow_full_round_trip` | **MUST NOT CONVERT — and this is the strongest non-conversion this thread has found.** It is a pytest-collected entry point; **raising IS its protocol**. Returning a `Failure` would make a failing round-trip read as a PASS in FOUR sibling repos. That is the `dx8l` booby trap pointed at a test gate: *a test that stops failing.* |
| `cli_e2e.run_workflow` | **NOT PUBLIC**, and would be a NON-conversion anyway: it raises `CoverageGateError` as a deliberate **fail-CLOSED** gate. Converting a fail-closed raise into a `Failure` return is precisely the fail-stale-instead-of-fail-closed inversion `dx8l` taught. |
| `cli_e2e.select_runner` | **PUBLIC, but its `raise ValueError` is a consumer WIRING BUG** (mock tier with no injected runner), not an expected failure. The railway carries expected failures; bugs propagate. Left unconverted, reasoning recorded. |
| `cross_repo/fabro_image_pin_rewrite.tag_version_component` | **NOT a conversion.** Legitimate absence. Recorded three times now — do not re-litigate. |
| `ensure_plugins.subprocess_runner`, `required_role_keys_declared.layout_dependent_check_slugs` | **NOT PUBLIC** by v178. The triage's `IOResult` reading is moot for them. |

**GENERALIZE THIS, because it binds the other five repos' 223:** the "explicit `raise`" class is
the WEAKEST of the triage's convert classes, not the strongest. A raise can be a protocol
(pytest), a fail-closed gate, or a bug — and in all three, converting to `Result` makes the
failure QUIETER, which is the wrong direction. **Ask what the raise IS before converting it.**

### 🕳️ THE BOOBY-TRAP CLASS — record it where the fan-out reads it (now also in ratified v178)

`manifest is None` did not FAIL against a `Success`. Against a `Result` that test is permanently
False, so **the guard silently STOPPED BEING A GUARD**, control flowed into `manifest.owner`, and
an access-gating marker went **STALE rather than failing closed**. *Fail-stale on an access gate
is strictly worse than fail-closed.*

**GREPPING FOR THE SYMBOL FINDS THE IMPORT; IT DOES NOT FIND THE GUARD.** Every remaining
conversion of a consumed symbol has this latent: a `None`-guard, a falsy test, an `or` default.
The second one will look exactly like the first. So the precondition has TWO steps, not one:
locate consumers by the v178 criterion, **then READ each consumption site's guard.**

**AND THE DUAL-SHAPE FIX OUTRANKS THE SEQUENCED ONE.** The `dx8l` repair made the consumer
tolerate BOTH `Manifest | None` and `Result[...]`, which satisfies "consumer wiring lands before
the change that assumes it" for EVERY pin version simultaneously — so the pin can move in either
direction without re-breaking, and neither a re-land nor a future revert can re-open it. **Carry
that shape into every remaining sibling wiring.**

### ⚠️ TWO PROCESS TRAPS PAID FOR THIS SESSION — both cost a rebuild

1. **The Green amend MUST use `--no-edit`, never `-F`/`-m`.** Passing a message file to
   `git commit --amend` **discards the `TDD-Red-*` trailers the Red leg recorded**; the
   commit-msg hook then appends only `TDD-Green-*`. It reads Red state from the PARENT commit, so
   it PASSES at amend time and the commit only fails later at `check-red-green-replay` on push.
   The remedy is a full rebuild of the pair from master — there is no repair in place.
2. **`propose_change.py` / `revise.py` have NO `__main__` guard.** `python -m
   livespec.commands.propose_change` imports the module and **exits 0 having done nothing** — a
   silent no-op that looks exactly like success. Invoke
   `.claude-plugin/scripts/bin/<command>.py` instead.

### ▶️ EXACT NEXT ACTION — **`wdn7`, THEN `nkkv`, THEN REGISTER, THEN ARM.**

**`5cai`'s three slices are LANDED. The row exists, is tested at 100%, and is deliberately
UNREGISTERED.** The next action is the remediation the pre-registration measurement found, in
this order:

1. **`livespec-dev-tooling-wdn7`** — this repo's 9 undeclared `checks/*.py::main` entries.
   Declaring them is what unblocks registration, and it is what walks into the count
   collision; read the ⛔ block in START-HERE before choosing how to resolve it.
2. **`livespec-dev-tooling-nkkv`** — `livespec-runtime`'s 11, a CROSS-REPO change in that
   repo. Measure that repo's own count before and after declaring rather than projecting it.
3. **Register the row** in `OBLIGATION_ROWS` — a six-line follow-up, at `error`, once both
   are clean. Registration is the step that makes it gate.
4. **Then arm**, subject to the `995m` known-gap statement and to whatever the count
   collision resolves to.

**Nothing is mid-flight; nothing needs new authority** (briefs 30–44 authorized `q5lb`,
`vzwa`, `5cai` and the arming sequence — an item boundary is a place to REPORT, not to WAIT).
Every worktree of this thread's is reaped and no branch of its own is open. **Several FOREIGN
worktrees exist; reap NONE of them, and enumerate with `git worktree list` rather than
trusting any count in this file.**

**⚠️ AND THE ROW'S FIRST REAL RUN FOUND TWO DEFECTS IN ITS OWN ORACLE — the generalizable
result of the whole slice.** The first measurement reported 54 undeclared consumptions and
**19 were false**: 14 from one byte-identical INSTALLED file whose consumer imports its own
copy, and 5 from clause 0's `_`-prefix disqualifier. Both ran in the OVER-enforcing
direction, which is the direction that discredits a row on its first run. **Measuring before
registering cost ~9 API calls and caught both; discovering them by turning something red
would have cost a red master and the row's credibility.** Do the same for any future
central-vantage row.

**(history, kept because it is why the tarball route exists)**

**`vzwa` IS CLOSED — the count is ZERO.** The paragraphs below describing it as the next
action are HISTORY; they are kept because the not-a-type-change reasoning is why the fix
was a RESTRUCTURE-and-fail rather than a bare type change, and that reasoning generalizes.

**`vzwa` IS NOW THE ONLY THING BETWEEN THIS REPO AND ZERO.** Two functions,
`canonical_check_slugs` and `world_gate_check_slugs`, both in `canonical_checks.py`. **Read 6i
BEFORE converting: it is not a type change.** `pkgutil.iter_modules` on a MISSING directory
yields no entries rather than raising, so `canonical_check_slugs()` returns an EMPTY tuple and
every consumer reads that as "this repo has no canonical checks" — which PASSES. Typing it
`IOResult` without deciding what an empty walk MEANS relocates the sentinel instead of removing
it. The likely better answer is RESTRUCTURE (inject the slug set — the `#841` precedent), and
**`canonical_check_slugs` is consumed by `livespec` PRODUCT code at 3 sites, so a signature
change is a `dx8l`-shaped fan-out and the consumer wiring lands FIRST, dual-shape.**

**THEN `5cai` — but read `livespec-dev-tooling-k76y` FIRST.** It is THREE slices, not one: a
tarball primitive on `FleetContext` (9 API calls per run instead of ~653), the fleet consumption
oracle, then the row plus its REGISTRATION in `OBLIGATION_ROWS`. The naive `file_text`-per-file
build is ~70× more expensive than it needs to be, and a pending `livespec` proposed change
(`github-app-request-budget.md`) exists because that budget is a live constraint.

**(superseded ordering, kept so the change is legible)** This section previously read
"`q5lb`, THEN `5cai`, THEN `vzwa`". `q5lb` landed and moved the check to 2, at which point
`vzwa` — not `5cai` — became the only gate on reaching ZERO. `5cai` is still binding before
ARMING; it is no longer binding before the count is clean.

**`q5lb` — v179 member 2, the `total_absence_returns` role key.** It has exactly ONE subject
in this repo today: `cross_repo/fabro_image_pin_rewrite.py:100 tag_version_component`, whose
`None` means "this tag HAS no version component" — a legitimate ABSENCE, re-established three
separate times in this file (§"METHOD CONSTRAINT FOR THE FAN-OUT"). Landing it takes the
check from 3 to 2, at which point **the two numbers AGREE at 2**.

- **MODEL IT ON `cross_repo_public_api` (SPECIFICATION v036), do not invent a second shape.**
  Same bounds: per-function, reason REQUIRED and PARSED rather than commented,
  staleness-detected with a HARD failure, and deliberately NOT in `REQUIRED_ROLE_KEYS` — a
  required key hard-errors eight sibling masters on their next pin bump to demand a
  declaration most have no content for. Reuse that loader and check shape.
- **The four bounds are part of the RULE, not implementation detail** (ratified text at
  `livespec/SPECIFICATION/non-functional-requirements.md` lines 708–719): a STRUCTURAL gate so
  only an `X | None` annotation can be declared at all; a written reason; a hard-failing
  staleness detector; and a fleet-wide COUNT reported by a central-vantage row — which is
  `5cai`'s surface, so the two items meet there.
- **The staleness detector earns its keep immediately** — it rejected two of six first-draft
  `cross_repo_public_api` entries, both authored from a CONSUMER's import statement without
  reading the DEFINITION.
- **`_returns_x_or_none` in `checks/_no_expected_failure_mode.py` already implements the
  structural gate** (clause (e)) and handles both `X | None` and `Optional[X]`. Reuse it rather
  than writing a third annotation reader.

**THEN `5cai`** — still binding before arming (brief 30). It is what makes `721o`'s
declaration VERIFIED rather than merely written. **THEN `vzwa`** — the two genuine violations,
see 6i, and read that block before converting anything: it is not a type change.

**THEN re-measure, confirm both numbers agree, and ARM — stating both numbers in the arming
commit.** If they disagree, the SIMULATION was wrong and that discrepancy is worth more than
the arming. **Then re-measure ONE sibling** to replace the retired 223/282 figures —
remembering those are now unknown in BOTH directions (6e) — report it, and **STOP**.

**Standing constraints for all of it:**

- **The check still scans ZERO files here** (`pure_trees`-scoped), so nothing new is exercised
  by `just check`. **Test on fixtures.** A green aggregate is not evidence any of it works.
- **`fleet/_rows_pin_currency.py` is at 246 LLOC and `fleet/fleet_conformance.py` at ~246,
  both against a 250 HARD ceiling.** A casual addition to either now reds the repo.
- **`git diff master HEAD` is NOT how you save a branch's work.** If master moved while you
  worked, that patch silently includes a REVERSAL of every commit master gained — here it
  would have reverted a release, a pin bump and an unrelated fleet feature. **Diff against the
  FORK POINT**, and read `git status` after applying a saved patch: the extra paths are the
  tell.
- **A Red-recorded test file is byte-identity-bound.** If it must change, the pair is REBUILT
  from master; there is no amend path. Put additional Green-leg tests in a `*_edges.py`
  sibling, which is this repo's existing idiom.
- **CI runs as ROOT.** A test that relies on POSIX permission enforcement (`chmod(0o000)`)
  passes locally and fails there. Prefer a uid-independent producer (a DIRECTORY where a file
  is expected raises `IsADirectoryError`). **Never reach for `skipif`** — a skipped negative
  test is worse than an absent one, because it reports as handled in the only environment that
  gates merges.
- **RED MODE REQUIRES EXACTLY ONE STAGED TEST FILE.** `just check-pre-commit` gates the Red
  scope on `test_count -eq 1 && impl_count -eq 0`. Stage TWO test files and it falls through to
  the FULL aggregate, where the Red leg's stubbed impl fails `check-per-file-coverage` and
  `check-lint` — a confusing failure that looks like a defect in the change. **A multi-module
  slice is several Red→Green PAIRS**, and two pairs in one PR is fine.
- **A FRESH WORKTREE NEEDS `just install-worktree-pack`.** Without it
  `check-primary-checkout-commit-refuse-hook-installed` fails `worktree_pack_absent`. Doc-only
  commits never reach that gate, so the failure first appears on the first commit that stages a
  `.py` — often several commits into a session, far from its cause.
- **MIRROR `_scan`, NEVER APPROXIMATE IT, when re-measuring.** This pass's own re-measure script
  applied v179 member 1 ALONE and reported **3** where the shipped check reports **2**. A
  measurement that UNDER-applies a ratified exemption reads as "the repo is dirtier than it is",
  and it would have restored the exact number the same pass had just retracted. Import the
  analyses the check imports and combine them the way `_scan` does.
- **🔴 PROSE-TWIN INSTANCE 11 — AND IT WAS IN A LEDGER ITEM WRITTEN TO CORRECT A DEFECT.**
  `livespec-dev-tooling-mmqe` was retitled, re-prioritised P0→P1 and re-scoped after its cause
  was retracted — and its DESCRIPTION's first paragraph still asserted all three retracted
  claims ("FAILING ON MASTER", "blocks EVERY pull request", "cannot be fixed from a PR"). A
  reader opening the item got the wrong cause in the first sentence. **The tally now reads:
  the ratified spec, four config headers, a diagnostic, a docstring, and the correction pass
  itself.** The generalisation is the uncomfortable one: **an amendment that changes behavior
  and leaves an authoritative statement of the old behavior standing is not a class of bug
  this thread finds in other people's work — it is one this thread keeps committing.** When you
  retract a cause, grep the artifact's OWN body and title for the retracted claim before
  moving on; a status field, a title and a description are three surfaces, and fixing one is
  the default failure.
- **🔴 A VALID PROBE IS NOT A TERMINATING LOOP. GIVE EVERY WAIT AN ITERATION CEILING THAT
  REPORTS.** This thread has now burned ~37 minutes twice on an `until`-loop that could
  never exit. The FIRST time the probe was invalid (`gh pr checks --json` was not a
  flag), and the recorded remedy was "verify the probe once before wrapping it". **That
  was necessary and NOT SUFFICIENT.** The second time BOTH probes were perfectly valid —
  `gh pr view --json state` and `gh pr checks` — and the loop still could not terminate,
  because the exit conditions did not COVER THE ACTUAL STATE: the PR was
  `mergeStateStatus=DIRTY` (a merge CONFLICT, so `state` can never become `MERGED`) and
  had **zero checks**, so a `grep fail` over check output could never match either. Two
  reachable-looking conditions, neither reachable. **The remedy is structural, not
  sharper predicates: bound the iterations and REPORT the state you actually observed
  when the bound is hit.** A loop that says "still DIRTY with 0 checks after 10 tries"
  finds the bug in one minute; a loop waiting for MERGED finds it never.
- **AND THE STATE THAT LOOP WAS HIDING IS ITS OWN LESSON: "no checks reported" IS NOT
  "pending".** A branch with ZERO runs and a conflict is the shape of a push that did not
  land the way you think it did. **Verify a push CREATED a run** (`gh run list --branch
  <b>`) rather than inferring the branch is merely early — and treat `DIRTY` as a
  first-class outcome to check for, not something to discover after a timeout.
- **🔴 PROSE-TWIN INSTANCES 11 AND 12 — and the pair is worse than either alone.**
  **11:** `livespec-dev-tooling-mmqe` was retitled, re-prioritised P0→P1 and re-scoped
  after its cause was retracted, and its DESCRIPTION's first paragraph still asserted all
  three retracted claims; then the TITLE written to fix it still carried the refuted
  mechanism. **Three surfaces — status, title, description — fixed one at a time,
  twice.** **12:** `.github/workflows/ci.yml`'s comment on
  `LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST` read *"Harmless for the other metadata legs —
  they do not read this var."* True when written, FALSE by the time it mattered, and
  nobody edited it. **So 11 is in a ledger item written to correct this very defect, and
  12 is in the config comment that asserted the failure mode was IMPOSSIBLE.** The tally:
  the ratified spec, four config headers, a diagnostic, a docstring, the correction pass
  itself, and an impossibility claim. **When you retract a cause, grep the artifact's own
  title AND body for the retracted claim; when you arm a severity flag, grep for comments
  asserting it is harmless.**
- **⚠️ AN AMBIENT ENV VAR MAKES A TEST'S EXPECTED EXIT CODE A PROPERTY OF THE HOST.**
  Measured: `test_ci_matrix_completeness.py`'s `_run_check` treated `env=None` as
  `run_env=None` — INHERIT the whole ambient environment — and `ci.yml` sets
  `LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST: "true"` for every `matrix.target` in the
  metadata job group, which flips that check from warn (exit 0) to FAIL (exit 4). **17
  tests asserting `returncode == 0` failed in CI and passed locally.** Reproduced exactly
  before fixing (`17 failed, 10 passed` with the var set; **27 pass** with the fix).
  **LATENT, NOT NEW:** the var had been set for that whole job group for some time; what
  changed is which legs RUN that file, and a leg that SPAWNS the check reads the var
  transitively. **The discriminator that proved the code under test was innocent:
  `check-coverage` and `check-per-file-coverage` PASSED on the same commit** — a
  fail-open-fixture explanation would have failed there too. Clear severity-arming vars
  from spawned subprocesses; keep only what the interpreter needs.
- **🔴 TWO GATES IN MUTUAL CONTRADICTION IS A CLASS, NOT A BUG — and this repo had one.**
  Red-Green-Replay makes a Red-recorded test file BYTE-IDENTITY-BOUND and its stated
  remedy is to put extra Green-leg tests in a `*_edges.py` sibling.
  `check_coverage_incremental` then measured each changed impl against ONLY
  `test_<name>.py`. **So following the first rule GUARANTEED failing the second** whenever
  the sibling carried a branch, and the author's only escape was to break byte-identity.
  It was already latent and invisible: `checks/required_role_keys_declared.py` has NINE
  lines covered solely by its `_edges.py` sibling, unnoticed until an unrelated one-line
  change dragged that file into the gate's scope. Fixed in PR #908 by selecting
  `test_<name>_*.py` siblings — an ANCHORED match, so `test_widget` does not drag in
  `test_widgetry.py`, with the base pairing still REQUIRED so a sibling cannot substitute
  for it. **Widening a test SELECTION can only make a coverage gate stricter**, which is
  what made it safe to change a check nine repos run. **When two of this repo's own rules
  meet, check whether satisfying one forecloses the other.**
- **⚠️ `git add -A` PICKS UP `uv.lock`, AND THAT REVERTS THE RELEASE MASTER GAINED.** A
  commit built in a worktree based on `1.8.3` carried `uv.lock`'s version back down from
  `1.8.4` — invisible in the change's own diff, surfacing as a REBASE CONFLICT in a file
  the change never meant to touch. Same family as "diff against the FORK POINT", one
  spelling over: here the reversal arrives through a generated lockfile rather than a
  stale diff base. **Read `git diff --cached --name-only <base>` before committing and
  drop anything you did not intend**; `.livespec.jsonc` arrives the same way from
  `just install-worktree-pack`.
- **NEVER HAND-SIMULATE A FIXPOINT — RUN IT.** Clause (d) reaches transitively, so every clause
  a body-only reading CAN check may pass while the only clause that fails is the one it cannot.
  Measured twice: 1-of-6 wrong at `classify_role_key_declarations`, then **2-of-4 wrong** on the
  member-1 exemptions this file itself recorded — both times erring toward EXEMPTION, the
  relaxing direction. The remedy is mechanical and cheap: import
  `functions_without_expected_failure_mode` and `repo_local_public_names`, feed them
  `resolve_check_universe()`, and read the answer. **Quote no clause-(d) figure you did not
  compute** — that is what makes a sibling's count honest when the fan-out reaches it.
- **WIRE-UP IS ITSELF A TESTABLE CLAIM.** `rvw3` shipped a separate test file asserting the
  CHECK CONSULTS the analysis, because a correct analysis nothing calls is this epic's own
  subject arriving one level up, in the wiring rather than in the rule. Every remaining piece
  here adds an analysis to a check; pin the consultation each time, BEFORE the failure can
  occur rather than after discovering it.

### ▶️ (superseded) EXACT NEXT ACTION — TRIAGE THE 3, THEN v179, THEN `5cai`

**✅ `721o` IS CLOSED — merged in four slices, all green on master:** SPECIFICATION **v036**
(the `cross_repo_public_api` role key, PR #854 → `02c2b005`), the loader (PR #855 →
`c11e8b08`), `checks/_public_api_consumption.py` (PR #858 → `a141df98`), and the criterion
wired into the check (PR #861 → `0788e93c`). The check reports **9** and still scans zero
files here, because it is still `pure_trees`-scoped.

**THE ORDER:**

1. **✅ THE 3 ARE TRIAGED — `9sl0` (filed). Now IMPLEMENT them.** See START-HERE 6g for each
   verdict and its reason. Order within the item: `holds_app_class_credential` (RESTRUCTURE,
   smallest, no consumer risk) → `fetch_manifest` (CONVERT, dual-shape wiring FIRST at both
   in-repo call sites) → `discover` (CONVERT, read `_rows_pin_currency.py` first).
   **Re-measure after EACH, never only at the end** — a conversion changes the offender SET,
   not just its size.
2. **v179's two members — FILED: `rvw3` (member 1, mechanical) and `q5lb` (member 2, the
   `total_absence_returns` key).** **Clause (d), the callee FIXPOINT, is not optional**:
   without it the check exempts functions that reach I/O one call away, which is the exact
   defect a hand reading of `classify_role_key_declarations` produced. Member 2's key is the
   same shape as `cross_repo_public_api` (v036) — per-function, reason-required,
   staleness-detected, NOT in `REQUIRED_ROLE_KEYS` — so reuse that loader and check shape.
   **`rvw3` carries the clause-(c) false positive as a first-class caveat**; do not implement
   clause (c) as if it were the rule itself.
2b. **`0yfo` — decompose `config.py`, then flip the `995m` predicate.** Not on the arming
   critical path by itself, but 995m IS (START-HERE 6f): either it lands, or the arming commit
   states in its own text that arming does not cover `config.py`.
3. **`5cai` — the CENTRAL half. ⛔ NOT OPTIONAL, AND IT MUST LAND BEFORE ARMING.** A
   central-vantage conformance row over the fleet's real consumption graph. This is the half
   that catches the next `parse_manifest` — see the ⛔ block below, a BINDING ruling.
   **It now has a concrete first job**: three measured cross-repo consumptions are
   deliberately UNDECLARED in this repo's `pyproject.toml` (see §"THE THREE UNDECLARED
   CONSUMPTIONS"), and a central row must either surface them or explain why not.
4. **Then re-measure, confirm BOTH numbers agree, and ARM.**
5. **Then re-measure ONE sibling** to replace the retired 223/282 figures, report it, and
   **STOP — do not start the fan-out.**

### 🕳️ THE THREE UNDECLARED CONSUMPTIONS — a hole in the check that is WIDER than the rule

Measured while authoring this repo's own `cross_repo_public_api` declaration. All three are
REAL — a sibling genuinely imports the name — and all three are deliberately NOT declared,
because declaring them would assert a scope the check does not apply:

| symbol | consumer | why it cannot be declared |
|---|---|---|
| `fleet/_context.py:resolve_owner` | beads-fabro's `codex_yolo_gate.py` HOOK | public NAME in a package-PRIVATE module |
| `testing/_cli_e2e_discovery.py:discover_fixtures` | four siblings, via a `cli_e2e` re-export | same |
| `config.py:iter_first_party_py_files` | git-jsonl's test tree | the FILE is not in the universe at all (`995m`) |

**THE FIRST TWO ARE ONE DEFECT.** `public_api_result_typed` skips `_`-prefixed FILES
wholesale, while v178 clause 0 disqualifies only a `_`-prefixed NAME. The file-level skip is
therefore WIDER than the ratified rule, and two cross-repo consumers are reaching straight
through it — one of them a HOOK, which is the `dx8l` blast-radius shape exactly.

### 🧭 TWO ORACLE DEFECTS THE FIXTURES CAUGHT — both in the RELAXING direction

Recorded because the fan-out will write this oracle's equivalent eight more times, and both
defects produce a SMALLER count, which reads as progress:

1. **A REPO-ROOT-RELATIVE PATH IS NOT AN IMPORT PATH.** `livespec-dev-tooling`'s package root
   IS its repo root, so the naive reading happens to work here — but a LAYERED consumer roots
   its package deeper (`.claude-plugin/scripts/livespec/parse/foo.py` is imported as
   `livespec.parse.foo`), and the naive reading resolves NOTHING there. The shipped oracle
   resolves module identity by dotted SUFFIX; on ambiguity every candidate counts, so doubt
   resolves toward MORE enforcement. **A check that silently resolves nothing is this epic's
   own failure mode, relocated into the oracle.**
2. **`config.pure_trees` ON A LOCAL `Config` INSTANCE RESOLVED TO THE `config` MODULE**,
   manufacturing 19 phantom consumptions. An attribute base must resolve through an actual
   `import` binding, never by matching a dotted expression against a module path. **That is
   this thread's own "read the callee, do not match the name" lesson recurring inside the
   oracle written to apply it — the third time it has recurred inside its own fix.**

**AND THE STALENESS DETECTOR EARNED ITS KEEP IMMEDIATELY**: it rejected two of the six
first-draft `cross_repo_public_api` entries — one naming a function that lives in a different
module than the consumer's import path suggests, one naming a file outside the universe.
Both were authored from the CONSUMER's import statement without reading the DEFINITION.

### ⛔⛔ `5cai` IS NOT OPTIONAL — ARMING WITHOUT IT REINTRODUCES THIS EPIC'S DEFECT VIA ITS OWN FIX

**BINDING supervisor ruling, brief 30. The arming gate is `721o` AND v179's TWO members AND
`5cai`. Not three of four.**

**WHY THE SPLIT EXISTS AT ALL.** A repo-local check structurally CANNOT see a sibling's import,
so `721o` necessarily has the repo **DECLARE** its cross-repo-consumed surface. That declaration
is also what answers the gameability objection to v178 — *"nobody imports it, therefore it is
not public"* is gameable by simply not importing something. **The declare-then-centrally-verify
split closes it: the repo declares, and a CENTRAL vantage checks the declaration against the
fleet's ACTUAL consumption graph.** Neither half is sound alone.

**SO SHIPPING `721o` WITHOUT `5cai` BUILDS A DECLARATION NOBODY VERIFIES — this epic's exact
defect, reintroduced by its own fix, at the very end.** Concretely: **a repo could declare an
EMPTY consumed-surface and every one of its public functions would fall out of scope, silently,
with the check GREEN. That is `pure_trees = []` wearing a new name** — the same shape this whole
epic exists to remove, one level up in the schema.

**IF `5cai` TURNS OUT LARGER THAN EXPECTED, ARMING WAITS.** Do NOT arm with an unverified
declaration and file `5cai` as a follow-up. The ruling is explicit: *"I would rather this epic
stay open than close with that shape in it."*

**⚠️ EVERY UNWRAP NEEDS A TEST THAT ASSERTS THE VALUE REACHES THE CALLER**, not merely that the
call succeeded — a passing row is what the bug produces. Treat "I am being careful here" as ZERO
evidence: the author of the fail-open warning committed that exact bug one commit leg later, and
what caught it was a behavioural test, not attention.

**⚠️ AND WHEN YOU ARM, EXPECT A SURPRISE AND TREAT IT AS A FINDING.** That is the first time this
check has ever looked at this repo's 145 files. **If the armed count disagrees with the
simulation in this file, the SIMULATION was wrong** — and that discrepancy is worth more than
the arming. Do not smooth it.

**⚠️ AND THE CHECK STILL SCANS ZERO FILES HERE** (`pure_trees`-scoped), so new code paths inside
it are NOT exercised by this repo's own `just check`. **Test them on fixtures**; a green
`just check` is not evidence any of it works.

### 🧭 A THIRD DISPOSITION — RESTRUCTURE, beside convert and exempt

**The railway is not the only correct answer to an offender. Sometimes the offender is a
function that should never have touched I/O.** Conversion 1 is the worked example: wrapping
`classify_role_key_declarations` in `IOResult` would have TYPED its I/O; injecting the slug set
REMOVED it, leaving the function genuinely total rather than merely honestly typed — and
deleting the test's `monkeypatch.setattr` of a module attribute, which was the smell announcing
the problem.

**Carry all three dispositions into the fan-out:**

1. **CONVERT** — the function has a real failure mode; put it on the railway.
2. **RESTRUCTURE** — the function shouldn't reach I/O at all; push the I/O to a caller that is
   already a boundary, and the function becomes total under v179 member 1 with no `Result`.
3. **EXEMPT** — v179's two members, or a ratified supervisor declaration.

**Prefer (2) when the I/O is incidental to what the function computes**, and check afterwards
whether the violation MOVED rather than vanished (it did here — see below).

### 🔁 A CONVERSION CHANGES THE OFFENDER SET, NOT JUST ITS SIZE — re-measure after EACH

**Hard rule, not hygiene.** Injecting the slug set made the classifier total AND made
`layout_dependent_check_slugs` public via a new cross-module import, so the violation
**RELOCATED** onto the function that actually does the I/O. The count was unchanged at 3 until
the second Red→Green pair typed the walker.

**Consequence for the fan-out: it CANNOT be planned as N independent conversions against a
fixed list.** A count taken before a conversion is not a count of the same thing afterwards.
Re-measure between conversions, never only at the end.

### 🧨 THIS CLASS IS CAUGHT BY MECHANISM, NEVER BY ATTENTION

**Put this in the fan-out constraint verbatim, because the evidence is embarrassing and
therefore worth trusting: the author of the warning committed the bug one leg after writing
it.** While landing conversion 1 I wrote a code comment warning about the fail-open unwrap, and
then committed spelling #2 of that exact trap in the next commit leg — **while actively thinking
about the hazard.**

What caught it was **a behavioural test and `check-types`**. Not vigilance. Not review. Not the
comment.

The reason is structural: every spelling produces a **plausible value rather than an error** —
`value_or(())` yields an empty set, `frozenset(IOResult.unwrap())` yields a set holding the
WRAPPER, `case IOSuccess(x)` binds the inner `Result`. None raises. **A warning you authored
does not protect you**, and the person most likely to write this bug is the one who just
documented it. Guard it with a test that asserts on the VALUE, or it is unguarded.

### ✅ THE GATES WORKED, AND THAT IS WORTH STATING PLAINLY

`check-assert-never-exhaustiveness` and `check-per-file-coverage` each caught a real defect
before push — the latter on an untested fail-closed branch — and **nothing was bypassed, no
`--no-verify`, no weakening.** This thread has spent most of its life on gates that did not
work; a gate catching a genuine defect is the system operating as designed and deserves the same
attention as a failure.

**BOTH RULINGS ARE NOW RATIFIED — v178 AND v179. No spec work remains before arming.** What is
left is implementation and two conversions:

1. **Implement v178's repo-local half** — `721o`. The consumption oracle MUST resolve imports to
   the DEFINING MODULE (see START-HERE 7a). **A repo-local check CANNOT see a sibling's import**,
   so this half needs the repo to declare its cross-repo-consumed surface, with `5cai` verifying
   the declaration against reality.
2. **Implement v179's two members** — `no-expected-failure-mode-mechanical-member` and
   `no-expected-failure-mode-declared-absence-key`. **Clause (d), the callee fixpoint, is not
   optional** — without it the check exempts functions that reach I/O one call away.
3. **Implement the CENTRAL half** — `5cai`. The half that catches the next `parse_manifest`.
### 🧪 A RED-LEG CONSTRAINT THIS REPO IMPOSES — it shapes how a Red test may be written

**100% per-file coverage applies to TEST files too, and at the Red moment every line AFTER the
first failing assertion is unexecuted and therefore UNCOVERED.** A Red leg must leave no line
behind. Three consequences, each paid for this pass:

1. **A Red test's failing assertion must be its LAST statement.** Combine conditions with `and`
   rather than stacking asserts.
2. **When the pre-conversion code RAISES, put the call INSIDE the assert** — the statement then
   still executes, so the line is covered even though the test fails.
3. **A multi-assertion existing test cannot be converted in the Red leg.** Put the Red in a
   SEPARATE new file (so the existing file still passes at Red) and move its call sites in the
   GREEN leg. `test_cli_e2e.py` has eight assertions on the returned result; converting it at
   Red would have left its whole body uncovered.

A second file may also join the GREEN leg for the same reason — `test_plugin_resolution.py` and
`test_rows_required_role_keys.py` both did. The byte-identity rule binds the RED-recorded test
file only.

4. **The 2 remaining conversions** — `u4ij`. **✅ CLOSED — all three landed.** Both were in
   `livespec_dev_tooling/testing/cli_e2e.py`.
   **Conversion 3's four-sibling precondition is DISCHARGED** (see the ✅ block above), so both
   are now unblocked. **Re-measure after EACH, not after both.**
   - **`select_runner`** — 1 product caller (`checks/plugin_resolution.py:470`, which GATES on
     `mode != _HARNESS_REAL` and returns 0 first, so the `ValueError` is UNREACHABLE there →
     use `.unwrap()`, not a match: 100% per-file coverage makes an unreachable failure branch
     uncoverable, and manufacturing a test for it would be the ceremony this thread refuses),
     1 internal caller (`cli_e2e.py:382`), 4 direct tests, plus `test_plugin_resolution.py`'s
     `_runner_factory` monkeypatch which must return the new shape. **Dependent test updates go
     in the RED leg** — the byte-identity rule forbids touching the test file between legs.
   - **`test_workflow_full_round_trip`** — all four consumers now tolerate both shapes.
5. **Then re-measure and arm ONLY when the ratified rule considers the remaining set correct.**
   **That is no longer "zero offenders"** — v178 and v179 both narrow what counts. State which
   number you mean. **DO NOT ARM BEFORE.**

**⚠️ AND THE IMPLEMENTATIONS CARRY A MANUFACTURED-GREEN RISK OF EXACTLY THIS THREAD'S KIND.**
`check-public-api-result-typed` is still `pure_trees`-scoped and scans ZERO files here, so new
code paths in it are NOT exercised by this repo's own `just check`. **Test them directly on
fixtures**, and do not read a green `just check` as evidence any of it works. The requirement
is not "tests exist" — it is that the new paths RUN, in a way that would go red if they were
wrong.

### ⛔ THE FAN-OUT NUMBER IS UNKNOWN, NOT LARGE — do not quote 223 or 282

**Both figures predate v178 and v179 entirely.** They were measured when "public API" meant
`__all__` membership and when the rule reached every public function regardless of whether it
had a failure mode. Both rulings narrow the count, and neither has been applied to any
sibling's universe. In THIS repo the same two rulings took 34 down to 2 — a ~94% reduction —
but that ratio is this repo's, not a fleet constant.

**And arming publishes the change to the other eight on their next pin bump**, measured
against THEIR universes, which nobody has re-measured since the criterion changed what public
means. **Re-measure per repo before quoting any fan-out figure**, and say "unknown" until then
rather than carrying a number whose basis was retired.

### 🔎 WHAT ARMING WILL ACTUALLY DO — treat every surprise as a finding

Arming runs `check-public-api-result-typed` over this repo's **145-file** universe for the
FIRST TIME in this epic's history. It has never looked at this repo. **Anything unexpected
there is a finding about the check or the repo, not something to smooth away** — the entire
subject of this thread is a check that reported success while scanning nothing, so the first
real scan is exactly where a suppressed surprise would be most expensive.

### 🗄️ (superseded through item 4) THE OLD NEXT ACTION

### ▶️▶️ START HERE — `zu85` OPTION (a). RULED, JUSTIFIED, AND THE FIRST EDIT IS WRITTEN OUT.

**Supervisor ruling (brief 24): option (a) APPROVED.** Per-name fleet-wide justification is
COMPLETE and lives on the `zu85` item. **No further measurement is owed — start editing.**

**Measured by tarball across ALL EIGHT siblings (not the search API, which rate-limited
mid-sweep and must never be read as an empty result): `otel_step_timer` module references
fleet-wide = 0.** No sibling imports the module or invokes it via `python -m`.

**THE EDIT.** In `livespec_dev_tooling/otel_step_timer.py`, narrow `__all__` from seven entries
to three:

```python
__all__: list[str] = ["DATASET", "DEFAULT_ENDPOINT", "main"]
```

Removing `parse_argv`, `build_trace_payload`, `run` and `post_span` — each 0 fleet references,
each an internal helper of a baked CLI, exported only so unit tests could reach them. That is
the SAME premise `#809` was ratified on (`check_mutation.py`'s `__all__` holds only `_`-prefixed
helpers). `check-all-declared` does NOT force exhaustiveness, so narrowing is compliant.
**`main` STAYS** — 15 fleet references invoke the baked binary `livespec-step-timer`, and they
reference the BINARY name, not a Python symbol, so they constrain `main` alone.

**Measured against the shipped `_find_offenders`: this takes the file 4 → 1.**

**⚠️ AND SPLIT IT THERE — DO NOT ALSO DECLARE THE FILE IN `supervisor_entry_files` IN THE SAME
CHANGE.** The probe's last step (1 → 0) needs that declaration, which grants FOUR exemptions —
and checking them individually, `no_except_outside_io` is **NOT warranted** here: the module uses
`contextlib.suppress`, not a broad `main()` `try`. Bundling it would smuggle in an exemption the
file does not need, which is the bulk-declaration hazard the ⛔ block forbids. **Let the residual
`main` join class B's 8 declarations**, where the four-exemption judgement is made per file.

Doc-only note: `zu85` is `blocked` in the ledger pending this execution; close it after (a) lands
and the class-B entry for this file lands.

### ▶️ THEN — Track B, and note the conversion set is nearly EXHAUSTED

Slice 3 (`filter_siblings`) landed as `bcbe035` (PR #826). **Only 4 offenders still have
a real failure track**, so Track B has roughly two slices left, not ten:

- `fleet/merged_branch_sweep.fetch_manifest -> Manifest | None` — now the strongest candidate,
  and its `None` genuinely carries TWO meanings (fetch failed vs. fetched-but-unparseable), a
  distinction slice 2 already exposed at its call site.
- `testing/cli_e2e.select_runner` and `cli_e2e.test_workflow_full_round_trip` — explicit
  `raise`.
- `cross_repo/fabro_image_pin_rewrite.tag_version_component` — **NOT a conversion.** Recorded
  twice already as a legitimate absence. Do not re-litigate it; read §"METHOD CONSTRAINT".

Plus the ~3 the triage read as real I/O wanting `IOResult` (`ensure_plugins.subprocess_runner`,
`cli_e2e.run_workflow`, `required_role_keys_declared.layout_dependent_check_slugs`).

**After those, conversion is DONE at ~39 offenders and the remaining work is not conversion at
all.** One slice per PR, each its own Red→Green pair, never batched.

**⛔ BEFORE CONVERTING ANY OF THEM: GREP ALL EIGHT SIBLINGS FOR THE SYMBOL.** This is not
advice, it is the precondition `dx8l` paid for — see §"THE THIRD AXIS". `fetch_manifest` and
`run_workflow` are exactly the shape that broke beads-fabro (`testing.cli_e2e` IS imported by
`livespec-driver-claude`, `-driver-codex` and `-orchestrator-git-jsonl`). **If a sibling imports
it, wire that sibling FIRST, tolerant of both shapes, and land the conversion only after.**

### 📋 THE WHOLE REMAINING QUEUE, IN ORDER (supervisor brief 23, scope items 1–5)

1. **`zu85` option (a)** — the `__all__` narrowing above. Ruled, justified, ready. 46 → 43.
2. **The FLEET-WIDE public-API criterion** — a propose-change defining what makes a function
   public API, then implement it in the check under Red→Green-Replay. Constraints from brief 23,
   as CORRECTED by brief 24: mechanically decidable; **not trivially gameable** (say plainly how
   it resists "just don't import it", or record the exposure); a name imported only by TESTS is
   NOT public API (say so, so nobody "fixes" it later); it must not let a genuinely
   consumer-facing surface escape; and it **MUST be FLEET-WIDE, not repo-local** — a repo-local
   oracle would have called `parse_manifest` non-public, the exact function that broke a sibling.
   State whether it weakens the rule or makes an existing reality expressible.
3. **Class B — 8 `main() -> int` supervisors**, a reasoned `supervisor_entry_files` entry EACH,
   never bulk. Includes `otel_step_timer`'s residual `main` from (a).
4. **Class C — the ~4–7 real conversions**, each gated on the sibling grep above.
5. **Re-measure, and ONLY at measured zero, arm.** Then fan out.

**THE HIGHEST-VALUE ITEM IS #2, NOT #1 OR #4.** It is establishing how much of the D class
(30 genuinely-total functions) is not public API — see §"THE `__all__` FINDING". That is the
critical path to arming; the remaining conversions are not.

**DO NOT start with `otel_step_timer.parse_argv`**, which every prior revision of this file
named as the START-HERE target. It is UNCONVERTIBLE — see `zu85` and START-HERE step 7.

**The Red→Green shape that cost two discarded attempts on slice 1, so it is written down:** when
the existing tests assert the OLD signature and live in the SAME file as the new tests, the
dependent updates MUST be in the **Red**, not the Green amend — the Red→Green byte-identity rule
forbids touching the test file between the two legs. Author the whole final test file, commit it
as Red with the impl untouched, then amend with the impl.

**AND THE STUB TECHNIQUE THAT MADE SLICE 2'S RED HONEST, which the two rules above do not
cover.** When the new test imports a symbol the conversion INTRODUCES (`ManifestParseError`), a
Red with the impl untouched dies on a COLLECTION error, which the hook accepts but which proves
only that the module is unimportable. Put a minimal STUB of the new symbol on disk at Red —
the dataclass and its `__all__` entry, with the converted function still returning the old type
— so the test imports cleanly and fails on ASSERTIONS. Slice 2's Red was 8 assertion failures
(`assert isinstance(None, Failure)`), zero collection errors. Then the Green amend replaces the
stub with the real implementation. **Assert with `isinstance(outcome, Success)` rather than
`is_successful(outcome)`**: `isinstance` never raises, so at Red it produces a clean assertion
failure instead of an `AttributeError` on the un-wrapped return.

**Also written down because it cost a duplicate file:** the two spec CLIs disagree on path
convention. `propose_change.py`'s `target_spec_files` REQUIRE the `SPECIFICATION/` prefix;
`revise.py`'s `resulting_files[].path` REJECT it (paths must be relative to `<spec-target>/`).

**Then, in any order** (neither blocks the other):

- **The nine undeclared supervisors** — per-file judgement, NOT a bulk declaration. See the ⛔
  block: declaring a file grants FOUR exemptions, not one. **v035 now states that fact in the
  ratified spec** rather than only in this repo's `pyproject.toml` comment.
- **The `zu85` exemption** — the spec decision that lets the four `otel_step_timer` offenders
  reach zero. Nothing else can close them.

**Then re-measure, and ONLY at measured zero, arm.** Then fan out to the other five repos' 223 —
not before. **Zero is not reachable until `zu85` is answered.**

### ✅ TRACK C IS DONE — ratified as **v035** on master, and it grew from one bullet to a CLASS

**MERGED: PR #824 → `703c5a6`.** `SPECIFICATION/history/v035/` is on master and
`proposed_changes/` is drained. Track C is closed.

Filed and accepted 2026-07-29 under the delegated accept/reject authority. The recorded scope was
one bullet — `contracts.md`'s `supervisor_entry_files` entry naming 1 consumer of 4. **Re-reading the whole section turned it into four wrong keys, wrong in BOTH
directions**, every correction measured by enumerating the modules under
`livespec_dev_tooling/checks/` that read `config.<key>`.

| key | was | now |
|---|---|---|
| `supervisor_entry_files` | 1 | **4** — adds `no_write_direct`, `public_api_result_typed`, `supervisor_discipline` |
| `commands_trees` | 2 | **3** — adds `public_api_result_typed` |
| `io_trees` | 4, **two of them FALSE** | **3** — drops `public_api_result_typed` + `no_write_direct`, adds `hook_trees_not_io_exempt` |
| `source_trees` | 13 named, **5 of them FALSE** | 8 AST-shape + `red_green_replay`, `rop_pipeline_shape`, `supervisor_discipline` |

**THE OVER-REPORT IS THE MORE DANGEROUS HALF, and it is a new sub-shape of this thread's
pattern.** An under-report understates a declaration's blast radius. An over-report documents an
exemption that **does not exist** — a repo declaring `io_trees` expecting `public_api_result_typed`
and `no_write_direct` to honor it gets a relaxation it never receives. That is the
manufactured-confidence failure of a check that scans zero files, **relocated from the code into
the schema documentation**. The thread has been hunting this shape in checks, config and prose;
this is its first appearance in a ratified consumer-facing contract.

**A PREAMBLE WAS RATIFIED FIRST, and it is what makes this durable rather than a data refresh.**
`partition_completeness` and `source_trees_scoped_to_consumer` read nearly EVERY role key
structurally, so the lists had two defensible readings producing different answers for every key
— and two authorities in this repo already disagreed because of it (the `pyproject.toml` comment
counted `partition_completeness` as a consumer, the spec did not). v035 defines the lists as
BEHAVIORAL consumers and names both meta-checks as excluded **by rule**, so their absence reads
as a decision rather than an oversight. Without that, the next editor correcting these lists has
no way to know whether `partition_completeness` belongs in all eleven or none.

**`pure_trees` and `covered_trees` were measured CORRECT and deliberately left alone.** Recorded
so a later editor does not assume the whole section was wrong — and because a method that only
ever deflates what it touches is not measuring.

**AND THE COUNT HID AN ERROR IN THIS REPO'S OWN CONFIG COMMENT.** The `pyproject.toml` comment
said `supervisor_entry_files` grants FOUR exemptions and listed them. Both halves were wrong and
**they cancel in the count**: `public_api_result_typed` was missing (a real exemption, wired by
#816 and never reflected) and `partition_completeness` was listed (it reads the key but grants no
exemption — it is bookkeeping). Still four. **A reader checking only the number would have seen
nothing wrong**, which is why this was found by measuring membership rather than by counting.

#### Still owned by someone else (unchanged)

1. **`livespec-dev-tooling-5ror` — ✅ CLOSED 2026-07-29.** Ratified as v034 (`3a7d8d8`). Kept
   here only so a reader of the old numbering does not go looking for it.
2. **The `unarmed_until` LIVENESS check — ARCHITECTURE DECISION.** Blocked on a vantage/credential
   question, now with hard cross-tenant measurements; see the ⛔ block below. It is proposal 3 of
   the filed spec change, so the obligation gets ratified before it is enforced.
3. **`livespec-dev-tooling-efxa` — DISPATCHER.** 30 of 31 checks never catch `ConfigParseError`.
   Factory-dispatchable; leave it. (`pj3j` is DONE — merged `c0c0472`.)
4. **`bd-ib-6qb2mc` — A HUMAN, IN ANOTHER TENANT** (beads-fabro, `blocked`/`needs-human`). Carving
   that repo's real pure tree, which is what its `unarmed_until` promises.
5. **`livespec-dev-tooling-m50u` — A HUMAN, then ANOTHER TENANT'S INTAKE.** A blessed
   declared-absent payload measured FALSE in `livespec-orchestrator-git-jsonl`. The measurement is
   done; the remedy is that repo's architectural call and must not be a naive prefix widening.
6. **`livespec-dev-tooling-clkf` — ✅ CLOSED 2026-07-29.** Ratified as v034 (`3a7d8d8`).
7. **Step 6's ARMING — AUTHORIZED, but SEQUENCED LAST and now BLOCKED ON `zu85`.** The
   maintainer's order is remediate → arm → fan out. Remediating `livespec-dev-tooling`'s own
   offenders is a PRECONDITION of arming, not a follow-up, and the count is now **47**, not the
   59 the blast-radius table below assumes. **Arm only at measured ZERO — and ZERO IS NOT
   REACHABLE BY CONVERSION**: 4 of the 47 are `otel_step_timer.py`'s, which cannot import the
   railway at all (`zu85`). The conversion floor is **43**. Closing the last four is a SPEC
   decision that nobody has started. The 282 fleet figure below is the FAN-OUT radius and is
   likewise pre-triage — it counts supervisor and `_`-prefixed cases the ratified v177 set and the
   underscore rule now exempt, so it will fall substantially when re-measured per repo.
8. **`livespec-dev-tooling-nauzq6` — A HUMAN** (`blocked` / `needs-human`, filed 2026-07-28). The
   installer/check divergence on an undeclared `neutral_hook_body_path`. The MEASUREMENT is done
   and recorded; what is owed is a design ruling on whether an operator-invoked reconcile surface
   may be lenient where its paired gate is strict. Do not "fix" it by gating the installer without
   that ruling — that breaks `just install-no-shadow-ledger` for exactly the repo mid-adoption
   that needs to run it.

### ✅ PHASE 3 — LANDED, REGISTERED, AND **EXERCISED**. Three pieces of evidence, because green proves nothing here

Merging a conformance row and running one are different facts, and this thread exists because they
were confused. All three were taken against the LANDED code.

1. **The CENTRAL CI SWEEP, App-token vantage** (job `90279534466`). The row ran against the LIVE
   nine-member manifest. **`blind_rows: 0`** — the engine's own count of rows that applied to at
   least one member and were evaluable for NONE — and **zero** `obligation row enforced NOTHING
   this run` events. The row is `central` vantage, so it enforces in BOTH automated CI and a local
   operator sweep; **it is out-of-vantage nowhere.**
2. **A DIRECT PER-REPO RUN against the forge**, live `gh` reads. Eight Python-bearing members
   EVALUATED and passed. `livespec-console-beads-fabro` returned
   `excluded-with-reason: no [tool.livespec_dev_tooling] block; not a layout-config consumer` — a
   **named** exclusion, not a silent skip. The per-repo table is the fleet-progress table below.
3. **A NEGATIVE PROOF that it can FAIL**, from the engine's own path — the fixture, below.

`_contract_rows.py` measures **195 LLOC** after registration: 55 under the hard ceiling, and still
5 under the SOFT one, so the NEXT obligation does not re-open `oitd`.

#### The fixture was supplying the very thing under test — and its failure is the proof

Registering the row turned **twelve** `test_fleet_conformance.py` tests red, correctly.
`_all_required_empty_block()` rendered EVERY required role key as `[]` / `""`, so the canned
"green fleet" member declared all five union keys with the retired ambiguous spelling:

```
error_findings=1  member='widget'  failing_rows=('role-key-spellings',)
widget: role key(s) still carrying the retired ambiguous empty spelling:
dataclasses_tree, neutral_hook_body_path, pure_trees, source_tree_prefixes, target_dirs
```

That is what a green run cannot give: the **registered** row evaluated a member through the **real
lane** and failed it. Renamed `_all_required_role_keys_block()` and split by half — the five UNION
keys carry a blessed spelling; every other required key **keeps `[]` / `""` deliberately**, because
for those emptiness makes the consuming check STRICTER rather than blinder. Rendering both halves
alike would teach the next reader of that fixture a rule that is wrong for five of the keys.

#### ⚠️ A LOCAL `just check` 64/64 does NOT mean the fleet row ran

`check-fleet-conformance` is behind the `LIVESPEC_RUN_FLEET_CONFORMANCE` lever and **SKIPS
locally**, counting toward "All 64 targets passed". It logs the skip with a hint, so it is honest
rather than silent — but inferring "the new fleet row passes" from a local aggregate green would
have been this thread's signature error. **CI sets the lever; local runs do not.** Verify a fleet
row by running the sweep or by reading the CI job, never from the local aggregate.

### ⛔ THE LIVENESS CHECK IS BLOCKED ON A VANTAGE DECISION — measured, not assumed

Phase 3 was asked to verify that an `unarmed_until` payload resolves to a **still-open** ledger
item. **The fleet row cannot answer that**, and the reason is structural rather than effort:

- Fleet rows run at the **CENTRAL vantage** — a GitHub credential reading committed files.
  `_rows_beads.py` is the precedent: even the beads-aware row only compares two committed
  connection FILES and never touches a ledger. There is no dolt-server and no tenant secret in the
  fleet-conformance CI context.
- The machinery that CAN reach `bd` is the **LOCAL vantage** (`_rows_local_beads.py`), whose
  documented discipline is *detect-and-guide*: WARNING-severity findings that explicitly "never fail
  the verb", plus a SKIP when the repo is not beads-backed. **That is exactly the wrong severity for
  a conformance gate** — it would ship a check that silently declines to enforce.
- **Cross-tenant makes it worse, not merely harder — and this is now MEASURED, not reasoned.**

| declaring repo | cited id | that id's tenant | resolvable from the DECLARING repo's own tenant? |
|---|---|---|---|
| `livespec` | `livespec-mutreal.1` | livespec | **YES** |
| `livespec-orchestrator-beads-fabro` | `bd-ib-6qb2mc` | livespec-orch-beads-fabro | **YES** |
| `livespec-overseer` | `livespec-mutreal.1` | livespec | **NO** |
| `livespec-orchestrator-git-jsonl` | `livespec-mutreal.1` | livespec | **NO** |

**CORRECTION to the earlier framing, which said a same-tenant resolver fails on three of four.**
Three repos DO cite `livespec-mutreal.1` — but one of those three is `livespec` ITSELF, where the
id is same-tenant. The real figure is **2 of 4**. Do not restore the higher number.

The conclusion is unchanged and sharper. **No single tenant credential resolves both ids:** the
`livespec` tenant resolves `livespec-mutreal.1` and NOT `bd-ib-6qb2mc`; the beads-fabro tenant
resolves the reverse. So this is not a per-repo mismatch to paper over — the declared id set spans
**two tenants with no superset credential in evidence**.

**The failure mode is the dangerous one.** A cross-tenant lookup returns
`Error fetching <id>: no issue found matching "<id>"` — a NOT-FOUND, not a permission error. A
defensively-written resolver treats not-found as a skip and **reports green**, which is precisely
this thread's signature failure. A naively-strict one reports a bogus finding against a valid id.
Neither measures liveness.

Both ids are in fact LIVE today (`livespec-mutreal.1` BACKLOG, `bd-ib-6qb2mc` BLOCKED), so all four
`unarmed_until` declarations point at genuine pending work — **measured by hand, out of band, and
NOT asserted by any check.**

**RE-CHECKED 2026-07-29, BOTH TENANTS, AND IT STILL HOLDS — `livespec-mutreal.1` BACKLOG,
`bd-ib-6qb2mc` BLOCKED.** Third consecutive session in which both resolve open, so all four
`unarmed_until` declarations still point at genuine pending work and nobody is in breach.
**Re-check this FIRST on any future cold start**, ahead of anything else on this thread: it is the
fastest-decaying fact here and the only one whose decay is SILENT. Two `bd show` reads, one per
tenant — `livespec-mutreal.1` from `/data/projects/livespec`, `bd-ib-6qb2mc` from
`/data/projects/livespec-orchestrator-beads-fabro`, because no single credential resolves both. `kmdn` exists precisely because when `livespec-mutreal.1` closes, three
repos breach a ratified obligation simultaneously and **nothing in the fleet notices** — no check
resolves these ids, by the structural argument above. Two `bd -C` reads is the whole cost; the
alternative is a fleet-wide ratified obligation quietly going false.

So it needs a new credential class or changed local-row severity semantics — an architecture
decision, not a check to bolt on. It is recorded as an explicit **non-guarantee in the row's own
docstring** rather than left implied.

### 🚫 THE LITERAL-STRING COMPANION CHECK — deliberately NOT built, and the reason is evidence

It was authorized "if cheap", and it is cheap. It was **not** built because the measured evidence
says **it would have caught ZERO of the five second sites**, and two of the repos it would have to
catch were scored prose-CLEAN by exactly that grep. Shipping it without a very loud non-guarantee
would be a check that overclaims its coverage.

**If it is built later, its docstring MUST say it narrows the prose gap and does not close it.**
Recorded so this is not silently re-litigated as an oversight.

### SIBLING PINS — fully open, and no longer a gate

Every repo carries `v0.57.0` and all eight are migrated. Retained as the rule for the NEXT
required-key schema change rather than as a live gate: a sibling cannot adopt a blessed spelling
until its own pin carries the accepting loader, so check the pin on the FORGE
(`[tool.uv.sources]` `tag = "vX.Y.Z"`) before touching a repo. **Do not trigger a release and do not
hand-edit a sibling's pin** — the `release-dispatch` fan-out does it, and a hand-edit races the
automation.

### ⚠️ THE CONFLATION THAT WOULD MAKE ALL OF THIS WORTHLESS

**Completing `8o8e.1` does NOT arm the railway check.** Declaring
`pure_trees = { not_applicable = "…" }` makes the SCHEMA honest; it does not make
`check-public-api-result-typed` scan anything, because that check is still `pure_trees`-scoped. So
after Phases 2, 3 and 4 land perfectly, it will STILL scan zero files in every flat-layout repo —
legitimately and honestly this time, and still zero.

Arming it means migrating it OFF `pure_trees` onto the git-derived `resolve_check_universe()` —
that is `8o8e`'s own step 6, and it is **NOT STARTED**. Closing `8o8e.1` must never be read as
closing `8o8e`. Full detail is on the `8o8e` epic.

---

## 🛑 CLOSURE PRECONDITION — read before planning anything else

**Neither `8o8e` nor THIS PLAN THREAD may close until `8o8e.1` is fixed FLEET-WIDE and VERIFIED**
(maintainer-declared 2026-07-28). "Verified" means **per-repo evidence** that the ambiguous
spelling is rejected and each repo declares the correct variant — **not** a green check in one
repo. Eight Python-bearing repos, eight pieces of evidence.

**STATUS 2026-07-28 (FINAL): ✅ DISCHARGED. `8o8e.1` is CLOSED, with eighteen pieces of evidence.**

The precondition is verbatim *"per-repo evidence that the ambiguous spelling is REJECTED and each
repo declares the correct variant — **not a green check in one repo**"*. That is two claims across
nine manifest members, and all eighteen hold.

**THE DELIVERY CHAIN — merged, released AND consumed.**

| link | evidence |
|---|---|
| merged | Phase 4 `b36e0b8` |
| released | `git tag --contains b36e0b8` → **`v1.0.0`**; ancestry confirmed |
| v1.0.0 commit | `20227edb6b10ed203f72ddb3a9233362472317f9` |
| consumed | all eight siblings DECLARE `tag = "v1.0.0"` **and** their `uv.lock` RESOLVES `livespec-dev-tooling==1.0.0` at `20227edb…` — matched per repo |

**Declared and RESOLVED were checked separately on purpose**: a repo that pins a tag whose lockfile
has not resolved is not yet rejecting anything.

**CLAIM 1 — REJECTED, per repo.** Exercised against the **checked-out `v1.0.0` tree** — the exact
commit every `uv.lock` names, not dev-tooling's working tree. Five union keys × nine repos =
**45 loads, 45 rejections**, every diagnostic naming all four blessed spellings. The pinned loader
carries **no** `LegacyAmbiguousEmpty` and **does** carry `Undeclared`. Absent, not merely
unreachable.

**CLAIM 2 — CORRECT VARIANT, per repo.** Phase 3's row, verified REGISTERED in `OBLIGATION_ROWS`
(`vantage=central`) and identity-checked against its assert function, run over the live manifest
from the same v1.0.0 tree: **nine members, nine `RowPass`.** `livespec-console-beads-fabro` returns
a NAMED `excluded-with-reason` — included deliberately, being the zero-Python member whose baseline
surfaced the `Undeclared` finding.

### ⚠️ THE CORRECTION THAT STAYS IN THIS RECORD

**I closed `8o8e.1` once already, on the strength of Phase 4 being MERGED.** It was released by
nobody and consumed by nobody; every sibling still pinned `v0.58.1`, whose loader accepted `[]`.
This file carries **MERGED ≠ RELEASED ≠ CONSUMED** as a rule, and I applied the first term as
though it were the third — on the item the rule was written for.

Caught before it did harm, reversed to `acceptance`, then discharged properly when the fan-out
actually completed. **Note the shape:** "not released, consumed by nobody" was TRUE when written
and FALSE within the hour. A record that ages that fast is what this epic is about, and the fix is
not to write faster — it is to re-derive before claiming.

---

**THE TWO HALVES.**

1. ✅ **"each repo declares the correct variant"** — DISCHARGED, and no longer a snapshot. The
   eight pieces of evidence exist (the fleet-progress table above), and **Phase 3 is what makes
   them keep being true**: it landed, it is registered, and it is exercised against the live fleet
   by the central CI sweep. This half moved from a hand-gathered measurement to a standing
   guarantee on 2026-07-28.
2. ✅ **"the ambiguous spelling is REJECTED"** — **DISCHARGED.** Phase 4 (`b36e0b8`, released as
   `v1.0.0`) deletes `LegacyAmbiguousEmpty` and makes `[]` / `""` on the five UNION keys a hard
   `ConfigParseError`. Every sibling now RESOLVES that loader, and it was exercised against the
   pinned tree per repo: 45 loads, 45 rejections.

The rule that nearly broke this — conflating a merge with a delivery is the same move as
conflating a green check with a passing one. It is the defect this thread exists to close, and it
is the one the thread nearly closed on.

### ✅ WHAT PHASE 4 ACTUALLY CHANGED, MEASURED — the 426a property holds

All NINE repos loaded through the **rejecting** loader on the day it merged. **Zero rejected.** Two
results carry it:

- **Seven repos still declare a CLEAN key as `[]`** — 13 declared-empty clean keys fleet-wide, all
  still parsing. The ratified carve-out (v033 §"Clean role keys retain `[]`") demonstrated rather
  than argued, and direct evidence that a blanket rejection would have broken seven repos for a
  defect they do not have.
- `livespec-console-beads-fabro` reports `Undeclared` ×5 where it reported `LegacyAmbiguousEmpty`
  ×5. **Same behavior, honest state.**

### 🔺 THE DEFECT FOUND INSIDE THE FIX — `LegacyAmbiguousEmpty` carried TWO meanings

It meant **both** "the consumer declared `[]`" **and** "the consumer never declared anything",
because the five `_BASELINE_*` constants bound it for a bare `Config()`. Two incompatible meanings
in one value — **inside the type introduced to make exactly that unrepresentable.**

It hid the way the original did: `_role_key_gate` tests `declared_keys` FIRST and hard-errors
there, so the baseline instance is never announced. **Unreachable through the gate, fully reachable
through the domain model** — which is how it survived three phases. Surfaced only because the
precondition was re-MEASURED rather than assumed: the console reported five, and checking why
rather than trusting the count is what found it.

Maintainer-ruled into a distinct **`Undeclared`** variant. Reusing `NotApplicable` was the tempting
one-liner and the wrong fix — it writes a **falsehood** into parsed data for every consumer without
a block. This also discharges `pk2x`'s standing note that "a key nobody wrote still parses to the
default".

---

## THE MAINTAINER RULING (2026-07-28) — four variants, and meaning (D) is BLESSED

Blessed spellings, each requiring a **non-empty** payload:

```toml
pure_trees = { not_applicable         = "<reason>" }
pure_trees = { superseded_by          = "<reason>" }
pure_trees = { unarmed_until          = "<ledger-id>" }
pure_trees = { convention_not_adopted = "<reason>" }
```

Accepted reasoning: **fewer variants force (B), (C) and (D) repos to LIE**, and that is how the
next silent dodge gets created. Four is what the eight live configs actually exhibit.

**The ruling carried an ORDERING CONDITION, and it is DISCHARGED.** Blessing (D) was safe only
because the coupling break removes (D)'s ability to disarm a check it never named. Phase 0 landed
first. Do not re-open this.

**Accepted cost, on the record:** blessing (D) permanently sanctions `claude_md_coverage` off in
five of eight repos and `tests_mirror_pairing` off in three — visible and greppable rather than
silent. It is **NOT** licence for the set to grow; a new `convention_not_adopted` still needs a
written reason.

### State the guarantee precisely — overclaiming it is its own defect

TOML has no sum types; nothing stops a person TYPING `[]`. The claim is exactly two things: after
parsing the ambiguity is **unrepresentable in the domain model**, and ambiguous input **fails loud
at load**. Never "impossible to express". The maintainer called this out by name.

### A SUPERSEDED AUTHORIZATION — do NOT implement the weaker fix

An early supervisor authorization said the fix "cannot be reject-empty, it must be that emptiness
stops implying scan-nothing". **The maintainer superseded that** — it removes the instance and
leaves the ambiguity representable. Do not resurrect it.

---

## WHAT LANDED, AND WHAT IT MEANS

### Phase 0 — `commit_pairs` coupling break (merged `5f82dbe`, released `v0.56.7`)

`str.startswith(())` is False for every input, so `source_tree_prefixes = []` made the commit-time
TDD pairing gate's source set empty **by construction** and its unpaired branch unreachable. Three
repos (`livespec-orchestrator-git-jsonl`, `livespec-overseer`, `livespec-runtime`) had declined the
tests-mirror convention by emptying that key and thereby switched off a gate **their config
comments never named**.

Fixed by `config.derive_source_prefixes` — union normalised `source_trees` into the prefix set.
Measured **set-identical** to the declared prefixes in all five armed repos, so it cannot redden a
passing repo; it adds exactly one prefix in each of the three disarmed ones.

### Phase 1 — the accepting loader (merged `8a61df6`, released in `v0.57.0`)

Five keys now parse into a discriminated union: `pure_trees`, `target_dirs`,
`source_tree_prefixes`, `dataclasses_tree`, `neutral_hook_body_path`.

**Five keys stay OUT, and that is deliberate** — `source_trees`, `io_trees`, `commands_trees`,
`supervisor_entry_files`, `covered_trees`. Bounded CLEAN **by execution**: they are exemption /
severity predicates whose consuming checks derive the universe from `resolve_check_universe()`, so
emptiness makes them STRICTER, not blinder. Routing them through the union is ceremony with no
defect behind it. (`source_trees` keeps one recorded caveat: empty WOULD be a severity softener, so
it is not structurally immune — only currently unexercised at 0 of 8.)

`[]` / `""` still parse and still behave exactly as today, as a distinct `LegacyAmbiguousEmpty`
that WARNs naming the repo and key. **Phase 1 rejects nothing and reddens nothing** — measured, 48
runs, 47 exit 0. (The one non-zero, `livespec / claude_md_coverage`, is PRE-EXISTING: master's
loader reproduces it identically. Flagged, not investigated — outside this item.)

**The Phase 2 work list was derivable by RUNNING the loader, and it is now EXHAUSTED: 29 (repo,
key) pairs → 0, across eight slices.** The per-repo breakdown with the exact variants is the
fleet-progress table near the top of this file. This paragraph is history, not a work list.

Enforcement shape: two exhaustive `match` sites carry `assert_never` (`config.role_absence`,
`_role_key_gate._announce_absence`) and every consumer routes through one, so a future variant
breaks the type gate rather than silently inheriting scan-nothing. When the five field types
changed, pyright enumerated all fourteen consumers — that is the mechanism working.

---

## ✅ PHASE 2 — COMPLETE. EIGHT SLICES, EIGHT REPOS, FLEET TOTAL 0

**Precondition, and it is PER-REPO, not fleet-wide:** a sibling cannot adopt a blessed spelling
until **its own pin** carries the accepting loader. Adopting earlier fails that repo's `just check`
with a `ConfigParseError` on an inline table its pinned loader cannot parse. Bump PRs land
independently and at different times, so check each repo's pin before touching it.

Sequence: `v0.57.0` released → `release-dispatch` fans out → each sibling gets an auto-merge
`chore(deps):` bump PR → **only then** is that repo migratable. **Every step has now completed for
all seven siblings**, so this precondition is SATISFIED fleet-wide and is retained as the rule for
the next schema change rather than as a live gate. Still verify the pin on the FORGE
(`[tool.uv.sources]` `tag = "vX.Y.Z"`, ≥ `v0.57.0`) before migrating a repo — cheap, and the
failure mode is that repo's `just check` dying on a `ConfigParseError`.

**Do not trigger a release. Do not hand-edit a sibling's pin** — the fan-out does it, and a
hand-edit races the automation.

### ✅ SLICE 1 IS DONE — `livespec-dev-tooling` migrated its own three keys (merged `b27401c`)

The producer went first: both producer and consumer, always on the current loader, so no pin wait.
All three took **(A) `not_applicable`**, each reason lifted from that key's own existing comment:
`pure_trees`, `dataclasses_tree`, `neutral_hook_body_path`.

**Verified on merged master by RUNNING it: this repo's `LegacyAmbiguousEmpty` count is 3 → 0**, all
three now report `role_key_spelling: not_applicable`, all six consuming checks exit 0, `just check`
64/64. The four spellings are now proven end-to-end against a real repo.

`pure_trees` is the case that justifies the union: `livespec` and `livespec-overseer` carry the
SAME empty value for the OPPOSITE reason (`unarmed_until = "livespec-mutreal.1"`). One value, two
meanings — now distinguishable.

### ✅ ALL EIGHT SLICES LANDED — and every spelling has a worked precedent

The full per-repo result, with each repo's own suite green under its OWN pinned loader, is the
fleet-progress table near the top of this file. It is **measured on the forge, not arithmetic**.

All four blessed spellings are exercised live: `livespec` proved (B) `unarmed_until`,
`livespec-driver-claude` proved (C) `superseded_by`, `livespec-runtime` proved (D)
`convention_not_adopted`, and (A) `not_applicable` is carried by four repos. A future repo has a
worked example of whichever variant its own comments select — which removes the "no prior art"
excuse for picking the tidy one.

Two results are worth protecting from a later tidy-up, and both are recorded in full above: the
**`pure_trees` split** (four `unarmed_until` / four `not_applicable`, discriminated by the repo's
own ratified constraint rather than by whether a `pure/` directory exists), and the **prose
finding** (five for five on second sites a grep cannot reach).

---

## HOW A RELEASE ACTUALLY REACHES A SIBLING (established, with evidence)

`release-please` (on push to master, opens/updates a release PR; merging it tags + releases)
→ `release-dispatch.yml` (on `release: published`, discovers siblings via the **`livespec-sibling`
GitHub topic**, fires `repository_dispatch: sibling-released`)
→ `bump-pin-from-dispatch.yml` (rewrites **four** pin formats, commits `chore(deps):`, opens an
auto-merge PR; deliberately runs NO consumer checks — the consumer's own CI is the gate).

**Load-bearing detail:** release-please MUST authenticate via the livespec GitHub App token, never
`GITHUB_TOKEN` — releases authored by `github-actions[bot]` do not fire `release: published`, so
the entire fan-out would silently never trigger.

---

## 📋 OPEN ITEMS

### Filed by this thread

| id | state | what |
|---|---|---|
| `8o8e` | epic | This thread's anchor. Cannot close until `8o8e.1` is fleet-wide fixed AND verified. |
| `8o8e.1` | **✅ CLOSED — precondition DISCHARGED** | Role-key schema type-safety. All four phases landed, spec ratified at v033, Phase 4 released as **`v1.0.0`** and consumed by all eight siblings (declared AND resolved). Eighteen pieces of per-repo evidence: 45 rejections against the pinned loader, nine `RowPass` from the registered Phase 3 row. |
| `5ror` | **✅ CLOSED 2026-07-29 — RATIFIED as v034 (`3a7d8d8`, PR #807)** | `contracts.md` recorded the library as pre-1.0 with MAJOR pinned at `0`, which a released and fleet-consumed `v1.0.0` made false. The clause was NORMATIVE, which is why it outranked ordinary prose staleness: it told a future editor a breaking change may land in a lower component. The v0.54.12 deviation record is PRESERVED and rescoped to the regime then in force. |
| `efxa` | open, P2 — factory-dispatchable | **30 of 31 checks never catch `ConfigParseError`**, so a config error escapes as a traceback rather than the structured diagnostic `contracts.md` promises. Unreachable before Phase 4; reachable now from a plausible config. The rejection works — what is owed is the RENDERING. |
| `clkf` | **✅ CLOSED 2026-07-29 — RATIFIED as v034 (`3a7d8d8`, PR #807)** | v033 ratified the TRANSITIONAL accepting-loader regime that Phase 4 ended hours later. Ratifying it was CORRECT — it is what authorized Phase 4 — so the defect was the standing description, not the decision. All three targets fixed: the `contracts.md` WARN clause, the `scenarios.md` acceptance scenario (REWRITTEN, not deleted), and the `heading-coverage.json` entry citing a test Phase 4 deleted. |
| `kmdn` | **blocked / needs-human, P2** | v033 turned four repos' `pure_trees = { unarmed_until = … }` into a RATIFIED obligation to arm, which nobody has scheduled. Three of the four cite a CROSS-TENANT id and no verifier resolves any of them. All four point at open work today — so nobody is in breach, which is exactly why it was filed now: when `livespec-mutreal.1` closes, three repos breach at once and nothing notices. |
| `kepq` | open, P2 (split) | Two standing `doctor-static` fail findings on master, so EVERY revise pass exits 3 on findings unrelated to the revision. The `canonical_checks.py` half is factory-dispatchable; the `SPECIFICATION/README.md` half MUST go through propose-change/revise. |
| `br4xar` | backlog | `tests_mirror_pairing` disarmed in 3 repos. **ALL THREE RE-DERIVED 2026-07-28: `23 / 6 / 58` is really `6 / 6 / ≤3`** — git-jsonl's 23 was a no-map artifact, runtime's 6 CONFIRMED unchanged, and overseer's 58 was 94% contamination (49 of the 58 are that repo's own co-located test files).** The source→test MAPPING this item asks for **already exists and is already consumed** — `config.mirror_pairings` takes precedence over the derived fallback at `tests_mirror_pairing.py:120`. 23 was what a prefix union produces WITHOUT a map. **Sizing: ~15 tests plus one design question, not an epic** — the only epic-shaped part left is overseer's co-located-layout question, which `tests_mirror_pairing` structurally cannot express. See the section below. |
| `hgfnqd` | ready | Collapse `red_green_replay._derive_impl_prefixes` into `config.derive_source_prefixes`. Duplicate logic left deliberately: 3 tests assert the private helper by name, and refactoring a second commit-time gate inside a gate-arming PR risks losing the ability to commit at all. |
| `pj3j` | **✅ CLOSED — merged `c0c0472`; ledger status transitioned 2026-07-28 after re-verifying BOTH sites by reading them** | This repo's OWN `MISSING_KEYS_EVENT` (`checks/required_role_keys_declared.py:40-43`) and `Config` docstring (`config.py:407`) still teach the retired declared-empty spelling. Higher-leverage than any config comment: the diagnostic is read at the moment someone decides what to write, and it is interpolated into the FLEET report too (`fleet/_rows_required_role_keys.py:99`). **After Phase 4 its remediation routes the reader into a `ConfigParseError`** — so, like `fwcwxv`, it must land BEFORE Phase 4. Unlike `fwcwxv` it is code and factory-dispatchable. The item records the trap: `[]` is wrong for the five UNION keys only; it stays LEGITIMATE for the five CLEAN ones, and this check spans both. |
| `oitd` | **CLOSED — PR #776 → `34c05c1`** | Decomposed `fleet/_contract_rows.py` (246 → 183 LLOC) by extracting the six `github-state` rows to `_contract_github_state_rows.py` and splicing them back in place. `OBLIGATION_ROWS` unchanged in content and ordering, verified by dumping every row's fields from both trees and diffing to empty. **195 LLOC** once the Phase 3 row was registered — still under the SOFT ceiling, so the next obligation does not re-open this. **Its recorded `depends on 8o8e.1` edge was INVERTED** (it was a prerequisite of `8o8e.1`'s Phase 3, not a consequent) and made the ledger show completed work as blocked; removed and re-recorded as a non-blocking `relates_to`. |
| `fwcwxv` | **✅ CLOSED 2026-07-28 — all three acceptance bullets discharged** | The spec propose-change, RATIFIED as v033 (`0500155`). Bullet 1: `history/v033/` exists and `proposed_changes/` is drained, and the CLEAN-keys carve-out survived into the RATIFIED TEXT — §"Clean role keys retain `[]`" is cited by name at each of the five clean entries (211/213/215/217/223), so the blanket-retirement trap was avoided in the spec and not merely in the proposal. Bullet 2: ordering verified as ANCESTRY, not a date — `git merge-base --is-ancestor 0500155 b36e0b8`. Bullet 3: the deferred docstring reword, merged `27c1d94` (PR #800). **Its ledger status read `blocked` / `needs-human` for hours after the human gate had cleared** — see the ⚠️ note in START HERE. |
| `bd-ib-6qb2mc` | **blocked / needs-human — FILED this session, in the `beads-fabro` tenant** | Carve `livespec-orchestrator-beads-fabro`'s real pure tree. It is the named work that repo's `pure_trees = { unarmed_until = ... }` points at, so it is the ONLY open item whose closure is referenced from a parsed config value in another repo. **Do NOT close it by declaring `not_applicable`** — that re-hides an obligation its own ratified `constraints.md` imposes; if the constraint is wrong, amend the SPEC first. `blocked` is correct rather than a formality: verifying the result is mechanical, choosing the cut is architectural. |
| `m50u` | **blocked / needs-human — FILED 2026-07-28** | A blessed declared-absent PAYLOAD can be false and nothing checks it. `livespec-orchestrator-git-jsonl`'s `source_tree_prefixes = { superseded_by = … }` is **measurably untrue** — 14 of 49 first-party `.py` fall outside the derived set — silently narrowing BOTH commit-time gates. Filed HERE rather than in the git-jsonl tenant deliberately: that repo's intake runs through its own orchestrator surface (the `bd-ib-6qb2mc` precedent), which is not installed here, and a raw cross-tenant `bd -C` would bypass the intake DoR that routed that precedent correctly. **First action: route the git-jsonl half through that repo's own intake.** |
| `qv3k` | **blocked / needs-human — FILED 2026-07-28** | `livespec_footgun_guard.py` is the fleet's THIRD shared hook body and the only one with **no carrier constant, no installer and no byte-identity check** — 8 copies, **7 distinct contents**. The precedent exists twice (commit-refuse hooks; the no-shadow-ledger body) and was simply never extended. `needs-human` because picking a canonical body among eight divergent copies could weaken a SAFETY guard in seven repos at once, and nothing yet establishes which copy blocks least. |
| `nauzq6` | **blocked / needs-human, P2 — FILED 2026-07-28** | `install_no_shadow_ledger` and `checks/no_shadow_ledger_body_identical` **DISAGREE on an UNDECLARED `neutral_hook_body_path`** — the installer reads `role_path` directly and no-ops (exit 0); the check runs `role_absence_exit_code` FIRST and hard-errors (exit 1). It is a REQUIRED union key, so omission is a misconfiguration — but the two modules are documented as mirroring each other, and BOTH docstrings claimed a consumer that "has not declared" it "sees neither installer nor verifier activity". **Measured false.** `needs-human` because the remedy is a design call, not a fix: gating the installer breaks it for the repo mid-adoption that most needs it, and "operator reconcile is deliberately lenient where the gate is strict" is a defensible answer nobody has ever written down. |
| `zu85` | **open, P2 — FILED 2026-07-29. BLOCKS ARMING.** | `otel_step_timer.py`'s 4 ROP offenders are UNCONVERTIBLE: the file is COPYd ALONE onto the fabro-sandbox image as `/usr/local/bin/livespec-step-timer`, its `Dockerfile.dockerignore` allowlists only that file into the build context, and it runs on the base image's system python3 before the first `uv sync`. The vendor-path idiom resolves to `/usr/local/_vendor` → `ImportError` at import time → every dispatched prepare step dies. Measured CONFINED: the only such module of the 20. Needs a ratified exemption (the v177 set has no member that fits, and `supervisor_entry_files` is the WRONG instrument — it would grant four unrelated exemptions to silence one check). **Do NOT close it by converting anyway and testing only the in-repo import path** — that passes green while the baked artifact is broken. |
| `otrq` | open, P3 — FILED 2026-07-29 | ROP slice 1 left a stale ``returned `None` `` docstring at `fabro_image_pin_rewrite.py:211`, created BY the conversion that retired that `None`. The function's BODY correctly branches on `refusal.reason` fifteen lines below. Prose-twin instance #10, and the sharpest sub-shape yet: the docstring a reader consults FIRST contradicts the code directly beneath it. Docs-only, RGR-exempt. |
| `pk2x` | backlog | Archive-on-epic-close — **ADOPT** ruled. Carries a note from this thread: a union makes `[]` unrepresentable after parsing, but **a key nobody wrote still parses to the default**, so pk2x's Exemption slot needs PRESENCE REQUIRED, not merely value well-formedness. |

**`fp5yfv` — VERIFIED 2026-07-28, and the answer is BOTH.** It is no longer a "possible stale
item"; it was measured against the live fleet, and the same note is attached to all three
entangled items (`fp5yfv`, `30g`, `9j8.7`) so whoever grooms them does not re-derive it.

- **Its recommendation LANDED.** `_IMPL_PREFIXES` is gone from product code; `_derive_impl_prefixes`
  unions each repo's own `source_trees` with its declared `source_tree_prefixes` — exactly what
  `fp5yfv` recommended and what `9j8.7` asked for. The surviving `_IMPL_PREFIXES` references are
  test-side only: `_HARDCODED_IMPL_PREFIXES_2026_07_25` is a REGRESSION BASELINE. **Do not "clean
  it up"** — same trap as `test_config_driven_checks.py:150`.
- **Every exposure the three items NAMED is CLOSED**, measured per repo: `livespec-driver-claude`
  **0 of 7** uncovered (it was the FULLY EXPOSED repo), `livespec-driver-codex` **0 of 8**, and
  beads-fabro's `.claude/hooks/` four-file exposure now covered because that repo DECLARES the
  prefix. The "codex is covered only ACCIDENTALLY" trap closed in the RIGHT direction: it is
  covered by a declared `livespec/hooks/`, and the bare legacy `livespec/` / `bin/` entries that
  used to catch it by accident are gone.
- **But the CLASS MOVED rather than closed — and it is LIVE.** Filed as
  **`livespec-dev-tooling-m50u`** (P2, `blocked`/`needs-human`). See the section below.

### 🔺 THE PATTERN WENT ONE LEVEL IN — a blessed PAYLOAD can be FALSE (`m50u`, filed 2026-07-28)

The prefix gate is now honest: it derives from what each repo DECLARES. So the failure mode changed
shape from *"a fleet-wide hardcoded list omits your tree"* to *"your own declaration omits your own
code"* — and **the second is harder to see, because the declaration parses as well-formed and
Phase 3's row passes it.**

`livespec-orchestrator-git-jsonl/pyproject.toml:337` declares
`source_tree_prefixes = { superseded_by = "first-party source surface already declared via
source_trees" }`. **Measured on the forge, that payload is FALSE:** running the shipped
`_derive_impl_prefixes` over its live config covers **35 of its 49** non-test, non-vendored
first-party `.py`. **14 fall outside.**

**RE-MEASURED 2026-07-28 FROM A `master` TARBALL — 49 / 35 / 14 reproduces EXACTLY, and the
ENUMERATION of the 14 is now COMPLETE.** The earlier breakdown listed 11 under
`.claude-plugin/scripts/bin/` plus `.claude/hooks/beads_access_guard.py` — **that is 12 against a
stated total of 14**, and the two it never named are the two that matter most:

| # | uncovered | why it matters |
|---|---|---|
| 1–11 | `.claude-plugin/scripts/bin/*` | as recorded — that repo's own operation surface. (Small correction: **three** `check_*.py`, not four; the total of 11 is right.) |
| 12 | `.claude/hooks/beads_access_guard.py` | as recorded |
| **13** | **`.claude/hooks/livespec_footgun_guard.py`** | the **`qv3k`** guard — git-jsonl is tied into `qv3k` exactly as `livespec-dev-tooling` is: same file, same outside-its-own-prefixes position |
| **14** | **`acceptance/test_git_jsonl_golden_master.py`** | **a TEST FILE classified as first-party PRODUCT code** |

**ENTRY 14 IS A NEW FABRICATION MODE, AND IT BREAKS THE RECORDED REMEDY.** git-jsonl declares
`tests_tree_prefix = "tests/"`, so its `acceptance/` tree sits OUTSIDE the tests exemption and
`filter_first_party_py` classifies that test as product code. Widening the prefix set to cover it
would make a TEST FILE owe a Red→Green pair (`red_green_replay` sees it as impl) **and** a paired
test of its own — `tests_mirror_pairing` demanding a test FOR a test.

That is the `livespec-overseer` category error **arriving in a second repo by a different route**:
overseer gets there by CO-LOCATING tests inside the source package, git-jsonl by having a SECOND
test root outside its declared `tests_tree_prefix`. Same absurd demand, different cause — which
points at the real gap: **`tests_tree_prefix` is a SINGLE prefix, and at least two repos have more
than one test root.**

So the recorded remedy — "widen the prefixes, but declare `mirror_pairings` too" — is **necessary
and NOT sufficient.** It does not cover entry 14, which needs either a second tests root (no such
key exists today) or an explicit exemption.

**TWO commit-time gates are narrowed, not one.** `config.derive_source_prefixes` is the SHARED
derivation, so a `.py` outside the set owes neither a Red→Green pair (`red_green_replay` sees
`impl_paths == []`) nor a source/test pairing (`commit_pairs_source_and_test` sees no first-party
source). Both exit 0 and log nothing.

**This is exactly the non-guarantee Phase 3's row documents, with its first live instance.** The row
checks the SPELLING of a declared-absent value, not the TRUTH of its payload — stated in its own
docstring on purpose. **A payload no checker reads is a comment with better syntax highlighting.**
That is not an argument against the union: the declaration is greppable, reasoned and reviewed,
which the bare `[]` never was. It is the next layer of the same onion.

**DO NOT fix it by widening the prefix set ALONE.** git-jsonl's own comment states the constraint: a
prefix set there additionally needs a paired `mirror_pairings`, because its tests live at
`tests/<pkg>` rather than mirroring `.claude-plugin/scripts/<pkg>`. Widening without the map is
what fabricates offenders.

**But the cost of doing it RIGHT is far lower than `br4xar` recorded — re-derived below: with the
two maps declared, git-jsonl has `0 fabricated / 6 REAL` offenders, not 23 fabricated.** The
declaration and those six tests must land together, or the repo cannot commit once armed.

**`livespec`'s 9 RESOLVED — and 6 are a SECOND instance in a DIFFERENT sub-shape.** The 2 under
`templates/orchestrator-plugin/` are **legitimately exempt, not a judgement call**: `config.py`'s
own first-party predicate exempts `templates/` by name ("copier payload livespec ships but does not
govern"). 1 is the `qv3k` footgun guard. The remaining **6 under
`.claude-plugin/scripts/_currency/` are a real gap** — unambiguously first-party (module
docstrings, its own `CLAUDE.md`, and **a complete mirrored test tree at `tests/_currency/`**), just
never added to `livespec`'s declared prefixes, of which it is a sibling.

**Keep the sub-shapes apart.** git-jsonl's is a **FALSE PAYLOAD** — a blessed variant whose stated
reason is untrue. `livespec`'s is an **INCOMPLETE LIST** — a populated, honest declaration that
simply does not enumerate everything. Identical failure, but **an incomplete list has no payload to
falsify**, so a payload-verifier would miss it entirely. The evidence that it is unintended rather
than a decision is the mirrored test tree: a repo that did not want `_currency/` governed would not
have written `tests/_currency/`.

`livespec-overseer` and `livespec-runtime` are 1 each, both the `qv3k` guard.

#### ✅ THE INCOMPLETE-LIST HALF IS MECHANICALLY CHECKABLE — oracle PROTOTYPED, check NOT built

`m50u`'s filing deferred a mechanical successor on the grounds that verifying a `superseded_by`
payload needs per-key semantics. **That holds for the false-payload half and NOT for the
incomplete-list half**, which already has an oracle: `config.resolve_check_universe()` returns the
repo's git-derived first-party `.py`. The check is a set difference —

```
universe  −  { p ∈ universe : p.startswith(derive_source_prefixes(config)) }  ==  ∅ ?
```

Run as a throwaway probe against THIS repo: universe 145, **uncovered 1 —
`.claude/hooks/livespec_footgun_guard.py`**. The same single file the forge-side measurement found,
by a completely different route (git `ls-files` + on-disk predicates vs. tree listing + fetched
blobs). **Two independent methods agreeing.**

**It wants to be a PER-REPO check under `checks/`, not a fleet row** — `resolve_check_universe()`
needs a git checkout (`git ls-files`, and `is_generated` reads contents), which the central vantage
has not. Locally it is free, and it puts the finding where the fix is: the repo that must edit its
own `pyproject.toml` is the repo that goes red.

**AND THE PROBE FOUND THIS REPO'S OWN INSTANCE.** `livespec-dev-tooling`'s universe INCLUDES
`.claude/hooks/livespec_footgun_guard.py` — `config.py` narrows the `.claude/` exemption to
`.claude/skills/` precisely so `.claude/hooks/**` stays first-party — while its declared
`source_tree_prefixes` is `["livespec_dev_tooling"]`. First-party by its OWN rule, outside its OWN
gates' prefix set. `livespec-j5i9` again: the repo that enforces the fleet is the least enforced.

**Not fixed inline, for a specific reason rather than caution:** declaring `.claude/hooks/` here
immediately subjects that file to `commit_pairs`, and **this repo has no
`tests/claude/hooks/test_livespec_footgun_guard.py`** (`livespec` has one; this repo does not). So
the one-line edit demands a test for a 240-line guard whose canonical content is itself `qv3k`'s
open question. **Sequence: `qv3k` picks the canonical body → the test is written against THAT → the
prefix is declared.**

**That footgun-guard aside was investigated after all, and the first figure was WRONG.** It said
"four distinct sha256s across the five places it lives". **Corrected: the file lives in EIGHT
repos and has SEVEN distinct contents** (239–313 lines; only `livespec-overseer` and
`livespec-runtime` agree). Filed as **`livespec-dev-tooling-qv3k`** — see the section below.

**HOW THE WRONG FIGURE HAPPENED — this repo's own hazard, in a new costume.** The path is NOT
uniform: `livespec-driver-codex` carries the guard at `livespec/hooks/`, everyone else at
`.claude/hooks/`. The first pass assumed `livespec-driver-claude` used `.claude-plugin/hooks/` by
analogy with the no-shadow body (which DOES live there), the fetch 404'd, and **the 404 JSON body
was hashed as though it were the file.** That is the `$(...)`-failure hazard already recorded
below, wearing different clothes: *a command that fails inside a substitution is
indistinguishable from one that legitimately returned something.* **Enumerate the tree first, then
fetch known paths. Never fetch a guessed path and hash whatever comes back.**

### 🛡️ `qv3k` — THE FLEET'S THIRD SHARED HOOK BODY HAS NO CARRIER AND NO IDENTITY CHECK, AND IT HAS FORKED

`livespec_footgun_guard.py` mechanically enforces this fleet's loudest standing rule — it blocks
`git commit/push --no-verify`, `git config core.bare true`, and a leading `LEFTHOOK=0` assignment.
**Eight repos carry it. Seven distinct contents.**

| repo | path | lines |
|---|---|---|
| `livespec` | `.claude/hooks/` | **313** |
| `livespec-driver-claude` | `.claude/hooks/` | **276** |
| `livespec-driver-codex` | `livespec/hooks/` | **246** |
| `livespec-dev-tooling` · `-orchestrator-git-jsonl` · `-overseer` · `-runtime` | `.claude/hooks/` | 240 (three DIFFERENT contents; overseer = runtime) |
| `livespec-orchestrator-beads-fabro` | `.claude/hooks/` | **239** |

**The precedent for fixing this already exists TWICE and simply was never extended.** The
commit-refuse hooks and the neutral no-shadow-ledger body each have a packaged carrier constant,
an installer, and a byte-identity check (`no_shadow_ledger_body_identical`, whose docstring calls
its target "INSTALLED FOREIGN CONTENT ... forbidden to hand-edit"). The footgun guard has **no
carrier, no constant, no role key, no check** — it was copied. `config.py`'s own first-party
universe comment names it in the SAME BREATH as the no-shadow guard, so the fleet's prose already
treats them as a pair while only one has the machinery.

**What is NOT claimed:** nothing establishes that any copy is WEAKER than another. The measurement
is DIVERGENCE — hashes and line counts, not behavior. Working out which copy blocks least is the
first real task and must precede picking a canonical body, because adopting the wrong one weakens
the guard in seven repos in one commit. That is why `qv3k` is `needs-human`, not `ready`.

**RE-MEASURED INDEPENDENTLY 2026-07-28 — 8 bodies / 7 distinct contents CONFIRMED to the digit**
(313 / 276 / 246 / 240×4 / 239, `livespec-overseer` == `livespec-runtime`). The method was chosen
to be independent of the original: git-tree ENUMERATION per repo, blob fetch by the enumerated
path, and **a runner that RAISES on a failed API call** — because the first figure was wrong from
hashing a 404 body, and a shell loop attempting this re-measurement failed the same way again
mid-run (a broken `PATH` made `head` unavailable, so eight repos reported "ABSENT from tree"). **A
command that fails inside `$(...)` is indistinguishable from one that legitimately returned
nothing — third instance on this thread. Prefer a runner that raises.**

### ⚖️ AND THE BLOCKING QUESTION HAS FOUR ORACLES ALREADY WRITTEN — `qv3k` is cheaper than filed

`qv3k` is `needs-human` because "nothing yet establishes which copy blocks least". **That premise
is materially weaker than recorded: FOUR of the eight carrying repos already have a paired test
for the guard, not one.**

| repo | paired test | size |
|---|---|---|
| `livespec-driver-codex` | `tests/hooks/` | **540 lines** (against a 246-line guard) |
| `livespec-orchestrator-beads-fabro` | `tests/hooks/` | **452 lines** |
| `livespec` | `tests/claude/hooks/` | **289 lines** |
| `livespec-driver-claude` | `tests/hooks/` | **144 lines** |
| `livespec-dev-tooling` · `-git-jsonl` · `-overseer` · `-runtime` | **NONE** | — |

So the question can be ANSWERED mechanically rather than argued: run each of the four suites
against all seven distinct bodies — a 4×7 matrix — and the copies that fail somebody's test are
the ones that block less. **This does not make `qv3k` `ready`** (adopting a canonical safety body
across seven repos still wants a human), but it removes "no prior art" as the reason and replaces
a reading exercise with a test run.

**One correlation, deliberately NOT promoted to a finding:** the four repos WITHOUT a test are
exactly the four SMALLEST bodies (239–240) and the four WITH one are the four largest (246–313),
consistent with copies being forked and then extended where they were exercised. **That is a line
count, not evidence that the untested copies block less.** Run the matrix before believing it.

It also re-confirms `m50u`'s sequencing note: `livespec-dev-tooling` genuinely has **no**
`tests/claude/hooks/test_livespec_footgun_guard.py` while `livespec` does. The sequence stands —
`qv3k` picks the body → the test is written against THAT → `.claude/hooks/` is declared here. The
four existing suites are the obvious raw material for that test.

### 🔢 `br4xar` RE-DERIVED IN FULL — `23 / 6 / 58` is really `6 / 6 / ≤3`

Measured while working `m50u`, because `m50u`'s stated trap ("do not widen the prefix set — it
reddens `tests_mirror_pairing` with the 23 offenders `br4xar` measured") depends on that number
being true. **It is not** — and neither is overseer's 58. All three repos are re-derived below.

**The mapping `br4xar` asks for ALREADY EXISTS and is ALREADY CONSUMED.**
`checks/tests_mirror_pairing.py:120` reads `pairings = config.mirror_pairings or
_derived_pairings_from_prefixes(...)`. `mirror_pairings` is a first-class role key that takes
PRECEDENCE over the derived fallback, consumed by four checks. So `br4xar`'s premise is right about
the union and wrong about the remedy needing to be built — **the remedy is a DECLARATION using
machinery that already ships.**

**Where 23 came from:** a prefix union with no map looks for tests at
`tests/.claude-plugin/scripts/bin/…`, which no repo has. Every one of the 23 is fabricated by the
MISSING MAP, not by missing tests. **A number produced by the wrong configuration is not a
measurement of the repo.**

Re-derived with the check's OWN `_expected_paired_test_path` naming rule and its OWN exemption
predicates run against the real files from `master` (not by running the check in that repo's
checkout — the evidence class is stated so it is not over-read):

| declared map | result |
|---|---|
| `.claude-plugin/scripts/bin` → `tests/bin` | **0 offenders.** 11 source / 11 test: 8 pair by name, 3 exempt. **`tests/bin/` already exists and already mirrors** — the tree the 23 was loudest about is empty. |
| `…/livespec_orchestrator_git_jsonl` → `tests/livespec_orchestrator_git_jsonl` | **6 real.** Of 35: 17 paired, 6 private-helper exempt, 6 pure-declaration exempt, 6 real. |

So git-jsonl moves from "epic-shaped, dominated by false positives" to **"declare two
`mirror_pairings` entries, then write six tests"** — which is not epic-shaped. **One caveat
survives:** arming it turns those six red the moment the declaration lands, so the declaration and
the six tests must land TOGETHER or the repo cannot commit.

**ALL THREE REPOS ARE NOW RE-DERIVED. `23 / 6 / 58` is really `6 / 6 / ≤3`.**

| repo | `br4xar` recorded | re-derived | verdict |
|---|---|---|---|
| `livespec-orchestrator-git-jsonl` | 23 fabricated | **6 real, 0 fabricated** | a no-map artifact |
| `livespec-runtime` | 6 real | **6 real** | **CONFIRMED unchanged** |
| `livespec-overseer` | 58 real | **≤3 real** | 94% contamination |

`livespec-runtime` holding EXACTLY is worth as much as the two corrections — it shows the method
is not simply deflating everything it touches.

**Overseer's 58 was the most wrong, and for an instructive reason: 49 of the 58 are the repo's own
TEST FILES.** `livespec-overseer` **co-locates** its tests inside the source package. Of 84 `.py`
under `overseer/`: **49 are `test_*.py`**, 23 are `_*.py` helpers, only **11 are production
modules** — and just 6 `.py` live under `tests/` at all. The check demands a
`test_test_claude_sessions.py` for `overseer/test_claude_sessions.py`. That is a category error,
not a backlog. **8 of the 11 production modules already carry a co-located test**; three do not
(`daemon.py`, `start.py`, `version.py`, and `start.py` is plausibly covered by
`overseer/test_overseer_start.py`, which the naming rule cannot see).

**THE STRUCTURAL FINDING, which matters more than the count: `tests_mirror_pairing` CANNOT MODEL A
CO-LOCATED LAYOUT.** Its model is `source_tree` → a DIFFERENT `test_tree`, and no configuration
helps — measured: `overseer → tests/overseer` gives 58, `overseer → tests` gives **58 as well**,
and `overseer → overseer` would pair the 8 correctly and then demand `test_test_*.py` for all 49
test files. So **`livespec-overseer`'s `convention_not_adopted` payload is TRUE** — the repo is not
dodging a convention it could adopt; the convention has no spelling that fits it.

**That is the balancing case for `m50u`, and it matters.** Two payloads checked: git-jsonl's
`superseded_by` **FALSE**, overseer's `convention_not_adopted` **TRUE**. So the defect is *not*
"declarations lie" — it is that **nothing distinguishes the two**, and only an out-of-band
measurement did. An unchecked claim is not presumed false, it is **unranked**.

**Sizing:** `br4xar` is roughly **15 tests plus one design question**, not an epic. The only
epic-shaped part left is the co-located-layout question, and it belongs to one repo.

### Carried forward (not this thread's to drive, but part of the finding)

| id | what |
|---|---|
| `w25v` | `vendor_update` hardcodes the plugin layout; cannot vendor into this repo's own tree. |
| `i04f` (livespec) | Spec states the Result-return rule twice with incompatible exemption sets. Needs ratification. |
| `j5i9` (livespec) | The cross-cutting FINDING: the repo that enforces the fleet is systematically the least enforced. |

---

## 🕳️ THE PATTERN THIS THREAD KEEPS FINDING

One shape, found repeatedly — **machinery that is correct for consumers and inert or wrong for the
repo that owns it**, and **an emptiness or absence that silently means consent**:

1. `check-public-api-result-typed` — scanned zero files in all nine repos (`8o8e`).
2. `check-plan-thread-anchor-declared` — an **ABSENCE** meaning consent, not an emptiness; a union
   does not fix that shape. **RE-DERIVED 2026-07-28 with the check's OWN `_declared_anchor`
   predicate (not another grep): 19 of 23 active fleet handoffs would fail, not 18 of 20** — and
   the old characterization *"armed only in the one repo with ZERO plan threads"* is stale twice
   over. `livespec-dev-tooling` is still the ONLY repo declaring
   `plan_lifecycle_anchor = true` — and **its thread(s) PASS.** So the shape is not "armed
   where there is nothing to check" but **"armed only where it already passes"**, which is the
   same defect wearing a less obvious face: the repo that adopts a convention first is the repo
   whose adoption the check can then never demonstrate. All 19 offenders sit in the eight repos
   that have not armed it. Two UNARMED repos already pass voluntarily (`livespec-driver-codex`,
   and one of git-jsonl's two on a CROSS-TENANT anchor the predicate accepts by design), so the
   19 is not 19 repos-worth of resistance.

   **RE-DERIVED AGAIN LATER THE SAME DAY, and the failure count is EXACTLY STABLE while the
   DENOMINATOR MOVED: 19 of 22, not 19 of 23.** `livespec-dev-tooling` archived one of its two
   threads in the interim, so it now has ONE active thread and it still passes. Both voluntary
   passers reproduce exactly (`livespec-driver-codex` 1/1; git-jsonl 1 of 2). **Note the shape of
   the drift** — the count of OFFENDERS did not move at all; the total did, because a compliant
   repo tidied up. A ratio recorded without its denominator's provenance would have read as
   progress.

   **The per-repo distribution, which the earlier re-derivation did not record:**

   | repo | armed | active | declares | FAILS |
   |---|---|---|---|---|
   | `livespec-orchestrator-beads-fabro` | no | 7 | 0 | **7** |
   | `livespec-console-beads-fabro` | no | 5 | 0 | **5** |
   | `livespec-overseer` | no | 4 | 0 | **4** |
   | `livespec-orchestrator-git-jsonl` | no | 2 | 1 | **1** |
   | `livespec` | no | 1 | 0 | **1** |
   | `livespec-driver-claude` | no | 1 | 0 | **1** |
   | `livespec-driver-codex` | no | 1 | 1 | 0 |
   | `livespec-dev-tooling` | **YES** | 1 | 1 | 0 |
   | `livespec-runtime` | no | 0 | 0 | 0 |
   | **TOTAL** | | **22** | **3** | **19** |

   **Two things the distribution shows that the bare 19 hides.** The failures are CONCENTRATED —
   16 of 19 sit in three repos — so this is not a fleet-wide culture problem but three plan-heavy
   tenants. And `livespec-console-beads-fabro`, the ZERO-PYTHON member excluded from every
   Python-based conformance row, carries **5 active plan threads, all failing**: the member the
   fleet's checks are least able to see is not the member with the least going on.
3. `file_lloc_hard_gate` — retired under `426a` for exactly this: "the omission read as
   conformance". Its retirement sequence is the migration template Phase 4 follows.
4. `commit_pairs` / `claude_md_coverage` / `tests_mirror_pairing` — disarmed by an empty role key
   (`8o8e.1`), and `commit_pairs` was disarmed by a declaration that named two OTHER checks.
5. `vendor_update` — the "only blessed re-vendor path" cannot target dev-tooling's own `_vendor/`.
6. `file_lloc_hard_gate` **again, from the other side** (`oitd`): the repo that SHIPS the fleet's
   size ceiling is the one whose own central obligation table hit it, and the ceiling silently
   converted "add a fleet obligation" into "refactor the central table first" — announced by
   nothing until the commit was already written. Not an emptiness this time but the same shape:
   **machinery correct for consumers and obstructive for the repo that owns it.**

7. **`m50u` — the shape's NEXT LAYER.** An emptiness that meant consent became a DECLARATION that
   means consent. `livespec-orchestrator-git-jsonl` declares `source_tree_prefixes = {
   superseded_by = "…already declared via source_trees" }` and the claim is measurably false — 14
   first-party `.py` outside the derived set, two commit-time gates narrowed. **A blessed payload
   nobody reads is a comment with better syntax highlighting.** Found by MEASURING a claim rather
   than by reading it; no check in the fleet would have surfaced it.

**And its prose twin, found TEN times now** — *an amendment that changed the behavior and left an
authoritative statement of that behavior standing*: the handoff's own heading → this repo's config
header (Piece A) → four sibling headers (`livespec-driver-claude` = Piece B) → the ratified SPEC
(`fwcwxv`) → the tool's own diagnostic output (`pj3j`) → **four more on 2026-07-28, all in
PR #800 (`27c1d94`)** → **and `otrq` on 2026-07-29**. Each instance was found by re-reading the
WHOLE document after a local edit, never by the edit itself. **A value-counting check cannot see
any of them.**

**INSTANCE 10 IS THE SHARPEST, because the conversion CREATED it.** `otrq` is a
``returned `None` `` docstring at `fabro_image_pin_rewrite.py:211` — left standing by ROP slice 1,
whose entire purpose was retiring that `None`. Fifteen lines below it the same function's body
correctly unwraps a `Failure` and branches on `refusal.reason`, carrying a comment explaining that
the railway conversion "earns its keep HERE". **One function, holding both the correct account and
its contradiction, with the contradiction in the docstring** — the part a reader consults first to
learn the contract. Slice 1 DID edit that function (it rewrote the body); it simply never re-read
the docstring as prose. Found on the next slice by reading the whole file rather than the diff.

**AND v035 IS THE SAME SHAPE ARRIVING IN A RATIFIED CONTRACT.** `contracts.md`'s `io_trees` entry
named two consuming checks that do not read the key, and its `source_trees` entry named five. Not
stale prose about behavior — a stale statement of WHICH CODE READS A KEY, in the document a
consumer reads to decide what to declare. See §"TRACK C IS DONE — v035".

### 🔺 THE 2026-07-28 FOUR — and the finding is the SURFACE CLASS, not the count

They were found while discharging `fwcwxv`'s last acceptance bullet, a ONE-LINE docstring reword.
Re-reading the surrounding surfaces rather than grepping for the retired phrase turned one line
into five sites, and **two of them outrank the bullet that led to them**:

1. **`livespec_dev_tooling/checks/CLAUDE.md` carried the retired copy-paste family VERBATIM** —
   "DECLARES EMPTY logs a structured `info` no-op … that is the sanctioned, visible opt-out".
   **`CLAUDE.md` FILES WERE NEVER A SWEPT SURFACE ON THIS THREAD.** The sweeps covered plan
   handoffs, `pyproject.toml` headers, the ratified spec and the tool's diagnostics — every one
   of them a file a person OPENS. A `CLAUDE.md` is **auto-injected into the context of every
   agent that touches its directory**, so it is the most-read prose in the repo and the least-read
   file. `checks/` is where every check lives, which makes this the widest-reach instance found.
   **Add `CLAUDE.md` to the sweep list for the next schema change.**
2. **`config.py`'s comment on the five union fields ARGUED AGAINST the variant shipping three
   lines below it** — "the baseline default is the legacy spelling rather than a sixth
   `undeclared` variant" — with `_BASELINE_* = Undeclared(...)` directly beneath it. A reader
   would conclude `Undeclared` had been considered and REJECTED. `Undeclared`'s own docstring 130
   lines earlier gives the correct account, so one file held **both the account and its
   contradiction, and the contradiction was the copy physically attached to the code.** This is
   the worst sub-shape yet: not merely stale, but actively arguing against the shipped design at
   the exact place a reader looks to understand it.
3. **`livespec_dev_tooling/CLAUDE.md`** claimed `load_config` falls back to "the livespec-core
   historical defaults"; the baseline is a bare flat `Config()` with NO declared keys, which is
   not a working configuration at all.
4. **Both no-shadow-ledger modules called `neutral_hook_body_path` "OPT-IN"** and claimed an
   undeclared key is a no-op on both sides. **Measured FALSE** — and measuring it surfaced a real
   BEHAVIORAL divergence beneath the prose, filed as **`nauzq6`** rather than fixed inline.

**THE GENERALIZATION WORTH KEEPING.** Instances 1 and 3 say the sweep's selection criterion was
wrong, not its diligence: it swept *documents*, and missed *injected context*. Instance 2 says
proximity is not protection — the comment nearest the code was the one that was wrong, because it
was written to justify a decision that was later reversed and nothing re-reads a justification.
**A comment that argues for a design is the one most likely to survive that design's reversal.**

#### ✅ AND THE FLEET-WIDE SWEEP OF THAT SURFACE IS DONE — **0 of 107. NOTHING IS OWED.**

Finding a NEW unswept surface class in the producer raises the obvious question of whether the
eight consumers carry it too. **Measured 2026-07-28, so nobody re-measures it:** every `CLAUDE.md`
in all eight siblings was ENUMERATED from each repo's default-branch git tree and its BYTES
fetched and searched — 51 in `livespec`, 25 in `-orchestrator-beads-fabro`, 17 in
`-orchestrator-git-jsonl`, 8 in `-runtime`, 2 each in `-driver-claude` / `-driver-codex` /
`-overseer`, 0 in `-console-beads-fabro`. **107 files, ZERO instances.**

**The exposure was confined to `livespec-dev-tooling` alone**, and the reason generalizes: the
PRODUCER's `CLAUDE.md` files describe the loader's role-key semantics because the loader is theirs;
consumer `CLAUDE.md` files describe their own packages and never restate that contract. So the
rule to carry forward is narrower and more useful than "sweep every CLAUDE.md fleet-wide" — it is
**sweep the CLAUDE.md files of the repo that OWNS the contract you just changed.**

**One false positive is worth recording, because it is the same hazard in miniature.** A code
search for `sanctioned` flagged `livespec-orchestrator-beads-fabro/dev-tooling/checks/CLAUDE.md`.
Fetching and READING it showed the word belongs to "the only sanctioned output surface" — structlog
output discipline, unrelated. **The negative was verified by reading, not by trusting the search**;
a session that had trusted the hit would have filed remediation against a clean repo, and one that
had trusted a bare grep-count would have missed that the hit was spurious.

When you find the next one, **file it rather than fixing it inline** — a same-shaped hole found
while fixing another is the cheapest it will ever be to close, and the pattern is the finding. A
merged PR body is NOT a work queue; an untracked deferral is the disease this item is about.

---

## ⚠️ HAZARDS ALREADY PAID FOR

**A green check proves nothing here.** `check-public-api-result-typed` ran green in all nine repos
while scanning ZERO files. Require the **file count actually scanned**, not exit status. Green is
the failure signature on this thread.

**AND A GREEN AGGREGATE CAN CONTAIN A SKIPPED TARGET.** Measured landing Phase 3:
`just check`'s `check-fleet-conformance` is behind the `LIVESPEC_RUN_FLEET_CONFORMANCE` lever, so
it SKIPS locally, exits 0, and counts toward "All 64 targets passed". The skip is logged with a
hint — honest, not silent — but the number 64 does not distinguish "ran and passed" from "declined
to run". **Verify a fleet row by running the sweep or reading the CI job**, and prefer the engine's
own `blind_rows` count, which is exactly the "did anything actually get enforced" measurement.

**A static grep names candidates; it has not measured them.** A grep for "checks lacking a vendor
exclusion" returned a 19-module superset that was not a work list. Nine checks reading
`config.source_trees` are exemption predicates, unaffected by emptiness. Only execution separates
them.

**Read config comments as admissions, not negligence.** Every `pure_trees = []` was documented and
honest; two say "NOT an oversight". The defect is the CATEGORY ERROR, not anyone's declaration.

**Verify against the FORGE, never a local checkout.** Local sibling clones read five releases stale
(`v0.56.1` where the forge said `v0.56.6`). Also: a naive `grep` for a version in `pyproject.toml`
returns the `requires-python` FLOOR, not the pin — the pin is `tag = "vX.Y.Z"` under
`[tool.uv.sources]`, one of four formats.

**Check whether a test fixture supplies the very thing under test. HIT TWICE NOW.**
`tests/livespec_dev_tooling/checks/conftest.py` overrides `tmp_path` to seed a FULL legacy
`[tool.livespec_dev_tooling]` block. A test in that directory that only creates files inherits it
and proves nothing. Overwrite `pyproject.toml` outright.

The second instance is worth more than the first: `test_fleet_conformance.py`'s
`_all_required_empty_block()` generated a "green fleet" member declaring EVERY required role key
as `[]` / `""` — the exact spelling Phase 3's row rejects. Twelve tests went red on registration
and **all twelve were right**. The lesson is directional: **a fixture that generates every key the
SAME way encodes an assumption the schema may no longer hold.** When the schema splits a key set
into halves that must be spelled differently, a uniform generator is the thing that breaks, and it
breaks pointing at the new check rather than at itself.

**`just check` passing does NOT mean a commit will land.** The staged-diff checks (`commit-pairs`,
`red-green-replay`) run only at commit/push time over the STAGED set.

**⛔ THE REMEDY FOR THE `$(...)` HAZARD — STATE IT, NOT JUST THE HAZARD. IT HAS COST THIS THREAD
THREE TIMES.** The rule below has been re-learned three separate ways, so the fix is promoted above
the anecdotes: **use a runner that RAISES on a non-zero exit, and enumerate before you fetch.** In
practice that means a Python helper whose `subprocess.run` wrapper raises on `returncode != 0`,
rather than a shell `$(...)` whose failure is indistinguishable from a legitimate empty result. The
three instances: (1) `gh pr checks --json` printing "unknown flag", read as "not yet", spinning a
loop for ~37 minutes; (2) a 404 body hashed as though it were a file, producing the WRONG `qv3k`
divergence figure; (3) a broken `PATH` making `head` unavailable, so eight repos reported "ABSENT
from tree" when the file was present in all eight. **All three were silent, and all three produced
a confident wrong answer rather than an error.** Rewriting instance (3) in a raising Python runner
is what produced the correct 8/7 measurement.

**VERIFY A POLLING PROBE ONCE BEFORE WRAPPING IT IN AN UNTIL-LOOP.** Measured, and it cost ~37
minutes: `until [ "$(gh pr checks <n> --json bucket --jq ...)" = "true" ]` spun forever because
`gh pr checks` does **not** support `--json` — it printed "unknown flag" plus usage, which the test
read as "not yet". **A command that FAILS inside `$(...)` is indistinguishable from one that
legitimately returns "not done".** The PR had already merged before the loop started. Note the
sub-command matters, not the tool: `gh pr view <n> --json state --jq .state` DOES support `--json`.
Run the probe bare, look at the output, THEN loop — and give the loop an iteration ceiling that
reports rather than hangs.

**THE REVISE STALE-BRANCH PRECONDITION FIRES ON THE REVISE'S OWN BRANCH. MEASURED 2026-07-29.**
Step 3.5 of the revise prose runs `no_stale_revise_branches`, which fails any local `spec/*` branch
ahead of `origin/master`. Filing a propose-change and revising it on ONE branch — which is the
natural shape, and the shape this thread used — makes the filing commit itself the "stale branch",
so the precondition fails on the very pass it is guarding. **It cannot distinguish an ABANDONED
`spec/*` branch from the branch the revise is currently running on.** The prose's own escape is
correct here (`--skip-stale-branch-check`) and it REQUIRES narrating the skip rather than taking it
silently — do that, every time, because the same override would also mask a genuinely abandoned
branch. Worth a check-side fix: excluding the current branch (`git rev-parse --abbrev-ref HEAD`)
would keep the guard and remove the false positive.

**⚠️ AND `revise` EXITING 3 IS NOT `revise` FAILING.** The post-step doctor runs AFTER the
file-shaping work, so a `fail` finding lifts the exit code on a revision that HAS ALREADY LANDED.
On 2026-07-29 it exited 3 with exactly `kepq`'s two standing findings (`README.md:19`,
`canonical_checks.py:98`), both in files the change never touched — while v034 was cut, paired into
history, and `proposed_changes/` drained. **Always verify what landed before treating exit 3 as a
failed revise:** check `history/vNNN/` exists, the proposed change moved with its `-revision.md`
pairing, and `doctor-out-of-band-edits` / `doctor-accept-decision-snapshot-consistency` passed.

**A LEDGER STATUS IS A CLAIM, NOT AN OBSERVATION — AND IT AGES LIKE ONE. MEASURED 2026-07-28.**
This file calls the ledger authoritative over itself. On a cold start that was FALSE for two items:
`pj3j` read `BACKLOG` and `fwcwxv` read `blocked` / `needs-human`, while both had verifiably landed
(`c0c0472`, `0500155`). **The work landed and the record of the work did not** — which is this
thread's own subject, one level up, in the tracker instead of the source. Note the asymmetry that
makes it dangerous: a stale-OPEN item manufactures phantom work, and `fwcwxv` specifically read as
"a maintainer still owes a propose-change" for a change already ratified, three lines from this
file's own **"Do NOT re-file it."** **Re-derive by reading the ARTIFACTS an item names** — the
commit, the file, the `history/vNNN/` directory — not by reading its status field. Closing a stale
item is reconciliation, not new work; leaving it is how the next session gets sent to redo
something.

**A STALE LOCAL CLONE WILL HAND YOU STALE PROSE, NOT JUST A STALE PIN.** `/data/projects/livespec-
runtime` read `tag = "v0.56.1"` while the forge had `v0.57.0` — six commits behind. The risk is not
only the version: the config COMMENTS you are mapping variants from may also be old. `git fetch`
alone does not fix it; `pull --ff-only` before reading anything you intend to act on.

### Red-Green-Replay traps, both hit here

1. **`ruff format` can invalidate an already-committed Red.** The pair requires the test file
   BYTE-IDENTICAL; a reformat trips `test-file-checksum-mismatch`. The fix is a fresh Red (the hook
   says so itself) — never a bypass.
2. **The pre-commit hook runs the FULL `just check` against the WORKING TREE.** A Red that also
   carries test files IMPORTING not-yet-existing symbols produces collection errors, which tank
   `check-per-file-coverage` and make the Red commit unmakeable. **Red carries ONLY the test file
   that fails on ASSERTIONS with the impl untouched; every dependent test update travels with the
   impl in the Green amend.**

---

## STANDING SAFETY

- Never `--no-verify`. Halt and report on hook failure.
- Every tracked-file change: worktree → PR → rebase-merge, under
  `~/.worktrees/livespec-dev-tooling/<branch>`. Never commit on the primary checkout.
- Run `just install-worktree-pack` in a fresh worktree BEFORE the first commit, or
  `check-primary-checkout-commit-refuse-hook-installed` fails with `worktree_pack_absent`.
- Branch off **forge-verified** `origin/master` — it moved twice under this session in one turn.
- **Six or more FOREIGN worktrees exist.** `git worktree list` before acting; reap none of them.
- Sibling repos are READ-ONLY until Phase 2 is authorized.
- **Never kill the acting overseer daemon** (tmux `livespec-overseer:1.1`) — it supervises the
  whole fleet and is the shipped product, not part of this thread.
