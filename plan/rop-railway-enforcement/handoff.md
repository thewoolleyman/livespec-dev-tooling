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

**Phases 0 and 1 have LANDED.** The next step is **Phase 2 (the per-repo migration), which is NOT
yet authorized** — eight repos is its own authorization and the supervisor holds it. Do not touch a
sibling repo without it.

### State as of 2026-07-28 (RE-DERIVE — this ages in minutes)

| thing | state |
|---|---|
| `livespec-dev-tooling` master | re-derive; was `472bbfc` when this line was written |
| Phase 0 — commit-pairs coupling break (PR #755) | **merged `5f82dbe`, RELEASED in `v0.56.7`** |
| Phase 1 — accepting loader (PR #759) | **merged `8a61df6`, RELEASED in `v0.57.0`** (verified: `git tag --contains 8a61df6` → `v0.57.0`) |
| Sibling consumption | **SIX of seven carry `v0.57.0`** (re-derived on the forge 2026-07-28) — the gate has OPENED. Only `livespec-driver-codex` lags at `v0.56.7`, and #296 is stuck on a PyPI TIMEOUT rather than a defect. See the pin table below. **RE-DERIVE per repo.** |
| Piece B — `livespec-driver-claude` prose (PR #317) | **merged `e8c8847`** — first sibling complete on BOTH axes |

**MERGED ≠ RELEASED ≠ CONSUMED.** Keep the three separate in every status claim. Conflating them
re-creates this thread's core defect — a green signal that means nothing — at the process level.

### 📊 FLEET PROGRESS — 2 of 8 repos DONE on both axes; 23 keys left, and the counts are now MEASURED

Re-derived 2026-07-28 by fetching all eight `pyproject.toml` from the **FORGE** and loading each
through `master`'s union loader. This is a SCHEMA measurement under one loader — deliberately, so
only the config varies — and is **NOT** each repo's CI result under its own pin.

| repo | values | the un-migrated keys | prose |
|---|---|---|---|
| `livespec-dev-tooling` | ✅ 0 (`b27401c`) | — | ✅ **CLEAN** — Piece A |
| `livespec-driver-claude` | ✅ 0 (`c7c7272`) | — | ✅ **CLEAN** — Piece B (`e8c8847`) |
| `livespec` | ✗ **2** | `pure_trees`, `neutral_hook_body_path` | clean |
| `livespec-driver-codex` | ✗ **3** | `pure_trees`, `dataclasses_tree`, `target_dirs` | ⚠️ stale |
| `livespec-orchestrator-beads-fabro` | ✗ **3** | `pure_trees`, `dataclasses_tree`, `neutral_hook_body_path` | ⚠️ stale |
| `livespec-orchestrator-git-jsonl` | ✗ **5** | all five | clean |
| `livespec-overseer` | ✗ **5** | all five | clean |
| `livespec-runtime` | ✗ **5** | all five | ⚠️ stale |

**FLEET TOTAL: 23 `LegacyAmbiguousEmpty`.** The previous arithmetic estimate was correct — this
also names the exact KEYS, which subtraction could not. Note `livespec` is `pure_trees` +
`neutral_hook_body_path`, **NOT** `source_tree_prefixes`.

**`livespec-driver-codex` is NOT blocked by a defect — #296 died on a PyPI TIMEOUT.** The pin is
still `v0.56.7` and bump PR **#296** is `OPEN | MERGEABLE | BLOCKED`, but 62 of 64 checks pass and
the two failures are not check logic: `check-hook-trees-not-io-exempt` died in dependency INSTALL
(`Failed to download ruff==0.8.6 ... operation timed out`) and `ci-green` failed because that job
did. It is **one re-run away**, not incompatible with `v0.57.0`.

**Deliberately NOT re-run.** Auto-merge is enabled on #296, so a re-run CHANGES that repo's pin
rather than merely observing it — an authorization call, not a worker call. But decide it against
what is true: "gated on a flake" and "gated on an incompatibility" deserve different answers, and
the older record implied the second.

### ⚠️ PROSE STALENESS — Phase 2's definition of done is VALUES **AND** PROSE

The retired wording is a header that still says:

> "declare it explicitly empty (`[]` ... `""` ...) ... Declared-empty is the sanctioned, VISIBLE
> opt-out: the gating check no-ops and says so in a structured info event."

That is the pre-`8o8e.1` regime, wrong on every clause, and it **instructs the next reader to write
the exact spelling this epic removes**.

**THREE repos still carry it** (swept on the forge 2026-07-28): `livespec-driver-codex`,
`livespec-orchestrator-beads-fabro`, `livespec-runtime`. Five are clean: `livespec`,
`livespec-dev-tooling`, `livespec-driver-claude`, `livespec-orchestrator-git-jsonl`,
`livespec-overseer`.

**All three remaining are ALSO value-un-migrated, so prose and values can land in ONE commit for
every one of them.** Piece B was the last repo where the two were forced apart.

**Phase 3's conformance check counts VALUES, so it can NEVER catch this.** A repo with perfect
values and a header pointing the other way scores a clean zero, and the config drifts back one
honest author at a time while the check stays green.

Full detail — including the suggestion of a cheap literal-string companion check for Phase 3 — is
on `livespec-dev-tooling-8o8e.1`.

### ✅ PIECES A AND B — BOTH DONE. Two repos are now complete on BOTH axes

**Piece A** (`livespec-dev-tooling`, `8b5ab7f`): its header no longer claims five keys "stay
empty/null" while three carry variants.

**Piece B** (`livespec-driver-claude`, PR #317 → `e8c8847`): the **first sibling** complete on both
axes, and necessarily a STANDALONE prose PR since its values had already landed in `c7c7272`.

Piece B fixed **two** stale sites, not one. The known one was the `IMPORTANT` header. Re-reading the
WHOLE block after the local edit — the discipline this thread keeps re-learning — turned up a
second: the fleet-check-coverage paragraph closed with "the remaining heavy product-tree role keys
are explicitly declared empty below", and three of them are not empty anymore. **Budget for the
second stale sentence in every remaining repo; the grep for the known wording will not find it.**

Its header now states the two-group split explicitly, including the part most likely to be lost in
a rewrite: the CLEAN keys keep `[]` as a LEGITIMATE spelling, because for them empty makes the
consuming check STRICTER rather than blinder. **Reuse that header as the template for the remaining
three.**

Values were verified UNCHANGED by measurement before and after the diff (`LegacyAmbiguousEmpty`
count 0 both times), `just check` green, 64/64 CI checks pass.

**Remaining prose work is THREE repos, and every one rides along with its values:**

| repo | prose | values | how to land it |
|---|---|---|---|
| `livespec-driver-codex` | ⚠️ stale | ✗ 3 keys — pin `v0.56.7` | ride-along — **but prose is NOT pin-gated and can land first** |
| `livespec-orchestrator-beads-fabro` | ⚠️ stale | ✗ 3 keys | ride-along: prose + values in ONE commit |
| `livespec-runtime` | ⚠️ stale | ✗ 5 keys | ride-along: prose + values in ONE commit |

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

### ▶️ EXACT NEXT ACTION

1. **The six remaining slices are all "values AND prose in ONE commit"** — Piece B was the last
   repo where the two were forced apart. **NONE of the six is authorized yet.** Exact key lists are
   in the fleet-progress table; they are measured, not arithmetic.
2. `livespec` is the delicate one — its `pure_trees` is the fleet's one known
   **(B) `unarmed_until = "livespec-mutreal.1"`** and must not be downgraded to `not_applicable`
   because that reads tidier. Its other un-migrated key is `neutral_hook_body_path`, **not**
   `source_tree_prefixes`.
3. **Decide `livespec-driver-codex` against the corrected diagnosis.** #296 failed on a PyPI
   download timeout, not on incompatibility — a re-run likely lands it and opens that lane. Auto-
   merge is on, so re-running is a state change in a fenced repo and needs authorization. Its
   PROSE fix is not pin-gated in any case.
4. Execute `livespec-dev-tooling-fwcwxv` — the spec propose-change for
   `SPECIFICATION/contracts.md` §"Consumer configuration schema". Already FILED; it needs a
   maintainer, **before Phase 4**, via `/livespec:propose-change` and never a direct edit.
5. Execute `livespec-dev-tooling-pj3j` — this repo's OWN `MISSING_KEYS_EVENT` and `Config`
   docstring still teach the retired spelling. **Before Phase 4**, for the same reason as `fwcwxv`:
   after Phase 4 that remediation text routes its reader straight into a `ConfigParseError`.
   Unlike `fwcwxv` it is code, autonomously verifiable, and factory-dispatchable.
6. Phase 3 (conformance check + a cheap literal-string companion check for the prose shape, which
   the value-counting check structurally cannot catch), then Phase 4 (rejecting loader) — which
   cannot land until all eight have migrated. Epic rule, non-negotiable.

### SIBLING PINS — the gate has OPENED for six of seven

Measured on the FORGE 2026-07-28. **This ages in minutes; re-derive per repo, never act on it:**

| repo | pin | |
|---|---|---|
| livespec | `v0.57.0` | migratable |
| livespec-driver-claude | `v0.57.0` | ✅ **DONE** — values `c7c7272`, prose `e8c8847` |
| livespec-orchestrator-beads-fabro | `v0.57.0` | migratable |
| livespec-orchestrator-git-jsonl | `v0.57.0` | migratable |
| livespec-overseer | `v0.57.0` | migratable |
| livespec-runtime | `v0.57.0` | migratable |
| **livespec-driver-codex** | `v0.56.7` | #296 open; **fails on a PyPI timeout, not a defect**. Do not touch without authorization — auto-merge is on. |

**Piece B is DONE and NOTHING is currently authorized.** All six remaining siblings are a separate
authorization. `livespec-driver-codex` is gated on #296 — which is a re-run away, not a real
incompatibility.

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

**The Phase 2 work list is derivable by RUNNING the loader. It was 29 (repo, key) pairs; slice 1
migrated this repo's 3 and slice 2 migrated `livespec-driver-claude`'s 3, leaving 23 — all of them
in siblings.** The per-repo breakdown with the exact KEYS is the fleet-progress table near the top
of this file; it is measured, and this paragraph is the history rather than the work list.

Enforcement shape: two exhaustive `match` sites carry `assert_never` (`config.role_absence`,
`_role_key_gate._announce_absence`) and every consumer routes through one, so a future variant
breaks the type gate rather than silently inheriting scan-nothing. When the five field types
changed, pyright enumerated all fourteen consumers — that is the mechanism working.

---

## ▶️ PHASE 2 — slices 1 AND 2 DONE; NOTHING currently authorized

**Precondition, and it is PER-REPO, not fleet-wide:** a sibling cannot adopt a blessed spelling
until **its own pin** carries the accepting loader. Adopting earlier fails that repo's `just check`
with a `ConfigParseError` on an inline table its pinned loader cannot parse. Bump PRs land
independently and at different times, so check each repo's pin before touching it.

Sequence, and the first two steps are DONE: `v0.57.0` released → `release-dispatch` fans out →
each sibling gets an auto-merge `chore(deps):` bump PR → **only then** is that repo migratable.

So Phase 2's gating question is now purely **"has THIS repo's bump PR landed yet?"** Check the
pin on the FORGE per repo (`[tool.uv.sources]` `tag = "vX.Y.Z"`, ≥ `v0.57.0`) before migrating it.

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

### ▶️ NEXT SLICE: six siblings, NONE authorized yet

Two of eight are DONE on both axes (`livespec-dev-tooling`, `livespec-driver-claude`). Six of seven
siblings carry `v0.57.0`, so the PIN gate is no longer what holds the rest — the AUTHORIZATION is.
Per-repo remaining counts and the exact un-migrated KEYS are in the fleet-progress table near the
top; they are now **measured on the forge, not arithmetic**.

`livespec`'s `pure_trees` is the fleet's one known **(B) `unarmed_until = "livespec-mutreal.1"`** —
do NOT downgrade it to `not_applicable` because that reads tidier. Telling (B) from (A) apart is the
entire point of the union, and `livespec-driver-claude` already proved (C) `superseded_by` holds
under real conditions.

Every remaining slice migrates **values AND prose together** — see the prose-staleness section.

Then **Phase 3** (a fleet-conformance check asserting zero `LegacyAmbiguousEmpty` across all eight —
this IS the closure precondition's evidence) and **Phase 4** (the rejecting loader; `[]` becomes a
hard `ConfigParseError`), per the `livespec-dev-tooling-426a` retirement template: verify everyone
conforms, THEN remove the lever, so the flip changes no repo's result on the day it lands.

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
