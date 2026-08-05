# pure-trees-role-key-scope

> **Ledger anchor:** epic `livespec-dev-tooling-8zv3` (P1). The ledger is authoritative
> over this file. Re-derive every number and every repo state before quoting it.
>
> ```bash
> cd /data/projects/livespec-dev-tooling && /usr/local/bin/with-livespec-env.sh -- bd show livespec-dev-tooling-8zv3
> ```
>
> **Rewritten 2026-08-05 at session wrap.** Everything below is measured, with the
> command that measured it. Where a claim is inherited rather than re-derived, it says so.

## ⛔ READ THIS FIRST — THE DECOUPLING SHIPPED AND WAS THEN REVERTED

`8zv3.3` landed as `46c5dab` ("scan the first-party universe, not pure_trees") and was
**fully reverted** by `f424711` ("restore the pure_trees gate on public_api_result_typed").

**Verified 2026-08-05 against `origin/master` = `42c7439`:**

```bash
git show origin/master:livespec_dev_tooling/checks/public_api_result_typed.py | grep -n 'role_absence_exit_code\|pure_trees'
git merge-base --is-ancestor f424711 origin/master && echo "revert IS on master"
```

The gate is back: `role_absence_exit_code` at :125, `_scan(pure_trees=...)` at :344/:385.
The docstring fix that shipped alongside it was reverted too.

**WHY, from the revert's own message — this is the load-bearing part.** Removing the gate
made the check scan repos whose public API it had never once read. That is
**enforcement-before-adoption**, and it turned **FIVE** fleet repos' master CI red:
`livespec`, `livespec-runtime`, `livespec-orchestrator-git-jsonl`,
`livespec-orchestrator-beads-fabro`, `livespec-overseer`. `livespec/.ai/ci-gate-discipline.md`
names that as revert-worthy and answers it with **revert-and-reland** — never a lever, env
var, carve-out, or severity demotion (`li-4x3a45` is the recorded wontfix on exactly that).

⚠️ **The analysis in this thread was not wrong; the SEQUENCING was.** The scope mismatch is
real and confirmed from ratified text (below). What failed was arming a widened criterion
across nine repos in one step. **Re-landing behind adoption is `livespec-dev-tooling-irtt`
and it is OPEN.** Do not re-land by simply reapplying `46c5dab`.

## ✅ CLOSED HAZARD — the stale spec proposal was WITHDRAWN

`SPECIFICATION/proposed_changes/pure-trees-scan-universe-decoupled.md` was **deleted** by
this commit, on a maintainer ruling of **WITHDRAW**. Verify it is gone:
`git ls-tree -r --name-only origin/master -- SPECIFICATION/proposed_changes/`.

It stated that `public_api_result_typed` no longer consumes `pure_trees` and that the
default-run no-op count is three. **Both were true when filed and were FALSE after
`f424711`.** A `/livespec:revise` pass would have ratified a false statement into ratified
`contracts.md` — the exact defect class this whole thread exists to close, arriving through
the spec lifecycle instead of through code.

