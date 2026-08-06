# pure-trees-role-key-scope

> **Ledger anchor:** epic `livespec-dev-tooling-8zv3` (P1). The ledger is authoritative
> over this file. Re-derive every number and every repo state before quoting it.
>
> ```bash
> cd /data/projects/livespec-dev-tooling && /usr/local/bin/with-livespec-env.sh -- bd show livespec-dev-tooling-8zv3
> ```
>
> **Rewritten 2026-08-06.** Everything below is measured, with the command that measured it.
> Where a claim is inherited rather than re-derived, it says so.
>
> **State in one line:** the withdrawal, both halves of the gate ruling, and `rjyc` have all
> MERGED. Nothing in this thread is parked — see **NEXT SESSION — START HERE** immediately
> below for what to do. The open item is `livespec-dev-tooling-irtt`,
> whose adoption bill is measured per repo below — **188 REPORTED / 123 DISTINCT at pass-1
> heads, 190 reported at pass-2 four hours later** (the reported/distinct gap is
> `overseer`'s byte-identical shipped mirror) — and whose next step is a SEQUENCING decision
> for the maintainer, not implementation.

## ▶️ NEXT SESSION — START HERE

**Nothing in this thread is parked and nothing is half-done.** Every branch this thread opened
is merged, every worktree it created is removed, and the primary is clean on `master`.

⛔ **DO NOT START `irtt` REMEDIATION.** The maintainer has not ruled on sequencing. This lane's
job was to MEASURE the decision, and the measurement is complete and recorded below.

**First action: report on the milestone channel**
(`tmp/overseer/pure-trees-role-key-scope/worker-status.log`) that measurement is complete and
this lane is awaiting the sequencing ruling. Then wait for the supervisor's dispatch.

**Owned by the SUPERVISOR, not by you — do not do these:**

- putting the `irtt` sequencing decision to the maintainer
- the `8zv3.5` keep-and-ratify spec change (the `_`-prefixed FILE skip)
- ledger items `livespec-dev-tooling-e5nz` (the LLOC ceiling CLASS) and
  `livespec-dev-tooling-6q5o` (the runner's push-path evidence gap)

If a supervisor dispatch is already waiting when you start, **follow that instead of this
paragraph** — it is newer than this file.

### ⚠️ Re-measure before quoting ANY number below

The bill moved **twice inside one session** (`dev-tooling` 0 → 2, `livespec-runtime` 11 → 13),
and the CRITERION moved too. Every figure here is stamped with its pass and its SHAs for that
reason. Quote nothing bare.

### How to re-measure (the harness was scratch and is gone — rebuild is ~20 lines)

Read-only, no pin bump, no CI. For each member: export `origin/master` into an isolated dir
(`git archive origin/master | tar -x -C <dir>`, then `git init && git add -A` so `git ls-files`
works), delete the exported `.mise.toml` (it is untrusted and shadows PATH), then from inside
that dir run dev-tooling's venv python over:

```python
config = load_config(repo_root=Path.cwd())
root, universe = resolve_check_universe()
sources = {rel: (root / rel).read_text() for rel in universe}
public = repo_local_public_names(sources=sources) | declared_public_names(
    declared=config.cross_repo_public_api, sources=sources)
total = functions_without_expected_failure_mode(sources=sources, io_trees=config.io_trees)
total |= declared_absence_names(declared=config.total_absence_returns, sources=sources)
total |= declared_variant_names(
    declared=config.single_meaning_variants, sources=sources, io_trees=config.io_trees)
# THE RULED BASIS: retain the `_`-prefixed FILE skip
for rel in [r for r in universe if not r.name.startswith("_")]:
    _find_offenders(source=sources[rel], rel_path=rel,
        commands_trees=config.commands_trees,
        public_names=frozenset(n for p, n in public if p == rel),
        no_expected_failure_mode=frozenset(n for p, n in total if p == rel),
        supervisor_entry_files=config.supervisor_entry_files)
```

All names import from `livespec_dev_tooling.checks.public_api_result_typed` and
`livespec_dev_tooling.config`.

⚠️ **Validate it before believing it.** The harness above was checked against the REAL shipped
decoupled check by exporting `46c5dab` and running its own
`python -m livespec_dev_tooling.checks.public_api_result_typed` with `PYTHONPATH` pointed at
that export — **8 of 9 repos matched exactly**. Do that again rather than trusting a
reconstruction. `livespec-runtime` reproducing exactly 11 offenders with the identities in the
`irtt` ledger is the cheapest single positive control.

## ⛔ READ THIS FIRST — THE DECOUPLING SHIPPED AND WAS THEN REVERTED

`8zv3.3` landed as `46c5dab` ("scan the first-party universe, not pure_trees") and was
**fully reverted** by `f424711` ("restore the pure_trees gate on public_api_result_typed").

**Re-verified 2026-08-06 against `origin/master` = `622167a`** — still true, the gate
remains restored:

```bash
git show origin/master:livespec_dev_tooling/checks/public_api_result_typed.py | grep -n 'role_absence_exit_code\|pure_trees'
git merge-base --is-ancestor f424711 origin/master && echo "revert IS on master"
```

The gate is back, at the CURRENT line numbers (they drift — re-grep rather than trusting
these): `role_absence_exit_code` imported at :125 and called at :461, `_scan(...)` called at
:483 still taking `pure_trees`, and `for tree_rel in pure_trees` at :385 inside `_scan`.
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

## ✅ CLOSED — livespec-dev-tooling-rjyc (P0) MERGED as dev-tooling #1309

**The fleet-conformance deadlock is closed.** A PR can now be graded on its own contents.
Verified on `origin/master` by reading the code, not a report: `fleet/_local_vantage.py` and
`fleet/_cli_parser.py` present, `_local_root_for` gating on exact name equality with a single
call site, and the member loop falling through to `member_tree_snapshot` at the canonical ref
for every non-self member.

⛔ **The acceptance criterion that must survive any future edit: SELF-ONLY.** What makes it
sound is not the equality test alone — it is that `local_repo` is **derived from the origin
remote, never configured**, and that `local_vantage` **fails closed to the forge vantage for
the WHOLE roster** in both unresolvable branches, explicitly refusing to fall back to a
directory name. That is why "a PR cannot declare itself to be a sibling" is true, and it is
the answer to the "a PR asserts its own conformance" objection rather than a restatement of
it. Generalize the local read to siblings and the consumption half becomes forgeable.

**Landing it also forced a mechanical extraction**, recorded here because the reason recurs:
`fleet_conformance.py` was at **247 LLOC against a 250 hard ceiling before rjyc** — three
lines of headroom — and rjyc adds 30. There is no arrangement in which 30 fits into 3.
`_local_vantage` (rjyc's own) and `_build_parser` moved out verbatim; 277 → **220**.
Extracting only `_local_vantage` was measured at **253 — still over**, so the split ordering
fails outright rather than merely being tight. The class-level condition is
`livespec-dev-tooling-e5nz`.

### The historical entry (superseded — kept for the reasoning only)

The durable fix for the fleet-conformance deadlock. Both positive controls were discharged
in production BEFORE the park, and they are restated in #1309 rather than re-run.

```text
STALE — the worktree fix-rjyc-self-member-local-vantage is REMOVED and the branch DELETED.
The work landed as dev-tooling #1309 (commit 1b126e8, rebased onto the measured head).
Nothing here needs resuming. Left in place only so the shape of the parked state is legible.
```

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

### Why it was parked — and why the remedy was WRONG

Three amend attempts were killed at the 1200s tool ceiling with **no hook ever refusing and
no verdict ever produced.** The diagnosis was right; the remedy — *wait for a quiet window* —
was wrong, and the numbers say so decisively.

Once the ceiling was removed (see below), the SAME amend was measured at:

| run | wall | outcome |
|---|---|---|
| amend (failing) | **25m17s** | FAILED, 2 targets named |
| amend (passing) | **53m38s** | PASSED, 66/66 |
| push | **41m51s** | PASSED |

⛔ **Every one exceeded 1200s. rjyc was never "slow under load" — it was UNLANDABLE, and no
quiet window would ever have landed it.** A remedy that waits for load to drop cannot fix a
job whose *successful* path is 2.5× the ceiling. Both the worker and the supervisor held the
wait-for-quiet theory; the measurement is what killed it.

## Completed and merged

| PR | what |
|---|---|
| dev-tooling **#1248** | `8zv3.3` decoupling + the cross-lane `shell_quality` declaration — **since reverted by `f424711`** |
| dev-tooling **#1258** | docstring un-shadow + the spec proposal — **docstring half also reverted; the proposal survives and is the hazard above** |
| runtime **#476** | pin bump to `v1.19.6`, unbreaking `livespec-runtime` master CI. 64 checks green. Runtime master now `120be92` |
| dev-tooling **#1293** | **withdrew** the stale spec proposal — the live hazard above |
| dev-tooling **#1295** | `scripts/gate-run.sh` — detached gate runs with durable verdicts |
| dev-tooling **#1300** | background-guard routes to the runner instead of into the silent kill |
| dev-tooling **#1309** | **`rjyc`** — self-member local vantage + the forced LLOC extraction |

**#476 verification, re-derived independently before pushing** (all four reproduced): on a
CONSTANT tree, `v1.19.3` → exit 1 with 11 offenders / `v1.19.6` → exit 0 `not_applicable`;
`f424711` is an ancestor of `v1.19.6` and not of `v1.19.3`; GHCR `python-v1.19.6` → 200 with
a known-present control at 200 and a fabricated control at 404; lock shas are the real tag
commits.

⚠️ **Runtime green means UNENFORCED, not verified.** `pure_trees` is `not_applicable` there,
so the check convicts nobody. The 11 offenders are still in that code.

## Structural findings — filed elsewhere, do not re-derive

- **`livespec-dev-tooling-rjyc`** — the vantage fix above. **CLOSED**, merged as #1309.
- **`livespec-dev-tooling-e5nz`** (P1) — the LLOC ceiling **CLASS**: files sitting just under
  a hard ceiling silently block the next change to them, whatever it is. #1309 fixed the
  INSTANCE (`fleet_conformance.py`), not the class. **Must not be closed by re-measuring that
  one file.**
- **`livespec-dev-tooling-6q5o`** (P2) — `gate-run.sh`'s "zero targets completed" note is
  true-but-misleading on the PUSH path, because lefthook buffers command output until the
  command finishes. It cannot distinguish "nothing ran" from "output is buffered". Two
  separate readers were misled by it within an hour. `DIED_WITHOUT_VERDICT` is unaffected —
  it keys on `exit_code` presence and process liveness, never on target counts.
- **`livespec-dev-tooling-irtt`** — arm `public_api_result_typed` behind adoption. **This is
  the re-land path for `8zv3.3`.** OPEN.
- **`livespec-dev-tooling-tkzf`** — `check-fleet-conformance-admin` reads adopter repos in
  OTHER organisations from a pre-commit hook; failure mode is "nobody here can commit, for a
  reason nobody here can fix". Cleared itself once.
- **`livespec-dev-tooling-9s2j`** — the row reports nothing when a consumed function is
  DELETED. Pre-existing, orthogonal, lives in `_public_api_graph` edge resolution, NOT in
  tree source. **Deliberately excluded from rjyc.**
- **`livespec-dev-tooling-niyl`** — gh apt pin. Fixed by `e12b4c9`.
- **Gate-vs-harness ceiling — ✅ RESOLVED by #1295 + #1300.** `.claude/settings.json` still
  commits `BASH_MAX_TIMEOUT_MS=1200000` and that was deliberately NOT raised (a larger ceiling
  is still a ceiling). Instead gate RUNTIME is decoupled from harness PATIENCE: the gate runs
  in its own detached `setsid` session via `scripts/gate-run.sh`, and a cheap RESTARTABLE
  waiter reports the verdict. **Nothing was weakened** — same command, same hooks, same
  targets; the gate's own exit code IS the verdict and the runner only transports it.
  The silent kill is closed structurally: `exit_code` present is the sole marker that a
  verdict exists, and `DIED_WITHOUT_VERDICT` exits **75** — distinct from 0 and from every
  gate failure code, so it can read as neither a pass nor a refusal.
  Read `.ai/gate-runtime-vs-harness-patience.md` before diagnosing any quiet gate.

## irtt adoption bill — MEASURED 2026-08-06, one basis, per repo

**Headline: 188 reported / 123 distinct at the pass-1 heads named in the table; 190 reported
at pass-2 four hours later.** All three are true and they answer different questions — the
reported/distinct gap is `overseer`'s mirror, and the 188→190 gap is four hours of ordinary
feature work. Both are explained below, and BOTH matter for scoping.

⛔ **BASIS: `_`-prefixed FILE SKIP RETAINED.** The maintainer ruled `8zv3.5`
**KEEP-AND-RATIFY**, so this is now THE enforcement basis, not one of two. **Do not report a
no-skip column** — printing both is what produced the two-bases addition error in `8o8e.17`.

Simulated READ-ONLY: each member's `origin/master` exported into an isolated tree, scanned
with the decoupled shape (git-derived first-party universe minus `_`-prefixed files) using
that repo's own config. No pin bumped, no check armed, no CI spent.

| repo | sha | universe | scanned | offenders | current gate |
|---|---|---:|---:|---:|---|
| `livespec-driver-claude` | `39ecf54` | 9 | 7 | **0** | NotApplicable |
| `livespec-driver-codex` | `8796fc1` | 7 | 3 | **0** | NotApplicable |
| `livespec-console-beads-fabro` | `706050b` | 1 | 1 | **0** | **Undeclared** |
| `livespec-dev-tooling` | `6072318` | 185 | 96 | 2 | NotApplicable |
| `livespec-orchestrator-git-jsonl` | `1dc175d` | 49 | 37 | 4 | UnarmedUntil |
| `livespec-runtime` | `ed5529f` | 31 | 26 | 11 | NotApplicable |
| `livespec` | `cead37c` | 150 | 108 | 13 | UnarmedUntil |
| `livespec-orchestrator-beads-fabro` | `41a4343` | 186 | 48 | 17 | UnarmedUntil |
| `livespec-overseer` | `1d191b1` | 244 | 148 | **141** | UnarmedUntil |
| **TOTAL** | | **862** | **474** | **188** | |

☝️ **This table is PASS-1, at the SHAs named in it.** A pass-2 four hours later measured
**190** (`livespec-runtime` 11 → 13). The table is kept at pass-1 SHAs deliberately, because a
row is only meaningful with the sha it was measured at — see the growth section below.

⚠️ **The bill is 188, not 160.** Every earlier per-repo number is stale — the epic's own table
evaluated each repo against ITS OWN pinned criterion (six at `1.17.1`, two at `1.18.7`) at
different SHAs, and six different-versioned criteria are not cross-comparable.

**Positive control discharged.** Six of nine convict with `file:line:function`.
`livespec-runtime` reproduces **exactly 11** and the function identities match the `irtt`
ledger's independently-recorded list verbatim — so the harness reproduces a known number AND
the exact identities, not merely "it returned something".

**No zero-over-zero.** Zero repos scan zero files; every `0` above is a genuine clean over a
non-empty scanned set, not the founding defect. Smallest scanned set is `console` at 1.

**All nine are currently unenforced** (NotApplicable / UnarmedUntil / Undeclared). The check
convicts NOBODY anywhere today. "Green means unenforced" is exact, not rhetorical.

### ⛔ REPORTED 188, DISTINCT **123** — `overseer` ships a byte-identical mirror

The 188 above is what the CHECK REPORTS. It is not the amount of work, because
`livespec-overseer` carries `.claude-plugin/overseer/` as a **shipped mirror** of `overseer/`:
**91 byte-identical file pairs, ZERO differing**.

| | reported | distinct | duplicates |
|---|---:|---:|---:|
| `livespec-overseer` | 141 | **76** | 65 |
| every other member | 47 | 47 | 0 |
| **fleet** | **188** | **123** | **65** |

(Pass-1 basis, same heads as the table above. The duplication ratio is a property of
`overseer`'s layout, not of a moment — it does not move with the bill.)

Deduplicated by `(sha256(file content), line, function)`, so it does not depend on knowing any
repo's mirror layout. Of `overseer`'s 141: **65 appear on BOTH sides, 0 are mirror-only, 11
are main-tree-only.** Duplication exists in exactly one member; the other eight are 1:1.

⚠️ **Both numbers are true and they answer different questions.** Arming `overseer` requires
all **141** reported offences to clear — the check counts files, not identities. But the
REMEDIATION SURFACE is **76** distinct functions, 65 of which are "fix in `overseer/`, then
re-sync the mirror". **Do not scope the program at 141, and do not promise 76 will clear it
without the sync.**

❓ **Open, not established:** I found no wholesale byte-parity gate for that mirror — only
`version.json` lockstep (`tests/test_release_please_version_lockstep.py`) and a
runnable-launcher script check. The 91 pairs are identical TODAY, but whether re-syncing after
a fix is one command or 65 hand-copies is **not something this measurement settled**, and a
mirror held in sync by discipline rather than a gate can drift. That question belongs to the
`livespec-overseer` lane, not here.

### Cross-validated against the REAL shipped decoupled check

The numbers are not from a reconstruction alone. `46c5dab` (the actual decoupling commit —
gate genuinely absent, `role_absence_exit_code` surviving only in a comment) was exported and
its REAL `public_api_result_typed` run against all nine member trees. **Eight of nine match
exactly**: 0/0, 0/0, 0/0, 4/4, 11/11, 13/13, 17/17, 141/141. Its `_scan` is also line-for-line
the shape reproduced here — `for rel_path in sorted(sources)`, skip `_`-prefixed names — and
carries a comment stating the `_`-skip was **carried over UNCHANGED**, so the ruled basis is
the basis it actually shipped with.

⚠️ **The ninth is a real finding: `livespec-dev-tooling` is 2 under TODAY's detectors and 0
under `46c5dab`'s, on the SAME tree.** Isolated by elimination rather than guessed — identical
universe (185 both), identical `repo_local_public_names` in `charters.py`, identical
`functions_without_expected_failure_mode`, identical `commands_trees` /
`supervisor_entry_files` / `io_trees`. The delta is inside `_find_offenders`: **the CRITERION
tightened.**

⛔ **So the bill depends on WHICH dev-tooling version is armed, not only on the target repo's
code.** Measure-then-remediate against a frozen number is unsound on TWO axes — repos accrue
offenders while unenforced AND the criterion moves underneath the number. This argues FOR
arming early and incrementally: an armed repo freezes its criterion at its own pin and becomes
a regression guard, where a big-bang program chases a moving target on both.

### Offender count is NOT the only failure path

`main()` also fails on `_report_bad_declarations`, and **that runs BEHIND the gate**, so in
every unarmed repo those declarations have never once been evaluated (the check's own
docstring says so). Measured for all nine: **`would_fail_on_declarations` is False
everywhere**, so arming the three zero-bill repos is genuinely free on BOTH paths.

Stated honestly: for seven of nine that pass is **VACUOUS** — they declare nothing, so the
detectors have nothing to reject. Only `dev-tooling` (21 declarations) and `runtime` (11) have
real ones, and both are clean.

### ⛔ HOW ARMING ACTUALLY WORKS — measured, and it is NOT what "arm a repo" suggests

Before any staged-arming plan is written, three mechanism facts. All measured, none inferred.

**1. The check is ALREADY WIRED AND RUNNING in 8 of 9 members.** It is in their `justfile`
and their `.github/workflows/ci.yml` today. It does not convict because it no-ops on the
`pure_trees` role-absence gate — which lives in **dev-tooling's code**, not in the member.
The sole exception is `livespec-console-beads-fabro`, which does not wire it at all (and that,
not an oversight, is why its `pure_trees` is `Undeclared` rather than `NotApplicable`).

⛔ **So "arm repo X" is NOT a per-repo wiring change.** There is nothing to switch on in the
member. Every wired member is already paying to run a check that is gated off.

**2. The arming lever is THE PIN.** Removing the gate is one change in dev-tooling; a member
becomes armed the moment it bumps to a dev-tooling version carrying it. That is exactly how
the original breakage happened — the release fan-out auto-bumped consumer pins, so the widened
criterion arrived in repos that had never adopted it.

**3. A per-member pin-HOLD mechanism ALREADY EXISTS.**
`livespec_dev_tooling/fleet/dispatch_matrix_filter.py` filters the release-dispatch sibling
matrix by per-member conformance verdicts: a non-conformant member is **EXCLUDED from the
matrix rather than dispatched-and-failed**, every exclusion is named, and it is fail-closed
with no lever, no warn-only mode and no bypass. Staged arming therefore does **not** require
inventing a hold mechanism — one is already in production.

⚠️ **BUT IT DOES NOT KEY ON THIS CRITERION, and that gap is the real design question.** The
filter keys on fleet-conformance rows, and the existing public-API row
(`_rows_public_api_conformance`, registered as `cross-repo-public-api-declared`) asserts
**declaration-versus-consumption** — whether a member's `cross_repo_public_api` omits a name a
sibling imports. It says nothing about Result-typing. So a Result-typing offence does **not**
currently make a member non-conformant and would **not** hold it out of the fan-out.

**What that means for the recommendation:** "arm the zero-bill repos now, hold the rest" is
mechanically reachable with machinery that already exists and is already fail-closed — but
only if something makes an unprepared member non-conformant, and today nothing does. Whether
that is a new registered row, a pin-posture declaration, or staged pin bumps is an `irtt`
DESIGN decision and is deliberately **not** settled here.

⛔ Note the constraint it must satisfy: this thread already ruled that re-landing must **NOT**
add a replacement role key, because a declaration whose emptiness means "skip me" is
indistinguishable from "genuinely no code" — the founding defect. Any staged-arming mechanism
has to hold repos back **without** reintroducing that.

### How much WORK is a conversion? Blast radius of the cheap five

"47 conversions" says nothing about effort — converting a return type cascades to callers. So
the in-repo call-site count per offender was measured by AST across the five cheap repos
(49 offenders at pass-2 heads):

| in-repo call sites | offenders |
|---|---:|
| 0 (leaf) | 11 |
| 1–2 | 32 |
| 3–5 | 4 |
| 6+ | **2** |

**43 of 49 (88%) have two or fewer in-repo callers.** Exactly one genuine hot spot exists:
`beads-fabro` `store.py::read_work_items` at **15**; the next is `livespec`
`config_edit.py::write_config_value` at 6. So the cheap-five program is overwhelmingly
small, local edits plus one function that needs real thought.

⚠️ **A first attempt at this over-counted badly and is worth recording as a trap.** Counting
calls by NAME across the universe put 13 offenders in the 6+ bucket, with five entries at
"23 calls" — all of them `main`, because every check module defines one and the counter
matched every `main(` in the repo. Import-aware counting (same-file calls, plus calls in files
that actually `from <module> import <name>`) drops those to 1 apiece, which is correct: a
module entry point called by its own `__main__` guard. **A name-keyed count over a repo full
of conventional names inflates precisely the bucket you would make decisions on.**

⚠️ **Limitation, stated rather than papered over:** this counts IN-REPO callers only.
Cross-repo consumption is a separate axis — it is what `cross_repo_public_api` declares and
what the `cross-repo-public-api-declared` row measures — so a function a SIBLING imports has
blast radius this number does not capture.

### What the distribution says about sequencing

- **Three zero-bill repos exist** and can be armed at zero remediation cost. They are the three
  SMALLEST universes — together **11 of 474 scanned files (2.3%)** — and an earlier draft of
  this section dismissed that as "nearly symbolic". ⛔ **THAT WAS WRONG, and the correction
  matters**: measured over 14 days, **100% of their scanned surface changed** — 7/7, 3/3, 1/1.
  Every file turned over inside two weeks. A guard on a surface with total recent churn is
  where a regression would actually land; small ≠ inactive, and file COUNT was the wrong
  proxy for guard value.
- **And those eleven files are HOOKS.** `driver-claude`'s scanned set is entirely
  `.claude-plugin/hooks/*` + `.claude/hooks/*`; `driver-codex`'s is entirely `livespec/hooks/*`.
  That is the case `filter_first_party_py` calls out — "a Driver repo's hooks are its entire
  first-party universe" — and it is agent-facing safety code, so arming it is worth more per
  file than the 2.3% suggests.

  Contrast the repos that CANNOT be armed cheaply: `overseer` 186 commits / 148 files and
  `dev-tooling` 177 / 83 over the same window. **Churn concentrates where the bill does**,
  which is an argument for arming the cheap ones early rather than a reason to dismiss them.
- **`livespec-overseer` alone is 141 of 188 reported — 75%** (and **76 of 123 distinct —
  62%**). The entire rest of the fleet is **47** on both bases, since only `overseer`
  duplicates.
- So the strong shape is: arm the three free ones, then the five cheap ones — dev-tooling 2,
  git-jsonl 4, runtime **11 at pass-1 / 13 at pass-2**, livespec 13, beads-fabro 17 =
  **47 → 49** — putting **EIGHT of nine repos under real enforcement for ~50 conversions
  rather than ~190**, and leaving `overseer` as a single-repo program scoped on its own
  merits instead of blocking the other eight.

  ⚠️ The cheap-five total MOVED between the two passes. Quote it with its pass and its heads,
  never bare — that is working rule 3 applied to this thread's own output.

### 🔥 THE BILL GROWS WHILE UNENFORCED — now TWO independent observations

A second full measurement pass was run at fresh forge heads ~4.5h after the first, same basis,
to test this claim rather than leave it resting on one data point. **Eight of nine heads had
moved.** Result:

| repo | pass 1 | pass 2 | delta |
|---|---:|---:|---|
| `livespec-runtime` | 11 | **13** | **+2** |
| every other member | — | unchanged | 0 |
| **fleet reported** | **188** | **190** | **+2** |

Nothing was ever REMOVED — zero offenders disappeared in either repo. The two observations are
independent, in DIFFERENT repos, and both arrived through ordinary feature work:

- `livespec-dev-tooling` 0 → 2: `charters/charters.py`, added 2026-08-05 23:10Z
- `livespec-runtime` 11 → 13: `github_budget_client_support.py::header_value` and
  `::mapping_option`, added by `c77f2d7` *"feat: mitigate github request budget pressure"*
  2026-08-06 01:21Z

⚠️ **Do not read a RATE off two points.** What is established is direction and mechanism: new
public API lands un-Result-typed because **nothing anywhere is checking** — the gate is off in
all nine members. The bill tracks the rate at which public API is written.

🔥 **Original single observation, kept:** `dev-tooling` was 93 scanned
with **ZERO** offenders on 2026-08-04. On 2026-08-06 it is 96 scanned with **TWO**, both
arriving in `61048d7` *"feat: expose importable charter-defect detectors"* — in the
enforcement-suite repo itself. **Any per-repo number has a shelf life: re-measure at arm
time, do not carry this table forward as current.**

⚠️ **Anomaly, flagged not filed:** `livespec-console-beads-fabro` declares `pure_trees`
**Undeclared**, not `NotApplicable`. Per `config.py` an undeclared required role key makes
role-gated checks HARD-ERROR naming the key rather than no-op, so console is in a different
state from the other eight. Its whole first-party universe is one file
(`dev-tooling/coverage-gate.py`).

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
- **`8zv3.5`** the `_`-prefixed FILE skip — **RULED: KEEP-AND-RATIFY.** The skip stays and
  is ratified explicitly, so the retained-skip basis is now THE enforcement basis. The
  ratification is a separate spec change and it belongs to the supervisor, NOT to an
  implementation lane. Do not touch the skip in any diff.
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
   when the verdict survives. Produced twice more this session, once inside a ruling
   (an INFERRED line count of 249 where the MEASURED value was 253 — over the ceiling, not
   under it) and once in a survey (three offenders quoted from the tail of an output whose
   real count was eleven).
6. **A stale artifact is not current state — check its own claim against `date -u`.** A
   usage-limit modal was obeyed for ~14 hours after its stated reset had passed; a spec
   proposal described behavior that had been reverted; a handoff described work that had
   merged. Same defect class, three surfaces. It is the class this thread exists to close,
   and the thread kept re-committing it.
7. **An instrument that cannot distinguish two states will eventually assert the wrong one.**
   `gate-run.sh`'s per-target evidence goes dark on the push path, and its accurate note
   ("zero targets completed") reads as "nothing is running". Prefer a signal that keys on
   something structural — `DIED_WITHOUT_VERDICT` keys on `exit_code` presence and process
   liveness, which is why it stayed correct where the progress evidence did not.
8. **Waiting is not a remedy for a job that cannot fit.** rjyc was parked for a quiet window;
   its PASSING run measured 53m38s against a 1200s ceiling. No window would have been quiet
   enough. Measure the successful path before choosing to wait for one.
