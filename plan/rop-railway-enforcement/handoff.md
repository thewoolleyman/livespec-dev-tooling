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

The blocking item is **`livespec-dev-tooling-8o8e.1`** (OPEN). Its ledger notes carry the full
record: the role-key classification, the maintainer ruling, the union design, the release
mechanism, and the Phase 1 proof. **Read the item before planning anything** — it is far more
detailed than this file, and this file deliberately does not duplicate it.

**Phases 0, 1 and 2 have ALL LANDED. All eight repos measure ZERO `LegacyAmbiguousEmpty`.**

**⛔ THAT IS NOT AN ARMED RAILWAY, AND THE DIFFERENCE IS THIS THREAD'S ENTIRE SUBJECT.**
`check-public-api-result-typed` is STILL `pure_trees`-scoped, so it still scans **zero files** in
every flat-layout repo — legitimately and honestly now, and still zero. Phase 2 made the SCHEMA
honest; it did not make any check scan anything. Arming means migrating that check off `pure_trees`
onto `resolve_check_universe()` — `8o8e`'s own **step 6, NOT STARTED**.

**Phase 3 is WRITTEN, TESTED and GREEN — and PARKED, not landed.** The conformance row that turns
the eight-repo measurement below into a standing guarantee lives on branch
`feat/fleet-row-role-key-spellings` (`dacfec1`) and cannot be REGISTERED, because
`fleet/_contract_rows.py` is 246 LLOC against a 250 hard ceiling and the table accepts no new row.
That is `livespec-dev-tooling-oitd` (P1) and it is the next action.

