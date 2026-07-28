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

## ▶️ START HERE — where the work actually is

> **COLD START, IN ORDER.** This file is all a fresh session inherits.
>
> 1. Re-derive live state — everything below ages in minutes:
>    `cd /data/projects/livespec-dev-tooling && /usr/local/bin/with-livespec-env.sh -- bd show livespec-dev-tooling-8o8e.1`
> 2. **NOTHING IS MID-FLIGHT.** No worktree of this thread's is open, no PR of its own is
>    unmerged, and no background job is running. There is no half-finished edit to find.
> 3. **PHASES 0, 1, 2 AND 3 HAVE ALL LANDED.** `oitd` is CLOSED (PR #776 → `34c05c1`) and
>    Phase 3 is MERGED **and REGISTERED** (PR #779 → `606f17b`). The row is demonstrably
>    walked by the real CI sweep — see the Phase 3 section for the three pieces of evidence.
> 4. **There is NO next action inside this thread's current authorization.** Every remaining
>    item is gated on someone else: Phase 4 on a MAINTAINER, the liveness check on an
>    ARCHITECTURE decision, `pj3j` on the Dispatcher, `bd-ib-6qb2mc` on a human in another
>    tenant. Do not invent one; see 📋 OPEN ITEMS for who owns each.
> 5. **Do NOT start Phase 4**, and do NOT run `/livespec:revise` — the spec change is filed and
>    awaiting a MAINTAINER, which is not this session's call.
> 6. **Do NOT start step 6.** It is the arming work and it is out of scope until authorized.
> 7. Phases 2 and 3 being complete is **not** the epic, and Phase 3 green is the single most
>    misreadable fact on this thread. See the ⛔ paragraph immediately below.


The blocking item is **`livespec-dev-tooling-8o8e.1`** (OPEN). Its ledger notes carry the full
record: the role-key classification, the maintainer ruling, the union design, the release
mechanism, the Phase 1 proof, and the Phase 3 exercise evidence. **Read the item before
planning anything** — it is far more detailed than this file, and this file deliberately does
not duplicate it.

**Phases 0, 1, 2 and 3 have ALL LANDED. All eight repos measure ZERO `LegacyAmbiguousEmpty`,
and Phase 3 is what makes that keep being true.**

**⛔ THAT IS NOT AN ARMED RAILWAY, AND THE DIFFERENCE IS THIS THREAD'S ENTIRE SUBJECT.**
`check-public-api-result-typed` is STILL `pure_trees`-scoped, so it still scans **zero files** in
every flat-layout repo — legitimately and honestly now, and still zero. Phases 2 and 3 made the
SCHEMA honest and made it STAY honest; neither made any check scan anything. Arming means migrating
that check off `pure_trees` onto `resolve_check_universe()` — `8o8e`'s own **step 6, NOT STARTED**.

**AND IT IS NOW MEASURED, NOT ASSERTED.** On 2026-07-28, every repo's live `pyproject.toml` was
loaded through the shipped loader and `config.pure_trees` resolved through the shipped
`role_trees()` accessor — the same call `public_api_result_typed.py:186` makes. **All eight
repos yield an EMPTY tree list. Fleet total scan roots: 0.** Four `UnarmedUntil`
(`livespec`, `livespec-orchestrator-beads-fabro`, `livespec-orchestrator-git-jsonl`,
`livespec-overseer`) and four `NotApplicable` (`livespec-dev-tooling`, `livespec-driver-claude`,
`livespec-driver-codex`, `livespec-runtime`). The thread's central claim is a measurement.

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
| Piece 1 — spec propose-change (PR #773) | **MERGED `f58e7d03` — the proposed-change FILE is ON MASTER at `SPECIFICATION/proposed_changes/role-key-declared-absent-spellings.md`. Do NOT re-file it.** It is FILED, not RATIFIED: `contracts.md`/`scenarios.md` are byte-unchanged, verified by diff. Awaiting a MAINTAINER at `/livespec:revise`. **Gates Phase 4.** |
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

### ▶️ EXACT NEXT ACTION — there is NONE inside the current authorization

Every remaining item is owned by someone else. **That is a real state, not a stall**, and the
right move is to say so rather than to manufacture work. Listed with its owner:

1. **`livespec-dev-tooling-fwcwxv` — MAINTAINER.** The spec change is FILED and MERGED to master
   (PR #773 → `f58e7d03`); it needs a decision, not another filing. Accept or reject at
   `/livespec:revise`. **Phase 4 cannot start until it is ACCEPTED**, or the spec actively
   contradicts the implementation the day Phase 4 ships.
2. **The `unarmed_until` LIVENESS check — ARCHITECTURE DECISION.** Blocked on a vantage/credential
   question, now with hard cross-tenant measurements; see the ⛔ block below. It is proposal 3 of
   the filed spec change, so the obligation gets ratified before it is enforced.
3. **`livespec-dev-tooling-pj3j` — DISPATCHER.** This repo's own `MISSING_KEYS_EVENT` and `Config`
   docstring still teach the retired spelling. Before Phase 4. Factory-dispatchable; leave it.
4. **`bd-ib-6qb2mc` — A HUMAN, IN ANOTHER TENANT** (beads-fabro, `blocked`/`needs-human`). Carving
   that repo's real pure tree, which is what its `unarmed_until` promises.
5. **`livespec-dev-tooling-m50u` — A HUMAN, then ANOTHER TENANT'S INTAKE.** A blessed
   declared-absent payload measured FALSE in `livespec-orchestrator-git-jsonl`. The measurement is
   done; the remedy is that repo's architectural call and must not be a naive prefix widening.
6. **Step 6 — NOT AUTHORIZED.** The arming migration. Do not start it.

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

**STATUS: EXACTLY ONE OF THE TWO HALVES IS DISCHARGED. Half a precondition discharged is not a
discharged precondition, and this is the moment it would be easiest to round up.**

1. ✅ **"each repo declares the correct variant"** — DISCHARGED, and no longer a snapshot. The
   eight pieces of evidence exist (the fleet-progress table above), and **Phase 3 is what makes
   them keep being true**: it landed, it is registered, and it is exercised against the live fleet
   by the central CI sweep. This half moved from a hand-gathered measurement to a standing
   guarantee on 2026-07-28.
2. ❌ **"the ambiguous spelling is REJECTED"** — still **FALSE**. Today `[]` parses to
   `LegacyAmbiguousEmpty` and WARNs; it is **ACCEPTED**. Rejection is **Phase 4**, which is
   unbuilt and gated on maintainer acceptance of the filed spec change. Every repo declaring the
   right variant is necessary and not sufficient — **nothing yet stops the next author writing
   `[]` again**; the fleet row would catch it after the fact, the loader would not refuse it.

So: read Phase 3 as "the migration can no longer silently regress", never as "the precondition is
met". Conflating a conformance sweep with a rejecting loader is the same move as conflating a green
check with a passing one — which is the defect this entire thread exists to close.

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
| `8o8e.1` | **OPEN, P1 — the live item** | Role-key schema type-safety. Phases 0–3 DONE and landed; Phase 4 gated on the maintainer. Its notes carry the Phase 3 exercise evidence and the cross-tenant liveness measurement. |
| `br4xar` | backlog | `tests_mirror_pairing` disarmed in 3 repos. **RE-DERIVED 2026-07-28 for git-jsonl and the headline number was an ARTIFACT: `0 fabricated / 6 REAL`, not 23 fabricated.** The source→test MAPPING this item asks for **already exists and is already consumed** — `config.mirror_pairings` takes precedence over the derived fallback at `tests_mirror_pairing.py:120`. 23 was what a prefix union produces WITHOUT a map. `livespec-runtime` (6) and `livespec-overseer` (58) were **NOT** re-derived. See the section below. |
| `hgfnqd` | ready | Collapse `red_green_replay._derive_impl_prefixes` into `config.derive_source_prefixes`. Duplicate logic left deliberately: 3 tests assert the private helper by name, and refactoring a second commit-time gate inside a gate-arming PR risks losing the ability to commit at all. |
| `pj3j` | **open, P2 — FILED by this session** | This repo's OWN `MISSING_KEYS_EVENT` (`checks/required_role_keys_declared.py:40-43`) and `Config` docstring (`config.py:407`) still teach the retired declared-empty spelling. Higher-leverage than any config comment: the diagnostic is read at the moment someone decides what to write, and it is interpolated into the FLEET report too (`fleet/_rows_required_role_keys.py:99`). **After Phase 4 its remediation routes the reader into a `ConfigParseError`** — so, like `fwcwxv`, it must land BEFORE Phase 4. Unlike `fwcwxv` it is code and factory-dispatchable. The item records the trap: `[]` is wrong for the five UNION keys only; it stays LEGITIMATE for the five CLEAN ones, and this check spans both. |
| `oitd` | **CLOSED — PR #776 → `34c05c1`** | Decomposed `fleet/_contract_rows.py` (246 → 183 LLOC) by extracting the six `github-state` rows to `_contract_github_state_rows.py` and splicing them back in place. `OBLIGATION_ROWS` unchanged in content and ordering, verified by dumping every row's fields from both trees and diffing to empty. **195 LLOC** once the Phase 3 row was registered — still under the SOFT ceiling, so the next obligation does not re-open this. **Its recorded `depends on 8o8e.1` edge was INVERTED** (it was a prerequisite of `8o8e.1`'s Phase 3, not a consequent) and made the ledger show completed work as blocked; removed and re-recorded as a non-blocking `relates_to`. |
| `fwcwxv` | **FILED as PR #773 — needs a MAINTAINER** | The spec propose-change. Four proposals: retire declared-empty for the union keys; preserve `[]` for the CLEAN keys with the stricter-not-blinder reason; ratify the constraint-based discriminator plus `unarmed_until` liveness; and the acceptance scenarios. **Filing is not ratifying** — accept or reject at `/livespec:revise`. **Phase 4 is gated on acceptance.** |
| `bd-ib-6qb2mc` | **blocked / needs-human — FILED this session, in the `beads-fabro` tenant** | Carve `livespec-orchestrator-beads-fabro`'s real pure tree. It is the named work that repo's `pure_trees = { unarmed_until = ... }` points at, so it is the ONLY open item whose closure is referenced from a parsed config value in another repo. **Do NOT close it by declaring `not_applicable`** — that re-hides an obligation its own ratified `constraints.md` imposes; if the constraint is wrong, amend the SPEC first. `blocked` is correct rather than a formality: verifying the result is mechanical, choosing the cut is architectural. |
| `m50u` | **blocked / needs-human — FILED 2026-07-28** | A blessed declared-absent PAYLOAD can be false and nothing checks it. `livespec-orchestrator-git-jsonl`'s `source_tree_prefixes = { superseded_by = … }` is **measurably untrue** — 14 of 49 first-party `.py` fall outside the derived set — silently narrowing BOTH commit-time gates. Filed HERE rather than in the git-jsonl tenant deliberately: that repo's intake runs through its own orchestrator surface (the `bd-ib-6qb2mc` precedent), which is not installed here, and a raw cross-tenant `bd -C` would bypass the intake DoR that routed that precedent correctly. **First action: route the git-jsonl half through that repo's own intake.** |
| `qv3k` | **blocked / needs-human — FILED 2026-07-28** | `livespec_footgun_guard.py` is the fleet's THIRD shared hook body and the only one with **no carrier constant, no installer and no byte-identity check** — 8 copies, **7 distinct contents**. The precedent exists twice (commit-refuse hooks; the no-shadow-ledger body) and was simply never extended. `needs-human` because picking a canonical body among eight divergent copies could weaken a SAFETY guard in seven repos at once, and nothing yet establishes which copy blocks least. |
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
first-party `.py`. **14 fall outside** — 11 under `.claude-plugin/scripts/bin/` (`next.py`,
`list_work_items.py`, `detect_impl_gaps.py`, `needs_attention.py`, four `check_*.py`, and three
more — that repo's own operation surface, not fixtures) plus `.claude/hooks/beads_access_guard.py`.

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

Smaller measured gaps, same run: `livespec` 9 uncovered (the 6-file
`.claude-plugin/scripts/_currency/` package, the footgun guard, and 2 under
`templates/orchestrator-plugin/` which are scaffold PAYLOAD — flagged, not asserted);
`livespec-dev-tooling`, `livespec-overseer` and `livespec-runtime` 1 each, all the same
`.claude/hooks/livespec_footgun_guard.py`.

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

### 🔢 `br4xar`'s "23 FABRICATED OFFENDERS" WAS AN ARTIFACT — re-derived to `0 fabricated / 6 REAL`

Measured while working `m50u`, because `m50u`'s stated trap ("do not widen the prefix set — it
reddens `tests_mirror_pairing` with the 23 offenders `br4xar` measured") depends on that number
being true. **It is not.** This re-derives ONE of `br4xar`'s three repos: `livespec-runtime` (6) and
`livespec-overseer` (58) were **NOT** re-derived — do not read this as having touched them.

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

Observed, not measured, about the other two: `livespec-runtime` HAS a `tests/livespec_runtime/`
mirror — exactly the DEFAULT derived shape — so its 6 is unlikely to be a mapping artifact.
`livespec-overseer` has NO `tests/overseer/` tree at all (flat `tests/` plus `tests/integration/`
and `tests/prompts/`), so its 58 is unlikely to collapse the way git-jsonl's 23 did, and it is the
case that genuinely needs a design decision.

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
   over. `livespec-dev-tooling` now has TWO active threads and is still the ONLY repo declaring
   `plan_lifecycle_anchor = true` — and **both of its threads PASS.** So the shape is not "armed
   where there is nothing to check" but **"armed only where it already passes"**, which is the
   same defect wearing a less obvious face: the repo that adopts a convention first is the repo
   whose adoption the check can then never demonstrate. All 19 offenders sit in the eight repos
   that have not armed it. Two UNARMED repos already pass voluntarily (`livespec-driver-codex`,
   and one of git-jsonl's two on a CROSS-TENANT anchor the predicate accepts by design), so the
   19 is not 19 repos-worth of resistance.
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

**And its prose twin, found five times now** — *an amendment that changed the behavior and left an
authoritative statement of that behavior standing*: the handoff's own heading → this repo's config
header (Piece A) → four sibling headers (`livespec-driver-claude` = Piece B) → the ratified SPEC
(`fwcwxv`) → the tool's own diagnostic output (`pj3j`). Each instance was found by re-reading the
WHOLE document after a local edit, never by the edit itself. **A value-counting check cannot see
any of them.**

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

**VERIFY A POLLING PROBE ONCE BEFORE WRAPPING IT IN AN UNTIL-LOOP.** Measured, and it cost ~37
minutes: `until [ "$(gh pr checks <n> --json bucket --jq ...)" = "true" ]` spun forever because
`gh pr checks` does **not** support `--json` — it printed "unknown flag" plus usage, which the test
read as "not yet". **A command that FAILS inside `$(...)` is indistinguishable from one that
legitimately returns "not done".** The PR had already merged before the loop started. Note the
sub-command matters, not the tool: `gh pr view <n> --json state --jq .state` DOES support `--json`.
Run the probe bare, look at the output, THEN loop — and give the loop an iteration ceiling that
reports rather than hangs.

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
