# Worktree-location enforcement — close the three fail-open layers

**Ledger anchor:** epic `livespec-dev-tooling-0eo`

**SLICES ARE FILED (2026-07-26).** All seven approved records live under the epic and are
intake-routed — see §"MAINTAINER RULING — FINAL CUT APPROVED AND FILED" for ids, states,
dependency edges, and lane evidence. *(This line previously read "No slices filed. The epic
is the thread's ledger identity only; A–E below are NOT work-items." That was true until the
final cut was approved.)*

**Opened:** 2026-07-20, out of a live violation in `livespec-console-beads-fabro`
(incident summary below). The original analysis was verified against `origin/master`
at **`2412e21`**.

**Remeasured 2026-07-25** against `origin/master` at **`413a407`** — 131 commits
later. See §"Reactivation audit — 2026-07-25" at the end of this file for the
measured delta, the corrections to premises that were wrong when written, and the
facts below that survived. Inline numbers and anchors in this file have been
updated to the 2026-07-25 measurement; do not reason from the `2412e21` counts.

---

## MAINTAINER RULING — full-location scope APPROVED (2026-07-25)

**This supersedes the definition-of-done question and every scope statement in this file
that assumes a nested-only cut.**

The maintainer ruled that this thread MUST enforce **both** clauses of
`livespec/SPECIFICATION/non-functional-requirements.md:1013`:

1. **No worktree may live inside any repository clone** (the negative clause — what the
   former item B addressed).
2. **Every governed fleet worktree must live under `~/.worktrees/<repo>/<branch>`** (the
   positive clause — what nothing addressed).

Therefore the definition of done is **wider than the former A–E nested-only cut**.

*(Superseded detail, 2026-07-25: this section originally re-drew the cut "with an **F**
slice for the adopter baseline". The subsequent NARROW boundary ruling removed F from this
thread — see §"MAINTAINER RULING — NARROW boundary". **The current final cut is A, B, C, D,
E, and optionally G.** Adopter baseline work is a separate follow-up, filed as `li-l53` and
`hl-nhw`.)*

### The ruling makes item B SIMPLER, not harder

Worth stating plainly because the opposite is the natural assumption. A nested-only rule
needs *nested detection* — compute the primary root, compare prefixes, then carve out
`.git/`. A positive-location rule needs only an **allow-list**:

```sh
case "$this_root/" in
  "$common_abs"/*)  ;;                       # tooling-internal (beads sync) — ALLOW
  "$sanctioned"/*)  ;;                       # under ~/.worktrees — ALLOW
  *)                refuse_unsanctioned ;;   # everything else — REFUSE
esac
```

**Clause 1 falls out of clause 2 for free**: anything inside a clone is, by construction,
not under `~/.worktrees/`, so it is refused without a separate nested test. The
`primary_root` computation and the prefix comparison both disappear. Rehearsed read-only
across all 40 worktrees on this host: 34 `ALLOW-SANCTIONED` (including all 5 orchestrator
`janitor-*`), 4 `ALLOW-TOOLING`, **2 `REFUSE`, zero false positives**.

Two scope notes on the clauses as worded. Clause 1 says "any repository clone", which is
broader than "governed" — but the hook only runs where it is installed, so the practical
enforcement surface is the governed set either way. And clause 2 is scoped to *governed
fleet* worktrees.

