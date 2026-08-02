# fleet-shell-quality-enforcement — why this shape

**Owning repo:** `livespec-dev-tooling` — it ships the enforcement suite the
fleet consumes by pin, so a shell-quality gate reaches every repo from here.
Routed here by maintainer decision 2026-08-02 under the fleet's
route-by-owning-component principle. Opened from the `livespec-overseer`
`supervisor-prompt-quality` track, which found the triggering defect.

**Ledger anchor:** epic **`livespec-dev-tooling-42t4az`** (this repo's tenant) —
the thread's status anchor. This thread is active if and only if that epic is
open, and archives to `plan/archive/fleet-shell-quality-enforcement/` when it
closes.

**Status is not stored here.** Read it from the ledger
(`list-work-items` / `next`). Every id in this file is cited read-only.

## What triggered this

`check-per-file-coverage` ran `set -uo pipefail` with **no `-e`**. A non-zero
`pytest` therefore did not abort the recipe, and the recipe's exit status
became the *last* command's — the coverage check. A test failing at an
assertion whose lines were already covered left coverage at 100% and the
target exited **0**.

Demonstrated in `livespec-overseer` rather than argued. One deliberately
failing test (a single statement, so its file stays 100% covered — precisely
the masked mode), identical in both runs:

| recipe form | recipe rc | verdict |
|---|---|---|
| `set -uo pipefail` | **0 — GREEN**, with `FAILED` in its own output | masked |
| `set -euo pipefail` | **1 — RED** | caught |

The sabotage was asserted to produce a real failure *before* either verdict was
read, per the rule that a sabotage producing no red is unverified rather than
passed.

This was never confined to developer hosts. In `livespec-overseer` the target
is its own CI matrix job **and was a required status check**, so the masked
green reached branch protection and the Dispatcher's "latest master is green"
pre-flight.

## The fleet measurement

Of 33 git repos on disk, 11 carry a `justfile` and 8 define
`check-per-file-coverage`. All five defective ones share the identical
two-command body, so all five mask the same way:

| `set -euo pipefail` (guarded) | `set -uo pipefail` (masked) |
|---|---|
| `livespec` | `livespec-overseer` *(fixed 2026-08-02)* |
| `livespec-driver-claude` | **`livespec-dev-tooling`** |
| `livespec-driver-codex` | `livespec-orchestrator-beads-fabro` |
| | `livespec-orchestrator-git-jsonl` |
| | `livespec-runtime` |

**`livespec-dev-tooling` is in the masked column, and that is the point.** It
ships the gates the whole fleet consumes by pin; its own green board is subject
to the same blind spot.

`livespec` core reached this diagnosis independently a month earlier and fixed
it in `bc5c9bce` (2026-07-01), subject *"chore: restore green master — narrow
README mermaid guard + unmask coverage recipe"*. The word "masking" is theirs.
So this is not a novel strengthening whose risk the fleet has not accepted —
the reference repo accepted it a month ago and five repos never caught up.

## Why a per-recipe fix is not the deliverable

The one-line edit is known and cheap. What this thread exists for is the
question the maintainer asked when the fix was proposed: **why do we allow this
inconsistency, and can it be enforced mechanically rather than remembered?**

Measured 2026-08-02:

- **Zero shell-lint checks exist.** `livespec_dev_tooling/checks/` holds **81**
  modules; none lints shell. Nothing greps for `shellcheck` in any workflow,
  `pyproject.toml`, `justfile` or doc.
- **`shellcheck` 0.10.0 is already installed on the dev host** and referenced
  nowhere. The tool is present; the wiring is absent.
- **The unlinted surface is two populations, not one:**

  | surface | count | shellcheck-able as-is? |
  |---|---|---|
  | tracked `.sh` files across 9 fleet repos | **48** | yes |
  | bash recipes inside 9 `justfile`s | **104** | **no** |

  Per-repo `.sh`: `livespec-dev-tooling` 19, `livespec-orchestrator-beads-fabro`
  16, `livespec` 4, `livespec-orchestrator-git-jsonl` 3,
  `livespec-console-beads-fabro` 2, and 1 each in `livespec-overseer`,
  `livespec-runtime`, `livespec-driver-claude`, `livespec-driver-codex`.

**The second population is the one that caused this defect, and it is the
harder one.** A `justfile` bash recipe is not a file shellcheck can read: it is
indented under a target, carries `{{...}}` `just` interpolation that is not
valid shell, and has its shebang on the recipe's first line. Any gate that
covers the surface which actually failed must extract recipes and neutralise
interpolation before linting — or assert the preamble structurally without a
full parse.

## The preamble idea, and its known limits

The maintainer's proposal is a shared boilerplate that every shell script
includes and that cannot rot or be omitted. Reference:
`https://github.com/thewoolleyman/bashstyle_examples` (`bash-boilerplate.sh`),
which sets `errexit`, `errtrace`, `noclobber`, `pipefail` and `nounset`,
installs an `onexit` trap on `HUP INT QUIT TERM ERR`, and provides
`enable_error_checking` / `disable_error_checking` plus `BASH_XTRACE` /
`BASH_VERBOSE` toggles.

Three constraints any design must survive, recorded so they are not
rediscovered:

1. **A sourced preamble cannot set shell options for a `just` recipe body in
   every case**, and adding a `source` line to 104 recipes is itself the kind of
   hand-maintained convention that rotted here. Asserting the *options* may
   generalise better than shipping the *file*.
2. **Blanket `-e` is not universally correct, and this repo family already
   reasons about that per recipe.** In `livespec-overseer` nine recipes use
   `set -uo pipefail` without `-e` and **only one was defective**: others
   document the omission deliberately (`check-prose-release-hygiene` explains
   that `grep -c` exits 1 on a zero count, so `-e` would abort at the very
   violation it reports), or end on their load-bearing command so status
   propagates, or `exit $?` explicitly. **A gate that promotes every one of
   these to an error would be wrong**, and "nine recipes are broken" was a false
   alarm caught only by reading each. The gate must distinguish *deliberate and
   documented* from *silently omitted* — those are byte-identical today, which
   is the real defect.
3. **A gate is not justified by being correct on the example that motivated
   it.** The originating track killed four plausible gates by measuring the
   whole corpus first, each with a false positive already sitting in the tree.
   Measure all 48 scripts and all 104 recipes before writing any rule.

## An adjacent root cause found in this repo

While answering "what allowed this to be omitted", a second instance of the
same class surfaced **in this repo's own bootstrap script**.

`dev-tooling/branch-protection.sh` is the fleet's only branch-protection
automation, and it deliberately declines to set required checks:

> `# required_status_checks is left null because the consumer's check names are`
> `# not known here; the required-PR gate already forces the PR/worktree flow.`

That premise was reasonable when written and the single-gate convention
obsoleted it: **`ci-green` is a fleet-constant name, knowable at bootstrap.**
Consequence — every repo's required-context list is hand-curated with no
template, no doc and no gate. Measured across all nine livespec-family repos,
eight required `ci-green` alone and `livespec-overseer` was a singleton
requiring 56 enumerated contexts and not `ci-green` (corrected 2026-08-02).

Copier is **not** the cause and should not be pursued as one: the template is
scoped to `templates/orchestrator-plugin/`, only 2 of 9 repos carry
`.copier-answers.yml`, and several hand-built repos still configured `ci-green`
correctly. Branch protection is a forge setting no template can set.

Whether this belongs in this thread or beside it is an open question. It is
recorded here because it is the same shape — a fleet convention with no
mechanical enforcement — and because it was found by the same question.

## Relationship to the livespec thread — DECIDED 2026-08-02

A sibling thread was opened hours after this one, at maintainer direction:
`livespec` `plan/fleet-shell-discipline/`, epic **`livespec-hhu5pn`**. It carries
the same triggering defect plus two requirements that post-date this thread —
forbid interpolated bash in `justfile` recipes, and make set-option discipline
appropriate per script rather than blanket.

**The maintainer decided the split, and NEITHER thread closes:**

| thread | owns |
|---|---|
| `livespec` (`livespec-hhu5pn`) | **the convention and its enforcement design** — what the rule IS, which set-options suit which script, how a deliberate deviation is declared so a gate can tell it from an accident |
| **this one** (`livespec-dev-tooling`, `42t4az`) | **building and shipping the check** — shellcheck adoption, the severity floor or baseline, the module itself, and its arrival in every consumer by pin bump |

**Why.** `livespec` already fixed the triggering defect once (`bc5c9bce`,
2026-07-01) and **it never propagated** to the five repos sharing the shape. A
convention living only in the reference repo's code does not travel; a check that
ships by pin does. This repo is the only one that can reach the whole fleet that
way, which is what it owns here.

**The cost:** two live threads on one subject drift unless the boundary is
written into both. It is written into both and onto both epics. If a piece of
work does not obviously belong to "what the rule is" or "how the rule ships",
raise it rather than filing it in whichever thread is closer to hand.

## Related records, cited read-only

- `livespec-overseer` `overseer-jdo` — the flaky aggregate. Its acceptance bar
  is statistical, and the sequencing **inverts**: unmasking is a precondition
  for measuring it, not a follow-up, because its own flaky test has asserts at
  statements 4 and 5 of 6, so a failure at the last leaves nothing unexecuted
  and the board goes green.
- `livespec-overseer` `overseer-rh1` — required-context alignment, including
  the mirror finding that a job branch protection treats as optional can still
  halt fleet dispatch through `master_ci_green`'s run-level read.
- `livespec-overseer` PR #470 — the single-repo `-e` fix and its proof.

## What is deliberately NOT decided here

Nothing is filed as ready work by this note. The open design questions are:
which of the two surfaces to gate first; whether the deliverable is a shipped
preamble file, a structural assertion about options, or both; and how a
deliberate, documented omission is expressed so the gate can tell it from an
accidental one.