**The proposal was not WRONG about the rule; it was STALE about the behavior.** The scope
mismatch it argues from is still real and still confirmed from ratified text (see "Still
true, still measured" below). Only its factual claims about shipped behavior died with the
revert.

⚠️ **`livespec-dev-tooling-irtt` files its own proposal — do not resurrect this one.** The
re-land must be described against what actually ships, when it ships (gate retained until a
repo adopts), not reconstructed from reverted behavior. The reasoning is preserved in `irtt`
and in this thread; nothing was lost in the deletion.

## PARKED WORK — livespec-dev-tooling-rjyc (P0), fully staged, resume verbatim

The durable fix for the fleet-conformance deadlock. **Implementation is COMPLETE and both
positive controls are DISCHARGED.** Only the Green commit is outstanding.

```text
worktree : ~/.worktrees/livespec-dev-tooling/fix-rjyc-self-member-local-vantage
branch   : fix/rjyc-self-member-local-vantage
HEAD     : 9224f2e  (Red commit, five TDD-Red-* trailers)
staged   : livespec_dev_tooling/fleet/_context.py
           livespec_dev_tooling/fleet/_rows_public_api_conformance.py
           livespec_dev_tooling/fleet/fleet_conformance.py
state    : leg-4 amend-in-progress (Red trailers at HEAD + impl staged)
resume   : cd <worktree> && mise exec -- git commit --amend --no-edit
```

⛔ **DO NOT unstage, reset, rebase, or clean this worktree.** The staged tree IS the work.

**What it does.** `_rows_public_api_conformance.py:133` was the sole `member_tree_snapshot`
call site, and it read EVERY member — including the repo under test — from the forge at its
canonical ref. So a PR could never be graded on its own contents, and `ci-green` gating on
that row made the repo unable to merge the fix for a finding the row itself raised. The self
member now reads its local checkout; every sibling keeps its forge ref.

⛔ **THE ACCEPTANCE CRITERION IS THE GUARDRAIL: self-only.** `_local_root_for()` enforces it
by exact name equality. The verdict is a JOIN — consumption edges come from OTHER members'
trees (unforgeable by the PR), only the declaration and own sources come from this one.
**Generalize local-read to siblings and the row stops meaning anything.** Any implementation
that does not enforce self-only is the wrong fix.

**Both controls discharged in production** (unit tests bypass `main()` and cannot prove the
wiring is bound):

| control | setup | result |
|---|---|---|
| convicts | removed `shell_quality::main` declaration from the LOCAL tree only; master still carried it | **EXIT=4**, named the function — forge-read would have PASSED |
| passes | restored byte-identical | **EXIT=0**, "fleet conformance passed", 9 members, 0 blind rows |

⚠️ **The sweep sits behind lever `LIVESPEC_RUN_FLEET_CONFORMANCE`.** My first control run
returned EXIT=0 with the lever unset — it skipped entirely. **A control that cannot fail is
not a control.** Always confirm the row actually RAN.

### Why it is parked, and the condition for resuming

Three amend attempts were killed at the 1200s tool ceiling. **No hook ever refused — no
verdict was ever produced.** Measured cause: 18 cores against load 50–66 sustained for over
an hour (trace `50.2 → 51.9 → 62.7 → 49.05 → 60.69 → 64.44 → 66.49`), from other lanes.
The same aggregate runs in 593s and 1043s unloaded.

**Resume only when load is quiet across SEVERAL samples** — a single sub-threshold reading
is a trough, not a recovery. That mistake was made once already in this thread.

## Completed and merged

| PR | what |
|---|---|
| dev-tooling **#1248** | `8zv3.3` decoupling + the cross-lane `shell_quality` declaration — **since reverted by `f424711`** |
| dev-tooling **#1258** | docstring un-shadow + the spec proposal — **docstring half also reverted; the proposal survives and is the hazard above** |
| runtime **#476** | pin bump to `v1.19.6`, unbreaking `livespec-runtime` master CI. 64 checks green. Runtime master now `120be92` |

**#476 verification, re-derived independently before pushing** (all four reproduced): on a
CONSTANT tree, `v1.19.3` → exit 1 with 11 offenders / `v1.19.6` → exit 0 `not_applicable`;
`f424711` is an ancestor of `v1.19.6` and not of `v1.19.3`; GHCR `python-v1.19.6` → 200 with
a known-present control at 200 and a fabricated control at 404; lock shas are the real tag
commits.

⚠️ **Runtime green means UNENFORCED, not verified.** `pure_trees` is `not_applicable` there,
so the check convicts nobody. The 11 offenders are still in that code.

## Structural findings — filed elsewhere, do not re-derive

- **`livespec-dev-tooling-rjyc`** — the vantage fix above. P0, parked, ready to resume.
- **`livespec-dev-tooling-irtt`** — arm `public_api_result_typed` behind adoption. **This is
  the re-land path for `8zv3.3`.** OPEN.
- **`livespec-dev-tooling-tkzf`** — `check-fleet-conformance-admin` reads adopter repos in
  OTHER organisations from a pre-commit hook; failure mode is "nobody here can commit, for a
  reason nobody here can fix". Cleared itself once.
- **`livespec-dev-tooling-9s2j`** — the row reports nothing when a consumed function is
  DELETED. Pre-existing, orthogonal, lives in `_public_api_graph` edge resolution, NOT in
  tree source. **Deliberately excluded from rjyc.**
- **`livespec-dev-tooling-niyl`** — gh apt pin. Fixed by `e12b4c9`.
- **Gate-vs-harness ceiling (surfaced, maintainer-facing, not filed by me).**
  `.claude/settings.json` commits `BASH_MAX_TIMEOUT_MS=1200000`; the pretooluse guard forbids
  backgrounding a gate command; the aggregate measures 593s/1043s unloaded and >1200s under
  load. So under sustained fleet load **this repo is uncommittable for product `.py`**, and it
  presents as a silent kill with **no verdict** — indistinguishable from a hook refusal unless
  you check whether any target actually ran. Same family as `tkzf`.

## Still true, still measured — the analysis the revert did NOT invalidate

**The premise, confirmed from ratified text** (not inferred): `livespec`
`SPECIFICATION/non-functional-requirements.md:114`, verified at SHA
`ac502374689222c1b607db3964fbbb7598a390fd`, binds the ROP railway to **every repo carrying
ANY first-party Python**, states there is **NO "thin repo" exemption**, and names the **SOLE
exemption** as **ZERO first-party Python**. `pure_trees` selects "has a pure-module subtree" —
never the binding condition. **The scope mismatch is real.**

**The consumer classification (AST, not grep).** Five real code consumers:
`check_mutation` (4 refs, GENUINE NEED), `pbt_coverage_pure_modules` (4, GENUINE NEED),
`public_api_result_typed` (4, the ONLY scope mismatch), `partition_completeness` (2, not a
scope gate), `source_trees_scoped_to_consumer` (2, not a scope gate).
`_import_resolution`, `_single_meaning_variants` and `fleet/_rows_public_api_conformance`
have **ZERO** code refs — prose only. An earlier "seven" came from `grep -rln`, which counts
files that merely mention the string. **Re-derive from the AST, not from a grep.**

**Of the checks consuming `resolve_check_universe()`, exactly ONE was role-gated** — this
check itself. Measured **19** call sites across 19 files, not twenty; `git grep -l` reports
22 because it counts the definition site and non-calling importers.

⛔ **DO NOT add a replacement role key** when re-landing. An empty universe is already a
legitimate "nothing to check" and `resolve_check_universe()` fails closed. A new declared key
would reintroduce the hazard: a declaration whose emptiness means "skip me",
indistinguishable from "genuinely no code".

## Do NOT touch

- **`8zv3.4`** fleet fan-out — blocked by `8zv3.5`.
- **`8zv3.5`** the `_`-prefixed FILE skip — worth **286 of 446** fleet offenders (64%); a
  separate, independently-argued decision. Surfaced to the maintainer as a prepared valve.
- **shell-quality wiring** — `fleet-shell-quality-enforcement` peer lane owns it. It is what
  breaks `livespec-runtime`'s `bump-pin` at step 11.
- **`plan/rop-railway-enforcement`** — ON HOLD.

## Working rules this thread earned the hard way

1. **Exit status is not evidence.** Confirm the check actually ran. Levers, skipped sweeps
   and killed processes all exit 0 or look like failures without being either.
2. **Run a positive control before believing an absence.** Four separate false-ABSENT probe
   results were recorded in one day (wrong package name, 403 scope, 1000-item truncation,
   missing OCI Accept header).
3. **Say which basis every number is on** — shipped semantics vs the epic's measurement basis
   differ on the `_`-file skip, and dev-tooling is 0 on one and 1 on the other.
4. **Quote the SHA.** Trees move within the hour; two supervisor-quoted head shas were
   already stale when handed over.
5. **A right conclusion does not launder a wrong premise.** Flag the supporting number even
   when the verdict survives.
