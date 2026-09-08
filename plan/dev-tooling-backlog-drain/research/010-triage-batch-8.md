# Triage batch 8 — P1 singletons, measured not read, 2026-09-08

**Status: PROPOSAL.** Dispositions await the maintainer's ruling. What was done
unilaterally is the reading — twelve items labelled `intake:triaged`, each
carrying its finding as a comment.

Untriaged open snapshot items: **89 before, 81 after** (119 at session start —
**38 read** across batches 5–8). Position **113/258**.

Every claim below was re-derived against the tree today. Where an item's own
figure had drifted, the new number is given with the old one beside it.

## A method note, because it nearly produced a wrong number in this very batch

My first probe of the check universe printed `universe size: 2`, and I almost
recorded that. `resolve_check_universe()` returns `tuple[Path, tuple[Path, ...]]`
— `(repo_root, files)` — so `len()` gave the tuple's arity. **The universe is 237
files.** This is the repo's own recorded discipline (inspect the shape before
indexing it) catching a live error, and it is the second time this session a
plausible-looking number came from reading the wrong container.

## `995m` + `0yfo` — one defect, and the damage compounds

`config.py` is **not** in the 237-file check universe, because
`is_generated(path=config.py)` returns **true**.

The mechanism is sharper than "loose matching", and I had to correct my own first
description of it. `is_generated` requires a line to *start with* one of the
extension's comment prefixes **and** contain the marker; its docstring is explicit
that `@generated` inside a docstring does **not** count. Running that logic over
the file, it trips at exactly two lines:

```
config.py:1178:# `is_generated` uses to recognize the `@generated` sentinel in EACH
config.py:1182:# that lets a single-line block comment such as `/* @generated */` count.
```

Both are ordinary `#` comments **explaining the prefix table**. The module that
documents the sentinel is excluded by it. The predicate behaves exactly as
specified; `config.py` is simply the one file whose comments must mention the
token.

**The cost is compounding, and that is the argument for priority.** Measured with
the repo's own `_count_lloc`:

| | 2026-07-29 | today |
|---|---:|---:|
| `config.py` LLOC | 560 | **643** |
| vs `check-file-lloc` hard ceiling 250 | 2.24× | **2.57×** |

It grew **83 LLOC — a third of the entire ceiling — while invisible to the check
that would have stopped it.** This is not a static defect awaiting tidying; the
exclusion actively buys room to keep breaching.

`0yfo`'s repair *order* is right (decompose, then un-exclude — un-excluding a
643-LLOC file into a 250 ceiling reddens the check immediately), but causation
runs the other way, so they should be scheduled as one change. Budget for a *set*
of findings: seven other applies-to-all checks have never inspected this file, and
the item's named keyword-only violation is still present (`assert_never` at line
212, single positional parameter, no `*`).

**A narrower fix worth pricing:** recognise the marker only in a file's **leading
comment block** — the convention `@generated` actually has. That excludes these
two mid-file comments, still catches every genuinely generated file, needs no
decomposition first, and fixes the class rather than the instance.

## PR #285 — close it, do not merge it

Found while triaging `995m`. Open since 2026-07-08 (62 days), touching
`config.py` and `test_config.py`.

- **Its fix already shipped.** The `/*` block-comment delimiter for C-family
  extensions is in master at `config.py:1192` and `:1195`. Its commit is not an
  ancestor of master, so it landed by another route or was reimplemented.
- **Merging it now would be a near-total revert:**

```
$ git diff --stat origin/master origin/pr285 -- livespec_dev_tooling/config.py tests/livespec_dev_tooling/test_config.py
 2 files changed, 229 insertions(+), 1982 deletions(-)
```

  Back to its merge base `16d47096` (release 0.34.0). That is not a conflict to
  resolve; it is two months of `config.py` undone.

Commented on the PR recommending closure; **not closed** — it is the maintainer's
PR, not this drive's. First of the four stale PRs read rather than merely counted.

## The fan-out cluster — and this drive just enlarged it

