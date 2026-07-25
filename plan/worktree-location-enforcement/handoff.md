# Worktree-location enforcement — close the three fail-open layers

**Ledger anchor:** epic `livespec-dev-tooling-0eo`

**No slices filed.** The epic is the thread's ledger identity only; A–E below are NOT
work-items. See §"First act is the maintainer's".

**Opened:** 2026-07-20, out of a live violation in `livespec-console-beads-fabro`
(incident summary below). The original analysis was verified against `origin/master`
at **`2412e21`**.

**Remeasured 2026-07-25** against `origin/master` at **`413a407`** — 131 commits
later. See §"Reactivation audit — 2026-07-25" at the end of this file for the
measured delta, the corrections to premises that were wrong when written, and the
facts below that survived. Inline numbers and anchors in this file have been
updated to the 2026-07-25 measurement; do not reason from the `2412e21` counts.

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
a latent gap. It fired once for real, and one live violation remains fleet-wide
(§openbrain). That difference is why this is its own thread rather than a fourth item
there.

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

### Status of the rollout question after these findings: STILL OPEN

A "wire-then-enforce" sequence (materialize the pack via a local obligation row plus a CI
install step, then land the per-repo justfile/gitignore wiring, then flip the default) is
a **recommendation only**. It has NOT been decided.

For the record, so it is never mistaken for a ruling: on 2026-07-25 a supervisor UI race
caused an `AskUserQuestion` picker to display "Wire-then-enforce" as an answer when the
maintainer had not chosen it. That selection is **void**. The three options in §rollout —
repriced by the findings above — remain unresolved, and any slice cut that assumes an
ordering is a draft.

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

### E — openbrain has the last live violation

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

#### Does this change B, or the thread's definition of done?

It does **not** change B. B's charter is "refuse worktrees nested in the primary's
working tree," and B does exactly that. Nothing measured here makes B wrong or
incomplete against its own specification.

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

Three distinguishable questions fall out, and collapsing them would be dishonest:

1. **Should B widen** from "not nested" to "anything not under `~/.worktrees/`"? A scope
   change to an already-settled decision.
2. **Is the thread done when A–E land**, given clause (i) stays unenforced? This
   determines whether an F slice exists and therefore whether A–E is the whole cut.
3. **Should `homelab` (and `resume`, `dolt-server`) get baseline hook + verifier wiring
   at all?** Measured: `homelab` has no commit-refuse hook installed and no verifier
   recipe, so *nothing* in A–E — widened B included — reaches it today. That looks like
   adopter-onboarding work owned by another lane, not by this thread.

Note the interaction with question 3: even answering question 1 "yes, widen B" would not
catch `homelab-substrate`, because `homelab` runs no hook. Widening B buys coverage only
in repos that already have the baseline. That materially weakens the case for folding a
widened B into this thread, and strengthens treating clause (i) as a separately-scoped
follow-on.

**Bottom line for the maintainer:** the A–E cut is approvable as *"close the nested
fail-open"*. It is **not** approvable as *"enforce the worktree-location rule"* until
question 2 is answered. Do not accept a cut whose acceptance criteria quietly claim the
latter.

## First act is the maintainer's — nothing here is agent-dispatchable

**The epic is anchored; no slices are filed.** That split is deliberate. An active plan
thread MUST declare a concrete ledger anchor — `plan_thread_anchor_declared` enforces it
mechanically, and its rationale is exactly this thread's own failure mode ("a completed
plan thread was once treated as done ... while the plan lifecycle was left incomplete").
So `-0eo` exists as the thread's ledger identity. But *slicing* A–E into work-items is
the maintainer's cut, and `capture-work-item` / `groom` are consent-gated — a session
wrapping up should not file that unprompted.

So the honest first act is a maintainer act:

1. Answer §rollout order (blocks everything).
2. File A–E as slices under `-0eo`, or run
   `/livespec-orchestrator-beads-fabro:plan worktree-location-enforcement` to resume this
   thread and let it do the filing with consent.

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
ledger edit. **The rollout order is UNDECIDED** — the "wire-then-enforce" sequence in
§rollout is a recommendation, and the picker answer that briefly displayed it was a
supervisor UI race artifact, now recorded as void.

The A–E cut is likewise unapproved, and per §"Does this change B, or the thread's
definition of done?" it is not yet approvable *as a charter-closing cut* at all: the
first genuinely maintainer-owned question is whether this thread's definition of done is
clause (ii) only (nested worktrees refused) or both clauses of the rule (every worktree
under `~/.worktrees/`). That answer determines whether an F slice exists, and therefore
whether A–E is the whole cut — which is upstream of sequencing it.