**Phase 4 MUST NOT start.** It cannot land until the filed spec change (PR #773) is ACCEPTED by a
maintainer, or the spec actively contradicts the implementation the day it ships.

### State as of 2026-07-28 (RE-DERIVE — this ages in minutes)

| thing | state |
|---|---|
| `livespec-dev-tooling` master | re-derive; was `472bbfc` when this line was written |
| Phase 0 — commit-pairs coupling break (PR #755) | **merged `5f82dbe`, RELEASED in `v0.56.7`** |
| Phase 1 — accepting loader (PR #759) | **merged `8a61df6`, RELEASED in `v0.57.0`** (verified: `git tag --contains 8a61df6` → `v0.57.0`) |
| Sibling consumption | **ALL SEVEN carry `v0.57.0`** — the pin gate is fully open; #296 merged after a re-run. **RE-DERIVE per repo.** |
| Piece B — `livespec-driver-claude` prose (PR #317) | **merged `e8c8847`** |
| Slice 3 — `livespec` values + prose (PR #1814) | **merged `6454b2cc`** — fleet's first `unarmed_until` |
| Piece 1 — spec propose-change (PR #773) | **FILED, awaiting a MAINTAINER** at `/livespec:revise`. Filing is NOT ratifying; `contracts.md` byte-untouched. **Gates Phase 4.** |
| Phase 3 — conformance row (`dacfec1`) | **BUILT + GREEN, PARKED — no PR.** Blocked on `oitd`; an unregistered row is a check that does not run. |
| Slice 4 — `livespec-runtime` values + prose (PR #366) | **merged `408388c`** — fleet's first two `convention_not_adopted` |

**MERGED ≠ RELEASED ≠ CONSUMED.** Keep the three separate in every status claim. Conflating them
re-creates this thread's core defect — a green signal that means nothing — at the process level.

### ✅ FLEET PROGRESS — 8 of 8 DONE. **FLEET TOTAL: 0.** This IS the closure-precondition evidence.

Measured on the **FORGE** after every merge, loading each repo's `pyproject.toml` through
`master`'s union loader. This is a SCHEMA measurement under one loader — deliberately, so only the
config varies. Each repo's own suite was ALSO run green under its OWN pinned loader, which is the
part the precondition demands.

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

### ▶️ EXACT NEXT ACTION — Phase 3 is BUILT but PARKED; one P1 unblocks it

1. **`livespec-dev-tooling-oitd` (P1) — decompose `fleet/_contract_rows.py`.** It measures **246
   LLOC against a 250 HARD ceiling**, so the fleet obligation table accepts **no new row at all**:
   registering one costs 257 in full form and **254 even at the tersest legal form**. This is the
   single thing standing between a written, tested, green Phase 3 row and it actually running.
2. **Then land `feat/fleet-row-role-key-spellings`** (commit `dacfec1`, pushed, **no PR**). It is a
   complete Red→Green pair: the row module at **100% line+branch**, **16 tests passing**, full
   `just check` **64/64**. It needs only its registration in the obligation table. It is parked
   rather than merged because **an unregistered obligation row is a check that does not run** —
   this epic's own defect.
3. **`livespec-dev-tooling-fwcwxv` — the spec change is FILED (PR #773) and needs a MAINTAINER.**
   Accept or reject at `/livespec:revise`. **Phase 4 cannot start until it is ACCEPTED**, or the
   spec actively contradicts the implementation the day Phase 4 ships.
4. **The `unarmed_until` LIVENESS check needs a VANTAGE DECISION before it can be built** — see the
   block below. It is proposal 3 of the filed spec change, so the obligation gets ratified before
   it is enforced.
5. **`livespec-dev-tooling-pj3j`** — this repo's own `MISSING_KEYS_EVENT` and `Config` docstring
   still teach the retired spelling. Before Phase 4. Factory-dispatchable; leave it for the
   Dispatcher.
6. **`bd-ib-6qb2mc`** (beads-fabro, `blocked`/`needs-human`) — carving that repo's real pure tree,
   which is what its `unarmed_until` promises.

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
- **Cross-tenant makes it worse, not merely harder.** Three repos cite `livespec-mutreal.1` (the
  `livespec` tenant); one cites `bd-ib-6qb2mc` (its own). A verifier holding ONE tenant's credential
  resolves at most one of the four — so a naive implementation false-negatives on the majority
  **while reporting green**, which is this thread's signature failure.

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

**STATUS: the eight pieces of evidence EXIST** (the fleet-progress table above — each repo measured
at zero AND its own suite green under its own pinned loader). **But the precondition is not yet
discharged, on two counts, and neither is a technicality:**

1. **"the ambiguous spelling is REJECTED" is still FALSE.** Today `[]` parses to
   `LegacyAmbiguousEmpty` and WARNs; it is ACCEPTED. Rejection is **Phase 4**, which is unbuilt.
   Every repo declaring the right variant is necessary and not sufficient — nothing yet stops the
   next author writing `[]` again.
2. **The evidence is a hand-gathered snapshot, not a standing guarantee.** It was true at the
   moment it was measured. **Phase 3 is what makes it keep being true**, and it is unbuilt.

So: read the table as "the migration is done", never as "the precondition is met". Conflating a
measurement with an enforcement is the same move as conflating a green check with a passing one —
which is the defect this entire thread exists to close.

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
| `8o8e.1` | **OPEN, P1 — the live item** | Role-key schema type-safety. Phases 0–1 done; Phase 2 next. |
| `br4xar` | backlog | `tests_mirror_pairing` disarmed in 3 repos. **The union is the WRONG fix there** — that check needs a source→test MAPPING, and a prefix union fabricates 23 false offenders in git-jsonl (whose real tests exist at `tests/<pkg>/`). Epic-shaped: 23 fabricated / 6 real (runtime) / 58 real (overseer, which has no `tests/overseer/` tree at all). |
| `hgfnqd` | ready | Collapse `red_green_replay._derive_impl_prefixes` into `config.derive_source_prefixes`. Duplicate logic left deliberately: 3 tests assert the private helper by name, and refactoring a second commit-time gate inside a gate-arming PR risks losing the ability to commit at all. |
| `pj3j` | **open, P2 — FILED by this session** | This repo's OWN `MISSING_KEYS_EVENT` (`checks/required_role_keys_declared.py:40-43`) and `Config` docstring (`config.py:407`) still teach the retired declared-empty spelling. Higher-leverage than any config comment: the diagnostic is read at the moment someone decides what to write, and it is interpolated into the FLEET report too (`fleet/_rows_required_role_keys.py:99`). **After Phase 4 its remediation routes the reader into a `ConfigParseError`** — so, like `fwcwxv`, it must land BEFORE Phase 4. Unlike `fwcwxv` it is code and factory-dispatchable. The item records the trap: `[]` is wrong for the five UNION keys only; it stays LEGITIMATE for the five CLEAN ones, and this check spans both. |
| `oitd` | **open, P1 — FILED this session. THE next action.** `fleet/_contract_rows.py` is **246 LLOC against a 250 HARD ceiling**, so the fleet obligation table accepts **no new row**: 257 with a full `manual_hint`, **254 even at the tersest legal form**. `OBLIGATION_ROWS` is the single table every lane reads, so the ceiling silently converts "add a fleet obligation" into "refactor the central table first" — and nothing announces that until the commit is written. Decompose it (a pure move; `OBLIGATION_ROWS` content and ordering MUST be unchanged), then register the parked Phase 3 row. |
| `fwcwxv` | **FILED as PR #773 — needs a MAINTAINER** | The spec propose-change. Four proposals: retire declared-empty for the union keys; preserve `[]` for the CLEAN keys with the stricter-not-blinder reason; ratify the constraint-based discriminator plus `unarmed_until` liveness; and the acceptance scenarios. **Filing is not ratifying** — accept or reject at `/livespec:revise`. **Phase 4 is gated on acceptance.** |
| `bd-ib-6qb2mc` | **blocked / needs-human — FILED this session, in the `beads-fabro` tenant** | Carve `livespec-orchestrator-beads-fabro`'s real pure tree. It is the named work that repo's `pure_trees = { unarmed_until = ... }` points at, so it is the ONLY open item whose closure is referenced from a parsed config value in another repo. **Do NOT close it by declaring `not_applicable`** — that re-hides an obligation its own ratified `constraints.md` imposes; if the constraint is wrong, amend the SPEC first. `blocked` is correct rather than a formality: verifying the result is mechanical, choosing the cut is architectural. |
| `pk2x` | backlog | Archive-on-epic-close — **ADOPT** ruled. Carries a note from this thread: a union makes `[]` unrepresentable after parsing, but **a key nobody wrote still parses to the default**, so pk2x's Exemption slot needs PRESENCE REQUIRED, not merely value well-formedness. |

**Possible stale item — VERIFY, do not assume:** `livespec-dev-tooling-fp5yfv` (2026-07-19,
BLOCKED) describes `red_green_replay._IMPL_PREFIXES` as a hardcoded list and *recommends deriving
impl paths from `source_tree_prefixes`* — which the code now does via `_derive_impl_prefixes`. It
may be already-fixed or largely superseded, and it overlaps `hgfnqd`. Check before grooming either.

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
2. `check-plan-thread-anchor-declared` — armed ONLY in the one repo with zero plan threads
   (`pk2x`); 18 of 20 fleet handoffs would fail it. An **ABSENCE** meaning consent, not an
   emptiness — a union does not fix that shape.
3. `file_lloc_hard_gate` — retired under `426a` for exactly this: "the omission read as
   conformance". Its retirement sequence is the migration template Phase 4 follows.
4. `commit_pairs` / `claude_md_coverage` / `tests_mirror_pairing` — disarmed by an empty role key
   (`8o8e.1`), and `commit_pairs` was disarmed by a declaration that named two OTHER checks.
5. `vendor_update` — the "only blessed re-vendor path" cannot target dev-tooling's own `_vendor/`.

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

**Check whether a test fixture supplies the very thing under test.**
`tests/livespec_dev_tooling/checks/conftest.py` overrides `tmp_path` to seed a FULL legacy
`[tool.livespec_dev_tooling]` block. A test in that directory that only creates files inherits it
and proves nothing. Overwrite `pyproject.toml` outright.

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