`ve7w`, `zm5cbp` and `lmv2` are three faces of one subject: **what the pin fan-out
structurally cannot propagate.**

| item | what it cannot carry |
|---|---|
| `ve7w` | the **publisher's own pin** — excluded from the dispatch matrix by ratified contract, "so a release does not echo back to itself". Cannot self-heal. |
| `zm5cbp` | the **producer's self-referential pins** — fire sometimes, skipping whole runs (v0.46.5 → v0.50.1; v0.47–v0.49 never landed) |
| `lmv2` | packaged **carrier bodies** — the fan-out rewrites pins only and never re-renders bodies, so a consumer's bump PR compares body-vs-*old* canonical and pin-vs-*new*, and self-blocks by construction |

A fix for any one that does not name the other two leaves a hole, and this repo
owns the mechanism all three describe.

**Likely shared root, worth one piece of research first:** `ve7w` and `zm5cbp` are
the same self-exclusion seen from both ends. The publisher cannot dispatch to
itself *by design*, so the self-bump must ride some *other* trigger — which
`zm5cbp` already says "fires sometimes and not others". Naming that trigger
plausibly unblocks both.

### The part that implicates this plan's own work

`lmv2` bounded its blast radius on 2026-07-23 to "exactly the two Drivers". The
tree now carries **ten** `CANONICAL_*_BODY` carriers — and
`livespec-dev-tooling-n4jm`, **dispatched by this drive and merged this morning as
PR #2034 / v1.64.0**, added another: `CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY`,
whose byte-identity check states in its own docstring that it is modelled on
`no_shadow_ledger_body_identical` — **`lmv2`'s first occurrence.**

So the next producer-side edit to the rate-limit decision body reproduces the July
self-block on the Drivers' bump PRs.

That is not an argument against `n4jm`; single-sourcing was right and the
byte-identity check is the correct mechanism. It means **every duplicate this
drive removes by adding a canonical carrier adds one more artifact the fan-out
cannot propagate.** `lmv2` is on the critical path of the fleet's own
consolidation programme, and `qx2l` and `n4jm` are its feedstock.

**Stated carefully:** those ten are not automatically ten instances. The mechanism
needs a carrier whose body *consumers commit*; the worktree-pack carriers are
provisioned and gitignored in consumers and plausibly never reach a bump PR. Which
of the ten qualify is a per-carrier check **not run here**, and it is `lmv2`'s
cheapest next step because it sets the real blast radius.

## `41sk` — third independent confirmation

`bd ready --json` → `[]`, while **four** items sit at `status == ready` (`fy02`,
`py9`, `zm5cbp`, `7us.7`). This repo's `AGENTS.md` already carries "bd ready is
DEAD here" with a separate 2026-08-19 measurement.

It still matters because the failure is **silent and exit-zero** — a cheerful
empty result indistinguishable from a true "nothing is ready". That is the same
shape as every other trap this session hit: an unarmed lever passing, a retired
check passing, an outcome naming a ref that does not exist.

## `crl2` + `idlx` — correctly blocked; do not schedule

Recorded deliberately, because this session found **three** items whose blocked
status *was* stale (batch 7) and these must not be swept up with them.

The constraint is ratified and this repo paid for it: `46c5dab` — the commit
`crl2` re-lands — turned **five repos red** and was reverted in `f4247110` /
PR #1285, after which the maintainer chose revert-and-reland *behind adoption*.

What a future pass can check cheaply instead of re-deriving: the adoption children
live in **other repos** (`8o8e.7/.8/.10/.11/.12/.13`, proposed for referral in
batch 5), while dev-tooling's own share — `8o8e.9` and `.14` — is **already
closed**. This lane unblocks when those referrals are accepted and completed, and
not before.

## What this batch asks for

1. Close PR #285 unmerged.
2. Schedule `995m` + `0yfo` as one change, and price the leading-comment-block fix
   for `is_generated` as the class-level alternative.
3. Decide `ve7w` / `zm5cbp` / `lmv2` together, starting with the one piece of
   research that names the self-bump trigger, and with `lmv2`'s per-carrier scan.
