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
| `livespec-dev-tooling` master | `89b5ec0` (`chore(master): release 0.57.0`) |
| Phase 0 — commit-pairs coupling break (PR #755) | **merged `5f82dbe`, RELEASED in `v0.56.7`** |
| Phase 1 — accepting loader (PR #759) | **merged `8a61df6`, RELEASED in `v0.57.0`** (verified: `git tag --contains 8a61df6` → `v0.57.0`) |
| Sibling consumption | **SIX of seven now carry `v0.57.0`** — the gate has OPENED. Only `livespec-driver-codex` lags at `v0.56.7` (bump PR #296 stuck). See the pin table below. **RE-DERIVE per repo.** |

**MERGED ≠ RELEASED ≠ CONSUMED.** Keep the three separate in every status claim. Conflating them
re-creates this thread's core defect — a green signal that means nothing — at the process level.

### 📊 FLEET PROGRESS — 2 of 8 repos migrated

| repo | values migrated | prose stale? |
|---|---|---|
| `livespec-dev-tooling` | ✅ `b27401c` (3 keys) | ⚠️ **YES — Piece A below** |
| `livespec-driver-claude` | ✅ `c7c7272` (3 keys) | ⚠️ **YES — see prose finding** |
| `livespec` | ✗ 2 keys | clean |
| `livespec-orchestrator-beads-fabro` | ✗ 3 keys | ⚠️ YES |
| `livespec-driver-codex` | ✗ 3 keys — **PIN-BLOCKED** | ⚠️ YES |
| `livespec-orchestrator-git-jsonl` | ✗ 5 keys | clean |
| `livespec-overseer` | ✗ 5 keys | clean |
| `livespec-runtime` | ✗ 5 keys | ⚠️ YES |

**⚠️ THE REMAINING PER-REPO COUNTS ARE ARITHMETIC, NOT A FRESH MEASUREMENT.** They are the
original 29-pair fleet measurement minus the two migrated repos. **Re-run the count per repo before
acting on it** — the numbers are a starting point, not evidence. (Running it: import each of the
six union-consuming checks in the target repo and tally
`role_key_spelling == "legacy-ambiguous-empty"` records.)

`livespec-driver-codex` is PIN-BLOCKED: pin `v0.56.7`, bump PR **#296** open and unable to land. Its
VALUES cannot migrate until that lands — but its PROSE fix is independent of the pin.

### ⚠️ PROSE STALENESS — Phase 2's definition of done is VALUES **AND** PROSE

`livespec-driver-claude` has correct values and a header that still says:

> "declare it explicitly empty (`[]` ... `""` ...) ... Declared-empty is the sanctioned, VISIBLE
> opt-out: the gating check no-ops and says so in a structured info event."

That is the pre-`8o8e.1` regime, wrong on every clause, and it **instructs the next reader to write
the exact spelling this epic removes** — in a repo whose values are already migrated.

Four repos carry that wording (re-derived from the forge): `livespec-driver-claude`,
`livespec-driver-codex`, `livespec-orchestrator-beads-fabro`, `livespec-runtime`. Four are clean:
`livespec`, `livespec-dev-tooling`, `livespec-orchestrator-git-jsonl`, `livespec-overseer`.
(`livespec-dev-tooling` carries a DIFFERENT variant of the same defect — Piece A.)

**Phase 3's conformance check counts VALUES, so it can NEVER catch this.** A repo with perfect
values and a header pointing the other way scores a clean zero, and the config drifts back one
honest author at a time while the check stays green. For repos not yet migrated, prose and values
can land in ONE commit.

Full detail — including the suggestion of a cheap literal-string companion check for Phase 3 — is
on `livespec-dev-tooling-8o8e.1`.

### ⏭️ PIECE A — dev-tooling's own stale header, UNBLOCKED, NOT LANDED

Master CI was red from a GitHub App rate limit (installation `131208965`) hit by
`check-fleet-conformance`, which reads siblings live. **That has since been re-run and master is
GREEN**, so this is no longer blocked. Recorded because the lesson survives the incident: a
fleet-state check can redden master with **no commit responsible**, and it clears on RESET, not on
retry — do not burn re-runs during a limit, and do not go hunting for a commit to revert.

`pyproject.toml` (this repo) lines ~96-100 still describe five role keys as staying "empty/null",
but `pure_trees` and `dataclasses_tree` now carry `{ not_applicable = ... }` and
`neutral_hook_body_path` — absent from that list entirely — does too.

Replace the block beginning `# The remaining role keys (io_trees, commands_trees, dataclasses_tree,`
and ending `` # `source_trees` universe. `` with a header stating: `io_trees`, `commands_trees`,
`covered_trees` stay a bare `[]` because they are EXEMPTION / SEVERITY predicates whose consuming
checks derive the universe from `resolve_check_universe()`, so empty makes them STRICTER never
blinder; and `pure_trees`, `dataclasses_tree`, `neutral_hook_body_path` are no longer empty because
their `[]` / `""` carried two incompatible meanings and each now declares a blessed variant carrying
its reason in the parsed value. Config-only — no RGR ritual, normal worktree → PR path.

### ✅ PIECE B — DONE. `livespec-driver-claude` migrated (merged `c7c7272`)

The first CROSS-REPO cut, and it proved two things slice 1 could not: the sibling path works
end-to-end under that repo's own AGENTS.md discipline and its own pinned `v0.57.0` loader (65-target
`just check` green), and **`superseded_by` works** — the fleet's first non-`not_applicable` variant.

`target_dirs = { superseded_by = "git-derived first-party universe owns the hook coverage" }`
is deliberately (C) and NOT (A): the concept applies there and IS satisfied, by
`resolve_check_universe()`. **Do not downgrade a (C) or a (B) into `not_applicable` because it reads
tidier** — `livespec`'s `pure_trees` is the fleet's one known **(B) `unarmed_until =
"livespec-mutreal.1"`** and must stay that way.

Verified on merged master by RUNNING it: `LegacyAmbiguousEmpty` 3 → 0.

### ▶️ EXACT NEXT ACTION

1. Land **Piece A** (above) — config-only, unblocked, this repo.
2. Then the five unauthorized siblings, one slice at a time, **values AND prose together**.
   `livespec` is the delicate one (its `pure_trees` is the (B) case).
3. `livespec-driver-codex` values wait on **#296**; its prose need not.
4. Phase 3 (conformance check + consider the prose companion check), then Phase 4 (rejecting
   loader) — which cannot land until all eight have migrated. Epic rule, non-negotiable.

### SIBLING PINS — the gate has OPENED for six of seven

Measured on the FORGE 2026-07-28. **This ages in minutes; re-derive per repo, never act on it:**

| repo | pin | |
|---|---|---|
| livespec | `v0.57.0` | migratable |
| livespec-driver-claude | `v0.57.0` | ✅ **MIGRATED** (`c7c7272`) |
| livespec-orchestrator-beads-fabro | `v0.57.0` | migratable |
| livespec-orchestrator-git-jsonl | `v0.57.0` | migratable |
| livespec-overseer | `v0.57.0` | migratable |
| livespec-runtime | `v0.57.0` | migratable |
| **livespec-driver-codex** | `v0.56.7` | **BLOCKED — bump PR #296 open and unable to land. Do not touch.** |

**Only Piece B (`livespec-driver-claude`) is authorized.** The other five siblings are a separate
authorization, and `livespec-driver-codex` is genuinely gated on #296.

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

**The Phase 2 work list is derivable by RUNNING the checks. It was 29 (repo, key) pairs; slice 1
migrated this repo's 3, leaving 26 — all of them in siblings.**

| repo | un-migrated | | repo | un-migrated |
|---|---|---|---|---|
| livespec | 2 | | livespec-orchestrator-beads-fabro | 3 |
| livespec-dev-tooling | **0 — MIGRATED** | | livespec-orchestrator-git-jsonl | **5** |
| livespec-driver-claude | 3 | | livespec-overseer | **5** |
| livespec-driver-codex | 3 | | livespec-runtime | **5** |

Enforcement shape: two exhaustive `match` sites carry `assert_never` (`config.role_absence`,
`_role_key_gate._announce_absence`) and every consumer routes through one, so a future variant
breaks the type gate rather than silently inheriting scan-nothing. When the five field types
changed, pyright enumerated all fourteen consumers — that is the mechanism working.

---

## ▶️ PHASE 2 — slice 1 DONE; ONE sibling authorized, the rest not

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

### ▶️ NEXT SLICE: five siblings, NONE authorized yet

Two of eight are migrated (`livespec-dev-tooling`, `livespec-driver-claude`). Six of seven siblings
carry `v0.57.0`, so the PIN gate is no longer what holds the rest — the AUTHORIZATION is. Per-repo
remaining counts are in the fleet-progress table near the top, **with the caveat that they are
arithmetic rather than a fresh measurement.**

`livespec`'s `pure_trees` is the fleet's one known **(B) `unarmed_until = "livespec-mutreal.1"`** —
do NOT downgrade it to `not_applicable` because that reads tidier. Telling (B) from (A) apart is the
entire point of the union, and `livespec-driver-claude` already proved (C) `superseded_by` holds
under real conditions.

Every remaining slice migrates **values AND prose together** — see the prose-staleness section.

---|---|---|---|---|
| livespec | 2 | | livespec-orchestrator-git-jsonl | 5 |
| livespec-driver-claude | 3 — **Piece B** | | livespec-overseer | 5 |
| livespec-driver-codex | 3 — **pin-blocked** | | livespec-runtime | 5 |
| livespec-orchestrator-beads-fabro | 3 | | | |

`livespec`'s `pure_trees` is the one known **(B) `unarmed_until = "livespec-mutreal.1"`** in the
fleet — do NOT downgrade it to `not_applicable` because that reads tidier. Telling (B) from (A)
apart is the entire point of the union.

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
