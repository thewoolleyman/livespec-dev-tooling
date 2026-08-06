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
> below for what to do. The open item is **`livespec-dev-tooling-idlx`** (EPIC, P1, READY —
> **NOT `irtt`, which is CLOSED**; see the correction directly below), whose adoption bill is
> measured per repo below — **188 reported / 123 distinct at pass-1 heads, 190 at pass-2 four
> hours later, and 190 REPORTED / 125 DISTINCT at pass-3 current heads** (the reported/distinct
> gap is `overseer`'s byte-identical shipped mirror, and it is the ONLY member where the two
> differ) — and whose next step is a SEQUENCING decision for the maintainer, not
> implementation. **Quote pass-3's 190/125 with its heads; the bare 123 is superseded.**

## ⛔ CORRECTION 2026-08-06 — `irtt` IS CLOSED; THE RE-LAND IS `idlx`

Earlier revisions of this file named `livespec-dev-tooling-irtt` as the open item in three
places. **That is false and was false when written.** Re-derived from the ledger, which this
file's own header names authoritative:

- **`livespec-dev-tooling-irtt` — CLOSED.** It is the INCIDENT item (five masters turned red
  by enforcement-before-adoption), and it closed on a two-half record: the revert shipped in
  `v1.19.6`, all five repos are at or past that pin, and all five masters are green on FRESH
  runs with run ids and headShas recorded. The close explicitly reads the per-repo STEP LIST
  rather than trusting the job conclusion — because a py-gated job reports SUCCESS while
  skipping (`livespec-dev-tooling-zi29`), which had misled that thread four times.
- **`livespec-dev-tooling-idlx` — EPIC, P1, READY.** "Re-land the `public_api_result_typed`
  un-gating behind adoption." **This is what owns the work**, and no earlier revision of this
  file mentioned it at all.

```bash
cd /data/projects/livespec-dev-tooling && /usr/local/bin/with-livespec-env.sh -- bd show livespec-dev-tooling-idlx
```

**`idlx`'s decomposition — 7 children, 101 distinct functions on ITS basis:**

| child | tenant | scope |
|---|---|---|
| `livespec-dev-tooling-yj09` | dev-tooling | stop the check reading co-located TEST modules as public API |
| `livespec-dev-tooling-crl2` | dev-tooling | re-land `46c5dab` — **blocked-by BOTH `yj09` AND `zi29`** |
| `bd-gj-vxa` | `livespec-orchestrator-git-jsonl` | 4 functions |
| `livespec-runtime-cq8` | `livespec-runtime` | 11 functions |
| `livespec-szto` | `livespec` | 13 functions |
| `bd-ib-vcq9` | `livespec-orchestrator-beads-fabro` | 17 functions |
| `overseer-bjrm` | `livespec-overseer` | 56 functions |

⚠️ **The five adoption children are wired ONE WAY ONLY.** Beads refuses cross-tenant edges, so
each carries `metadata.non_local_depends_on` pointing back at `idlx` and **nothing blocks
mechanically**. "`crl2` must not land until all five are closed" is PROSE. Re-measure each id
from ITS OWN repo checkout — `bd` resolves the tenant from the working directory.

**This is working rule 6 committed inside the record written to prevent it — third surface.**
A stale proposal, a stale handoff, and now a stale ledger reference in the handoff's own
headline. Verify against `bd` before quoting any item's state, including from this file.

## ▶️ NEXT SESSION — START HERE

**Nothing in this thread is parked and nothing is half-done.** Every branch this thread opened
is merged, every worktree it created is removed, and the primary is clean on `master`.

⛔ **DO NOT START `idlx` REMEDIATION** (this was written as "`irtt` remediation"; same work,
corrected id). The maintainer has not ruled on sequencing. This lane's job was to MEASURE the
decision, and the measurement is complete and recorded below.

**First action: report on the milestone channel**
(`tmp/overseer/pure-trees-role-key-scope/worker-status.log`) that measurement is complete and
this lane is awaiting the sequencing ruling. Then wait for the supervisor's dispatch.

### ✅ ALREADY DONE ON 2026-08-06 — do NOT redo any of this

