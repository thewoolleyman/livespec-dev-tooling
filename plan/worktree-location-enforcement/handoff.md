# Worktree-location enforcement — close the three fail-open layers

**Ledger anchor:** epic `livespec-dev-tooling-0eo`

**No slices filed.** The epic is the thread's ledger identity only; A–E below are NOT
work-items. See §"First act is the maintainer's".

**Opened:** 2026-07-20, out of a live violation in `livespec-console-beads-fabro`
(incident summary below). All analysis in this file was verified against
`origin/master` at **`2412e21`**; every line anchor is from that commit.

## Charter

The rule "every worktree lives under `~/.worktrees/<repo>/<branch>`, NEVER inside a
clone" is stated in prose in each repo's `AGENTS.md` and enforced by **nothing**. Three
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
`2412e21`: the fail-open line is untouched, no config key exists anywhere, no pack is
installed in 7 of 8 governed repos.

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
6. `AGENTS.md` §"Red-Green-Replay commit protocol" (`:100-142`) — binds item A.

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

## Fleet impact — verified 2026-07-19/20

8 repos run the verifier. Console names its recipe `check-baseline`; the other 7 name it
`check-primary-checkout-commit-refuse-hook-installed` (an earlier scan for `check-baseline`
alone under-reported this — do not repeat that mistake).

| Repo | verifier | pack |
|---|---|---|
| livespec | YES | **ABSENT** |
| livespec-dev-tooling | YES | **ABSENT** |
| livespec-driver-claude | YES | **ABSENT** |
| livespec-driver-codex | YES | **ABSENT** |
| livespec-orchestrator-beads-fabro | YES | **ABSENT** |
| livespec-runtime | YES | **ABSENT** |
| livespec-console-beads-fabro | YES | **ABSENT** |
| livespec-orchestrator-git-jsonl | YES | present ✅ |

`livespec-orchestrator-git-jsonl` is the **only** compliant repo — model the sweep on it.

Note `livespec-dev-tooling` itself is non-compliant. Fix it in the same change so the
canonical repo is exemplary rather than exempt.

12 repos carry `.livespec.jsonc` and get the key: the 8 above plus dolt-server, homelab,
openbrain, resume. In those 4 the key is **inert documentation** — they wire no verifier,
so nothing reads it. Say so rather than implying coverage.

## THE ONE OPEN QUESTION — rollout order

Unanswered when the prior session ended. It gates all execution:

- **Pack-install-first (no red window).** Run `install-worktree-pack` across the 7
  non-compliant repos *before* landing the verifier change. Harmless on its own — an
  installed pack is already valid under today's rules. Nothing ever goes red.
- **Verifier-first (red as forcing function).** Land the change; each repo goes red at
  its next pin bump until it installs.

The prior session's recommendation was **pack-install-first**, on the grounds that
staggered pin bumps mean the red window is not atomic and would surface as unrelated CI
failures in 7 repos over an unpredictable window. Not a decision — a recommendation.

The same question applies independently to item B's hook reinstall, where it is sharper:
a byte-mismatched hook fails the verifier in **every** repo, including the 4 that
currently pass by having no pack.

## The work

### A — verifier: absent pack becomes a FAIL, gated on config

`_inspect_worktree_pack` (`:279-309`) returns `[]` when no pack file exists (`:298-300`).
That single early-return is the entire hole. Replace with a `.livespec.jsonc` read:
`required` (default) → absent pack is a new `worktree_pack_absent` failure carrying the
existing `_WORKTREE_PACK_REMEDY` (`:211`, already wired at `:359`); `optional` → today's
skip. Malformed declaration → FAIL, per the `harnesses` precedent.

Keep the existing partial-install and byte-drift arms exactly as they are.

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

### C — installer + docs write the key with its default

Installation docs must write `worktree_discipline.pack` with its default value, so new
adopters get it without archaeology.

### D — fleet sweep

Install the pack in the 7 non-compliant repos; write the key into all 12 `.livespec.jsonc`;
re-run `install-commit-refuse-hooks` everywhere after B lands. Order per §rollout.

### E — openbrain has the last live violation

```
/data/projects/openbrain/.claude/worktrees/fix-ob-6vt-thought-detail-save  [fix/ob-6vt-thought-detail-save]
```

Confirmed still live 2026-07-20. It is in the **working tree**, not `.git/`, so item B
will hard-refuse its next commit. Maintainer decided: **relocate it as part of the sweep**
(`git worktree move` to `~/.worktrees/openbrain/<branch>`), before B ships, so nobody is
stranded mid-branch. Check for uncommitted work there first and report before moving.

A fleet rescan on 2026-07-20 using the §B rule (with the `.git/` carve-out applied) found
openbrain as the **only** genuine violation — which is independent confirmation the
carve-out is drawn correctly: it cleanly separates beads' four internal sync worktrees
from real ones.

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

## Sequencing

1. **Rollout order decided first** — it changes the shape of D, not just its timing.
2. **A and B are independent code changes** but share one fleet sweep; land them close
   together so the sweep runs once, not twice.
3. **E before B ships** — otherwise openbrain's live worktree is stranded on first commit.
4. `livespec-dev-tooling`'s own pack install rides A (self-compliance).
5. Parallel-safe against `livespec-console-beads-fabro`'s `plan/repo-invariant-guards/`
   — no shared files. That thread's `-mvu22t` item ports `red_green_replay.py` **from**
   this repo; it reads, does not write, so there is no contention.

## Gates

- Maintainer decision on rollout order.
- Maintainer epic anchor + item filing (see above).
- Red-Green-Replay on A and B (product `.py`; docs-only changes like this file are exempt).