*(Superseded, 2026-07-25: this paragraph originally concluded that "the adopter baseline
(slice F) is load-bearing". Under the NARROW ruling it is **not load-bearing for this
thread** — clause 2 binds the 9 `fleet` repos, all of which have the substrate, so B and D
alone satisfy it. The observation that three governed adopters run no livespec hook remains
true and is the FOLLOW-UP's subject, tracked as `li-l53` and `hl-nhw`.)*

### Re-measured before re-cutting (2026-07-25T15:35Z)

Per the ruling's instruction not to rely on earlier counts:

| dimension | measurement |
|---|---|
| `origin/master` | `c16f358` (24 commits past the audit's `413a407` start) |
| ledger epic `livespec-dev-tooling-0eo` | still **BACKLOG**, **no children**, updated 2026-07-20 |
| fleet membership | **9 fleet members + 3 adopters** (openbrain/pinned, resume/pinned, homelab/released); unchanged |
| installed hooks | **9 of 9 fleet clones canonical** (`3a3f60cbd4d2`); openbrain a **stub/other**; resume and homelab **none** |
| verifier wired | **9 of 9 fleet**; **0 of 3 adopters** |
| pack wiring (gitignore + 2 `import?` + recipe) | **full in 3** (`…beads-fabro`, `…git-jsonl`, `…console`); **absent in 6 fleet + 3 adopters** |
| pack materialized | **1** (`livespec-orchestrator-git-jsonl`) |
| worktrees on host | **40** |
| live violations under BOTH clauses | **2**, both nested, both in governed repos: `livespec-overseer/.claude/worktrees/dod-corrections` (fleet member; **another session's — do not touch**) and `openbrain/.claude/worktrees/fix-ob-6vt-…` (adopter; inspected, safe to move) |

No peer-case violation is live right now (`homelab-substrate` was removed by the `homelab`
track mid-audit), but the class remains unenforced until B widens.

### The re-cut

**A — verifier: absent pack becomes a FAIL, gated on config, AND discoverability asserted.**
Scope-corrected twice over. Adds the `worktree_discipline.pack` read (absent key → default
`required`; `optional` → skip; malformed → FAIL) **and** an assertion that the two
`import?` lines are present, without which a byte-perfect pack passes while `just --list`
shows nothing. Prerequisites in the same slice: a `worktree-pack` LOCAL obligation row so
`just bootstrap` self-heals, and a CI install step mirroring `ci.yml:409-411` — without
them A reds this repo's own CI on its landing PR. Product `.py` → Red–Green–Replay.

**B — hook: positive-location enforcement (supersedes nested-only).** The allow-list `case`
above, satisfying both clauses. Carries the sandbox-exempt guard (an exempt primary falls
through the earlier arm and would otherwise be refused — measured), a decision on the
spec's janitor carve-out for worktrees inside an integration clone, and a rename of the
shadowed `git_dir`. Honest limit unchanged: no `pre-worktree-add` hook exists, so this
fires at first *commit*. Product `.py` → Red–Green–Replay.

**C — installer + docs write the key with its default.** Unchanged.

**D — fleet wiring + hydration sweep.** **6 tracked wiring PRs** (`livespec`,
`livespec-dev-tooling`, `livespec-driver-claude`, `livespec-driver-codex`,
`livespec-runtime`, `livespec-overseer`), ~10 lines each, modelled on
`livespec-orchestrator-git-jsonl`; plus `just bootstrap` in the 2 wired-but-unhydrated
repos, which need no PR at all.

**E — relocate the live nested worktrees.** openbrain's is inspected and safe
(clean tree, unpushed `296dd1f`, no upstream, no live owner). `livespec-overseer`'s
belongs to **another session** and must not be touched without its owner — E cannot close
unilaterally.

**F — adopter baseline and positive-location reach. NOT IN THIS THREAD (narrow boundary
ruling, 2026-07-25).** F was originally cut as "required by the ruling" on the assumption
that clause 2 might bind all 12 governed repos. The **narrow boundary is now approved** —
this thread enforces both clauses across the **9 `fleet` repos only** (§"MAINTAINER RULING
— narrow boundary"). All 9 already carry the substrate, so **clause 2 is met by B and D
alone and F carries no work for this thread.**

Adopter enforcement is a **separate follow-up**, already filed as two blocked backfill
work-items (`li-l53` in the resume tenant, `hl-nhw` in the homelab tenant) — see the ruling
section for their scope. openbrain has no backfill item yet; **E still retains the safe
openbrain relocation**, which is hygiene and needs no substrate.

Retained here for context only: clause 2 is unenforceable in the three governed adopters
today — openbrain runs a stock lefthook stub, resume and homelab run no livespec hook, and
none of the three wires the verifier — and two **bespoke location-blind implementations**
(`openbrain/scripts/refuse-primary-commit.sh`, `resume/scripts/check-primary-checkout.ts`)
remain unreconciled. That is now the follow-up's subject, not this thread's.

**G — birth procedure (NEW, proposed; deferrable).** Only `impl-plugin` has a copier
template, and it is the fully-compliant one. Members of the other six classes are
hand-scaffolded and born unwired — `livespec-overseer` is the proof, and it is also where
the second live violation appeared. Without G the sweep fixes the population and not the
generator, and clause 2 decays with each new member. Not strictly required for clause 2 to
be true today, so the maintainer may defer it; it should be a decision, not an omission.

**Sequencing dependencies** (not an approved order — see §rollout): A's prerequisites must
land before A's default flips or this repo's CI reds; D's wiring must exist before A's FAIL
is actionable in the 6 unwired repos; **F is no longer in this thread** and gates nothing
here (NARROW ruling — clause 2's reach across the 9 `fleet` repos is delivered by B and D);
E is independent of everything and half-blocked on another session; G is independent.

### Adopter substrate is NOT uniform — measured 2026-07-25 (now the FOLLOW-UP's input, not F's)

Per the narrow ruling this no longer scopes a slice in this thread; it is retained because
it is the evidence the two filed backfill items (`li-l53`, `hl-nhw`) are built on.

F was originally written as "install the canonical hook and wire the verifier in openbrain,
resume, and homelab". **As stated it was not executable in two of the three.** What each
adopter can actually run:

| adopter | justfile | mise config | lefthook | dev-tooling package | verdict |
|---|---|---|---|---|---|
| **openbrain** | yes | `.mise.toml` | yes | **vendored** `livespec_dev_tooling/` | **reachable** |
| **resume** | **no** | **`mise.toml`** (present) | no | no | needs substrate; has a Bun/TS harness |
| **homelab** | **no** | no | no | no | **no substrate**; dependency-free POSIX hook only |

**Correction (2026-07-25):** an earlier version of this table recorded resume as having no
mise config. That was wrong — it was measured by testing for `.mise.toml`, and resume's file
is **`mise.toml`** (no leading dot). resume also has `.githooks/pre-commit`, `package.json`,
`bun.lock`, and `scripts/check-primary-checkout.ts`. Its route is native TypeScript parity
*or* a deliberate substrate change — **not** an accidental import of Python/`just`. `li-l53`
records that explicitly.

- **openbrain** has a `just` surface, mise, lefthook, and a vendored `livespec_dev_tooling/`
  package, so it can run the installer and host a verifier recipe. Its work is real but
  bounded: install the canonical hook over the stock lefthook stub, wire the verifier, and
  reconcile `scripts/refuse-primary-commit.sh` so there is one location-aware rule.
- **resume** — corrected measured state (an earlier version of this bullet said it "carries
  only a `package.json`", which understated it). resume has a **Bun/TypeScript harness**
  (`package.json`, `bun.lock`), a **`mise.toml`** (note: no leading dot — the earlier
  measurement wrongly tested for `.mise.toml`), a **bun bootstrap hook installer**,
  **`.githooks/pre-commit`**, and **`scripts/check-primary-checkout.ts`**. What it does NOT
  have is a `just` surface, a lefthook config, or any Python runtime — so the canonical
  Python/`just` delivery path cannot simply be dropped in. Its own check is TypeScript
  because that is its ecosystem, not because it lacks tooling. Route is native TypeScript
  parity **or** a deliberate substrate change; `li-l53` records that decision explicitly so
  Python or `just` is never imposed by accident. **This is follow-up input, not this
  thread's work.** The canonical hook body is portable `/bin/sh` and could be placed by
  hand, but the *installer* and the *verifier* are Python and cannot run there today.
- **homelab** has none of the four. The manifest itself records why: all its wiring is
  *"DEFERRED to the post-seed onboarding pass"* — an onboarding this thread does not own.

**Consequence: clause 2 cannot be fully realized by this thread alone under a broad
reading.** F splits into F1 (openbrain — do it), F2 (resume — blocked on baseline
substrate), F3 (homelab — blocked on a manifest-declared onboarding owned elsewhere).

### A scoping edge in the ruling's clause 2 — needs one word from the maintainer

Clause 2 reads *"every governed **fleet** worktree must live under
`~/.worktrees/<repo>/<branch>`"*. The manifest draws that distinction explicitly
(`.livespec-fleet-manifest.jsonc:38-40`): adopters are *"governed repos … that adopted the
workflow but are **NOT the livespec fleet**"*.

So there are two readings, and they size F very differently:

- **Narrow (fleet = the 9 manifest `fleet` entries).** All 9 already have the substrate —
  justfile, mise, the verifier, and a canonical hook. F reduces to **nothing**, and clause 2
  is fully achievable by B + D alone. F1–F3 become a separate hardening thread.
- **Broad (all 12 governed repos).** F is required, and two thirds of it is blocked on
  substrate and onboarding work this thread does not own — so the thread cannot reach
  "done" without adopting or waiting on that work.

This is **not** a re-litigation of the approved scope; both clauses stand either way. It is
a question of which repo set clause 2 binds, and it changes whether F is in this thread or
the next one. It should be answered alongside rollout order, not after slices are filed.
**[ANSWERED — NARROW.** Clause 2 binds the 9 `fleet` repos
(§"MAINTAINER RULING — NARROW boundary"). F is **not** in this thread; adopter backfill is
`li-l53` and `hl-nhw`.**]**

## MAINTAINER RULING — rollout order: Option 3, hook-first, APPROVED (2026-07-25)

**Approved ordering:** early positive-location hook enforcement, **paired with an
actionable remedy message**, followed by pack prerequisites and fleet wiring, and only then
the required-default flip.

```
E (openbrain half only)  →  B + remedy-string fix  →  A-prereq  →  D-wiring  →  A-flip
```

**Two notes on what this diagram does and does not say.**

- **F is deliberately absent.** An earlier rendering of this diagram ended
  `… → A-flip → F → (G)`. The later **NARROW boundary ruling removed F from this thread**
  entirely (§"MAINTAINER RULING — NARROW boundary"), so a current ruling diagram must not
  carry it. Adopter coverage is follow-up work tracked as `li-l53` and `hl-nhw`.
- **C and G are unplaced, and that is not an oversight.** The rollout ruling specified early
  hook enforcement with an actionable remedy, then pack prerequisites and fleet wiring,
  then the required-default flip. It did **not** place **C** (installer + docs write the key
  with its default) or **G** (birth procedure). **Their placement remains part of final-cut
  approval** and must not be inferred from this diagram.

Read the three options below for the evidence behind the choice; they are retained as the
record of what was weighed, not as live alternatives.

**Dependencies the ruling explicitly preserves — do not paper over these:**

- **E is only half-closable by this thread.** openbrain's nested worktree is inspected and
  safe to move (clean tree, unpushed `296dd1f`, no upstream, no live owner).
  `livespec-overseer/.claude/worktrees/dod-corrections` belongs to **another live session**;
  this thread has no authority over it and MUST NOT touch it. E closes for openbrain and
  stays open for the overseer worktree until its owner acts. Do not record E as done on the
  openbrain half alone.
- **B needs that session warned before it reaches the overseer clone.** Once B's hook is
  installed there, commits from that worktree are refused. B takes effect per clone only on
  hook reinstall (`just bootstrap`), so the rollout is operator-paced — use that pacing
  rather than assuming the session will notice.
- **Adopter substrate does not exist in two of three.** resume has no `just` surface, no
  lefthook, and no way to run a Python installer; homelab has none of the four and the
  manifest declares its wiring DEFERRED to an onboarding pass this thread does not own.
  **Superseded as an F-scoping note by the narrow ruling** — this is now the follow-up's
  input (`li-l53`, `hl-nhw`), not a slice in this thread.
- **The remedy message is part of B, not a follow-up.** `_WORKTREE_PACK_REMEDY` names
  `just install-worktree-pack`, which does not exist in 5 of 9 fleet repos. Shipping B
  before that is fixed produces refusals whose stated remedy fails.

**Nothing is gated any more — the final cut was APPROVED and FILED 2026-07-26** (see that
ruling section for ids, states and lanes). *(This line previously read "Still gated, and
blocking slice filing: the FINAL CUT only.")* The fleet-boundary
question below was ANSWERED — narrow (§"MAINTAINER RULING — NARROW boundary"). Nothing may
be filed as a dev-tooling implementation slice, moved, dispatched, or implemented until the
final cut is approved.

## MAINTAINER RULING — FINAL CUT APPROVED AND FILED (2026-07-26)

The four open questions were answered **exactly as recommended**: (1) split A into A1 and
A2 as two work-items; (2) place C in the same work-item as A2; (3) defer G but file it as a
tracked follow-up; (4) file E-overseer now as blocked on the owning session.

**All seven records are filed under epic `livespec-dev-tooling-0eo` and intake-routed.**

| # | slice | id | state | depends on |
|---|---|---|---|---|
| 1 | **E-openbrain** — relocate | `livespec-dev-tooling-0eo.1` | **ready** | — |
| 2 | **B** — positive-location hook + remedy | `livespec-dev-tooling-6fmfzk` | **ready** | — |
| 3 | **A1** — obligation row + CI step + self-wiring | `livespec-dev-tooling-cmc3ah` | pending-approval | 2 |
| 4 | **D** — fleet wiring + hydration sweep | `livespec-dev-tooling-o5vltq` | pending-approval | 3 |
| 5 | **A2 + C** — flip + discoverability + docs | `livespec-dev-tooling-skl77m` | pending-approval | 3, 4 |
| 6 | **E-overseer** — relocate | `livespec-dev-tooling-3iizsd` | **blocked** | cross-session (prose) |
| 7 | **G (DEFERRED)** — birth procedure | `livespec-dev-tooling-xxdxqv` | **backlog** | — |

Every record verified: exists exactly once, parented to the epic, `origin:freeform`,
`intake:triaged`, **no `gap_id`**, no `spec_commitment_hint`, `assignee` unset (records
expose the tenant/default owner `chad@thewoolleyman.com`). Dependency edges materialize as
real `[blocks]` relations — `bd dep tree` shows `5 → {3, 4}` and `4 → 3 → 2`.

**Lane evidence.** Only **`0eo.1` and `6fmfzk`** are in the ready lane. `cmc3ah`, `o5vltq`,
`skl77m`, `3iizsd`, and `xxdxqv` are each verified **absent** from it. Note `bd ready`
reports "No open issues" because it selects `status=open`; the orchestrator ready lane is
`status=ready`, so `bd list --status ready` is the correct check.

**G cannot dispatch as current-cut work**: routed to `backlog`, which is not the ready lane.
Its checklist recorded `single_coherent_done=False` honestly — G's scope (this thread vs.
the birth-procedure lane) is undecided, so it is not yet one coherent done-state.

**E-overseer routes blocked** via `dependency_linked=False`, which is the honest gate
answer: its real blocker is another live session's ownership of the worktree, which is not
a beads issue and therefore **has no id to depend on**. It carries
`blocked-reason:needs-human` and states in prose that the absence of a blocking edge is by
construction, not evidence of readiness.

### How they were filed — and a capability gap worth recording

Filed via the required capture path: `append_work_item` (the orchestrator capture
operation) → same-tenant `bd update --parent livespec-dev-tooling-0eo` → shared
`apply_intake_dor`. Raw `bd create` was **not** used for items 2–7, because it bypasses the
shared intake gate.

**The capability gap, confirmed in the distributed code:** `WorkItem` has **no parent
field** (24 fields enumerated; `parent-ish: NONE`), and `new_work_item_id` emits a flat
`<prefix>-XXXXXX` id, so the capture operation cannot place a record under an epic at
capture time. `bd update --parent` bridges it in the same tenant. The visible consequence
is a **mixed id shape** — `0eo.1` was born hierarchical via an earlier `bd create --parent`,
the rest are flat ids reparented afterwards. Cosmetic; all seven are true children.

**Runtime note:** the orchestrator modules are NOT importable from `livespec-dev-tooling`'s
uv environment (`livespec_runtime` absent). The correct runtime is the **distributed
plugin's own bootstrap** — `.claude-plugin/scripts/bin/_bootstrap.py`, which inserts
`scripts/` and `scripts/_vendor/` (where `livespec_runtime` is vendored) and self-heals
credentials. Do not inject a sibling checkout and do not treat dev-tooling's uv env as the
operation runtime.

### Exact next action

**Work `livespec-dev-tooling-6fmfzk` (B)** — it and `0eo.1` are the only ready items, and B
is first in the approved hook-first order. Before B reaches the `livespec-overseer` clone,
**warn the session owning `.claude/worktrees/dod-corrections`**; B takes effect per clone
only on `just bootstrap`, so the rollout is operator-paced.

*(Historical: the proposal below is what was approved. Retained as the record of what was
put to the maintainer.)*

## PROPOSED FINAL CUT — as presented 2026-07-25 (APPROVED; see the ruling above)

**Status: APPROVED and filed** — see §"MAINTAINER RULING — FINAL CUT APPROVED AND FILED".
The four questions at the end were all answered as recommended.

### Exact sequence

```
E(openbrain)  →  B + remedy  →  A1-prereq  →  D-wiring  →  A2-flip + C  →  (G deferred)
```

### C placement — proposal, not inference

**C lands in the same change as A2-flip.** C writes `worktree_discipline.pack` with its
default into the installer and installation docs. Its central claim — that an absent key
*means* `required` — becomes true only when A2 flips the default. Landing C earlier
documents something false; landing it later leaves a window where a freshly wired repo is
silently non-conformant because nothing told the operator to write the key. Same-change is
the only placement where documentation and behaviour are never out of step.

**The rollout ruling did not place C.** This is a proposal.

### G — recommend DEFER, and file as a tracked follow-up

The case for deferring strengthened during preparation: **once A2 lands, a new fleet member
born unwired reds its own verifier.** `livespec-overseer` carried the verifier recipe and
merely lacked the pack, so after this cut the born-unwired gap is **loud, not silent**. That
makes G a friction fix rather than a hole.

Defer must not become drop: without G the generator keeps producing what D cleans up, and
that generator is where the second live violation appeared. G plausibly belongs to the
fleet-membership / birth-procedure lane, like the adopter backfill.

### Work-item split and dependency edges

Six filable items:

| # | slice | RGR | blocked by |
|---|---|---|---|
| 1 | **E-openbrain** — relocate the nested worktree | no | — |
| 2 | **B** — positive-location hook + actionable remedy | **yes** | — (warn the overseer session before its clone reinstalls) |
| 3 | **A1** — `worktree-pack` obligation row + CI install step + this repo's own wiring | **yes** | 2 (ordering only) |
| 4 | **D** — 6 wiring PRs + 2 `just bootstrap` runs | no | 3 |
| 5 | **A2 + C** — config-gated flip + `import?` assertion + installer/docs | **yes** | 3, 4 |
| 6 | **E-overseer** — relocate | no | **another session** — not dispatchable |

**Hard edges:** `3 → 5` (without A1, A2 reds this repo's own CI on its landing PR) and
`4 → 5` (without D, A2 costs ~58 dead bump PRs per fleet-day). Items 1 and 2 have no
blockers — which is why the approved order starts there. **Item 6 has no encodable blocker**:
same prose-only class as `li-l53` / `hl-nhw`. G, if taken, is item 7 — blocked by nothing,
gating nothing.

### Per-slice acceptance criteria

**B.** Sanctioned `~/.worktrees/<repo>/<branch>` delegates; primary refuses via the existing
arm; nested refuses; **peer refuses** (the spec's named case, no coverage today);
`.git/`-internal delegates; **sandbox-exempt primary still delegates** (existing test must
stay green); a symlinked path yields an identical verdict. Remedy text names
`git worktree move` and **no recipe**, because B ships before D. Injected defects that must
red: remove the carve-out → beads-sync case; drop the exempt guard → the existing exempt
test; revert to nested-only → the peer case; repoint the sanctioned root → the sanctioned
case. Red–Green–Replay: test-only Red with `CANONICAL_HOOK_BODY` unmodified on disk.

**A1.** `just bootstrap` in a pack-less clone materializes all four files, idempotently; the
row sits **before** `commit-refuse-hooks` so that row's broad assert passes for the right
reason; CI installs the pack for the verifier matrix entry; this repo's own
gitignore/`import?`/bootstrap tail land so the materialized pack is not four untracked
files. Injected defect: delete one pack file after bootstrap → the row's assert reds and its
reconcile clears it. RGR.

**A2 + C.** Key absent + pack absent → **FAIL**; explicit `"optional"` + pack absent →
**skip**; malformed block → **FAIL**; **key absent + pack present → PASS** — the arm where
the `harnesses` precedent diverges and must not be copied, pinned by its own test. Existing
partial-install and byte-drift arms unchanged. Missing `import?` lines → **FAIL**, so a
byte-perfect pack can no longer pass while `just --list` shows nothing. The
`.livespec.jsonc`-absent arm's verdict must be a **stated choice with rationale**, not
inherited. C: a freshly wired repo's config carries the key with its default and comment.
Injected defect: remove `dev-tooling/` in a required repo → red; same repo with `"optional"`
→ skip. RGR.

**D.** All 6 unwired repos gain the four wiring components; **`just --list` shows
`worktree-create` in all 9** (today: 1). The 2 wired-but-unhydrated repos go green on
`just bootstrap` alone, **no PR**. Each repo's `just check` passes with the pack
materialized. Do **not** copy git-jsonl's `chmod` of the hydrate stub — per-ecosystem and
optional.

**E.** openbrain lists at `~/.worktrees/openbrain/fix-ob-6vt-thought-detail-save`; `296dd1f`
still reachable on its branch; `.claude/worktrees/` removed. A fleet rescan under B's rule
reports **zero** refusals among governed repos. **E cannot close while the overseer worktree
stands** — recording it done on the openbrain half is the failure mode to avoid.

**G (if ever taken).** A repo scaffolded for each non-`impl-plugin` class is born with the
four wiring components and the `.worktrees` prose.

### Authority still needed for E

**openbrain — none beyond approving this cut.** The original decision covered relocation,
the NARROW ruling explicitly retained it, and it is inspected: clean tree, unpushed
`296dd1f` with no upstream, no live owning process, stale since 2026-06-24.
`git worktree move` preserves the commit; `remove` would destroy it.

**`livespec-overseer/.claude/worktrees/dod-corrections` — not this thread's to take.** It
belongs to another live session, was created mid-audit, and carries two commits. Two things
are needed, neither of them this thread's to grant: that session's owner relocating it or
explicitly handing it over, **and a warning to that session before B reaches the overseer
clone**, since once its hook is reinstalled, commits from that worktree are refused.

### THE FOUR OPEN APPROVAL QUESTIONS

1. **A1/A2 split** — file A as two items (recommended: they land at different times with
   different risk), or one item landing twice?
2. **C placement** — same change as A2 (recommended), or separate?
3. **G** — defer and file as a tracked follow-up (recommended), include in this cut, or drop?
4. **E-overseer** — file item 6 as blocked-on-another-session now, or leave it out of the cut
   and carry it in prose until that session acts?

Everything else follows from rulings already given.

## MAINTAINER RULING — NARROW boundary APPROVED (2026-07-25)

**This thread enforces both full-location clauses across the 9 repos classified `fleet` in
the manifest.** Adopter enforcement is a **separate follow-up**. **E retains the safe
openbrain relocation.**

Consequences, applied throughout this file:

- **Slice F carries no work for this thread.** All 9 fleet repos already have the
  substrate, so clause 2 is met by **B and D alone**. F's original "required by the ruling"
  framing is superseded.
- **The final cut is A, B, C, D, E, (G)** — F drops out. G remains proposed and deferrable.
- **Two backfill work-items were filed at maintainer direction** (filing consent given
  explicitly; no further consent sought):

  | tenant | id | title |
  |---|---|---|
  | `resume` (prefix `li`) | **`li-l53`** | Backfill worktree-location enforcement (both clauses) into resume's Bun/TypeScript harness |
  | `homelab` (prefix `hl`) | **`hl-nhw`** | Backfill worktree-location enforcement (both clauses) into homelab's POSIX hook substrate |

  Both are `type: task`, label `origin:freeform`, no `gap_id`, no `spec_commitment_hint`,
  `status: blocked`, and **absent from `bd ready`** (verified).

  **On assignee/owner — stated precisely, correcting an earlier overclaim.** No explicit
  assignee was supplied during capture, and `--json` reports `assignee: null`. But the
  records are NOT ownerless: raw `bd show` displays `Owner: thewoolleyman`, and the JSON
  `owner` field is **`chad@thewoolleyman.com`** (with `created_by: thewoolleyman`) — the
  tenant/default owner applied at capture. An earlier version of this section claimed only
  "`assignee: null`", which is not a supportable description of what these records expose.
  Each cites this thread and epic `livespec-dev-tooling-0eo`, names its repo target and
  autonomy tier (resume `wip_cap: 5`; homelab `wip_cap: 0`, dispatch-off), and carries
  objective **prerequisite / implementation / acceptance** sections.

  **Cross-tenant blockers are recorded in prose, not as edges.** beads `depends_on` is
  same-tenant only, so neither record can encode its dependency on
  `livespec-dev-tooling-0eo`. Both say so explicitly and warn that the absence of blocking
  edges is by construction, not evidence of readiness. `hl-nhw` additionally carries the
  manifest-deferred onboarding decision as a second unencodable blocker.

  **openbrain has no backfill item** — only E's relocation, which stays in this thread.

The evidence weighed before the ruling is retained below as decision history.

### Provenance of the F-contradiction cleanup (2026-07-25)

PR #658 recorded this ruling but left F described as current, required, and a gate in
several places it had not touched, plus an understated description of resume's substrate and
an unsupportable "`assignee: null`" characterisation of the two filed records. Those
contradictions were **detected by the supervisor in an independent full-file review after
#658 had already auto-merged**, and were corrected in a dedicated follow-up docs PR.

**This was a correction of the record, NOT a new maintainer decision.** No ruling changed:
scope remains full-location, rollout remains Option 3 hook-first, the boundary remains
NARROW, and the final cut remains A, B, C, D, E, (G).

## Boundary question — the two readings weighed (record; NARROW approved above)

**ANSWERED 2026-07-25 — NARROW.** Retained as decision history. Below is the exact wording
on both sides, re-checked against `livespec` master, with consequences and the
recommendation that was made.

### The spec defines a ubiquitous language that separates the two

`SPECIFICATION/non-functional-requirements.md:209`, verbatim:

> **Ubiquitous language.** A **governed repo** is any repository under the workflow (it
> carries a `.livespec.jsonc`); the **livespec fleet** is `livespec`'s own self-application
> family; an **adopter** is a governed repo or family that *adopted* the workflow but is not
> the livespec fleet (it MAY be a fleet itself).

So `governed ⊃ {fleet, adopters}`, and "fleet" **excludes** adopters by definition. The
manifest says the same at `.livespec-fleet-manifest.jsonc:38-40`: adopters are *"governed
repos … that adopted the workflow but are **NOT** the livespec fleet"*.

### The worktree rule's own wording is mixed

`SPECIFICATION/non-functional-requirements.md:1013`, verbatim, with the scoping phrases
marked:

> **Every git worktree** lives under a single per-user root — `~/.worktrees/<repo>/<branch>`
> — NEVER as a peer of the first-class clones in the workspace directory
> (`/data/projects/<repo>`). The workspace directory therefore holds only original clones,
> and **every fleet repo's** worktrees are isolated under one enumerable, reapable root. The
> rule is **fleet-wide-by-intent**: it applies uniformly to `livespec` and **every sibling
> repo**.

Three scoping phrases, and they do not agree: an **unqualified** opener ("Every git
worktree"), then two **fleet-scoped** restatements ("every fleet repo's", "fleet-wide … and
every sibling repo").

### The decisive contrast: this document has a term for "both", and did not use it here

The same spec says **"fleet+adopter-wide"** when it means both — twice, in the two
obligations that most resemble this one:

- `:113` — *"**Red-green-replay is fleet+adopter-wide.** … REQUIRED in EVERY
  livespec-governed repo …"*
- `:114` — *"**The ROP railway is fleet+adopter-wide.** Every livespec-governed repo …"*

§"Worktree root" says **"fleet-wide"**, not "fleet+adopter-wide", and does not use
"governed" anywhere. In a document that demonstrably distinguishes the two forms, that is a
deliberate contrast rather than loose drafting.

**Counterweight, stated fairly.** The opener is unqualified, and `:215` mandates `just` for
*"every governed repo — fleet and adopter"*, so the document does extend some floor
obligations to adopters. And openbrain — an adopter — is where one of the two live
violations actually sits.

### Consequences of each reading

| | **Narrow — the 9 `fleet` entries** | **Broad — all 12 governed repos** |
|---|---|---|
| Substrate | all 9 have justfile, mise, verifier, canonical hook | 3 adopters: 1 reachable, 2 without substrate |
| Slice F | **reduces to nothing**; clause 2 met by B + D | required, and 2/3 blocked on work this thread does not own |
| Reachable "done" | yes, entirely within this thread | **no** — depends on homelab's manifest-DEFERRED onboarding |
| Coverage left open | adopter repos, incl. openbrain's live violation | none in principle |
| Bespoke forks reconciled | no — openbrain's bash and resume's TypeScript stay | yes |

### Recommendation: NARROW, with adopter coverage split into its own thread

Four reasons. The spec's own contrast between "fleet-wide" and "fleet+adopter-wide" is the
strongest textual signal and points narrow. Both of §"Worktree root"'s restatements are
fleet-scoped. Under narrow, clause 2 is fully achievable here — every one of the 9 has the
substrate today. And under broad, this thread's done-ness becomes hostage to an onboarding
pass the manifest itself defers and another lane owns, which is how threads end up
permanently almost-finished.

**What the narrow reading must NOT be allowed to hide:** openbrain has a live violation and
two adopters run location-blind forks of the same structural test. Narrow does not make
that acceptable — it says it is *a different thread's* work, with its own gates. Two
concrete guards if narrow is chosen: keep **E's openbrain relocation in this thread**
(relocation is hygiene and needs no substrate, so it is severable from enforcement reach),
and file the adopter-coverage follow-on **before** closing this one, so the gap is carried
rather than dropped.

## Rollout order — the three options weighed (record; Option 3 approved above)

**Option 3 is APPROVED** (§"MAINTAINER RULING — rollout order", 2026-07-25). Options 1 and
2 are retained below **only as decision history** — the evidence that was weighed — and are
NOT live alternatives. Do not re-open them without a new ruling.

**What changed about this question under the widened scope.** The old binary pitted
"pack-install-first" against "verifier-first", both about item A. That is now secondary:
**A is not the slice that stops violations — B is.** A makes the sanctioned tool
discoverable and mandatory; B refuses the commit when someone bypasses it anyway. Under the
ruling B also became *simpler* (an allow-list, no nested detection) and it is **CI-immune**
(`ci.yml` installs the hook from the same wheel it verifies), so it reds nothing and needs
no fleet wiring to ship. Meanwhile the harm is measurably ongoing — a second live violation
appeared during one day's audit, with commits landed from it.

> **The `F` tails in the three option diagrams below are SUPERSEDED.** All three were
> written before the NARROW boundary ruling, which removed F from this thread. Their
> `→ F → (G)` endings are **not part of the current sequence** — the approved sequence is
> the one in §"MAINTAINER RULING — rollout order", which ends at `A-flip`, with C and G
> unplaced pending final-cut approval. The diagrams are kept verbatim so the comparison
> that was actually weighed stays legible.

**Option 1 — Prerequisites-first, enforce-last.**
`A-prereq → D-wiring → E → A-flip → B → F → (G)`
Nothing ever reds and nothing is refused unexpectedly; every step is additive until the end.
Cost is exposure: the fail-open stays open across ~7 landings before anything is refused.
Given the measured recurrence, that exposure is not theoretical.

**Option 2 — Enforce-first, red as forcing function.**
`A-flip → repos go red → wiring follows under pressure`
Not literally executable without the CI install step (this repo's own CI reds on the landing
PR). Measured cost past that: ~7.3 releases/day, tag-scoped bump branches that never retry
in place, giving roughly **58 dead bump PRs per fleet-day** across 8 repos with pins frozen.
Weaker than it looks under the ruling: it pressures the *pack* layer while B — the layer
that actually stops violations — is independent and arrives no sooner.

**Option 3 — Hook-first (the recommendation).**
`E (openbrain half) → B → A-prereq → D-wiring → A-flip → F → (G)`
B ships early because it is the cheap one: no wiring dependency, no CI red, and it rehearsed
clean across all 40 host worktrees (34 allow-sanctioned incl. every `janitor-*`, 4
allow-tooling, **2 refusals, zero false positives**). A and D follow as unhurried hygiene,
with A's flip *after* D, so Option 2's red window never opens at all. Rollout is naturally
gradual: B takes effect per clone only when that clone's hook is reinstalled via
`just bootstrap`.
Two costs to weigh. `livespec-overseer/.claude/worktrees/dod-corrections` belongs to a live
session and would be refused once B reaches that clone — hence E's openbrain half first and
a heads-up to that session before B lands; **this thread must not touch that worktree.** And
B without A leaves `just worktree-create` undiscoverable in 8 of 9 repos, so operators hit a
refusal whose remedy names a command that does not exist there — pair B with the
remedy-string fix.

**Recommendation: Option 3.** The harm is silent violations, B is the only slice that stops
them, and B is the cheapest and least disruptive item in the cut. Landing A's flip after D's
wiring means Option 2's cost is simply never incurred — so the red-window debate that has
gated this thread since it opened largely dissolves once B is no longer sequenced behind A.
Treat G as deferrable but *decided*: without it the sweep fixes the population while the
generator keeps minting unwired repos, which is exactly where the second violation appeared.

## CURRENT STATE — read this before anything else

This file grew from 265 to ~1200 lines during the 2026-07-25 audit, and several of its
original section headings and opening lines were written before findings that contradict
them. **Where an older passage and this section disagree, this section wins.** Each claim
here names the section carrying its evidence.

**The rule is ratified spec, not just prose.** `livespec/SPECIFICATION/non-functional-requirements.md:1013`
states it positively — every worktree under `~/.worktrees/<repo>/<branch>` — and the one
prohibition it spells out is the **peer** case. B, **as widened by the full-location
ruling**, is a positive-location allow-list and therefore catches the peer case, the nested
case, and anything else outside the sanctioned root. *(This line previously read "…the peer
case, which item B does not catch" — true of the pre-ruling nested-only B, false of the
current one.)* → §"THE SPEC ALREADY ANSWERS…"

**There are two live nested violations, not one.** `openbrain/.claude/worktrees/fix-ob-6vt-…`
and `livespec-overseer/.claude/worktrees/dod-corrections` — the latter **created during
this audit**, with commits landed from it, invisible to `git status` because that repo
gitignores `.claude/worktrees/`. The premise that this "fired once for real" is retired.
→ §"A SECOND LIVE VIOLATION…"

**Item B reaches fewer repos than assumed.** It changes `CANONICAL_HOOK_BODY`, which
9 fleet clones run. openbrain runs a stock lefthook stub plus its own bespoke script;
resume has a third implementation in TypeScript. All three are location-blind; B fixes
one. → §"CORRECTION (2026-07-25)" in §"Fleet impact" and its sub-table.

**Item A as specified does not close its layer.** A byte-perfect pack with no `import?`
lines passes the verifier while `just --list` shows no `worktree-create`. Today the
sanctioned tool is discoverable in **1 of 9** governed repos. → §"A AS SPECIFIED DOES
NOT CLOSE…" and §"Discoverability of the sanctioned tool".

**The pack is gitignored-and-materialized, not tracked**, so "pack-install-first" was never
a sequence of PRs, and landing A reds this repo's own CI on the PR that lands it.
→ §"The pack is GITIGNORED-AND-MATERIALIZED".

**Slice D is 6 tracked PRs, not 8 repos.** Three repos are already wired; two of those need
only `just bootstrap`. And the fleet keeps minting unwired repos because only one of seven
repo classes has a copier template. → §"D is two different jobs".

**Widening B to the spec's rule is a three-line change** and rehearses clean: 34 sanctioned
allows, 4 tooling allows, exactly 2 refusals, zero false positives. → §"Widening to the
spec's rule was rehearsed".

**Decision status (updated 2026-07-25).** **Scope approved** — full-location, both
clauses (§"MAINTAINER RULING — full-location scope"). **Rollout order approved** — Option 3,
hook-first (§"MAINTAINER RULING — rollout order"). **Boundary approved** — NARROW, the 9
`fleet` repos (§"MAINTAINER RULING — NARROW boundary"); F drops out and adopter backfill is
filed as `li-l53` / `hl-nhw`. **The final cut is now APPROVED and FILED (2026-07-26).** No
slices are filed, no worktree has been moved or touched, the ledger is untouched, and no
product change has been made. A "wire-then-enforce"
answer displayed on 2026-07-25 was a supervisor UI-race artifact and is void.

### Superseded claims — do not act on these if you meet them elsewhere in the file

| claim, as originally written | status |
|---|---|
| "one live violation remains fleet-wide (§openbrain)" / §E's heading "openbrain has the last live violation" | **superseded** — two nested violations, plus the peer case |
| "openbrain's hook is an older canonical body, byte-correct against its own pin" | **wrong** — it is a stock lefthook stub with no livespec refuse logic |
| "`pwd -P` is a real bug source here, not a hypothetical" | **unsupported** — changes no verdict; git already emits physical paths |
| "the rule is stated in prose in each repo's `AGENTS.md`" | **too generous** — 9 of 13; and it is *also* ratified spec |
| "the hook reinstall does not propagate … per-clone and per-machine" | **overstated** — `local_reconcile`'s `commit-refuse-hooks` row already self-heals it |
| "pack-install-first: run `install-worktree-pack` across the non-compliant repos" as a PR sweep | **false premise** — the pack is untracked |
| `/data/projects/homelab-substrate` as a live peer violation | **gone** — removed by the `homelab` track mid-audit; the structural gap remains |
| `AGENTS.md` §Red-Green-Replay at `:100-142` | `:100-147` |

---

## Charter

The rule "every worktree lives under `~/.worktrees/<repo>/<branch>`, NEVER inside a
clone" is stated in prose in *most* governed repos' `AGENTS.md` and enforced by
**nothing**. (Measured 2026-07-25: 9 of 13 governed clones mention `.worktrees` at all;
`livespec-driver-codex`, `livespec-overseer`, and `homelab` have zero mentions and
`dolt-server` has no `AGENTS.md`. The original "each repo" claim was too generous —
prose coverage is itself incomplete, which strengthens the case for a mechanical
guard rather than weakening it.) Three
layers were each assumed to cover it; all three fail open, silently, in exactly the
scenario that occurred.

Unlike `livespec-console-beads-fabro`'s `plan/repo-invariant-guards/` (a sibling thread
of the same *mechanism* — mechanical guards for unenforced invariants), this is **not**
a latent gap. It has fired for real **more than once**, and violations remain live
fleet-wide. That difference is why this is its own thread rather than a fourth item there.

*(Originally written as "it fired once for real, and one live violation remains
fleet-wide (§openbrain)". Retired 2026-07-25: a second nested violation appeared in
`livespec-overseer` **during this audit**, with commits landed from it — see §"A SECOND
LIVE VIOLATION". Treat the base rate as unknown and non-zero, not as one historical
incident with one remnant.)*

## The incident (why this exists)

On 2026-07-19 a session archiving the console autonomous-mode plan created its worktree
at `/data/projects/livespec-console-beads-fabro/worktrees/archive-console-autonomous-mode`
— inside the primary clone. It committed (`66947e0`), opened and merged PR #295. The
maintainer noticed only because `git status` on master showed `?? worktrees/`.

The violation was live ~25 minutes. Master itself was never modified. The offending
session relocated and cleaned up its own mess on request; the empty `worktrees/` dir was
removed 2026-07-19. **Nothing about the root cause was fixed** — re-verified on
`413a407` (2026-07-25): the fail-open line is untouched and still at
`:298-300`, `grep -rn worktree_discipline` over the whole repo returns **zero hits**
(no config key exists anywhere), and no pack is installed in **8 of 9** verifier-running
fleet repos.

The causal chain, which is the actual design input:

1. The session was cwd'd in the primary. It **did** look for the sanctioned tool — ran
   `just --list`, found no `worktree-create` recipe, and fell back to raw
   `git worktree add worktrees/<branch>` (a cwd-relative path).
2. It found nothing because the pack is not installed here, and the root justfile uses
   `import?` (optional) — so a missing pack produces **no error and no hint**, it simply
   vanishes from `just --list`.
3. The commit-refuse hook let the commit through because it is *structural*: it compares
   git-dir to git-common-dir, i.e. it enforces "not the primary" and is **blind to
   where** a worktree lives. A nested worktree has differing dirs, so the refuse branch
   is skipped.

## Read first

1. This file.
2. `livespec_dev_tooling/checks/primary_checkout_commit_refuse_hook_installed.py`
   — the fail-open site is **`:298-300`** (`any_present` → `return []`). Pack constants
   at `:202`, `:210-211`; the remedy string reused at `:359`.
3. `livespec_dev_tooling/install_commit_refuse_hooks.py` — `CANONICAL_HOOK_BODY` starts
   `:72`; the existing refuse branch is **`:117-123`**. The new branch goes after `:123`.
4. `livespec_dev_tooling/checks/plugin_resolution.py` — **the precedent to copy.** Its
   `harnesses` key (`:96-97`, `load_harnesses`) is a `.livespec.jsonc` declaration with
   exactly the fail-closed semantics wanted here: file absent → SKIP, key absent → FAIL
   ("required fleet-wide since M6"), block malformed → FAIL.
5. `livespec_dev_tooling/install_worktree_pack.py` + `livespec_dev_tooling/worktree_pack/`
   — the four canonical pack bodies (single source).
6. `AGENTS.md` §"Red-Green-Replay commit protocol" (`:100-147`, i.e. the section runs
   to end-of-file) — binds item A. *(Anchor corrected 2026-07-25; `AGENTS.md` grew from
   142 to 147 lines. The four `.py` files at items 2–5 are **byte-identical** to
   `2412e21`, so every anchor into them still holds — verified by
   `git diff 2412e21..origin/master` reporting no change for any of them.)*

## The two decisions the maintainer already made

Both were settled 2026-07-19. Do not relitigate; they are inputs, not options.

**A. Config key, defaulting to required.** A `.livespec.jsonc` declaration, sibling to
`harnesses`, whose *absence* means `required`:

```jsonc
"worktree_discipline": {
  // "required" (default when the key is absent): the worktree-discipline pack
  // MUST be installed — run `just install-worktree-pack`.
  // "optional": legacy skip-when-absent; an explicit, reviewable opt-out.
  "pack": "required"
}
```

Honest note recorded at decision time: because the default is `required`, writing
`"required"` explicitly is semantically a **no-op**. Enforcement comes entirely from the
default. The sweep's value is discoverability, and making any future `"optional"` an
explicit reviewable opt-out rather than silence. Do not mistake the sweep for the fix.

**B. Hard refuse (not warn) for nested worktrees**, with a `.git/` carve-out:

```sh
git_dir=$(cd "$common_dir" && pwd -P)
primary_root=$(cd "$(dirname "$git_dir")" && pwd -P)
this_root=$(cd "$(git rev-parse --show-toplevel)" && pwd -P)
case "$this_root/" in
  "$git_dir"/*)      ;;                         # tooling-internal — ALLOW
  "$primary_root"/*) refuse_nested_worktree ;;  # nested in working tree — REFUSE
esac
```

**The carve-out is load-bearing, not defensive.** A naive "refuse anything under the
primary root" breaks **beads' own sync worktrees**, which deliberately live in `.git/`:

```
agent-flywheel                       .git/beads-worktrees/beads-sync
beads                                .git/beads-worktrees/beads-metadata
gdk-in-a-box-agent-flywheel-wrapper  .git/beads-worktrees/beads-sync
personal-knowledge-base              .git/beads-worktrees/beads-sync
```

**`pwd -P` is also load-bearing on this host.** `/data/projects/<repo>` and
`/home/ubuntu/workspace/<repo>` are the SAME repos — verified by identical inode on
`.livespec.jsonc` (`28058364` for `livespec`). Without physical-path resolution the
prefix comparison gives different answers depending on which path a worktree was created
through. This is a real bug source here, not a hypothetical.

## The trap that makes rollout order the whole problem

**The hook body is byte-compared, not fingerprinted.** The verifier requires the
installed hook to be *byte-identical* to `CANONICAL_HOOK_BODY` (`:71`, `:82`); the
"prior loose substring-fingerprint logic" was explicitly **RETIRED** (`:20`).

Consequence: **the moment item B changes `CANONICAL_HOOK_BODY`, every already-installed
hook in every repo becomes byte-different → `hook_body_mismatch` FAIL**, until
`just install-commit-refuse-hooks` re-runs in each. Hooks live in untracked
`.git/hooks/`, so this is per-clone and per-machine — it does not propagate with a pin
bump.

Item A has the same shape: flipping the default reds every repo lacking a pack.

So **both** items are pin-bump-coupled fleet sweeps, not local changes. That is the
single most important fact in this file.

## Fleet impact — remeasured 2026-07-25

**Membership source of truth** is livespec core's committed
`.livespec-fleet-manifest.jsonc` (GitHub repo topics are only a discovery safety net).
As of livespec `991943ef` it lists **9 fleet members** + **3 registered adopters**
(openbrain, resume, homelab). `dolt-server` is *not* registered — its adopter
registration is explicitly DEFERRED in the manifest — but its clone does carry a
`.livespec.jsonc`, so it is a governed-ish carrier, not a fleet member. Counting it
gives the 13 clones surveyed below.

**Delta vs the 2026-07-19/20 table:** `livespec-overseer` was added to the fleet as the
`control-plane-tool` class (livespec `f9664481`, class ratified in spec v171
`a2afda9b`). It runs the verifier and has **no pack** — so the non-compliant
verifier-running count went **7 → 8**, and the `.livespec.jsonc` carrier count went
**12 → 13**.

9 repos run the verifier. Console names its recipe `check-baseline`; the other 8 name it
`check-primary-checkout-commit-refuse-hook-installed` (an earlier scan for `check-baseline`
alone under-reported this — do not repeat that mistake).

| Repo | manifest | verifier recipe | pack (`dev-tooling/`) | installed hook |
|---|---|---|---|---|
| livespec | fleet/core | YES | **ABSENT** | canonical ✅ |
| livespec-dev-tooling | fleet/enforcement-suite | YES | **ABSENT** | canonical ✅ |
| livespec-driver-claude | fleet/driver-plugin | YES | **ABSENT** | canonical ✅ |
| livespec-driver-codex | fleet/driver-plugin | YES | **ABSENT** | canonical ✅ |
| livespec-orchestrator-beads-fabro | fleet/impl-plugin | YES | **ABSENT** | canonical ✅ |
| livespec-runtime | fleet/library | YES | **ABSENT** | canonical ✅ |
| livespec-console-beads-fabro | fleet/console | YES (`check-baseline`) | **ABSENT** | canonical ✅ |
| **livespec-overseer** *(new)* | fleet/control-plane-tool | YES | **ABSENT** | canonical ✅ |
| livespec-orchestrator-git-jsonl | fleet/impl-plugin | YES | present ✅ (4/4) | canonical ✅ |
| openbrain | adopter (pinned) | **none** | ABSENT | **differs** (older pin) |
| resume | adopter (pinned) | **none** | ABSENT | **no hook** |
| homelab | adopter (released) | **none** | ABSENT | **no hook** |
| dolt-server | *unregistered* | **none** | ABSENT | **no hook** |

`livespec-orchestrator-git-jsonl` is still the **only** compliant repo — model the sweep
on it. All 4 pack files are present and byte-current there.

Note `livespec-dev-tooling` itself is non-compliant. Fix it in the same change so the
canonical repo is exemplary rather than exempt.

**The 9 fleet clones' installed hooks are all byte-identical to the current
`CANONICAL_HOOK_BODY`** (sha256 prefix `3a3f60cbd4d2`, 3494 bytes) — so today there is
no pre-existing hook drift for item B to be blamed for.

**CORRECTION (2026-07-25), superseding an earlier claim in this file.** The `openbrain`
row was previously recorded here as "hook differs (`b649c648302b`) — a *pinned* adopter
running an older `livespec-dev-tooling`, byte-correct against its own pin." **That was
wrong, and it was inferred rather than inspected.** Inspected:

- `openbrain/.git/hooks/pre-commit` is a **stock lefthook stub**. `grep -c "livespec
  commit-refuse hook"` against it returns **0** — it carries no livespec refuse logic of
  any version. It is not an older canonical body; it is not a canonical body at all.
- `openbrain` carries its **own, unrelated** primary-refuse mechanism:
  `scripts/refuse-primary-commit.sh` (epic `ob-apw`), wired through `lefthook.yml:25-26`
  and `:183-184`. It is *not* installed as the pre-commit hook; lefthook invokes it.
- That script uses the same `--git-dir` vs `--git-common-dir` structural test as the
  livespec hook, so it enforces "not the primary" and is **equally blind to worktree
  LOCATION** — the identical fail-open this thread exists to close, independently
  reimplemented.

##### The location-blind test exists in THREE independent implementations

A fleet-wide sweep (2026-07-25) for bespoke refuse mechanisms beyond the canonical hook
found that openbrain is not a one-off:

| implementation | language | where | reaches |
|---|---|---|---|
| livespec `CANONICAL_HOOK_BODY` | `sh`, in `.git/hooks/` | `install_commit_refuse_hooks.py:72` | the **9 fleet clones** |
| openbrain `scripts/refuse-primary-commit.sh` | `bash`, via lefthook | epic `ob-apw` | openbrain only |
| resume `scripts/check-primary-checkout.ts` | TypeScript | resume | resume only |

`resume`'s header states the same structural rule in the same terms — *"refuses a commit
whose repository git-dir equals its git-common-dir — the signature of the primary
checkout"* — and, like the other two, never mentions worktree location. (It is not
referenced from `package.json`, `lefthook.yml`, or a `justfile`; where it is invoked from,
if anywhere, was not established.)

**Item B changes one of the three.** The other two are separate repos' files. So "the
fail-open is closed" after B is true only of the fleet-clone population — a third of the
implementations by count, and the two outside it belong to the adopters that carry no
verifier and no canonical hook. Any acceptance criterion phrased fleet-wide must say
which implementation it is talking about.

This also reframes the root cause. The location-blindness is not one oversight in one
hook body; it is what **everyone independently converges on** when they implement
"worktree-mandatory" from the structural git-dir test, because that test answers "am I in
the primary?" and nobody notices it never asked "am I in the right *place*?". A fix that
lands only in `CANONICAL_HOOK_BODY` leaves the pattern intact and available to be
reimplemented a fourth time.

**Consequence for item B and slice E — item B does not reach openbrain.** The handoff's
§E claim that openbrain's nested worktree "is in the working tree, not `.git/`, so item B
will hard-refuse its next commit" **does not hold**: B changes `CANONICAL_HOOK_BODY`, and
openbrain does not run that body. Landing B, and openbrain later bumping any pin, changes
nothing there. Closing the openbrain violation mechanically would additionally require
either installing the livespec canonical hook in openbrain or porting the §B location
test into `scripts/refuse-primary-commit.sh` — neither of which is in the A–E cut, and
the second of which is another repo's file.

This does not change E's *relocation* action, which stands on its own. It changes E's
stated *justification*: relocating openbrain's worktree is hygiene and consistency with
the rule, **not** "otherwise B strands it mid-branch". Do not carry the stranding
rationale forward.

The byte-compare point that survives: it is always against the canonical body of the
version a repo pins, so a fleet clone on an older pin can legitimately differ from
master. That is simply not what is happening in openbrain.

### Discoverability of the sanctioned tool, measured directly (2026-07-25)

The table above reports pack *files*. What an operator actually experiences is whether
`just --list` offers `worktree-create`. Ran it in all 9 verifier-running repos:

| repo | `import?` lines | pack file | `just --list` shows `worktree-create` |
|---|---|---|---|
| livespec | 0 | no | **no** |
| livespec-dev-tooling | 0 | no | **no** |
| livespec-driver-claude | 0 | no | **no** |
| livespec-driver-codex | 0 | no | **no** |
| livespec-runtime | 0 | no | **no** |
| livespec-overseer | 0 | no | **no** |
| livespec-orchestrator-beads-fabro | 2 | **no** | **no** ← `import?` no-ops |
| livespec-console-beads-fabro | 2 | **no** | **no** ← `import?` no-ops |
| livespec-orchestrator-git-jsonl | 2 | yes | **yes** |

**The sanctioned tool is discoverable in exactly 1 of 9 governed repos.**

The two middle-column failures are distinct and both matter. Six repos have neither half.
But `livespec-orchestrator-beads-fabro` and `livespec-console-beads-fabro` have the
`import?` lines *and no pack*, so the optional import silently no-ops — that is
**fail-open layer 1 from §"The incident", live in two repos right now**, not a historical
description.

And the sharpest form of it: **`livespec-console-beads-fabro` is the repo where the
incident happened.** Its preconditions are unchanged. A session there today runs
`just --list`, sees no `worktree-create`, and has exactly the same reason to fall back to
raw `git worktree add` that the 2026-07-19 session had. The remediation described in
§"The incident" cleaned up the *instance*; this measurement is what "nothing about the
root cause was fixed" looks like when you run it rather than read it.

The 4 non-fleet rows carry (or would carry) the key as **inert documentation** — they
wire no verifier, so nothing reads it. Say so rather than implying coverage. `resume`,
`homelab`, and `dolt-server` have no commit-refuse hook installed at all, so item B
cannot reach them either.

## THE ONE OPEN QUESTION — rollout order

> **It is no longer the one open question, and it is no longer first.** The 2026-07-25
> audit found that the definition of done is settled by ratified spec (§"THE SPEC ALREADY
> ANSWERS…"), which determines whether the cut is A–E or wider — and that is upstream of
> sequencing it. It also found the binary below rests on a false premise (§"The pack is
> GITIGNORED-AND-MATERIALIZED"). Read the two subsections after the original text before
> treating any option here as live.

Unanswered when the prior session ended. It gates all execution:

- **Pack-install-first (no red window).** Run `install-worktree-pack` across the 8
  non-compliant repos *before* landing the verifier change. Harmless on its own — an
  installed pack is already valid under today's rules. Nothing ever goes red.
- **Verifier-first (red as forcing function).** Land the change; each repo goes red at
  its next pin bump until it installs.

The prior session's recommendation was **pack-install-first**, on the grounds that
staggered pin bumps mean the red window is not atomic and would surface as unrelated CI
failures in 7 (now 8) repos over an unpredictable window. Not a decision — a
recommendation.

### The red window, actually measured (2026-07-25)

That "unpredictable window" reasoning was never quantified. It is now, and the numbers
point the same direction but for a **different and much stronger reason**.

| measurement | value |
|---|---|
| `livespec-dev-tooling` releases, last 7 days | **51** (~7.3/day) |
| `livespec-dev-tooling` releases, last 30 days | 128 |
| pin bumps landed per member, last 30 days | 98–112 (~3.5/day); `livespec-overseer` 25, it joined recently |
| members whose last pin bump landed on 2026-07-25 | **8 of 8** |
| bump branch naming | `<prefix>-<source_repo>-<tag>` (`.github/actions/bump-pin-rewrite/action.yml:135`) |

Two consequences, and they pull against each other:

**The window is not long-tailed — it is immediate.** Every member bumped its pin *today*.
A verifier-first red would therefore hit all 8 non-compliant repos within hours, not
drift in as scattered mystery failures weeks apart. On that axis the original worry was
misplaced: the red would be loud and simultaneous, which is what a forcing function is
supposed to be.

**But stalled bump PRs ACCUMULATE rather than being retried in place.** The bump branch
is **tag-scoped**, so each new release mints a *fresh* branch and a *fresh* PR. A repo
that goes red does not sit on one failing PR waiting to be fixed — it collects a new one
per release. At ~7.3 releases/day across 8 non-compliant repos that is on the order of
**~58 new dead bump PRs per fleet-day**, every day, until each repo is wired. Their pins
freeze meanwhile, so those members stop receiving unrelated genuine fixes for the
duration.

So the honest framing of the trade is not "no red window vs. an unpredictable one". It is:

- **wire first** → zero dead PRs, and the fail-open stays open for however long the wiring
  takes;
- **enforce first** → the hole closes at once and the red is unmissable, at a cost of
  roughly 58 dead PRs per day and 8 frozen pins until the wiring lands.

That cost scales with how long the wiring takes, which is the next measurement.

### What the per-repo wiring actually costs (2026-07-25)

Measured off `livespec-orchestrator-git-jsonl`, the only compliant repo, which is the
model to copy. The tracked change per repo is small:

- `.gitignore` — **4 lines** (`:13-16`), one per pack file;
- `justfile` — **2** `import?` lines (`:91`, `:135`), a **2-line** `install-worktree-pack`
  recipe, and a **1-line** `bootstrap` tail calling it.

That is roughly **10 tracked lines per repo**, plus explanatory comments, in 5 repos that
have none — `livespec`, `livespec-driver-claude`, `livespec-driver-codex`,
`livespec-runtime`, `livespec-overseer` — and a partial top-up in `livespec-dev-tooling`
(has the recipe; needs gitignore, imports, and the bootstrap tail). Two repos
(`livespec-orchestrator-beads-fabro`, `livespec-console-beads-fabro`) have the recipe and
imports and need only their gitignore and bootstrap tail confirmed.

`git-jsonl`'s third bootstrap line (`chmod +x dev-tooling/worktree-hydrate.sh`) is
**not** general — the hydrate stub is per-ecosystem and optional
(`worktree_pack/worktree-lib.sh:45-50` treats it as "if present", and the shipped one is a
no-op). Do not copy it blindly.

**Bearing on the decision:** ~10 lines × ~6 repos is a short wiring pass, not a campaign.
That materially favours wiring first — the fail-open's extra exposure is measured in a
handful of small PRs, whereas the enforce-first cost is ~58 dead PRs per day of the same
interval. Still the maintainer's call; this is the arithmetic, not the ruling.

### The mechanics under this question CHANGED since `2412e21` — reprice it

Three findings from the 2026-07-25 remeasurement change the failure window of each
option. Do not answer the old binary without them.

1. **The release fan-out preflight became a per-member FILTER, not a blocking gate**
   (`livespec_dev_tooling/fleet/dispatch_matrix_filter.py`, new since `2412e21`;
   `reusable-release-dispatch.yml`). Previously a red fleet halted the whole fan-out.
   Now a non-conformant member is **excluded from the dispatch matrix** and named in an
   annotation + step summary, while conformant members still receive their dispatch.
   This makes the verifier-first red *quieter and longer-lived* per repo, not louder:
   an excluded repo stops receiving pin bumps until someone acts on the annotation.
   Note this filter keys off **fleet-conformance** rows, not off the repo-local
   `check-primary-checkout-commit-refuse-hook-installed` verifier — see item 3.

2. **`reusable-pin-freshness.yml` no longer runs `just check` before opening the bump
   PR** (that step was extracted out; the header now says it "runs no consumer checks
   itself, so the failure surfaces on the PR's own status checks"). Under verifier-first,
   each member's next bump PR therefore **opens and then goes red on its own CI**, and
   auto-merge stalls. The failure mode is 8 stalled bump PRs, not 8 skipped bumps.

3. **Item B never reds CI at all.** `ci.yml:409-411` installs the canonical hook via
   `python3 -m livespec_dev_tooling.install_commit_refuse_hooks` from the *same wheel*
   the check then verifies against, immediately before running the
   `check-primary-checkout-commit-refuse-hook-installed` matrix entry. A fresh CI
   checkout is therefore always byte-current by construction. **Item B's blast radius is
   developer clones only** — which is materially smaller than the handoff previously
   implied.

### Correction to a premise that was wrong when written

The original text said the hook reinstall "is per-clone and per-machine — it does not
propagate with a pin bump", implying a manual `just install-commit-refuse-hooks` in every
clone. That understates what already exists: `livespec_dev_tooling/fleet/local_reconcile.py`
(which predates `2412e21` — this was a miss, not a delta) walks
`contract.LOCAL_OBLIGATION_ROWS`, and the **`commit-refuse-hooks` row carries both an
`assert_local` (runs the verifier) and a `reconcile_local` (runs the installer)**.
`just bootstrap` is a thin delegator to it. So item B's per-clone reinstall is already
mechanized: `just bootstrap` in each clone asserts and self-heals the hook.

**But there is no worktree-pack local row.** `grep -rn worktree_pack livespec_dev_tooling/fleet/`
returns nothing. So under item A, the `commit-refuse-hooks` row's assert (which shells
out to the whole verifier, pack arm included) would go red in a pack-absent repo while
its reconcile — which only installs the hook — **cannot clear it**. That is an
un-self-healing row, and it is a design input for slice A/D: either add a
`worktree-pack` local obligation row with `install_worktree_pack` as its reconcile, or
extend the existing row's reconcile. This did not exist as a consideration in the
original cut.

### The pack is GITIGNORED-AND-MATERIALIZED, not tracked — this invalidates the question as posed

Measured 2026-07-25, after the first audit PR (#631) had already merged. This is the
single most consequential correction in the thread, because the maintainer's open
question was framed on the opposite assumption.

**Evidence.**

- `livespec_dev_tooling/install_worktree_pack.py:19-21` states it outright: "The pack
  files are UNTRACKED-AND-INSTALLED, NOT tracked-committed: a consumer `git rm`s them
  from version control, gitignores them, and (re)materializes them via
  `just install-worktree-pack` from `bootstrap`/CI."
- `livespec-orchestrator-git-jsonl/.gitignore:12-16` gitignores all four pack files;
  `git ls-files dev-tooling/` there tracks only `CLAUDE.md` and `worktree-hydrate.sh`.
- What actually makes that repo compliant is `livespec-orchestrator-git-jsonl/justfile:196-199`
  — a `bootstrap` TAIL calling `just install-worktree-pack`, whose own comment says the
  tail is "not a verb obligation row, so both MUST survive the rewire."

**Consequence 1 — "pack-install-first" is not a sequence of PRs.** There is nothing to
commit. The §rollout option described as "run `install-worktree-pack` across the
non-compliant repos before landing the verifier change" cannot be a fleet sweep of pack
bodies, because pack bodies are never committed anywhere. The tracked work is entirely
different: `.gitignore` entries, the two `import?` lines, an `install-worktree-pack`
recipe, and a `bootstrap` tail.

**Consequence 2 — item A reds `livespec-dev-tooling`'s OWN CI on the very PR that lands
it.** `git ls-tree -r origin/master dev-tooling/` returns only `CLAUDE.md`; this repo's
`.gitignore` has no pack entries; the pack is not materialized here; and `bootstrap`
(`justfile:76-77`) delegates to `local_reconcile`, which has no worktree-pack row.
Meanwhile `ci.yml:409-411` installs the commit-refuse *hook* before the
`check-primary-checkout-commit-refuse-hook-installed` matrix entry but **never installs
the pack**. So a fresh CI checkout has zero pack files; today that is a skip, and under A
with the default `required` it is an immediate FAIL. The red is not deferred to a
downstream pin bump — it lands on the enforcement PR itself.

**Consequence 3 — A's remedy string names a command most repos do not have.**
`_WORKTREE_PACK_REMEDY` (`:211`) says "run `just install-worktree-pack`". Measured across
the 9 verifier-running repos:

| | repos |
|---|---|
| has `install-worktree-pack` recipe | 4 — `livespec-dev-tooling`, `livespec-orchestrator-beads-fabro`, `livespec-orchestrator-git-jsonl`, `livespec-console-beads-fabro` |
| has the two `import?` lines | 3 — `livespec-orchestrator-beads-fabro`, `livespec-orchestrator-git-jsonl`, `livespec-console-beads-fabro` |
| has **neither** | 5 — `livespec`, `livespec-driver-claude`, `livespec-driver-codex`, `livespec-runtime`, `livespec-overseer` |

In those 5, an operator hitting A's new FAIL is told to run a recipe that does not exist.
And even after the pack files exist, without the `import?` lines `just --list` still shows
no `worktree-create` — **which is causal-chain steps 1–2 of the original incident,
unchanged**. Installing pack bodies alone does not close the hole in those repos.

`livespec-dev-tooling` itself has the recipe but no `import?` lines, no gitignore entries,
and no `bootstrap` tail — so it is non-compliant in a *different* way than the table in
§"Fleet impact" implies. That table's `pack: ABSENT` column is accurate about the files;
it does not capture the wiring, which is the part that is actually tracked.

### A new argument FOR item B: the `git status` tripwire mostly does not exist

The 2026-07-19 incident was caught only because `git status` on master showed an
untracked `worktrees/`. Measured 2026-07-25 across the 9 verifier-running repos: **8 of 9
gitignore a worktrees directory** (`.claude/worktrees/` or equivalent).
`livespec-console-beads-fabro` — the one repo where the incident fired and was caught — is
the **only** one that does not. Everywhere else the tripwire that caught it is absent by
construction, and openbrain's live violation sits in a gitignored `.claude/worktrees/`
exactly so.

This is independent support for decision B's *hard refuse* over a warn, and it was not
part of the record when B was settled.

### Status of the rollout question after these findings — HISTORICAL PRE-RULING; ANSWERED

> **CURRENT ANSWER, stated first: rollout order IS decided.** **Option 3, hook-first, is
> APPROVED** by maintainer ruling (§"MAINTAINER RULING — rollout order"). The text below is
> the pre-ruling status and is retained only as history. Do not read "STILL OPEN", "NOT been
> decided", or "remain unresolved" below as current.
>
> The UI-race note below **remains valid and is unaffected**: that picker selection was void
> then and is void now. It is simply not the basis of the current position — the later,
> genuine maintainer ruling is, and that ruling is authoritative.

*(Original pre-ruling text follows.)*

A "wire-then-enforce" sequence (materialize the pack via a local obligation row plus a CI
install step, then land the per-repo justfile/gitignore wiring, then flip the default) is
a **recommendation only**. It has NOT been decided. **[SUPERSEDED — decided: Option 3.]**

For the record, so it is never mistaken for a ruling: on 2026-07-25 a supervisor UI race
caused an `AskUserQuestion` picker to display "Wire-then-enforce" as an answer when the
maintainer had not chosen it. That selection is **void**. *(Still true.)* The three options
in §rollout — repriced by the findings above — remain unresolved, and any slice cut that
assumes an ordering is a draft. **[SUPERSEDED — Option 3 was subsequently ruled by the
maintainer; the options are resolved.]**

## The work

### A — verifier: absent pack becomes a FAIL, gated on config

**The fail-open, demonstrated rather than read (2026-07-25).** `_inspect_worktree_pack`
was executed directly against four throwaway trees in a scratch dir — no repo touched:

| tree state | verdict |
|---|---|
| pack entirely absent — **the live state of 8 of 9 verifier-running repos** | **`PASS`** ← the hole |
| pack complete + byte-correct — the state of `livespec-orchestrator-git-jsonl` | `PASS` |
| pack partial (one file removed) | `FAIL worktree_pack_file_missing` |
| pack present but drifted | `FAIL worktree_pack_body_mismatch` |

Stated as sharply as it goes: **installing three of the four pack files is a FAIL;
installing none of them is a PASS.** The check punishes a partial install and rewards a
total absence. That is the fail-open in one line, and it is now an executed result rather
than an inference from `:298-300`.

It also fixes the shape of slice A's Red test precisely: the test must assert that row 1
becomes a FAIL under `required`, while rows 3 and 4 keep their existing failure modes
unchanged — the §"Keep the existing partial-install and byte-drift arms exactly as they
are" requirement below is what stops a fix for row 1 from collapsing rows 3 and 4 into it.

`_inspect_worktree_pack` (`:279-309`) returns `[]` when no pack file exists (`:298-300`).
That single early-return is the entire hole. Replace with a `.livespec.jsonc` read:
`required` (default) → absent pack is a new `worktree_pack_absent` failure carrying the
existing `_WORKTREE_PACK_REMEDY` (`:211`, already wired at `:359`); `optional` → today's
skip. Malformed declaration → FAIL, per the `harnesses` precedent.

**The `harnesses` precedent does NOT match decision A on the arm that matters.** Read
`load_harnesses` (`plugin_resolution.py:334-361`) — its four states are:

| `.livespec.jsonc` state | `harnesses` verdict | what decision A wants for `worktree_discipline` |
|---|---|---|
| file absent / unreadable / not an object | **SKIP** | *undecided — see below* |
| file present, key absent | **FAIL** ("required fleet-wide since M6") | **apply the default `required`**, i.e. FAIL only if the pack is also absent |
| key present, garbled | **FAIL** | FAIL — matches |
| key present, well-formed | OK | OK — matches |

The two agree on the malformed and well-formed arms. They **disagree on key-absent**:
`harnesses` fails outright on a missing key, whereas decision A's whole design is that a
missing key silently *means* `required`. So "copy the `harnesses` precedent" is the right
instinct for the malformed arm and the wrong instruction for the key-absent arm. Slice A
must implement the table's right-hand column, not `load_harnesses` verbatim, and its Red
test should pin the key-absent-plus-pack-present case as a **PASS** — which
`load_harnesses` would fail.

**And the file-absent arm is an unclosed fail-open by a different door.** If A inherits
`SKIP` for a missing `.livespec.jsonc`, then `rm .livespec.jsonc` becomes an undocumented,
unreviewable opt-out from worktree discipline — the exact silent-opt-out shape decision A
was written to eliminate (§"making any future `\"optional\"` an explicit reviewable
opt-out rather than silence"). All 13 governed clones carry the file today, so this is
latent, not live.

SKIP is *defensible* here for the same reason `plugin_resolution` gives it — the check may
run in a non-governed directory, where failing would be wrong. But it must be a **stated
choice with that rationale**, not an arm inherited by copy-paste. Name it in slice A's
acceptance criteria either way.

Keep the existing partial-install and byte-drift arms exactly as they are.

#### A-PREREQ — IMPLEMENTATION-READY PREP (2026-07-25)

The two prerequisites A cannot land without — the `worktree-pack` local obligation row and
the CI install step — prepared to implementation-ready. Both live in `livespec-dev-tooling`
only, so both are **boundary-independent**. Nothing implemented.

**1. Row ORDER is the whole design, and the obvious placement is wrong.**
`local_reconcile.py:85-91` walks `LOCAL_OBLIGATION_ROWS` **sequentially in tuple order**,
asserting first and reconciling only an unmet row. The `commit-refuse-hooks` row sits at
position 3 (`_contract_local_rows.py:89`) and its `assert_local` shells out to the **whole
verifier module** — pack arm included.

So if a `worktree-pack` row is appended anywhere *after* it, then in a pack-absent repo
under A:

1. `commit-refuse-hooks` asserts → runs the whole verifier → **FAILS on the pack arm**;
2. its reconcile installs the hook — which was never the problem — and the row still
   reports a finding;
3. the pack is only materialized later, by a different row.

The result is a row failing for another row's obligation, with a reconcile that cannot
clear it. That is the un-self-healing shape flagged earlier, made worse by the failing row
running first.

**Resolution — place `worktree-pack` at position 3, immediately BEFORE `commit-refuse-hooks`
(after `uv-sync`).** Then the pack is materialized first and the hook row's broad assert
passes for the right reason. `uv-sync` must still precede it, because the reconcile runs
`python -m livespec_dev_tooling.install_worktree_pack`.

The purer alternative — narrowing `commit-refuse-hooks`'s assert so each row asserts only
its own obligation — is a larger diff that changes existing behaviour, and it discards a
useful end-to-end check. Prefer the reorder; keep narrowing in reserve if row attribution
later becomes confusing. Note the residue either way: if the pack row's reconcile *fails*,
the hook row fails too and the same cause is reported twice.

**2. The row itself.** `assert_local` byte-compares the four `_WORKTREE_PACK_FILES` in
`dev-tooling/` (the same comparison `_inspect_worktree_pack` already makes — import the
constants, do not restate the bodies); `reconcile_local` runs the installer, mirroring
`reconcile_commit_refuse_hooks` at `_rows_local.py:86-93`. It is a row *with* a real
`assert_local`, not a pure provisioning row, because it leaves persistent state — exactly
the criterion `_contract_local_rows.py:55-64` states.

**3. The CI step can mirror the hook step verbatim — verified.**
`ci.yml:410-412` installs the hook with plain `python3` **before** `mise trust` and
`uv sync`, because it needs only the stdlib plus the in-package vendored `structlog`.
`install_worktree_pack` has the same import surface — `stat`, `subprocess`, `sys`,
`pathlib`, vendored `structlog` — and imports cleanly under system `python3` 3.13.7 with a
`main()`. So the step is:

```yaml
- name: Install canonical worktree pack (satisfy invariant)
  if: matrix.target == 'check-primary-checkout-commit-refuse-hook-installed'
  run: python3 -m livespec_dev_tooling.install_worktree_pack
```

placed beside the existing hook step and gated on the same matrix target. **Without this
step A reds this repo's own CI on the PR that lands it** — tracked `dev-tooling/` holds only
`CLAUDE.md`, so a fresh CI checkout has zero pack files.

**4. This repo also needs its own wiring, and it rides A-prereq.** `livespec-dev-tooling`
has the `install-worktree-pack` recipe but **no** `.gitignore` entries, **no** `import?`
lines, and **no** `bootstrap` tail. Adding the row supplies the bootstrap path, but the
gitignore entries are still required or the freshly materialized pack shows up as four
untracked files in `git status` — the canonical repo failing its own rule. Include them.

**5. Sequencing inside the approved order.** A-prereq is additive: the row and the CI step
change no verdict while the default is still today's skip-when-absent. It can land any time
after B and before D without a red window, which is exactly why the approved order places it
there.

#### A AS SPECIFIED DOES NOT CLOSE THE LAYER IT WAS WRITTEN TO CLOSE

Demonstrated 2026-07-25 in a scratch tree — pack installed byte-perfect, root justfile
carrying no `import?` lines (the state of 5 governed repos):

```
verifier verdict with FULL byte-correct pack + no import? lines: PASS
just --list  ->  Available recipes:
                     check
worktree-create present?  ->  0
```

**The verifier never reads the justfile.** `_inspect_worktree_pack` looks only for four
files under `dev-tooling/`; it returned PASS on a bare temp directory whose entire content
was that pack. Nothing anywhere verifies the two `import?` lines —
`grep -rn "import?" livespec_dev_tooling/checks/ livespec_dev_tooling/fleet/` is empty, and
`canonical_recipe_fidelity` covers only `check-<slug>:` recipes, not the pack's imports.

Now re-read §"The incident" causal chain. Step 1 was *"ran `just --list`, found no
`worktree-create` recipe, and fell back to raw `git worktree add worktrees/<branch>`"*.
The operative failure was **the sanctioned tool was not discoverable**, not "four files
were missing from a directory". Item A as written makes the *files* mandatory and leaves
*discoverability* exactly as it was.

**And A's remedy actively rewards the broken state.** After A lands, the cheapest way for
a repo to clear a `worktree_pack_absent` FAIL is to install the four files and stop —
which is precisely the configuration demonstrated above: **verifier-green and
operator-broken.** A session in such a repo runs `just --list`, still sees no
`worktree-create`, and falls back to raw `git worktree add` exactly as in the incident.
Only item B would then catch it, at first commit, after the directory exists.

That incentive inversion is invisible today only because no repo is currently in the
pack-files-without-imports state — the 3 repos with imports also have the recipe, and the
5 without have neither. Landing A creates the pressure that produces that state for the
first time.

**Slice A must therefore also assert discoverability**, by one of:

- extending the verifier to require the two `import?` lines in the root justfile (keeps
  the single-source byte-compare shape, adds a `worktree_pack_not_imported` failure mode);
  or
- having `install_worktree_pack` write the `import?` lines itself, so installing the pack
  is inherently sufficient — at the cost of the installer mutating a tracked file, which
  is a shape it does not currently have.

The first is the smaller change and matches how the pack is already verified. Either way
this is a **correction to slice A's scope, not an optional extra**: without it, A closes a
proxy for the hole rather than the hole.

**Bound by Red-Green-Replay** (product `.py`): stage the test ALONE, commit, confirm it
fails; then `git commit --amend` with the impl. Test bytes must be identical across the
pair. Existing tests to extend:
`tests/livespec_dev_tooling/checks/test_primary_checkout_commit_refuse_hook_installed.py`
and `tests/livespec_dev_tooling/test_install_worktree_pack.py`.

### B — hook: refuse commits from a worktree nested in the primary's working tree

Insert the §B branch after `CANONICAL_HOOK_BODY:123`. Also `.py`, so also Red-Green-Replay.

**Honest limit, and it belongs in the doc comment:** git has no `pre-worktree-add` hook,
so this fires at first *commit*, after the directory already exists. It cannot prevent
creation. It converts a 25-minute silent violation into an immediate refusal — that is
the actual promise; do not overstate it.

#### B — IMPLEMENTATION-READY PREP (2026-07-25)

B is first in the approved rollout order and is **boundary-independent** — it lands in the
9 fleet clones under either reading of clause 2 — so it was prepared to
implementation-ready while the boundary question was still pending. The boundary has since
been ruled NARROW, which does not change any of it — B lands in the 9 fleet repos either
way. Nothing below was implemented.

**1. The sanctioned root already has one definition — reuse it, do not invent a second.**
`livespec_dev_tooling/fleet/_rows_local.py:112-114` defines it as `<home>/.worktrees`, and
the `worktree-root-mise-trust` obligation row uses exactly that. The hook must derive it
the same way (`$HOME/.worktrees`), so the hook and the row can never disagree about what
"sanctioned" means. This also matches the spec's "single **per-user** root" wording.

**2. Deriving it from `$HOME` is what makes B testable.** `_run_installed_hook` in
`tests/livespec_dev_tooling/test_install_commit_refuse_hooks.py:128-140` already builds an
`env = dict(os.environ)` and mutates `PATH`; adding `env["HOME"] = str(tmp_path/"home")` is
a one-line extension. A hook that read the root from anywhere else would need a new seam.

**3. B BREAKS an existing passing test, and that is correct.**
`test_installed_hook_delegates_at_worktree` (`:218-232`) asserts `returncode == 0` and no
`"refusing"` for a worktree created by `_init_primary_with_worktree`, which places it at
`tmp_path / "wt-feature"` (`:93`) — a pytest tmpdir, **not** under `$HOME/.worktrees`. Under
B that worktree is unsanctioned and must be refused. The test encodes the *pre-B* contract
("a worktree delegates"); B changes it to "a **sanctioned** worktree delegates, an
unsanctioned one refuses". **Update that test as part of B's Red step** — either point its
fixture at a sanctioned root under a faked `$HOME`, or split it into the sanctioned and
unsanctioned cases. Do not delete it.

**4. The sandbox-exempt regression is ALREADY covered — the suite will catch it.**
`test_installed_hook_sandbox_exempt_bypasses_refuse_at_primary` (`:235-251`) asserts
`returncode == 0` and no `"refusing"` at an exempt primary. Since `livespec.sandboxExempt`
makes the existing arm fall through, a naive B refuses that primary and **this existing
test goes red**. That upgrades the earlier finding from "remember to add a guard" to "the
guard is already enforced by a test you cannot ignore". Keep it green by guarding the new
branch on `sandbox_exempt`, or by anchoring the pattern so it cannot match the primary's own
root.

**5. The remedy message MUST NOT reference the pack.** The ruling pairs B with an
actionable remedy, and B ships *before* D's wiring — so a message pointing at
`just install-worktree-pack` or `just worktree-create` names a recipe absent from 5 of 9
fleet repos at the moment B lands. The remedy must stand on plain git:

```
livespec: refusing commit from a worktree outside the sanctioned root
  this worktree:  <this_root>
  sanctioned:     $HOME/.worktrees/<repo>/<branch>
  to fix:         git worktree move "<this_root>" "$HOME/.worktrees/<repo>/<branch>"
```

`git worktree move` is available everywhere and preserves unpushed work. Once D lands, the
message MAY additionally mention `just worktree-create` for new worktrees — but the plain-git
line must remain, because adopters and any repo mid-sweep will not have the recipe.

**6. Red step (product `.py` → Red–Green–Replay).** Stage the test file ALONE with
`CANONICAL_HOOK_BODY` unmodified on disk. New/updated cases, all driving the installed hook
through the existing `_run_installed_hook` harness with a faked `$HOME`:

| case | expected |
|---|---|
| worktree under `$HOME/.worktrees/<repo>/<branch>` | delegates, rc 0, no "refusing" |
| worktree nested inside the primary's working tree | **refuses**, rc 1, message names the move command |
| worktree that is a *peer* of the primary (not nested, not sanctioned) | **refuses** — this is the clause the spec names explicitly |
| worktree under the primary's `.git/` (beads-sync shape) | delegates, rc 0 — the carve-out |
| primary checkout, not exempt | refuses via the **existing** arm (unchanged message) |
| primary checkout, `sandboxExempt=true` | delegates, rc 0 — existing test, must stay green |

The peer case is the one with no current coverage at all and is the reason the spec's named
prohibition went unenforced; it must be in the Red.

**7. Acceptance evidence — the injected defects that must turn it red.** Per the charter, a
verifier that cannot fail is not a verifier. Each of these must produce a red run:

- delete the `.git/` carve-out arm → the beads-sync case reds (rehearsed: all three sampled
  beads worktrees flip to refused);
- drop the `sandbox_exempt` guard → the existing exempt-primary test reds;
- replace the allow-list with the old nested-only test → the **peer** case reds;
- point the sanctioned root at a literal other than `<home>/.worktrees` → the sanctioned
  case reds.

**8. Still needs a decision inside B: the janitor carve-out.** The spec's §"Worktree root"
parenthetical puts "orchestrator-internal janitor worktrees, which the Dispatcher creates and
removes **inside the integration clone**" out of scope. B refuses exactly that shape, and the
`.git/` carve-out does not cover a janitor worktree in an integration clone's *working* tree.
All 5 current `janitor-*` worktrees sit under `~/.worktrees/…-beads-fabro/` and pass, so
nothing breaks today. B must either carve the case out explicitly or state that the
inside-the-clone configuration is unsupported — silently refusing a spec-sanctioned case is
the same class of error as silently allowing one.

#### B rehearsed against real host paths — 2026-07-25

The §B snippet was executed read-only against the live host (no repo mutated, no hook
installed, no config written) to check it before anyone writes the Red test. The rule is
sound on the cases the acceptance criteria name, but **the snippet as recorded above has
one real defect**, and one of its stated justifications does not hold up.

**Canonical rule — behaves as specified:**

| case | verdict |
|---|---|
| primary `/data/projects/livespec-dev-tooling` | `PRIMARY-EXIT` — the existing `:120-123` arm fires; the new branch is never reached |
| sanctioned `~/.worktrees/livespec-dev-tooling/ci-concurrency-group` | `ALLOW` |
| nested `openbrain/.claude/worktrees/fix-ob-6vt-thought-detail-save` | **`REFUSE-NESTED`** ✅ |
| beads `agent-flywheel/.git/beads-worktrees/beads-sync` | **`ALLOW-TOOLING`** ✅ |

**Injected-defect proof — the rule CAN turn red.** Removing the `.git/` carve-out arm and
re-running flips all three beads sync worktrees tested (`agent-flywheel`, `beads`,
`personal-knowledge-base`) from `ALLOW-TOOLING` to `REFUSE-NESTED`. That is the concrete
injected defect the acceptance criteria should name for slice B: **delete the carve-out
arm and the beads-sync case must go red.** A carve-out test that cannot fail is not a
test.

**DEFECT in the snippet as recorded: a sandbox-exempt primary would be hard-refused.**

`livespec.sandboxExempt=true` makes the existing arm at `:120` deliberately NOT exit —
that is the documented in-sandbox opt-out (`install_commit_refuse_hooks.py:88`: "with it
set the refuse branch is skipped so in-sandbox [commits work]"). Control therefore falls
through to the new §B branch, where `this_root == primary_root`, and

```
case "/data/projects/livespec-dev-tooling/" in "/data/projects/livespec-dev-tooling"/*)
```

**matches**, because `*` matches the empty string after the trailing slash. Verdict:
`REFUSE-NESTED`. The new branch would silently revoke the sandbox opt-out for every
exempt primary.

Latent, not live — `livespec.sandboxExempt` is unset in every repo checked on this host,
so nothing is broken today and it would first surface in a sandboxed CI context. Two
candidate fixes, both cheap: guard the new branch with the same `sandbox_exempt` test, or
anchor the nested pattern as `"$primary_root"/?*` so it requires at least one character
after the slash. **Slice B must carry a Red test for the exempt-primary case**, or this
ships as a regression.

**Also: the snippet shadows `git_dir`.** It assigns `git_dir=$(cd "$common_dir" && pwd -P)`,
clobbering the value read at `:117`. Nothing after `:123` reads `git_dir` today (only
`hook_name` and the `exec`), so it is not a live corruption — but it reads as if it reuses
the earlier value when it does not. Rename it in the implementation.

**Correction: `pwd -P` is NOT demonstrated load-bearing.** Re-running every case with
`pwd -P` replaced by plain `pwd` changed **no verdict**. The reason is that
`git rev-parse --show-toplevel` and `--git-common-dir` already emit *physical* paths: from
`/home/ubuntu/workspace/openbrain/.claude/worktrees/fix-ob-6vt-…`, `--show-toplevel`
returns `/data/projects/openbrain/.claude/…` and `--git-common-dir` returns
`/data/projects/openbrain/.git`. Git normalizes before the comparison ever runs.

The inode evidence in §E is still correct — the two trees *are* aliases — but it proves
aliasing exists, not that aliasing changes a verdict. The earlier claim that this is "a
real bug source here, not a hypothetical" is **unsupported**; treat `pwd -P` as cheap,
harmless insurance rather than as a fix for an observed bug. (The one place it could
matter — an aliased *primary* where `--git-common-dir` returns the relative `.git` — is
reachable only in the sandbox-exempt case the defect above says to exclude outright.)

### C — installer + docs write the key with its default

Installation docs must write `worktree_discipline.pack` with its default value, so new
adopters get it without archaeology.

### D — fleet sweep

Install the pack in the **8** non-compliant verifier-running repos; write the key into
all **13** `.livespec.jsonc` carriers; ensure every clone's hook is current after B
lands. Order per §rollout.

Per the correction in §rollout, the hook leg of this sweep is `just bootstrap` (the
`local_reconcile` `commit-refuse-hooks` row), not a bespoke per-clone
`install-commit-refuse-hooks` walk. The pack leg has **no** such row today; adding one
is part of the slice.

#### D is two different jobs, not one — WIRED vs HYDRATED (measured 2026-07-25)

The fleet-impact table's `pack: ABSENT` column conflates two states that need completely
different remedies. Measured across all 9 verifier-running repos, the four wiring
components (`.gitignore` ×4, both `import?` lines, the `install-worktree-pack` recipe, the
`bootstrap` tail) are present in **3** repos and absent in **6**:

| state | repos | what clears A's new FAIL |
|---|---|---|
| **wired, not hydrated** — all 4 components present, pack files simply not materialized on this host | `livespec-orchestrator-beads-fabro`, `livespec-console-beads-fabro` | **`just bootstrap`.** No PR, no tracked change. Host-local, exactly like `.git/hooks/` |
| **wired and hydrated** | `livespec-orchestrator-git-jsonl` | nothing — already green |
| **unwired** — none of the 4 components | `livespec`, `livespec-dev-tooling`, `livespec-driver-claude`, `livespec-driver-codex`, `livespec-runtime`, `livespec-overseer` | a ~10-line tracked PR each, then `just bootstrap` |

All three wired repos carry byte-identical wiring, including the same
`chmod +x dev-tooling/worktree-hydrate.sh` bootstrap line.

**This shrinks D and sharpens the rollout arithmetic.** The tracked fleet sweep is **6
repos, not 8** — and two of the eight "non-compliant" repos are one command away from
green with no PR at all. It also means A's FAIL, when it lands, will be a *different kind
of problem* in each group, so the remedy string must cover both: run `just bootstrap`
first, and only if the recipe does not exist, wire the repo.

#### Why the fleet keeps producing unwired repos

`livespec/templates/orchestrator-plugin/` is fully compliant — it ships all four wiring
components plus 6 `.worktrees` mentions in its `AGENTS.md`. A repo scaffolded from it is
**born compliant**, which is why the wired repos are wired.

But it is the **only** template. The manifest defines seven classes — `core`,
`enforcement-suite`, `impl-plugin`, `driver-plugin`, `library`, `console`,
`control-plane-tool` — and `ls livespec/templates/` returns exactly one entry. Every
member of the other six classes is scaffolded by hand.

`livespec-overseer` is the proof: the newest fleet member, class `control-plane-tool`, a
class with no template, born with **zero** wiring and **zero** `.worktrees` prose in its
`AGENTS.md`. It did not drift out of compliance — it was never in it.

So the fleet's own birth procedure reproduces exactly the non-compliance A–E is trying to
sweep away, and will keep doing so for every future non-`impl-plugin` member. Sweeping the
6 repos without addressing this fixes the population and not the generator. Whether that
belongs in this thread or in the fleet-membership/birth-procedure lane is a scoping call
for the maintainer — but it should be a decision, not an omission.

### E — relocate the live nested worktrees (openbrain, and now livespec-overseer)

*(Heading corrected 2026-07-25 — it previously read "openbrain has the last live
violation", which is no longer true on two counts: `livespec-overseer` acquired a nested
worktree mid-audit, and the spec's named prohibition is the peer case, which E never
covered. E's scope as written below is openbrain only; whether it grows to cover the
overseer worktree — which belongs to another session — is part of the unapproved cut.)*

```
/data/projects/openbrain/.claude/worktrees/fix-ob-6vt-thought-detail-save  [fix/ob-6vt-thought-detail-save]
```

**Re-inspected 2026-07-25 and still live.** Measured state:

- working tree is **clean** — `git status --short` is empty, so there is no uncommitted
  work to lose;
- branch `fix/ob-6vt-thought-detail-save` sits at `296dd1f`
  ("Fix thought detail save importance payload (ob-6vt)") with **no upstream** —
  `git ls-remote --heads origin 'fix/ob-6vt*'` returns nothing, so that commit exists
  **only** in this worktree's branch. It is unpushed work; a `git worktree move`
  preserves it, a `git worktree remove` would destroy it;
- directory mtime is **2026-06-24**, 31 days stale;
- **no live process is cwd'd inside it** (scan of `/proc/*/cwd`), and there is no tmux
  session for openbrain. No evidence of an owning live session.

It is in the **working tree**, not `.git/`, so it is a genuine violation of the rule.
**But item B will NOT refuse its next commit** — see the correction in §"Fleet impact":
`openbrain` runs no livespec canonical hook at all (its `.git/hooks/pre-commit` is a stock
lefthook stub), so changing `CANONICAL_HOOK_BODY` does not reach it. Relocate it for
hygiene and consistency with the rule, not because B would otherwise strand it.
Maintainer decided: **relocate it as part of the sweep** (`git worktree move` to
`~/.worktrees/openbrain/<branch>`), before B ships, so nobody is stranded mid-branch.
The pre-move inspection this called for is now done and recorded above; the move itself
still needs maintainer authority and has NOT been performed.

A fleet rescan on 2026-07-25 using the §B rule (physical paths via `realpath`, `.git/`
carve-out applied) across every clone under `/data/projects`, `/home/ubuntu/workspace`,
and `~/.worktrees` again found openbrain as the **only** genuine nested violation, out of
34 non-primary worktrees — independent confirmation the carve-out is still drawn
correctly. The same four beads sync worktrees are still what the carve-out protects:

```
agent-flywheel                       .git/beads-worktrees/beads-sync
beads                                .git/beads-worktrees/beads-metadata
gdk-in-a-box-agent-flywheel-wrapper  .git/beads-worktrees/beads-sync
personal-knowledge-base              .git/beads-worktrees/beads-sync
```

**`pwd -P` re-verified as load-bearing:** `/home/ubuntu/workspace` is a symlink whose
`realpath` is `/data/projects`, and `.livespec.jsonc` in both paths resolves to the same
inode (`29625545` for `livespec-dev-tooling`, `28075442` for `livespec`). Without
physical-path resolution the prefix comparison still gives different answers depending
on which path a worktree was created through.

### A SECOND LIVE VIOLATION APPEARED DURING THIS AUDIT (2026-07-25)

A fleet-wide rescan at 15:2x found a nested worktree that **did not exist** at the
10:2x scan earlier the same day:

```
/data/projects/livespec-overseer/.claude/worktrees/dod-corrections   [docs/dod-corrections-pr78]
```

Read-only inspection (not touched, not moved — it is another session's worktree):

- created **2026-07-25 15:21**, hours into this audit;
- branch `docs/dod-corrections-pr78`, already carrying commits (`7e51fdf`, `c28b64b`);
- working tree clean;
- no process currently cwd'd inside — which does **not** establish abandonment; a session
  between turns looks identical. Ownership was not established and no action was taken.

**Why this matters more than the count.**

1. **It is in a governed fleet repo that DOES run the canonical hook.** Unlike openbrain,
   `livespec-overseer` carries the canonical `CANONICAL_HOOK_BODY` byte-for-byte. So item
   B **would** have refused those two commits. This is the first measured case where B is
   demonstrably the operative control rather than a control that cannot reach the repo.
2. **It was completely invisible.** `git status` on the primary shows nothing, because
   `livespec-overseer/.gitignore:5` ignores `.claude/worktrees/`. The 2026-07-19 incident
   was caught *only* because `livespec-console-beads-fabro` does not gitignore its
   worktrees directory. Here there was no tripwire at all — this was found by running the
   §B rule, not by anyone noticing.
3. **It changes the thread's own premise.** §"The incident" describes a violation that
   "fired once for real". That is no longer accurate. It fires **repeatedly**, in fleet
   repos, silently, and it fired again *while this thread was actively auditing the
   hazard* — with commits landed from the offending worktree. The honest framing is a
   recurring live defect with an unknown base rate, not a single historical incident with
   one lingering remnant.

That third point is the strongest argument in the file for doing this work at all, and it
is empirical rather than rhetorical. It also argues against any rollout option whose cost
is measured purely in dead PRs: every day the fail-open stays open is a day this can
happen again unnoticed.

### Widening to the spec's rule was rehearsed — it is cheap and clean

Since `SPECIFICATION/non-functional-requirements.md:1013` states the rule positively (see
§"THE SPEC ALREADY ANSWERS…"), a widened branch was rehearsed read-only against **every**
worktree on this host — refuse anything that is neither tooling-internal nor under
`~/.worktrees/`:

```sh
case "$this_root/" in
  "$common_abs"/*)  ;;                        # tooling-internal — ALLOW
  "$sanctioned"/*)  ;;                        # under ~/.worktrees — ALLOW
  *)                refuse_unsanctioned ;;    # everything else — REFUSE
esac
```

Result over 40 worktrees:

| verdict | count | which |
|---|---|---|
| `ALLOW-SANCTIONED` | 34 | every worktree under `~/.worktrees/`, **including all 5 orchestrator `janitor-*` worktrees** |
| `ALLOW-TOOLING` | 4 | the beads `.git/beads-worktrees/` sync worktrees |
| **`REFUSE-UNSANCTIONED`** | **2** | `openbrain/.claude/worktrees/fix-ob-6vt-…`, `livespec-overseer/.claude/worktrees/dod-corrections` |

**Zero false positives.** Both refusals are genuine violations. The janitor worktrees pass
because they currently live under the sanctioned root, which also means the spec's
janitor carve-out costs nothing *today* — though the collision noted in §"THE SPEC ALREADY
ANSWERS…" still applies if a Dispatcher ever places them inside the integration clone.

**Bearing on the maintainer's decision:** widening from "not nested" to the spec's actual
rule is a **three-line change to the same `case` statement**, not a redesign, and on
current host state it refuses exactly the two things that should be refused. Whatever the
choice, it should not be made on an assumption that widening is expensive — measured, it
is not.

(The rehearsal also carries the sandbox-exempt guard from §B's earlier rehearsal; without
it the widened arm refuses exempt primaries for the same reason.)

### The §B rule does NOT catch peer worktrees — a newly measured gap

The 2026-07-25 rescan surfaced **5 worktrees that live outside `~/.worktrees/` but are
not nested under their primary's working tree**, so §B's `case "$this_root/" in
"$primary_root"/*)` arm never matches them:

```
/data/projects/homelab-substrate                     ← primary: /data/projects/homelab  (GOVERNED adopter)
/home/ubuntu/.local/state/kilroy/attractor/runs/*/worktree  (×4)  ← primary: /data/projects/cxdb-graph-ui  (not governed)
```

`homelab-substrate` is the one that matters: `homelab` is a **registered adopter**, and a
peer-directory worktree violates the prose rule exactly as a nested one does — item B
will silently allow it. The four kilroy worktrees are tool-managed run scratch in a
non-governed repo and are almost certainly fine to leave alone.

> **Update, same day (2026-07-25): `/data/projects/homelab-substrate` no longer exists.**
> It was removed by the `homelab` track during the hours this audit ran —
> `git -C /data/projects/homelab worktree list` now shows only the primary, and the
> worktree was not relocated under `~/.worktrees/`. This thread did not touch it and does
> not own it. **The live instance is gone; the structural gap is not.** The rule below
> still permits a peer-directory worktree of any governed repo, and the next one will be
> just as silent. Do not let the disappearance of the example be read as closure of the
> finding — that is exactly the "it fired once and was cleaned up, so nothing needs
> fixing" pattern this whole thread exists to reject.

This is a **scope finding, not a defect in the settled decision B**: the maintainer chose
"refuse *nested*", and nested is what B refuses. But the handoff previously implied
openbrain was the last violation fleet-wide, and that is no longer true under the prose
rule — only under the narrower nested rule. Whether to widen the refusal to
"anything not under `~/.worktrees/`" is a **new** question the maintainer has not been
asked, and it is deliberately NOT folded into the A–E cut below.

#### THE SPEC ALREADY ANSWERS THE DEFINITION-OF-DONE QUESTION (2026-07-25)

The rule is **not** merely `AGENTS.md` prose. It is a ratified invariant in livespec core
at `SPECIFICATION/non-functional-requirements.md:1013`, §"Worktree root and mise trust":

> Every git worktree lives under a single per-user root — `~/.worktrees/<repo>/<branch>` —
> NEVER as a peer of the first-class clones in the workspace directory
> (`/data/projects/<repo>`). … The rule is fleet-wide-by-intent: it applies uniformly to
> `livespec` and every sibling repo. (Orchestrator-internal janitor worktrees, which the
> Dispatcher creates and removes inside the integration clone per its own configuration,
> are out of scope for this maintainer/agent convention.)

Read it precisely, because it does not say what this thread assumed:

1. **The primary clause is POSITIVE** — every worktree lives under
   `~/.worktrees/<repo>/<branch>`. That is the invariant.
2. **The one explicitly-named prohibition is the PEER case** — "NEVER as a peer of the
   first-class clones in the workspace directory". The spec names
   `/data/projects/<repo>`-adjacent placement by name. That is **exactly the case item B
   does not catch**, and exactly what `/data/projects/homelab-substrate` was.
3. **The nested case item B does catch is not named at all.** It is forbidden only as a
   consequence of the positive clause.

So the framing in this thread has been backwards. `homelab-substrate` was not a
peripheral scope curiosity — it was a **direct violation of the only prohibition the spec
spells out**, while openbrain's nested worktree violates the positive clause the spec
leads with. A cut that closes the nested case and leaves the peer case open satisfies
neither the letter nor the lead of the ratified invariant.

**Consequence for the maintainer's first question:** the definition of done is not an open
choice between "clause (ii) only" and "both clauses" — the spec already picked. Enforcing
only nested-refusal leaves a ratified invariant unenforced in the very case it names. The
live question is narrower and different: *does this thread widen to the spec's actual
rule, or does it ship the nested-only cut and open a follow-on to close the rest?* Both
are legitimate; presenting the first as "done" is not.
**[ANSWERED — the thread widened. B is a positive-location allow-list, both clauses are
enforced, and the boundary is the 9 `fleet` repos. The follow-on covers adopters only, as
`li-l53` and `hl-nhw`.]**

**A second thing the spec settles — and a possible collision with B.** The parenthetical
carves out "orchestrator-internal janitor worktrees, which the Dispatcher creates and
removes **inside the integration clone**". Worktrees inside a clone are precisely what
item B hard-refuses. The `.git/` carve-out does not help: it covers beads' sync worktrees
under `.git/beads-worktrees/`, not a janitor worktree in an integration clone's *working
tree*. Today's janitor worktrees all sit under `~/.worktrees/livespec-orchestrator-beads-fabro/`
(`janitor-bd-ib-*`), so nothing is broken now — but if a Dispatcher ever creates them where
the spec says it may, **B would refuse their commits**, and B's carve-out set would need a
third arm. Slice B should either state that this configuration is unsupported or carve it
out; silently refusing a spec-sanctioned case is the same class of error as silently
allowing one.

#### Does this change B, or the thread's definition of done? — HISTORICAL PRE-RULING ANALYSIS, FULLY SUPERSEDED

> **READ THIS FIRST. Everything in this subsection is pre-ruling analysis, retained only as
> decision history. It is NOT current advice, and several of its statements are now false.**
>
> **The current answers:**
> - **B IS widened.** B is a **positive-location allow-list** — refuse any worktree that is
>   neither tooling-internal nor under `~/.worktrees/`. It is no longer the nested-only rule
>   this subsection analyses.
> - **Both clauses are required.** Full-location scope was approved
>   (§"MAINTAINER RULING — full-location scope"), so the "which clause" question below is
>   settled: both.
> - **The boundary is NARROW** — the 9 `fleet` repos
>   (§"MAINTAINER RULING — NARROW boundary"). All 9 have the substrate, so clause 2 is
>   delivered by **B and D**; there is no F slice in this thread.
> - **Adopter gaps are follow-up work**, filed as **`li-l53`** (resume tenant) and
>   **`hl-nhw`** (homelab tenant). openbrain keeps only E's relocation.
> - **The current final cut is A, B, C, D, E, (G).**
>
> In particular, this subsection's closing "bottom line" — that the cut is approvable only
> as *"close the nested fail-open"* and not as *"enforce the worktree-location rule"* — is
> **superseded**. Under the approved full-location scope with a widened B, the cut DOES
> enforce the rule, across the 9 fleet repos.

*(Original text follows, unmodified except where a later measurement corrected a fact.)*

It does **not** change B. B's charter is "refuse worktrees nested in the primary's
working tree," and B does exactly that. Nothing measured here makes B wrong or
incomplete against its own specification. **[SUPERSEDED — B's charter is now the
positive-location allow-list; B was widened by the full-location ruling.]**

It **does** put the thread's definition of done in question, and that must be settled
before the A–E cut can be called approvable. The charter's own rule, as written at the
top of this file, has two clauses:

- **(i) positive** — every worktree lives under `~/.worktrees/<repo>/<branch>`;
- **(ii) negative** — never inside a clone.

**A–E as cut enforces only (ii).** `/data/projects/homelab-substrate` satisfies (ii) and
violates (i), and B will permit it silently. So landing all of A–E would close the
nested-worktree hole — a real, narrower, still-valuable claim — while leaving the
charter's stated rule partially unenforced. A "done" claim phrased as "the rule is now
enforced" would be false; phrased as "nested worktrees are now refused" it would be true.
**[SUPERSEDED — the cut now enforces BOTH clauses across the 9 fleet repos, because B was
widened to a positive-location allow-list. `homelab-substrate` no longer exists, and
`homelab` is out of the narrow boundary in any case.]**

Three distinguishable questions fall out, and collapsing them would be dishonest:

1. **Should B widen** from "not nested" to "anything not under `~/.worktrees/`"? A scope
   change to an already-settled decision.
   *(**ANSWERED: YES.** B was widened; the positive-location allow-list is the current B.
   Rehearsed clean across 40 host worktrees — 2 refusals, zero false positives.)*
2. **Is the thread done when A–E land**, given clause (i) stays unenforced? This
   determines whether an F slice exists and therefore whether A–E is the whole cut.
   *(Historical. Answered: scope is full-location, and the boundary is NARROW — so F exists
   only as follow-up work outside this thread. Current final cut: A, B, C, D, E, (G).)*
3. **Should `homelab` (and `resume`, `dolt-server`) get baseline hook + verifier wiring
   at all?** Measured: `homelab` has no commit-refuse hook installed and no verifier
   recipe, so *nothing* in A–E — widened B included — reaches it today. That looks like
   adopter-onboarding work owned by another lane, not by this thread.
   *(**ANSWERED: yes, but as a separate lane.** The NARROW boundary puts adopters outside
   this thread; the backfill is filed as `li-l53` and `hl-nhw`, both blocked.)*

Note the interaction with question 3: even answering question 1 "yes, widen B" would not
catch `homelab-substrate`, because `homelab` runs no hook. Widening B buys coverage only
in repos that already have the baseline. That materially weakens the case for folding a
widened B into this thread, and strengthens treating clause (i) as a separately-scoped
follow-on. *(This reasoning was accepted — it is part of why the boundary was ruled NARROW.
But note its premise held only for adopters: all 9 fleet repos DO have the baseline, so a
widened B buys full clause-2 coverage there.)*

**Bottom line for the maintainer — SUPERSEDED, DO NOT ACT ON THIS.** The original text
read: *"the A–E cut is approvable as 'close the nested fail-open'. It is not approvable as
'enforce the worktree-location rule' until question 2 is answered."*

That is no longer the position. Question 2 **was** answered — full-location scope, both
clauses, NARROW boundary — and B **was** widened accordingly. **The current cut
(A, B, C, D, E, (G)) IS approvable as "enforce the worktree-location rule", scoped to the
9 `fleet` repos.** Acceptance criteria SHOULD claim exactly that, and must additionally
name the boundary so the adopter gap is visible rather than implied.

## First act is the maintainer's — nothing here is agent-dispatchable

**The open questions, in dependency order (2026-07-25).** The original text below lists
rollout order first; that ordering is superseded. Ask them in this order:

1. ~~**Does this thread enforce the spec's rule, or only the nested half?**~~
   **ANSWERED 2026-07-25 — full-location scope approved, both clauses.** See §"MAINTAINER
   RULING" at the top. The cut was briefly drawn as A–G; after the NARROW boundary ruling
   the **current final cut is A, B, C, D, E, (G)** — F is follow-up work, not this thread's.
2. ~~**Rollout order**~~ **ANSWERED 2026-07-25 — Option 3, hook-first, approved.** See
   §"MAINTAINER RULING — rollout order". The next open decision is the fleet-boundary
   question — **ANSWERED: narrow** (§"MAINTAINER RULING — NARROW boundary"). Only the final
   cut remains.
3. **The cut and its acceptance criteria**, re-cut once 1 and 2 settle — including the
   scope corrections to A (discoverability), B (sandbox-exempt guard, janitor carve-out,
   reach limited to fleet clones), D (6 tracked PRs + 3 bootstraps), and E (two worktrees
   now, one of them another session's).
4. **Authority to relocate.** openbrain is inspected and safe to move (clean tree,
   unpushed `296dd1f`, no upstream, no live owner). `livespec-overseer`'s belongs to
   another session and must not be touched without its owner.

**[SUPERSEDED 2026-07-26 — the slices ARE now filed](#) — seven records under the epic,
intake-routed; see §"MAINTAINER RULING — FINAL CUT APPROVED AND FILED". The paragraph below
describes the pre-approval state and its rationale, which is why filing waited for consent.**

**The epic is anchored; no slices are filed.** That split is deliberate. An active plan
thread MUST declare a concrete ledger anchor — `plan_thread_anchor_declared` enforces it
mechanically, and its rationale is exactly this thread's own failure mode ("a completed
plan thread was once treated as done ... while the plan lifecycle was left incomplete").
So `-0eo` exists as the thread's ledger identity. But *slicing* A–E into work-items is
the maintainer's cut, and `capture-work-item` / `groom` are consent-gated — a session
wrapping up should not file that unprompted.

So the honest first act is a maintainer act:

1. Answer §rollout order (blocks everything).
   *(**DONE** — Option 3, hook-first, approved.)*
2. File A–E as slices under `-0eo`, or run
   `/livespec-orchestrator-beads-fabro:plan worktree-location-enforcement` to resume this
   thread and let it do the filing with consent.
   *(**STILL OPEN, and now the ONLY gate.** The cut to file is **A, B, C, D, E, (G)** — not
   A–E as written above, and not A–G. Scope, rollout order, and the boundary are all
   approved; filing awaits approval of the final cut and its acceptance criteria.)*

Nothing here is agent-dispatchable until slices exist: `next` ranks work-items, and this
thread has none.

**Re-verified 2026-07-25:** `bd show livespec-dev-tooling-0eo` reports the epic still
`BACKLOG`, P2, updated 2026-07-20; `bd list --parent livespec-dev-tooling-0eo` reports
"has no children" and `bd dep tree` shows the epic alone. There is still no topic
implementation branch (`git branch -a --list '*worktree*' '*nested*' '*0eo*'` is empty),
no topic worktree, and no open PR for this thread — the only open PR on the repo is
#285 (`fix/generated-block-comment-syntax`), unrelated. The parked state is intact and
nothing was filed in the interim.

## Sequencing

1. **Rollout order decided first** — it changes the shape of D, not just its timing.
2. **A and B are independent code changes** but share one fleet sweep; land them close
   together so the sweep runs once, not twice.
3. **E before B ships** — otherwise openbrain's live worktree is stranded on first commit.
4. `livespec-dev-tooling`'s own pack install rides A (self-compliance).
5. Parallel-safe against `livespec-console-beads-fabro`'s `plan/repo-invariant-guards/`
   — no shared files. That thread's `-mvu22t` item ports `red_green_replay.py` **from**
   this repo; it reads, does not write, so there is no contention.
   *(Re-checked 2026-07-25: that thread still exists at
   `livespec-console-beads-fabro/plan/repo-invariant-guards/handoff.md` and the
   no-shared-files claim still holds.)*

## Gates

- Maintainer decision on rollout order.
- Maintainer epic anchor + item filing (see above).
- Red-Green-Replay on A and B (product `.py`; docs-only changes like this file are exempt).

## Reactivation audit — 2026-07-25

Measured against `origin/master` at `413a407` (131 commits past the `2412e21` base),
livespec core at `991943ef`. What follows is the delta only; the sections above already
carry the corrected facts.

### Survived unchanged — the thread's premises are still true

- All four `.py` files the analysis anchors into are **byte-identical** to `2412e21`
  (`git diff 2412e21..origin/master` reports no change for the verifier, the hook
  installer, the pack installer, or `plugin_resolution.py`). Every line anchor into them
  holds.
- The fail-open early return is still at `:298-300`.
- `worktree_discipline` appears **nowhere** in the repo — decision A is entirely
  unimplemented.
- The `.git/` carve-out is still load-bearing (same 4 beads sync worktrees).
- `pwd -P` is still load-bearing (`/home/ubuntu/workspace` → `/data/projects` symlink,
  identical inodes).
- openbrain is still the only genuine **nested** violation fleet-wide.
- Epic `-0eo` still has zero children; no topic branch, worktree, or PR exists.
- Parallel-safety against the console's `repo-invariant-guards` thread still holds.

### Changed — and it changes the decision

1. **Fleet membership grew.** `livespec-overseer` joined as `control-plane-tool`.
   Non-compliant verifier-running repos **7 → 8**; `.livespec.jsonc` carriers **12 → 13**.
2. **Release fan-out preflight: blocking gate → per-member filter**
   (`dispatch_matrix_filter.py`, new). A non-conformant member is excluded from dispatch
   and annotated; conformant members still get theirs. Structural failures still halt
   fail-closed.
3. **`reusable-pin-freshness.yml` dropped its pre-PR `just check`.** Bump PRs now open
   unconditionally and fail on their own CI, so verifier-first yields *stalled bump PRs*
   rather than *skipped bumps*.
4. **Item B cannot red CI.** `ci.yml` installs the canonical hook from the same wheel
   immediately before the check. B's blast radius is developer clones only.

### Corrections to premises that were wrong when written

- **`local_reconcile` already existed** (it predates `2412e21`; the original session
  missed it). Its `commit-refuse-hooks` LOCAL row has both an assert and a reconcile, and
  `just bootstrap` delegates to it — so per-clone hook reinstall is already mechanized.
  The handoff's "does not propagate ... per-clone and per-machine" framing overstated the
  manual burden of item B.
- **There is no `worktree-pack` local row**, so under item A the `commit-refuse-hooks`
  row becomes assert-red / reconcile-can't-fix in every pack-absent repo. New design
  input for slices A/D.
- **The prose rule is not in every repo's `AGENTS.md`** — 9 of 13 mention `.worktrees`;
  `livespec-driver-codex`, `livespec-overseer`, `homelab` have none and `dolt-server` has
  no `AGENTS.md`.
- **openbrain is not the last violation under the prose rule** — only under the narrower
  nested rule. `/data/projects/homelab-substrate` is a peer-directory worktree of the
  governed adopter `homelab` that item B will not catch.
- **`AGENTS.md` §Red-Green-Replay anchor** `:100-142` → `:100-147`.

### Late findings — measured after PR #631 merged

These four landed after the first audit PR and are recorded in the sections above:

1. **The pack is gitignored-and-materialized, not tracked** — so the rollout question's
   "pack-install-first" option was framed on a false premise. See §"The pack is
   GITIGNORED-AND-MATERIALIZED".
2. **Only 4 of 9 verifier-running repos expose an `install-worktree-pack` recipe**, and
   only 3 carry the `import?` lines. A's remedy string is unactionable in 5 repos, and
   pack bodies alone would not restore `just --list` discoverability there — the original
   incident's causal steps 1–2.
3. **Item A reds `livespec-dev-tooling`'s own CI on its landing PR**, because `ci.yml`
   materializes the hook but never the pack and `bootstrap` has no worktree-pack row.
4. **8 of 9 verifier-running repos gitignore a worktrees directory**, so the `git status`
   tripwire that caught the original incident is absent almost everywhere — independent
   support for B's hard refuse.

### Explicitly NOT done in this pass

No slices filed, no worktree moved, no implementation dispatched, no spec change, no
ledger edit — true as of that pass. **Superseded 2026-07-26: the seven approved slices are
now filed and intake-routed.** No worktree has been moved and nothing has been dispatched or
implemented.

**Decision status as of 2026-07-25** (this paragraph records a snapshot of an earlier pass;
these are its outcomes, not still-open items): scope is **APPROVED** — full-location, both
clauses (§"MAINTAINER RULING — full-location scope"), so the definition-of-done question
this pass raised is settled; the cut was briefly A–G and is now **A, B, C, D, E, (G)** after
the NARROW boundary ruling dropped F to a follow-up. Rollout order is
**APPROVED** — Option 3, hook-first (§"MAINTAINER RULING — rollout order"), which supersedes
the "wire-then-enforce" recommendation this pass floated; the picker answer that briefly
displayed that recommendation was a supervisor UI race artifact and remains void
independently of the later ruling.

**The final cut was APPROVED and FILED 2026-07-26.** The fleet-boundary question was
answered NARROW (§"MAINTAINER RULING — NARROW boundary").