A session ran after the block above was written and did the report, then kept measuring. **The
report has been filed; filing it again is harmless but redundant.** What it added, all merged
(dev-tooling #1326, #1327, #1328, #1329, #1330), so that none of it is repeated:

- **`irtt` is CLOSED and `idlx` is the re-land** — the correction at the top of this file.
- **The harness was REBUILT from the recipe in this file and both controls discharged.** You do
  not need to re-derive whether the recipe works; it does. See the ✅ note in the recipe section
  for the two things the recipe omits.
- **The `overseer` `+20` question is SETTLED: 11 basis + 9 growth**, by a four-head replay. The
  earlier "re-derive the `+18` first" instruction is DISCHARGED — do not chase it again.
- **PASS-3 over all nine exists: 190 reported / 125 distinct.** Quote it with its heads.
- **The second failure path was re-checked** — `would_fail_on_declarations` False fleet-wide.
- **All nine declarations re-read at pass-3 heads** — still unenforced, nothing moved.
- **Only SEVEN of nine repos are reachable by the pin**, because `console` is unwired.
- **`idlx`'s effort buckets are RE-DERIVED** by AST evidence (#1332, #1333): entrypoint 17,
  raises 7, raises-transitive 4, optional-return 17, total-bool 4, pure-total 38, judgement 38.
  **17 of 125 are undeclared module entry points** — candidate config-gap fixes, not
  conversions.
- ⛔ **`runtime` is the LEAST cheap of the cheap five** (#1334, #1335): **all 13 of its
  offenders sit in files vendored into 2–4 other repos**, verified byte-identical. `idlx`'s
  smallest-first ordering puts it SECOND, which defeats that ordering's own stated purpose.
- **Vendoring is a THIRD blast-radius channel** invisible to both existing measures; the
  declared-import axis sees only **3 of runtime's 13**.
- **`check-vendor-manifest` does NOT enforce content parity** — metadata only, and it exits 0
  when the manifest is absent. 740 vendored files are in sync by discipline, not by a gate.
- **The blast-radius "overwhelmingly small, local edits" conclusion is WITHDRAWN** (#1336). The
  caller COUNTS stand; reading them as a cost statement did not.
- ⛔ **Declaring the 17 entry points would buy FOUR exemptions each, not one** (#1338) — the
  ratified spec's own words. That is a carve-out, which the re-land constraint forbids.
- ⛔ **`total_absence_returns` CANNOT take `lane_of`/`is_item_ready`** (#1339) — bound 1 gates it
  to `X | None` and hard-REJECTS other shapes. An earlier recommendation of mine to use it there
  is WITHDRAWN. No declaration key reaches a total non-`Optional` public function at all.
- 🔑 **57% of the bill (71 of 125) is reachable by NO declaration key** (#1340) — conversion is
  its only sanctioned disposition. Syntax-only measurement; the most trustworthy number here.

### ⚖️ WHICH OF THIS LANE'S NUMBERS TO TRUST — read this before quoting any of them

This lane corrected itself repeatedly, and the corrections were not evenly distributed. They
concentrated in one KIND of claim. Sorted by how much weight each will bear:

**✅ Strong — a control was discharged, or it is pure syntax:**
- The per-repo bills (pass-1/2/3) — the harness reproduced `runtime`'s 11 BY IDENTITY and
  `overseer`'s 141/76/65 exactly.
- **71 of 125 reachable by no declaration key** — return-annotation shape only.
- The vendoring measurement — content hashes, verified byte-identical across four repos.
- `entrypoint` 17 — `__main__`-guard evidence, and it independently matched `idlx`'s ~18.
- Every quotation from ratified `contracts.md` — re-read at source, not recalled.

**⚠️ Weak — absence-based, and it mis-filed a known counterexample:**
- `pure-total` 38 and `total-bool` 4. `parse_cross_repo_manifest` was filed here while its own
  docstring said it raises. Treat as "looks total", never as "has no failure mode".

**⛔ Wrong, and recorded rather than deleted — every one was an INFERENCE I had not measured:**
- the `overseer` `+20` blamed on basis (it was 11 basis + 9 growth)
- `check-vendor-manifest` assumed to enforce parity (it validates metadata only)
- the 17 entry points read as cheap (they are four-way carve-outs)
- `total_absence_returns` proposed for `lane_of` (structurally rejected)
- "eight of nine repos armed" (seven — `console` is unwired)

**The pattern is exact and worth inheriting: every wrong item was reasoned to; every strong item
was measured or read at source. When this lane guessed, it was wrong about 5 times out of 5.**

⛔ **What is NOT done, and is the actual open question:** the maintainer has still not ruled on
sequencing. Nothing above changes that — it makes the ruling better-informed, not unnecessary.

⚠️ **Everything measured here has a shelf life.** The bill moved twice inside one session and
`overseer` moved +60 in three days before plateauing. **Re-measure at arm time.** The harness
recipe is in this file precisely so that is cheap.

**Owned by the SUPERVISOR, not by you — do not do these:**

- putting the `idlx` sequencing decision to the maintainer
- the `8zv3.5` keep-and-ratify spec change (the `_`-prefixed FILE skip)
- ledger items `livespec-dev-tooling-e5nz` (the LLOC ceiling CLASS) and
  `livespec-dev-tooling-6q5o` (the runner's push-path evidence gap)

If a supervisor dispatch is already waiting when you start, **follow that instead of this
paragraph** — it is newer than this file.

## 📋 FOR THE SEQUENCING RULING — the whole decision brief, on one screen

This file is **1300+ lines**. The ruling should not require reading them. Everything below is
measured and each line names the section carrying the evidence.

**The bill.** 190 reported / **125 distinct** at pass-3 current heads. `overseer` is 141 of 190
(74%) and 76 of 125 (61%); the whole rest of the fleet is 49. *(→ PASS-3 table.)*

**Six findings that bear on the ORDER, none of which the ledger currently reflects:**

1. ⛔ **`zi29` is a PREREQUISITE, not a cost item.** On a zero-`.py` PR the check job reports
   SUCCESS while every real step skips — the mechanism by which five masters sat red while PRs
   kept merging. Arming ANY repo ahead of it lets the next breakage hide identically, including
   the zero-bill ones. **Free on remediation ≠ safe to arm.** *(→ sequencing section.)*
2. ⛔ **The re-land reaches SEVEN of nine repos, not eight.** `console` wires the check nowhere,
   so no dev-tooling release arms it; it needs a member-side change. *(→ free-by-pin table.)*
3. ⛔ **`runtime` should be LAST of the cheap five, not second.** `idlx` orders smallest-first
   "so the triage pattern is set on cheap surfaces"; `runtime` is 76% unreachable-by-declaration
   AND 100% vendored into 2–4 repos. Two independent measures, same verdict — the ordering
   defeats its own stated purpose. *(→ ordering + vendoring sections.)*
4. ✅ **`overseer-bjrm` is both bigger and smaller than the ledger says.** The ledger scopes it
   at **56**; it measures **65** on that same basis (growth, not disagreement). But **27 of its
   76 are `X | None`-shaped**, so ~34 are declaration-eligible and **42 are hard conversions** —
   "76 conversions" overstates it. *(→ per-repo eligibility.)*
5. 🔑 **57% of the bill (71 of 125) can be reached by NO declaration key** — conversion is its
   only sanctioned disposition. Per-repo spread runs 38% (`livespec`) to 100% (`dev-tooling`).
   The "config gap" framing cannot shrink this program much. *(→ declaration-key section.)*
6. ⛔ **The 17 entry points are NOT cheap wins.** Declaring one grants **FOUR exemptions at
   once** per ratified `contracts.md:225` — a carve-out, which the re-land constraint forbids.
   *(→ four-exemptions note.)*

**One question someone must ANSWER, not measure, before `runtime` is opened:** `lane_of` and
`is_item_ready` are flagged; `idlx` says Result-typing them would be WRONG; and **no declaration
key can reach them** (`total_absence_returns` hard-rejects non-`X | None` shapes). The ledger,
the vocabulary and the check disagree. That is semantic and it is not this lane's call.
*(→ the withdrawn-recommendation correction.)*

**Two standing conditions the ruling should not assume away:**

- **The bill GROWS while unenforced** — three independent observations, `overseer` +60 raw in
  under three days before plateauing. Any frozen number has a shelf life; re-measure at arm time.
- **Vendored copies and `overseer`'s mirror are in sync by DISCIPLINE, not by a gate.**
  `check-vendor-manifest` validates metadata only and exits 0 when the manifest is absent.

⛔ **What this lane did NOT decide, deliberately:** the order itself, whether any declaration is
granted, and how repos are held back without reintroducing a "declaration whose emptiness means
skip me". Those are the maintainer's.

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

✅ **THE RECIPE WAS REBUILT FROM THIS FILE ALONE ON 2026-08-06 AND IT WORKS.** A later session
reconstructed the harness using only the block above, and it reproduced BOTH recorded controls
exactly: `livespec-runtime` @ `ed5529f` → universe 31 / scanned 26 / **11 offenders** with the
identities matching `irtt`'s list verbatim, and `livespec-overseer` @ `1d191b1` → **244 / 148 /
141 reported / 76 distinct / 65 duplicates**, matching the pass-1 table row for row. So the
recipe is sufficient; you do not need the original scratch harness.

⚠️ **Two additions that the recipe above does NOT tell you, learned rebuilding it:** import
`resolve_check_universe` from `...checks.public_api_result_typed` (not from `config`), and note
that `_find_offenders` returns `(line, name)` pairs — the useful outputs are (a) dedup by
`(sha256(file_content), line, name)` for the distinct count and (b) a `"test" in filename`
partition, which is what makes this lane's numbers comparable to `idlx`'s.

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
across nine repos in one step. **Re-landing behind adoption is `livespec-dev-tooling-idlx`
(READY) and specifically its child `livespec-dev-tooling-crl2`, which is blocked-by `yj09` and
`zi29`.** (This paragraph said "`irtt` and it is OPEN" — `irtt` is the closed INCIDENT item.)
Do not re-land by simply reapplying `46c5dab`.

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

⚠️ **The re-land (`livespec-dev-tooling-crl2`, under `idlx`) files its own proposal — do not
resurrect this one.** (Written as "`irtt` files its own proposal"; corrected id.) The
re-land must be described against what actually ships, when it ships (gate retained until a
repo adopts), not reconstructed from reverted behavior. The reasoning is preserved in `irtt`
(closed items keep their notes), in `idlx`, and in this thread; nothing was lost in the
deletion.

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
- **`livespec-dev-tooling-irtt`** — the INCIDENT (five masters red from
  enforcement-before-adoption). **CLOSED**, verified per-repo on fresh runs. It is NOT the
  re-land and never was.
- **`livespec-dev-tooling-idlx`** (P1, READY) — arm `public_api_result_typed` behind adoption.
  **This is the re-land path for `8zv3.3`.** OPEN, 7 children (see the correction section at
  the top). Its `crl2` child is blocked-by `yj09` and `zi29`.
- **`livespec-dev-tooling-zi29`** (P1) — a py-gated check job reports SUCCESS while skipping
  the check itself, so a REQUIRED context certifies nothing. **This is why five masters could
  sit red while PRs kept merging**, and `idlx` names it a PREREQUISITE: re-arming ahead of it
  would let the next breakage hide identically. Cross-repo, 6 of 10 repos.
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

## The adoption bill (`idlx`) — MEASURED 2026-08-06, one basis, per repo

*(Titled "irtt adoption bill" in earlier revisions; the bill is `idlx`'s — see the correction
at the top of this file.)*

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

✅ **RE-VERIFIED at pass-3 current heads by reading each `origin/master:pyproject.toml`, not
carried forward** — this is the claim the whole recommendation rests on, so it is the one worth
re-reading rather than assuming. **Nothing has changed:** `not_applicable` in `livespec-runtime`,
`livespec-driver-claude`, `livespec-driver-codex`, `livespec-dev-tooling`; `unarmed_until =
"livespec-mutreal.1"` in `livespec`, `livespec-overseer`, `livespec-orchestrator-git-jsonl`;
`unarmed_until = "bd-ib-6qb2mc"` in `livespec-orchestrator-beads-fabro`; and
`livespec-console-beads-fabro` declares **no `pure_trees` key at all**.

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
that is a new registered row, a pin-posture declaration, or staged pin bumps is an `idlx`
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
`config_edit.py::write_config_value` at 6.

⛔ **THIS PARAGRAPH USED TO CONCLUDE "so the cheap-five program is overwhelmingly small, local
edits plus one function that needs real thought". THAT CONCLUSION IS FALSE and is withdrawn.**
The COUNTS above are unchanged and still correct — what was wrong was reading them as a
statement about EFFORT. Measured later in this file: **all 13 of `runtime`'s offenders live in
files vendored into 2–4 other repos**, so 13 of the cheap five's 49 (**27%**) are coordinated
multi-repo re-vendors that this table scores as ≤2-caller trivia. **A caller count is a
statement about one repo; it was never a statement about cost.**

The corrected reading: the cheap five is overwhelmingly small and local **in the four repos
that carry no vendoring** (`dev-tooling` 2, `git-jsonl` 4, `livespec` 13, `beads-fabro` 17),
plus `runtime`'s 13, which are not local at all.

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

⛔ **AND THAT LIMITATION WAS ITSELF UNDERSTATED — there are THREE channels, not two.** The
paragraph above names in-repo callers and declared IMPORT edges. **Vendored source copies are a
third**, and neither instrument sees them: a vendored copy is not a caller and not an import, so
no declaration graph resolves it. Measured (below): of `runtime`'s 13 offenders, **3 are
declared import edges and 10 are vendor-only** — so the declared-import axis, the one this note
pointed at as the remedy, captures **3 of 13** of that repo's real exposure.

### 🔁 RECONCILED against `idlx`'s own decomposition — 4 of 5 agree exactly

`idlx` was decomposed on **2026-08-04** and carries its OWN per-repo cut, totalling **101
distinct functions**. This lane measured the bill independently on **2026-08-06**. Comparing
them is arithmetic over two existing records — **no third measurement pass was run**:

| repo | `idlx` (2026-08-04) | measured here (2026-08-06) | agrees? |
|---|---:|---:|---|
| `livespec-orchestrator-git-jsonl` | 4 | 4 | ✅ |
| `livespec` | 13 | 13 | ✅ |
| `livespec-orchestrator-beads-fabro` | 17 | 17 | ✅ |
| `livespec-runtime` | 11 | 11 pass-1 / **13** pass-2 | ⚠️ +2 |
| `livespec-overseer` | 56 | **76** distinct | ⛔ +20 |

**Three exact agreements across two independent measurements, two days and two bases apart,
are a positive control on BOTH** — neither number set is a reconstruction artifact.

The two disagreements have KNOWN and DIFFERENT causes, and neither is a measurement error:

- **`runtime` +2 — GROWTH, not disagreement.** `idlx`'s 11 matches this lane's pass-1 exactly.
  The extra 2 arrived afterwards in `c77f2d7` *"feat: mitigate github request budget pressure"*.
  The two records agree; the CODE moved between them. This is the growth-while-unenforced
  finding showing up as a discrepancy between two honest counts.
- **`overseer` +20 — RE-DERIVED BY MEASUREMENT (2026-08-06). It is 11 BASIS + 9 GROWTH, and
  `idlx`'s numbers are on the SAME basis as this lane's, just at an earlier head.**

  ⛔ **Two earlier drafts of this bullet were wrong and are corrected here.** The first
  attributed the whole 20 to "basis". The second decomposed it as
  `+18 raw / +11 test / −9 dedup` and asserted "only the `+11` and `−9` are basis". The
  arithmetic reconciled, but the ATTRIBUTION was wrong: the `−9` is **growth**, not basis.
  Both drafts were guesses at a cause; this one is measured.

  `overseer`'s master was replayed at four heads with the rebuilt harness (recipe above,
  positive control discharged — `livespec-runtime` @ `ed5529f` reproduced **exactly 11** with
  identities matching `irtt` verbatim, and `overseer` @ `1d191b1` reproduced the pass-1 row
  **244 / 148 / 141 / 76 / 65** exactly):

  | head | date | raw | distinct non-test |
  |---|---|---:|---:|
  | `b3ae0dd` | 2026-08-03T18:12 | 81 | 35 |
  | `baa60f8` | 2026-08-04T03:38 | 115 | 52 |
  | **`idlx`'s stated figures** | **2026-08-04 (decomposed)** | **123** | **56** |
  | `e1d257c` | 2026-08-04T22:48 | 137 | 63 |
  | `1d191b1` | 2026-08-06 (pass-1) | 141 | 65 |

  **`idlx`'s 123 and 56 both land inside a monotone trajectory on THIS basis**, between the
  03:38 and 22:48 heads of the very day it was decomposed. Two independent figures landing in
  the right interval on the right day is not a coincidence of bases — `idlx` measured the same
  way, earlier. So the correct decomposition of `76 − 56 = 20` is:

  | component | size | kind |
  |---|---:|---|
  | 11 co-located TEST modules `idlx` subtracts, this basis reports | **11** | **BASIS** — and it is exactly what `yj09` exists to make unnecessary |
  | `overseer` growth from mid-08-04 to 08-06 (distinct non-test 56 → 65) | **9** | **GROWTH** |

  ⚠️ **The comparable quantity is this lane's distinct-NON-TEST (65), not its distinct (76).**
  `idlx`'s 56 was never comparable to 76. The test-file hit count is **constant at 11 across
  all four heads**, which is what independently confirms it as a basis term rather than drift.

⛔ **THE +20 IS A LIVE SCOPING QUESTION FOR THE SEQUENCING RULING, NOT A BOOKKEEPING NOTE.**
`overseer-bjrm` is the single most expensive adoption child, and it is scoped in the ledger at
a number **26% below** what this lane measures. Whichever way it resolves, resolve it BEFORE
that child is dispatched — and note that the two bases can only converge after `yj09` lands,
since until then the check genuinely does read those test modules as public API.

### 🔁 EFFORT BUCKETS RE-DERIVED BY AST EVIDENCE — `idlx` asked for this explicitly

`idlx` records "HEURISTIC BUCKETS over the 101, **to be re-derived rather than trusted**:
~19 parse/load/resolve … ~18 CLI/entrypoint … 64 needing per-function judgement". Re-derived
here over the **125 distinct at pass-3 heads**, classified by **AST evidence rather than by
name** — the name-keyed approach already over-counted once in this thread:

| bucket | evidence used (first match wins) | n | share |
|---|---|---:|---:|
| **entrypoint** | the function is invoked inside its own file's `if __name__ == "__main__":` guard | **17** | 14% |
| **raises** | the body contains an explicit `raise` | **7** | 6% |
| **total-bool** | annotated `-> bool`, no `raise`, no I/O-looking call | **4** | 3% |
| **judgement** | everything else | **97** | 78% |

Per repo: `dev-tooling` 0/0/0/2 · `git-jsonl` 0/0/0/4 · `runtime` 1/2/1/9 · `livespec` 2/0/0/11 ·
`beads-fabro` 7/2/0/8 · `overseer` 7/3/3/63. **Cheap five (49): 10 entrypoint, 4 raises,
1 total-bool, 34 judgement.**

**✅ Cross-validates `idlx` from an independent method.** `idlx` estimated **~18** CLI/entrypoint
by name; this measures **17** by `__main__`-guard evidence over a *larger* set. Two methods, two
days apart, landing one apart.

**⛔ 17 of 125 are module ENTRY POINTS, and ALL 17 are undeclared in `supervisor_entry_files`**
(16 `main`, 1 `run`) — concentrated in `beads-fabro` 7 and `overseer` 7. The check has a
declared exemption for exactly this shape, so these are **candidate CONFIG-GAP fixes rather than
Result conversions**. `idlx` reaches the same read from a sample (`hygiene_scan_cli.py:23 main`).

⚠️ **"Candidate" is load-bearing — do NOT bank 17 free wins.** Whether a given `main` *ought* to
be declared is a judgement: `supervisor_entry_files` is for supervisor entry points specifically,
and a plugin hook's `main` may not qualify. What is measured is the SHAPE, not the entitlement.

⛔ **AND THE RATIFIED SPEC MAKES THAT CAVEAT MUCH STRONGER THAN "it may not qualify".**
`livespec-dev-tooling` `SPECIFICATION/contracts.md:225` (current ratified text, re-read
2026-08-06) says `supervisor_entry_files` is consumed by **FOUR** checks —
`no_except_outside_io`, `no_write_direct`, `public_api_result_typed`, `supervisor_discipline` —
and states verbatim:

> **Declaring one path here grants ALL FOUR exemptions at once**, and a consumer adding a file
> to satisfy one check receives the other three **without deciding anything** … Each entry
> SHOULD therefore carry a written reason, and a repo that has not declared a path gets nothing.

Concretely, per that same clause: `no_write_direct` would exempt **the WHOLE FILE** from the
direct-write ban (not merely its `main()`), and `supervisor_discipline` would exempt it from the
`sys.exit` / `raise SystemExit` confinement rule.

⛔ **SO DECLARING THE 17 TO CLEAR THIS CHECK WOULD SILENTLY BUY THREE UNRELATED EXEMPTIONS PER
FILE.** That is not a config tidy-up; it is a blanket carve-out purchased to make one check
green. **It is also exactly what this thread's own re-land constraint forbids** — no lever, no
carve-out, no severity demotion (`li-4x3a45` is the recorded wontfix), and
`livespec/.ai/ci-gate-discipline.md` names that class as revert-worthy.

✅ **The honest restatement:** the 17 are **not 17 cheap wins and not 17 conversions either.**
They are 17 decisions, each of which the ratified spec says SHOULD carry a written reason, and
each of which grants four exemptions if taken. Whoever sequences this should price them as
judgement calls with a blast radius, **not** as the cheapest bucket on the board — which is how
a 14%-of-the-bill "config gap" naturally reads.

⚠️ **`raises` = 7 is a LOWER BOUND on genuine violations, not the count of them.** It only finds
functions that raise EXPLICITLY. A function signalling failure by returning `None`, `-1` or an
empty result is a genuine violation too and lands in `judgement`. **The 97 is not "97 hard
conversions"** — it is "97 the evidence available here cannot settle", which is why my
`judgement` bucket is larger than `idlx`'s 64: stricter thresholds, not a different population.

**Validated before being believed** (working rule 2), by reading source rather than trusting the
labels: `beads-fabro` `.claude-plugin/hooks/codex_yolo_gate.py:199 main` really is called from
`if __name__ == "__main__": raise SystemExit(main())`; `spec_reader.py:57
read_specification_history` really does `raise SpecVersionNotFoundError` when the version
directory is absent — a textbook expected external failure sitting off the railway.

### 🔬 THE 97 `judgement` RESIDUE, SPLIT FURTHER — and where the method BREAKS

The 97 above was "the evidence available cannot settle this". Two further passes settle 59 of
it. **The totals reconcile exactly: 17 + 4 + 38 + 38 = 97**, so this REFINES the table above,
it does not replace it.

| bucket | evidence | fleet (125) | cheap five (49) |
|---|---|---:|---:|
| entrypoint | called under its own `__main__` guard | 17 | 10 |
| raises | explicit `raise` in its own body | 7 | 4 |
| **raises-transitive** | calls something IN THE SAME FILE that raises | **4** | **3** |
| **optional-return** | annotated `X \| None` **and** returns `None` on some path | **17** | **2** |
| total-bool | `-> bool`, no raise, no I/O | 4 | 1 |
| **pure-total** | no raise, no I/O, no `None`-return, concrete return type | **38** | **16** |
| judgement | still unsettled | **38** | **13** |

**The honest split is PRESENCE vs ABSENCE evidence, and only one half is bankable:**

- **45 of 125 rest on POSITIVE evidence** (entrypoint 17 + raises 7 + raises-transitive 4 +
  optional-return 17). Each has something affirmatively present in the source.
- **42 of 125 rest on ABSENCE** (pure-total 38 + total-bool 4) — "no failure mode I could
  detect". ⛔ **Do NOT bank these as 'needs no conversion'**; see the counterexample below.
- **38 remain genuinely unsettled.**

#### ⛔ The absence-based buckets are UNSOUND under delegation — proven, then partly fixed

Pass 2 classified `livespec-runtime` `types.py:211 parse_cross_repo_manifest` as **pure-total**
while **its own docstring says "Raises `CrossRepoSchemaError`"**. The `raise` lives two hops
down in `_require_field`; body-only AST analysis cannot see delegated failure.

Pass 3 added a within-file transitive closure (a function raises if anything it calls in the
same file raises). `parse_cross_repo_manifest` now classifies correctly — **but the fix moved
only 4 of 41.** ⚠️ **Cross-FILE and cross-MODULE delegation remains invisible**, so `pure-total`
is a floor on "looks total", never a finding that a function has no failure mode.

⚠️ **This is the same trap as the name-keyed call counting**, in a new disguise: an absence is
much weaker evidence than a presence, and absence-of-evidence classifiers fail silently. The
`raises` family is a LOWER BOUND that can only grow; `pure-total` is the bucket that will
shrink as evidence improves. **Spend scepticism on the second one.**

#### ✅ But sampling the residue found something that CHANGES the cost model

`livespec-runtime` `hygiene_scan.py:42 scan_hygiene` sits in `pure-total`, and reading it shows
why the bucket is not simply noise. Its docstring states:

> ⛔ THE RAILWAY TERMINATES HERE, AND THE SIGNATURE IS HELD ON PURPOSE. … consumed ACROSS REPOS
> by source copy … Widening the return type to `IOResult` is a coordinated multi-repo change,
> not a side effect of putting the leaf on the railway, so it is **filed rather than taken
> here.** See `detect_stale_worktrees` for the sibling terminal.

**Verified on the forge, not taken on the docstring's word:** `livespec-orchestrator-beads-fabro`
and `livespec-orchestrator-git-jsonl` BOTH carry `_vendor/livespec_runtime/hygiene_scan.py`,
`hygiene_scan_cli.py` and `hygiene_scan_worktrees.py` — **vendored source copies**.

⛔ **VENDORING IS A THIRD BLAST-RADIUS CHANNEL, AND BOTH EXISTING MEASURES ARE BLIND TO IT.**
The handoff's caller counts are IN-REPO only; the `cross-repo-public-api-declared` row measures
IMPORT edges. **A vendored copy is neither** — it is not an import, so no declaration graph sees
it. Converting `scan_hygiene` is a coordinated THREE-repo change that both instruments score as
cheap and local.

✅ **A hazard this raised and then CLOSED: the fleet total does NOT double-count vendored code.**
`_vendor` is excluded from the first-party universe entirely (**0 of `beads-fabro`'s 186**), and
a content-hash check across all six repos finds **zero** offenders appearing in more than one
repo — fleet-wide distinct is 125, identical to the per-repo sum. Cross-repo duplication is a
BLAST-RADIUS problem, not a counting problem.

**And `lane_of` lands in `pure-total`** — the very function `idlx` independently names as a pure
total classifier where Result-typing would be **WRONG**. Two methods agreeing on a specific
function is worth more than either bucket total.

### 🔥🔥 MEASURED: ALL 13 OF `livespec-runtime`'S OFFENDERS ARE VENDORED INTO OTHER REPOS

The vendoring channel above was found by sampling. Measured directly, it is not an edge case —
**it is the whole of one cheap-five repo.**

Method: hash every tracked `.py` under a `_vendor/` path in all nine repos (**740 files, 293
distinct contents**), then match each flagged offender's file by CONTENT hash.

| offender file (`livespec-runtime`) | functions | vendored into | copies |
|---|---:|---|---:|
| `cross_repo/types.py` | 2 | `livespec`, `beads-fabro`, `git-jsonl` | **4** |
| `github_auth/config.py` | 1 | `livespec`, `beads-fabro`, `git-jsonl` | **4** |
| `github_auth/credential_helper.py` | 1 | `livespec`, `beads-fabro`, `git-jsonl` | **4** |
| `hygiene_scan_cli.py` | 2 | `livespec`, `beads-fabro`, `git-jsonl` | **4** |
| `work_items/lifecycle.py` | 2 | `livespec`, `beads-fabro`, `git-jsonl` | **4** |
| `cross_repo/resolve.py` | 1 | `livespec` | 2 |
| `github_budget_client_support.py` | 2 | `livespec` | 2 |
| `hygiene_scan.py` | 1 | `livespec` | 2 |
| `hygiene_scan_worktrees.py` | 1 | `livespec` | 2 |
| **TOTAL** | **13 of 13** | | |

**Verified byte-identical, not merely same-named**: `work_items/lifecycle.py` hashes to
`32e0b4ff…` in `livespec-runtime` AND in all three consumers' `_vendor/livespec_runtime/`.
Four copies in lockstep today.

⛔ **SO `runtime` IS THE LEAST CHEAP OF THE CHEAP FIVE, NOT THE MIDDLE OF IT.** It is 13 of the
cheap five's 49 (**27%**), and **every single one** is a coordinated 2-to-4-repo re-vendor
rather than a local edit. The blast-radius table that put 88% of conversions at ≤2 in-repo
callers **cannot see this** — it counts in-repo callers, and these copies are not callers.

⚠️ **Only `runtime` is affected.** Zero offenders in the other five billed repos sit in
exactly-vendored files. There is exactly one weaker signal elsewhere:
`beads-fabro` `store.py:102 read_work_items` (the 15-caller hot spot) shares a BASENAME with
files in `livespec` and `git-jsonl` but **not** their content — so it is a parallel
implementation, not a vendored copy. Reported as basename-only evidence, deliberately not
counted with the 13.

#### ⚠️ And nothing ENFORCES the lockstep — same class as the `overseer` mirror question

All three consumers wire `check-vendor-manifest`, so it is tempting to conclude the copies are
gated. **They are not.** Read the check
(`livespec_dev_tooling/checks/vendor_manifest.py`): it validates `.vendor.jsonc` **METADATA
ONLY** — that each entry has a non-empty `upstream_url` and `upstream_ref`, a parseable
`vendored_at`, and a correct `shim` flag. It performs **no content comparison** (no `sha256`,
no `hashlib`, no parity check anywhere in it) and it **exits 0 when the manifest is absent**.

So the 740 vendored files are held in sync by DISCIPLINE, not by a gate — precisely the open
question this thread already raised for `overseer`'s 91-pair mirror, now shown to be a
**fleet-wide** property rather than one repo's layout quirk. A conversion that lands in
`runtime` without re-vendoring will not be caught by `check-vendor-manifest`.

**What this does NOT mean** — stated because the natural next inference is wrong: it does not
inflate the bill. `_vendor` is excluded from every first-party universe, so the vendored copies
are never scanned and never counted (see the closed hazard above). This is entirely a
COORDINATION cost, not a counting one.

### ⛔ `idlx`'s SMALLEST-FIRST ORDERING PUTS THE MOST COORDINATION-HEAVY REPO SECOND

`idlx` orders its adoption children **"smallest-first so the triage pattern is set on cheap
surfaces before the expensive one"**: `git-jsonl` 4 → **`runtime` 11** → `livespec` 13 →
`beads-fabro` 17 → `overseer` 56.

**Measured, that ordering defeats its own stated purpose.** `runtime` sits second, and it is the
ONE repo where every offender is a coordinated multi-repo re-vendor. Ranking by *count* ranks it
cheap; ranking by *what a conversion costs* ranks it last of the five.

| repo | bill | vendored out | import-edge declared | coordination |
|---|---:|---|---|---|
| `dev-tooling` | 2 | none | 21 declared, 0 flagged | **local** |
| `git-jsonl` | 4 | none | none | **local** |
| `livespec` | 13 | none | none | **local** |
| `beads-fabro` | 17 | none (1 basename-only) | none | **local** |
| `runtime` | 13 | ⛔ **13 of 13** | 3 of 13 | ⛔ **2–4 repos per change** |

**Suggested reordering, if the stated purpose is to be served:** `dev-tooling` (2) →
`git-jsonl` (4) → `livespec` (13) → `beads-fabro` (17) → **`runtime` (13) LAST of the five**.
Same repos, same total, but the pattern gets set on genuinely local surfaces first.

#### The three functions carrying BOTH blast-radius channels

Only **3 of runtime's 13** are declared `cross_repo_public_api` — i.e. visible to the
`cross-repo-public-api-declared` row. **All three are ALSO vendored into three repos**, so they
carry both channels at once:

- `cross_repo/types.py::parse_cross_repo_manifest`
- `work_items/lifecycle.py::lane_of`
- `work_items/lifecycle.py::is_item_ready`

⛔ **The other 10 of 13 are vendored but NOT declared — invisible to the declaration graph.**
That quantifies the blind spot: the fleet's own cross-repo instrument sees **3 of 13** of
runtime's coordination exposure.

🔥 **And two of those three are `lane_of` and `is_item_ready` — the exact functions `idlx`
names as pure total classifiers where Result-typing would be WRONG.** They are simultaneously
the most expensive things to convert in the cheap five (4 copies + a declared import edge each)
and, by the ledger's own reading, things that **should not be converted at all**. That is a
strong argument for disposing of them via a `total_absence_returns` DECLARATION rather than a
conversion — and it is a decision worth taking BEFORE anyone opens `runtime`, not during.

⛔ **CORRECTION 2026-08-06 — THAT RECOMMENDATION IS STRUCTURALLY IMPOSSIBLE AND IS WITHDRAWN.**
I checked my own recommendation against the ratified text and it does not survive.

- **Measured signatures**: `lane_of -> Lane`, `is_item_ready -> bool`. Neither is `X | None`.
- **Ratified `SPECIFICATION/contracts.md:247`, bound 1 of FOUR**: `total_absence_returns`
  "reaches ONLY functions whose return annotation is of the form `X | None`", and an entry
  "naming a function of any other shape MUST be REJECTED with a hard failure naming that entry,
  neither silently ignored nor accepted, so the key is not a general-purpose escape hatch."

So declaring these two would not exempt them — it would **hard-fail the check**, naming my own
entry. The key is gated precisely against the use I proposed for it.

**Nor does any other declaration key reach them:**

| key | why it cannot take `lane_of` / `is_item_ready` |
|---|---|
| `total_absence_returns` | bound 1: `X \| None` only; these are `Lane` and `bool` — **hard reject** |
| `single_meaning_variants` | relieves functions returning a **declared union**; these return neither |
| `supervisor_entry_files` | they are not entry points — and it would buy four exemptions (above) |

⛔ **SO THERE IS NO SANCTIONED DECLARATION FOR A TOTAL, NON-`Optional` PUBLIC FUNCTION. The only
disposition the vocabulary offers is CONVERSION** — which is exactly what `idlx` says would be
WRONG for these two.

**And the check has already ruled against them on its own terms.** It computes
`functions_without_expected_failure_mode` and exempts that set without any declaration; these
two are flagged, so they are **not** in it. ⚠️ Read the implementation before over-reading that:
per `_no_expected_failure_mode.py` a function is disqualified by a local (a)/(b)/(c) condition
**or by an unresolvable callee, or by any disqualified first-party callee** — so exclusion can
reflect analysis conservatism rather than a genuine failure mode. It is not proof they fail.

✅ **What this leaves for the ruling — a genuine contradiction, not a cost question.** The
ledger says converting these is wrong; the enforcement vocabulary offers no way to say so; and
the check's own exemption did not fire. **Resolving that is a SEMANTIC decision someone must
take**, and it is exactly the kind of thing that surfaces mid-conversion and stalls a repo if
it is not taken first. Whether the right answer is a new bound, a spec amendment, or simply
"convert them anyway" is **not** this lane's call.

⚠️ Stated as a recommendation, not a ruling: whether they are genuinely total is a semantic
judgement this lane did not make. What is measured is that converting them is maximally
expensive and that the ledger already doubts they should be converted.

### 🔑 HOW MUCH OF THE BILL CAN A DECLARATION EVEN REACH? **57% CANNOT.**

The `lane_of` correction above is not a two-function curiosity. Every declaration key is gated
on the **RETURN-ANNOTATION SHAPE**, so eligibility is decidable by syntax alone. Measured over
all 125 at pass-3 heads:

| the only key that could reach it | fleet (125) | cheap five (49) |
|---|---:|---:|
| `supervisor_entry_files` (called under a `__main__` guard) | 17 | 10 |
| `total_absence_returns` (`X \| None` / `Optional[X]`) | 31 | 4 |
| `single_meaning_variants` (a union with no `None` limb) | 6 | 6 |
| ⛔ **NO KEY REACHES IT** | **71 (57%)** | **29 (59%)** |

Return-annotation shapes across the 125: **concrete 76, optional 31, union 6, unannotated 12.**

⛔ **CONVERSION IS THE ONLY SANCTIONED DISPOSITION FOR 71 OF 125.** No declaration, no config
change and no reason-string can retire them — the keys are gated against exactly that.

✅ **AND THIS NUMBER IS METHODOLOGICALLY SOLID WHERE THE BUCKET TABLE IS NOT.** It uses **return
annotation shape only** — no failure-mode inference, no absence evidence — so it is not exposed
to the weakness recorded in working rule 12. Quote this one more confidently than `pure-total`.

⚠️ **"Reachable" is NECESSARY, NOT SUFFICIENT — the 54 are a CEILING, not a plan.** Each key
carries further bounds: `total_absence_returns` needs a written reason per entry plus a
hard-failing staleness detector; `single_meaning_variants` subtracts any function calling a
side-effecting primitive directly; `supervisor_entry_files` grants FOUR exemptions at once and
this thread's own re-land constraint forbids buying carve-outs to make a check green. **The
real declarable set is smaller than 54 — possibly much smaller.**

**So the honest scoping statement for the ruling:** even in the maximally permissive world where
every syntactically-eligible function were declared — a world the spec's bounds and this thread's
anti-carve-out rule both forbid — **at least 57% of the bill is still code conversion.** The
"config gap" framing cannot shrink this program much, and it should not be presented as though
it might.

#### Per repo — the fleet number hides a 38%-to-100% spread

| repo | bill | entry | `X \| None` | union | ⛔ NO KEY | % unreachable |
|---|---:|---:|---:|---:|---:|---:|
| `livespec-dev-tooling` | 2 | 0 | 0 | 0 | **2** | **100%** |
| `livespec-orchestrator-git-jsonl` | 4 | 0 | 2 | 0 | **2** | 50% |
| `livespec-runtime` | 13 | 1 | 2 | 0 | **10** | **76%** |
| `livespec` | 13 | 2 | 0 | 6 | **5** | **38%** |
| `livespec-orchestrator-beads-fabro` | 17 | 7 | 0 | 0 | **10** | 58% |
| `livespec-overseer` | 76 | 7 | 27 | 0 | **42** | 55% |

**Three things this changes:**

- ⛔ **`runtime` is worst on BOTH axes and that settles the ordering question.** It is 76%
  unreachable-by-declaration (highest of the cheap five) AND 100% vendored. Two independent
  measures, same verdict: **do it last, not second.**
- ✅ **`overseer-bjrm` is meaningfully smaller than 76.** Its **27 `X | None`-shaped** functions
  are the fleet's largest declarable group (27 of the 31 fleet-wide), so up to **34 of its 76**
  are declaration-eligible and **42 are hard conversions**. Scoping that child at "76
  conversions" overstates it — though 27 written reasons is not nothing, and each must survive
  the hard-failing staleness detector.
- **`livespec` is the cheapest per unit of bill** at 38% unreachable, carrying all six of the
  fleet's union-shaped functions. If a repo is wanted to set the triage pattern on the widest
  variety of dispositions, it is the one with the most kinds of them.

⚠️ Same caveat as above, restated because a per-repo table invites planning directly off it:
**eligible is not grantable.** These are ceilings per repo, not budgets.

### What the distribution says about sequencing

- ⛔ **THE THREE ZERO-BILL REPOS ARE NOT THE SAME KIND OF FREE — measured 2026-08-06, and this
  corrects the bullet directly below.** "Arm the three free ones" treats them as one move. Two
  of them are one move; the third is a different change in a different place.

  | repo | wires the check? | `pure_trees` | what arming it actually costs |
  |---|---|---|---|
  | `livespec-driver-claude` | **YES** (justfile) | `not_applicable` | **nothing in the member** — armed by the re-land at its next pin bump |
  | `livespec-driver-codex` | **YES** | `not_applicable` | **nothing in the member** — same |
  | `livespec-console-beads-fabro` | ⛔ **NO — zero references in its entire tree** | **UNDECLARED** | **a member-side WIRING change; the re-land does not reach it at all** |

  Measured by `git grep` over each `origin/master`: `console` matches
  `public.api.result.typed` in **zero** files; `driver-claude` matches in its `justfile`.
  So `console` is **invisible to the pin lever** — the re-land arms every WIRED member, and
  `console` is not one. It cannot be armed by a dev-tooling change at all.

  ⚠️ **And today, wiring it without also declaring the key FAILS rather than no-ops.** Verified
  in the shipped gate (`checks/_role_key_gate.py::role_absence_exit_code`), which is a code read,
  not an inference from prose: `if key not in config.declared_keys: log.error(...); return 1`.
  Key OMISSION is a hard error by design — the union is about EMPTINESS, and absence is
  deliberately loud.

  ✅ **But that caveat expires with the re-land**, and saying so matters or it will be
  over-applied: once `crl2` removes the `pure_trees` consult, the undeclared key is no longer
  read by THIS check, so `console` would need wiring only. The wiring requirement is durable;
  the declaration requirement is an artifact of the pre-re-land state.

  **Net for sequencing: TWO repos are free-by-pin, not three.** `console` is a separate, small,
  member-side task that no dev-tooling change will accomplish — and its bill is 0 over a
  1-file universe either way.

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
- **`livespec-overseer` alone is 141 of 188 reported — 75% at PASS-1** (and **76 of 123
  distinct — 62% at pass-1**); **141 of 190 — 74%, and 76 of 125 — 61%, at PASS-3**. The entire
  rest of the fleet is **47 at pass-1 / 49 at pass-3** on both bases, since only `overseer`
  duplicates. The share barely moves; the totals do.
- So the strong shape is: arm the **TWO free-by-pin ones**, then the five cheap ones —
  dev-tooling 2, git-jsonl 4, runtime **11 at pass-1 / 13 at pass-2 / 13 at pass-3**,
  livespec 13, beads-fabro 17 = **47 → 49 → 49** — putting **SEVEN of nine repos under real
  enforcement for ~50 conversions rather than ~190**, and leaving `overseer` as a single-repo
  program scoped on its own merits instead of blocking the rest.

  ⛔ **SEVEN, not eight — and this is the second number the console finding moves.** The old
  text said EIGHT of nine, counting `console` among the repos the re-land reaches. It does not
  reach it: `console` is unwired, so the pin arms `driver-claude`, `driver-codex`,
  `dev-tooling`, `git-jsonl`, `runtime`, `livespec`, `beads-fabro` — **seven**. `console` is an
  eighth only after a member-side wiring change that no dev-tooling release performs. The
  conversion cost (~50) is unaffected, because `console`'s bill is 0 either way; what changes
  is how many repos the re-land actually arms.

  ⛔ **AND "cheap" IS WRONG FOR `runtime`.** All 13 of its offenders sit in files vendored
  into 2–4 other repos (measured above), so its share of the cheap five is coordinated
  multi-repo work, not local edits. If the point of going cheap-first is to set the triage
  pattern on easy surfaces, **`runtime` is the wrong repo to start with** — `dev-tooling` (2)
  and `git-jsonl` (4) carry no vendoring at all.

  ⛔ **This bullet used to read "arm the three free ones" and that was wrong** — see the
  free-by-pin correction above. `console` is the third zero-bill repo but it is **not** armed
  by the pin; it is a separate member-side wiring task, and it is NOT part of the "eight of
  nine" that the re-land reaches. Counting it as a third free arm is what made one move look
  like three.

  ⚠️ The cheap-five total MOVED between passes (47 → 49, then flat at pass-3). Quote it with
  its pass and its heads, never bare — that is working rule 3 applied to this thread's own
  output.
- ⛔ **A PREREQUISITE SITS OUTSIDE THIS DISTRIBUTION AND OUTRANKS IT: `zi29`.** `idlx` names it
  a prerequisite, and it is not a cost question — on a zero-`.py` PR the check job reports
  SUCCESS while every real step skips, so a REQUIRED context certifies nothing. That is the
  mechanism by which five masters sat red while PRs kept merging. **Arming ANY repo ahead of
  `zi29` means the next breakage hides exactly the same way**, including the three
  zero-remediation repos this section argues to arm first — those are free on REMEDIATION cost,
  which is not the same as safe to arm. Cheapness does not clear the prerequisite.

### 🔥 THE BILL GROWS WHILE UNENFORCED — now THREE independent observations

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

### 🔥🔥 A THIRD OBSERVATION, AND IT DWARFS THE OTHER TWO — `overseer` +60 raw in <3 days

The two `+2` observations above are not the scale of this effect. Replaying `overseer`'s own
master at four heads (the same replay that settled the `+20` question, above):

| head | date | universe | scanned | raw | distinct non-test |
|---|---|---:|---:|---:|---:|
| `b3ae0dd` | 2026-08-03T18:12 | 174 | 82 | **81** | **35** |
| `baa60f8` | 2026-08-04T03:38 | 214 | 122 | 115 | 52 |
| `e1d257c` | 2026-08-04T22:48 | 232 | 140 | 137 | 63 |
| `1d191b1` | 2026-08-06 | 244 | 148 | **141** | **65** |

**Raw +60 (81 → 141, +74%) and distinct non-test +30 (35 → 65, +86%) in under three days**, on
**141 commits** in that window. Monotone at every step; **nothing was ever removed**. The
scanned universe itself grew 82 → 148, so this is genuinely new first-party code arriving
un-Result-typed, not a detector artifact.

⛔ **THIS LANDS ON THE MOST EXPENSIVE ADOPTION CHILD.** `overseer-bjrm` is scoped in the ledger
at 56. That number was accurate the day it was written and is **65 on its own basis** two days
later. A remediation program scoped against any frozen `overseer` figure is chasing a target
moving at roughly the rate the team writes code — which is the argument for arming EARLY (an
armed repo freezes its criterion and becomes a regression guard) rather than for measuring
harder.

⚠️ **Still do not read a RATE off this.** It is one repo in one unusually high-churn window
(the foreman work). What it establishes is that the effect is **not small** — an order of
magnitude beyond the `+2`s — in exactly the repo where the bill already concentrates.

⛔ **AND IT HAS ALREADY PLATEAUED — recorded because it undercuts the paragraph above.** A
PASS-3 over all nine at current heads (below) finds `overseer` **unchanged at 141 / 76** even
though its head moved `1d191b1` → `b42d7db`. So the `+74%` is a BURST, not a trend, and anyone
quoting it as a run-rate — including a later revision of this file — would be over-claiming
from the same three-day window it was measured in.

### PASS-3 — all nine at current heads, 2026-08-06 (harness validated, controls first)

| repo | sha | universe | scanned | reported | distinct | vs pass-1 |
|---|---|---:|---:|---:|---:|---|
| `livespec-driver-claude` | `dab39c0` | 9 | 7 | **0** | 0 | 0 |
| `livespec-driver-codex` | `61be068` | 7 | 3 | **0** | 0 | 0 |
| `livespec-console-beads-fabro` | `706050b` | 1 | 1 | **0** | 0 | 0 |
| `livespec-dev-tooling` | `c8fadd4` | 186 | 96 | 2 | 2 | 0 |
| `livespec-orchestrator-git-jsonl` | `42bffbd` | 49 | 37 | 4 | 4 | 0 |
| `livespec-runtime` | `12dc3e0` | 37 | 32 | **13** | 13 | **+2** |
| `livespec` | `8855018c` | 151 | 108 | 13 | 13 | 0 |
| `livespec-orchestrator-beads-fabro` | `6ae82dc3` | 186 | 48 | 17 | 17 | 0 |
| `livespec-overseer` | `b42d7db` | 244 | 148 | 141 | **76** | 0 |
| **TOTAL** | | | | **190** | **125** | **+2** |

**What pass-3 adds beyond a refresh:**

- **It confirms pass-2's 190 independently, at DIFFERENT heads.** Two measurements, different
  SHAs, same total — the 190 is not a one-off reading.
- **It supplies the DISTINCT figure pass-2 never had: 125** (pass-1 was 123; the `+2` is
  runtime's). Use 125 with these heads, never the bare 123.
- **The `+2` is still runtime's and only runtime's**; every other repo is flat since pass-1.
- **The three zero-bill repos are STILL zero** — that property has now survived three passes.
- **The cheap five is 49 at these heads** (2 + 4 + 13 + 13 + 17), matching the `47 → 49`
  recorded from pass-2. **`overseer` is 141 of 190 reported (74%) and 76 of 125 distinct (61%).**
- **`overseer` is the ONLY repo with a duplicate mirror or test-file hits** — 11 test-file hits
  and 65 duplicate pairs, every other member 0 and 0. Its `reported ≠ distinct` is unique in the
  fleet, which is why it is the only row where the two bases can disagree at all.
- **The SECOND failure path was re-checked at these heads too, not assumed to have held.**
  `_report_bad_declarations` runs BEHIND the gate, so it is unverified in every unarmed repo.
  Re-measured over all nine: `would_fail_on_declarations` is **False everywhere**, and the
  declaration counts reproduce the earlier record exactly — `dev-tooling` **21**
  (14 `cross_repo_public_api` + 4 `total_absence_returns` + 3 `single_meaning_variants`) and
  `runtime` **11**, with **0 stale and 0 rejected** in both. The other seven declare **nothing**,
  so their pass on this path is **VACUOUS** — stated because "clean on both paths" reads much
  stronger than "has nothing to be wrong about". **Arming the three zero-bill repos is still
  free on BOTH paths at current heads.**

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
9. **`merged: true` does not mean YOUR work merged.** Auto-merge fires as soon as checks go
   green on **whatever the branch held at that moment** — it does not wait for you to finish
   pushing. #1327 merged its first commit while two further commits were still being pushed to
   the same branch, stranding them on a branch whose PR was already closed. It was caught only
   because the merged head sha did not match the last-pushed head. **Either arm auto-merge
   LAST, or open one PR per unit of work — and always compare the merged sha against the sha
   you pushed.** Same family as the rest of this list: a status field that is true while
   meaning something narrower than the reader assumes.
10. **When a guard denies you, READ THE GUARD — do not iterate on the incantation.** The
    fleet's `github_rate_limit_guard.py` (in the `livespec-driver-claude` plugin) denied four
    legitimate one-shot commands in this session. Reading it took one minute and found three
    defects: its loop detector matches the bare English words `for` / `while` / `until` /
    `select` / `sleep` **anywhere in the command string**, so a PR-create whose BODY PROSE
    contains "for" is denied; its read-detector matches the `pr` CLI verb, so PR-**create** and
    PR-**merge** are classified as READS; and its denial text prescribes `gh api --cache
    <duration>` while the deny function **never consults `--cache`**, so the prescribed remedy
    cannot clear the check. It denied a plain file-append containing no network call, purely
    because the text being appended described the bug. ⚠️ **Not filed here — the hook belongs
    to the `livespec-driver-claude` lane.** Recorded because the first two denials were routed
    around with `--body-file` WITHOUT understanding the cause, and a guard that trains
    workarounds instead of teaching its rule will keep collecting them.
11. **A COUNT is not a COST.** The blast-radius table measured in-repo callers correctly and
    was then read as "these are small local edits". It was not: 13 of those ≤2-caller functions
    are vendored into 2–4 repos, so each is a coordinated multi-repo change. The number was
    right and the inference from it was wrong. **Before treating any count as an effort
    estimate, ask what the count is blind to** — here, every consumption channel that is not a
    call.
12. **ABSENCE evidence is far weaker than PRESENCE evidence, and it fails SILENTLY.** A
    classifier that files things by what it CANNOT find will confidently mis-file anything
    whose evidence lives one hop away. `parse_cross_repo_manifest` was classified "no failure
    mode" while its own docstring said it raises — the `raise` was two calls down. A
    presence-keyed bucket (`raises`, `optional-return`) can only be a LOWER bound and gets
    safer as evidence improves; an absence-keyed bucket (`pure-total`) can only shrink and is
    where the wrong answers hide. **Spend scepticism on the absence bucket, and sample it by
    reading source before quoting it.**
