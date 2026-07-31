# `qndn` — the 75, triaged per function

**Item:** `livespec-dev-tooling-qndn` (P0) · **Epic:** `livespec-dev-tooling-8o8e` ·
**Thread:** `plan/rop-railway-enforcement/`

This file discharges `qndn`'s reading half: **every one of the 75 has a disposition, and
every disposition names the evidence it rests on.** It does NOT drop the `_`-prefixed FILE
skip and does NOT arm anything — that is the remediation half, sequenced after this.

> **⛔ READ THIS FIRST, because the count moves and the reason matters.** Three of the six
> disposition classes are not conversions, and one of them says the CHECK is wrong rather
> than the code. That is not the count dissolving on inspection: **70 of 75 stand as real
> work**, and each of the 5 exceptions was established by naming the exact call that
> convicted it, not by an argument that the number was inconvenient.

---

## 1. THE MEASUREMENT, RE-DERIVED — never inherited

Run on master **`d6f1796`** with the SHIPPED analyses over the SHIPPED
`resolve_check_universe()`, simulating arming (scan universe = the git-derived first-party
set) with the `_`-prefixed-FILE skip as the only variable. Master then advanced to
`fef174e`; `git diff --stat d6f1796..fef174e -- livespec_dev_tooling/` is **EMPTY** (two
`docs(plan):` commits), so the figures below hold unchanged on `fef174e`.

| | |
|---|---|
| universe files | **155** |
| `_`-prefixed FILES (skipped today) | **65** — 42% |
| actually scanned today | **90** |
| v178 public | **182** |
| v179 member-1 exempt (computed) | **390** |
| v179 member-2 exempt (declared) | **1** |
| member sets DISJOINT | **yes** |
| `supervisor_entry_files` | **33** |
| stale declarations / rejected declarations | **0** / **0** |
| **offenders CARRYING the `_`-FILE skip** | **0** |
| **offenders DROPPING it** | **75** |

Reproduces `qndn`'s own figures exactly. The entire delta is
`if py_file.name.startswith("_"): continue` at `public_api_result_typed.py:310`.

## 2. HOW EACH FUNCTION WAS CONVICTED — measured, not simulated

`qndn` binds this: *"THE 35 TRANSITIVE ARE THE DANGEROUS CLASS AND MUST NOT BE HAND-READ …
run the analysis per function; never simulate it."* So conviction was attributed by
re-running the shipped `calls_of` per call node, with nested calls stripped so no call is
blamed for a callee's I/O:

| conviction basis | n |
|---|---|
| **LOCAL** — own body raises, tries, or reaches I/O | **40** |
| **TRANSITIVE** (clause d) — clean body, a callee reaches I/O | **24** |
| **CLAUSE (e) ONLY** — clean body, clean callees, `X \| None` | **11** |

**⚠️ `qndn`'s skeleton said LOCAL 40 / TRANSITIVE 35. That 35 is 24 + 11, and splitting it
matters.** The 11 clause-(e)-only functions have NO I/O anywhere in their reachable graph —
they are convicted purely by an `X | None` signature, which is exactly the population
member 2's `total_absence_returns` key exists to sort. Folding them into "transitive" hides
that four of them are declarations rather than code.

## 3. THE THREE STANDING METHOD CONSTRAINTS, ANSWERED FOR THE WHOLE SET

1. **Real failure track, or a legitimate absence?** — asked per function; it is what
   separates the `CONVERT` column from the `DECLARE` column below.
2. **CAN this module import `returns` in EVERY environment it executes in?** — every one of
   the 75 is a helper module INSIDE the installed package, beside the vendored
   `_vendor/returns`, so the house `_VENDOR_DIR` preamble resolves. **But the 2026-07-30
   fan-out outage was caused by a BARE import in a `python -m` entry point, and several of
   these helpers are imported BY entry points** (`cross_repo/ci_yaml_canonical_reconcile.py`
   consumes `_ci_matrix_parse`). Every converted module gets the preamble; no bare
   `from returns… import` anywhere.
3. **Does any SIBLING import this symbol?** — **RUN WITH THE SHIPPED `5cai` ORACLE against
   the LIVE fleet, not grepped** (supervisor brief 52 constraint 3; a bare-name grep is
   measured wrong on this thread). Same denominator the pre-registration run published:

   **⚠️ THE TABLE BELOW IS THE *PRE-FIX* RUN AND IS KEPT ONLY BECAUSE ITS ANSWER WAS WRONG.**
   The current answer is the one further down (63 edges, 2 of the 75). It is retained rather
   than overwritten because "the oracle said 1" is the evidence for why `8o8e.3` exists.

   | PRE-FIX (superseded) | |
   |---|---|
   | roster members | 9 |
   | members **READ** | **9** |
   | members unavailable | **0** |
   | files unparsed | **0** |
   | cross-member edges examined | ~~58~~ |
   | **of the 75, edges found** | ~~**1**~~ |

   **`fleet/_context.py::resolve_owner` ← `livespec-orchestrator-beads-fabro`'s
   `.claude-plugin/hooks/codex_yolo_gate.py`.** Uniquely resolved. That is the `dx8l`
   consumer, in a HOOK, which is the worst blast-radius shape this fleet has. **Consumer
   wiring lands FIRST, dual-shape, in beads-fabro, before the conversion lands here.**

   **🔴🔴 AND THE ORACLE CONTRADICTED THIS REPO'S OWN `pyproject.toml`, SO I CHECKED WHICH
   ONE WAS WRONG. IT WAS THE ORACLE.** The comment claims
   `testing/_cli_e2e_discovery.py::discover_fixtures` is *"reached by four siblings as
   `cli_e2e.discover_fixtures` through a re-export"*. The oracle emits **ZERO edges** for it.
   Resolved by reading the nine member tarballs the oracle had already fetched: **all four
   siblings genuinely reference `discover_fixtures`** — `livespec-driver-claude`,
   `livespec-driver-codex`, `livespec-orchestrator-beads-fabro` and
   `livespec-orchestrator-git-jsonl`, each in `tests/e2e-cli/`, each via
   `from livespec_dev_tooling.testing import cli_e2e` then `cli_e2e.discover_fixtures(...)`.
   **The record is TRUE and the row is BLIND.**

   **THE MECHANISM, at `_public_api_graph.py:263` — `if name not in functions[defining]:
   continue`.** `functions[cli_e2e.py]` holds the functions **DEFINED** in `cli_e2e.py`;
   `discover_fixtures` is **IMPORTED** there and re-exported through `__all__`. So the
   attribute reach resolves to `cli_e2e.py` correctly and is then **SILENTLY DROPPED** — and
   it is never re-resolved through the re-export to `_cli_e2e_discovery.py`, so **no edge is
   emitted to EITHER file.** The same file's `test_workflow_full_round_trip`, which IS defined
   in `cli_e2e.py`, is seen from all four — which is what proves attribute reaches work and
   isolates the re-export as the cause.

   **✅ FIXED, AND THE FIX IS MEASURED — `8o8e.3`, `_public_api_graph._through_reexports`.**
   A reach landing on a facade is now re-resolved to the module that DEFINES the name,
   bounded by a visited set so a re-export cycle terminates. Re-run against the live fleet
   over the SAME denominator (9 roster / **9 READ** / 0 unavailable / 0 unparsed):
   **cross-member edges 58 → 63**, and the third axis over the 75 goes **1 → 2**:

   | of the 75, consumed by a sibling | consumers |
   |---|---|
   | `fleet/_context.py::resolve_owner` | beads-fabro's `codex_yolo_gate.py` hook |
   | `testing/_cli_e2e_discovery.py::discover_fixtures` | **all four** — both Drivers, both orchestrators |

   **⛔⛔ AND TWO CLAIMS ARE RETRACTED — BOTH MINE, BOTH BY MEASUREMENT RATHER THAN ARGUMENT.**

   **RETRACTION 1: "it blocks `5cai`'s own completeness claim" — FALSE.** Measured: the row's
   `_undeclared` returns **`()` for every member, before AND after the fix — 0 findings
   fleet-wide either way.** The reason is CLAUSE 3, which exempts a name the repo-local check
   already scopes. And the exemption is not a coincidence here, it is **structural**: to be
   re-exported at all, a name must be imported across a module boundary INSIDE its own repo,
   which is v178 clause 1 — so **every re-exported name is repo-locally public by
   construction**, and clause 3 exempts it in every case, not just this one. `5cai` reporting
   PASS on this repo was CORRECT, not blind.

   **RETRACTION 2: "it retro-scopes the `wdn7`/`nkkv` twenty" — FALSE, and this one was
   PREDICTED then MEASURED rather than merely withdrawn.** The prediction followed from
   Retraction 1's structural argument; the re-run confirms it. **The twenty does not rise.
   `wdn7` and `nkkv` stand as measured and as closed.**

   **▶️ SO WHAT DOES THE BLIND SPOT ACTUALLY COST? THE THIRD AXIS — and it nearly cost it in
   this very session.** Supervisor brief 52 mandates answering *"does any sibling import this
   symbol?"* with THIS ORACLE rather than a grep. Pre-fix it answered **1 of 75** and silently
   omitted `discover_fixtures`'s FOUR sibling consumers. **Converting `discover_fixtures` on
   that answer would have shipped a signature change to four repos with no dual-shape wiring —
   `dx8l` exactly, the failure this row was built to prevent.** Only this repo's own
   `pyproject.toml` comment caught it. **That is the gate: not under-declaration, but the
   dx8l precondition on the CONVERT class.** It is on the arming critical path for that reason
   and no other.

   **AND THE DROP WAS A BARE `continue` WITH NO RECORD** — unlike `unparsed`, which this same
   graph deliberately carries in-band so an unread file cannot be mistaken for a clean one. A
   resolved-then-discarded reach had no such carrier, which is why the blind spot was
   invisible for as long as it was.

   **▶️ AND DROPPING THE SKIP CREATES A DECLARATION OBLIGATION THIS FILE MUST NOT LET SINK.**
   `resolve_owner` and `discover_fixtures` are deliberately absent from
   `cross_repo_public_api` today, on the stated ground that *"declaring them would assert a
   scope this check does not actually apply"*. **The moment the skip drops, the scope DOES
   apply and that ground expires.** Both entries become owed in the same change. A third
   omission (`config.py::iter_first_party_py_files`) stays owed to `995m`, a different hole.

   **⛔ AND EVERY NEW DECLARATION MUST BE RUN THROUGH ITS OWN DETECTOR AS IT IS AUTHORED**
   (supervisor brief 52 constraint 1), because `ueni` makes the gate that would catch a bad
   one UNREACHABLE until the arming commit itself: `main()` calls
   `role_absence_exit_code(role=config.pure_trees)` FIRST, and this repo declares
   `pure_trees = { not_applicable = … }`, so `stale_declarations` and `rejected_declarations`
   are both structurally unreached here. **The 0 stale / 0 rejected in §1 measures the CURRENT
   five declarations, not any added.** The DECLARE class below is exactly where new
   `total_absence_returns` entries get authored, and **member 2 bound 1 REJECTS rather than
   skips** — so its gate becomes reachable for the first time in the one commit that must not
   go red, since lefthook then blocks the fix. Import `rejected_declarations` /
   `stale_declarations` and run them per new entry, the same way the count was measured.

## 4. THE DISPOSITIONS

| class | n | what it means |
|---|---|---|
| **CHECK-FIX** | ~~4~~ **3** | the machinery convicts conformant code — fix the check, not the function |
| **CONVERT** | ~~38~~ **40** | an inhabited failure track modelled off-railway |
| **DECLARE** | ~~4~~ **2** | a legitimate ABSENCE — v179 member 2 `total_absence_returns` |
| **COUPLED** | **1** | becomes a DECLARE once the function it reads converts; not before |
| **TYPE-SLICE** | **23** | the fleet `RowOutcome` family — ONE type-level decision, not 23 conversions |
| **OPEN** | ~~5~~ **6** | a genuine design choice this triage surfaces rather than settles |

**3 + 40 + 2 + 1 + 23 + 6 = 75, exactly.**

### ⛔⛔ 4d-BIS — DECLARE WAS 4 AND IS **2**, AND THE CALLERS' READING FOUND AN INCONSISTENCY INSIDE MY OWN TABLE

**Why DECLARE got a reading the other classes did not.** CONVERT, CHECK-FIX and TYPE-SLICE
are recoverable — get one wrong and you do unnecessary work, or a check stays wrong and the
next measurement catches it. **DECLARE is not symmetric with those.** A wrong entry writes a
ratified exemption into `pyproject.toml` that removes a function from the rule's scope
permanently, in the one direction this epic has spent its life removing: a value that means
"stop looking here".

**AND THE MECHANISM CANNOT CATCH IT.** `_declared_absence_returns._split` produces exactly two
rejections — UNRESOLVED and NOT_ABSENCE_SHAPED. **Neither asks whether the `None` is really an
absence.** The reason string is parsed for PRESENCE, never for truth. So a clean
`rejected_declarations` run is the kind of green this thread exists to distrust: it proves the
annotation is `X | None` and the function exists, and nothing about the judgement. It was run
per entry anyway (0 rejected, 0 stale) because it catches a mis-typed or stale entry cheaply —
**but it is not cited as evidence the dispositions are right.**

**THE DISCRIMINATOR, and it is the one that decided all four: HOW MANY DISTINCT CONDITIONS
COLLAPSE ONTO THE ONE `None`.** `tag_version_component`, the ratified precedent, collapses
exactly one. A `None` covering an absent key AND a malformed value carries a failure alongside
the absence, and no caller can tell them apart.

| candidate | conditions on `None` | callers' reading | verdict |
|---|---|---|---|
| `_role_key_gate::role_absence_exit_code` | **1** — the role is not declared-absent | all five: `if gate_exit is not None: return gate_exit`. Pure control flow. The failure/violation channel is the INT (1 undeclared, 0 declared-absent), never the `None` | **DECLARE** |
| `_no_except_outside_io_markers::sanctioned_marker_flavor` | **1** — the span holds no marker comment; no error path (`_clause_colon_line` floors via `min(..., default=…)`) | caller appends an offense — but about the SCANNED SOURCE, not about its own inability | **DECLARE** |
| `_connection::impl_plugin_name` | **4** — `implementation` absent OR not an object; `plugin` absent OR not a string | `_rows_baseline` turns it into `_UNREACHABLE` → a **RowFinding**; its docstring says "which link BROKE". `_rows_local_jsonc` → a warning **RowFinding** | **CONVERT** |
| `_connection::named_plugin_connection` | **6+** — inherits all four, plus block absent/not-an-object, plus connection absent/not-an-object | same two row callers, both reporting | **CONVERT** |

**🔴 AND THE READING CAUGHT AN INCONSISTENCY IN THIS FILE, which is the triage working on
itself.** `connection_block` was already disposed **CONVERT** here on exactly this ground —
"THREE meanings in one sentinel". `named_plugin_connection` has the same shape and this table
gave it **DECLARE**. Two functions in the same module, one rule, opposite verdicts. The
caller reading is what exposed it.

**⛔ AND THE LITERAL FORM OF THE CALLER TEST WOULD GET `sanctioned_marker_flavor` BACKWARDS.**
"If any caller reports a violation on the `None`, it is a failure track" convicts it — its
caller does append an offense. But that offense is the CHECK'S OWN VERDICT about the code being
scanned ("this broad handler carries no marker"), not a report that the function could not
answer. Contrast `extract_check_recipe_body`, which earned CONVERT here: its callers emit
`check_recipe_not_found` and say they **CANNOT VERIFY** — a caller reporting its own inability.
**The test is whose failure is being reported, not whether a finding appears.** Converting
`sanctioned_marker_flavor` would put the MAJORITY answer on the failure track.

### ⛔⛔ 4a-BIS — CHECK-FIX WAS 4 AND IS **3**. THE CORRECTION IS MINE, IT WAS CAUGHT BY THE FIX'S OWN MEASUREMENT, AND THE METHOD FLAW BEHIND IT MATTERS MORE THAN THE COUNT.

The CHECK-FIX changes landed and the repo went **75 → 72**, not 75 → 71. Three dropped —
`memoized_snapshot`, `comment_lines`, `statement_colons`. **`extract_created_worktree_paths`
DID NOT**, and it never would have.

**WHY: IT WAS DOUBLY CONVICTED ALL ALONG.** Verified on unmodified master — `local_io=True`
(the `Path(raw)` false positive) **AND** both its callees carry a `try`
(`_transcript_line_segments` catches `json.JSONDecodeError`,
`_created_worktree_targets_from_segment` catches `ValueError` from `shlex.split`). Removing
the local basis leaves clause (d) standing.

**THE METHOD FLAW, AND IT IS THIS THREAD'S SIGNATURE DEFECT IN MY OWN TOOL.** The triage
classifier assigns **ONE** conviction basis per function — it tests LOCAL first and stops —
and §2's table reports that one basis as though it were exhaustive. **It is not.** A function
carrying both a local and a transitive disqualifier appears in §2 as purely LOCAL, and any
disposition reasoning "remove the local basis and it is acquitted" is unsound for it.

**BOUNDED, and the bound was measured rather than asserted.** It changes a disposition only
where the argument depended on removing the local basis — the CHECK-FIX class, 4 functions,
of which 3 did drop. **No CONVERT disposition moves**: those functions are convicted either
way and the conversion is owed regardless. **⚠️ But §2's LOCAL/TRANSITIVE/CLAUSE-(e) split is
a partition of FIRST-FOUND basis, not of all bases — do not read it as exhaustive, and do not
re-derive anything from it that depends on a function having only one.**

`extract_created_worktree_paths` moves to **OPEN**, alongside `is_docs_only_change` and
`scenario_tier_violations`, and it is the same question: two callees deliberately collapse a
parse failure onto a safe value (`[line]`, `[]`). One ruling covers all three.

### 4a. ⛔ THE CHECK-FIX CLASS IS FIDELITY, NOT A DISCOUNT — and it is the MIRROR of the skip

**Say it in these words, because the instinct will be to read it as the count being talked
down.** The `_`-prefixed-FILE skip is non-conformance with the ratified rule in the
**RELAXING** direction: v178 clause 0 disqualifies a `_`-prefixed **NAME**, never a FILE.
These four are non-conformance in the **TIGHTENING** direction, by the same standard:

- **`memoized_snapshot` IS ALREADY ON THE RAILWAY.** It returns `SnapshotResult`, and
  `_snapshot.py:148` reads `SnapshotResult = IOResult[TreeSnapshot, SnapshotUnavailable]`.
  `_is_railway_compliant` compares the annotation's TERMINAL NAME against
  `{"Result", "IOResult"}`, and **a type alias defeats that match.** Arming without this fix
  reports a violation against code that already complies.
- **`io.StringIO` is an IN-MEMORY buffer**, and it convicts `comment_lines` and
  `statement_colons` because the module is *named* `io` and `io` is in `_IO_MODULES`.
- **`Path(raw)` is a value CONSTRUCTION**, and it convicts `extract_created_worktree_paths`
  because `pathlib` is in `_IO_MODULES` at MODULE granularity — the set cannot separate
  `Path(...)` from `Path.read_text()`.

**This is PR #748's lesson in the opposite direction.** Wiring the spec's own exemptions IN
was fidelity; so is refusing to convict what the spec's own clause (c) does not describe.
**A check that flags conformant code burns the rollout's credibility on false positives** —
the supervisor charter names that risk by name — and this one would do it in the arming
commit itself.

**⛔ AND THE LIMIT, so this class cannot grow by argument.** ~~It is 4 of 75.~~ **It is 3 —
see 4a-bis, which is a correction to this section made by measuring the fix rather than by
re-reading it.** Each names the exact call, isolated by re-running the shipped analysis with
nested calls stripped. A further member requires the same evidence, not a resemblance —
**and it must also be checked for a SECOND conviction basis**, which is precisely what the
fourth member turned out to have.

### 4b. ⚠️ `preflight_credential` IS *NOT* IN THAT CLASS, and the distinction is load-bearing

It is convicted solely by `sleep(...)` — an INJECTED PARAMETER
(`sleep: Sleeper = time.sleep`). That looks like the same false positive and **is not**: a
bare-name call is *documented* doubt in `_no_expected_failure_mode`, and doubt disqualifies
**by design**, in the conservative direction. Filing it as a machinery defect would convert
a deliberate conservatism into a bug report. It is `OPEN` instead, and the question it poses
is narrow and answerable: *is a bare call to a PARAMETER resolvable (an injected seam, which
that module's own docstring says is not a boundary) rather than doubtful?*

### 4c. THE `RowOutcome` RULING — 23 functions, ONE decision, and a live defect inside it

`RowOutcome = RowPass | RowFinding | RowSkip` (`fleet/_context.py:111`) is a **hand-rolled
sum in which `RowSkip` IS the failure track** — its own docstring reads *"The row could not
be definitively evaluated"*. That is `filter_siblings() -> FilterOutcome | FilterError`, the
shape the step-6 triage ruled CONVERT, at 23 instances.

**IT IS NOT 23 INDEPENDENT CONVERSIONS, and treating it as such is the trap.** Both engines
walk row tables typed by one Protocol (`_contract_model.RowFn`,
`_contract_local_rows`), and the ~40 rows member 1 EXEMPTS return the same type. Converting
only the convicted 23 leaves one Protocol with two return shapes.

**🔴 AND BUILDING THIS TRIAGE FOUND A LIVE DEFECT IN THAT TYPE — `RowSkip` CARRIES TWO
MEANINGS AND THE TWO LANES READ IT OPPOSITE WAYS.**

| lane | reads `RowSkip` as | consequence |
|---|---|---|
| CENTRAL (`_lanes.py:173`) | *"not evaluable (can't-read is not absent)"* | feeds **`blind_rows`**, which REDS master |
| LOCAL (`local_reconcile.py:94`) | *"row not applicable"* | benign `log.info`, never counted |

And the central lane already has a SEPARATE, correct spelling for inapplicability —
`RowPass(note=_EXCLUDED_NOTE_PREFIX + reason)` (`_lanes.py:188`). Yet
`_rows_local_beads.py` returns `RowSkip(reason="no .beads tenant directory (not a
beads-backed repo)")` for exactly that, and `_rows_beads.py`'s central row returns
`RowSkip(reason="…carries no dolt.* connection keys")` — **not beads-backed, an
inapplicability, on the lane where a skip counts toward blind.** Its docstring conflates
both in one sentence: *"(not beads-backed / can't-read is not absent)"*.

**This is `pure_trees = []` in the fleet outcome type**: one value meaning both "does not
apply" and "could not be read", with the reading decided by which engine happens to receive
it. **And `blind_rows: 0` is the number this epic just declared load-bearing for `5cai`'s
health.** A conversion to `Result[RowVerdict, RowUnevaluable]` fixes the conflation by
construction — which is the strongest argument for taking the type slice rather than
deferring it.

**⛔ THE ONE RESOLUTION THAT IS FORBIDDEN:** asserting in config or in a docstring that
`RowOutcome` "is" the sanctioned railway spelling for this subsystem. Nothing ratified says
so. If that is the right answer it is a `livespec` propose-change, argued in the open —
the epic's own founding rule, *"if an exemption is right, ratify it; do not let it persist
as an unenforced clause."*

**⛔⛔ AND THE CONFLATION FIX IS *DECOUPLED* FROM THE 23 — an earlier revision of this file
coupled them and that was WRONG (supervisor brief 53, and the correction is accepted).**
Writing "the conflation is the strongest argument for taking the type slice" attached a LIVE
defect in a currently-gating row to the largest, least-settled block in the triage — the one
§7 says needs its decision taken before any of it is written. **That is `qndn`'s own shape
exactly: a true finding, correctly written, tied to a gate that may not fire for a long time,
outliving the epic built around it.** The two are now separate items with separate gates.

**AND THE CONFLATION IS LIVE IN REGISTERED CODE, which is stronger than "latent".**
`assert_tenant_connection_consistency` is registered in `OBLIGATION_ROWS` as
`beads-tenant-connection-consistency` and returns `RowSkip` at `_rows_beads.py:68` ("carries
no dolt.* connection keys") and `:73` ("carries no impl-plugin connection block") — **both
INAPPLICABILITIES, on the CENTRAL lane, where a skip counts toward blind.** `_lanes.py`
states the consequence and leaves no way out: *"There is no lever, env var, exemption list,
or opt-out: a lane that owns a row it could not read exits non-zero, always."* **So if the
beads-backed population among applicable members ever reaches zero, that row goes blind and
fails every central run fleet-wide for a condition that is not a failure at all.**
`blind_rows: 0` today is contingent on at least one applicable member still evaluating.

**THE TARGETED FIX NEEDS NO NEW TYPE and is already in the lane:**
`RowPass(note=_EXCLUDED_NOTE_PREFIX + reason)`, which `_lanes.py:188` already renders as
"fleet obligation excluded with reason". Three call sites — `_rows_beads.py:68`, `:73`, and
`_rows_local_beads.py`'s `_SKIP_NO_BEADS`, benign on the local lane today and the same wrong
spelling, which stops being benign the moment that row gains a central twin.

### 4d. THE DUPLICATION FINDING — the justfile `check:` parser exists FOUR times

Surfaced by triaging `extract_check_recipe_body`, which appears twice in the 75 because the
repo carries two copies of it:

| copy | where |
|---|---|
| 1 | `checks/_ci_matrix_parse.py::extract_check_recipe_body` |
| 2 | `checks/_tool_backed_surfaces.py::extract_check_recipe_body` |
| 3 | `checks/required_role_keys_declared.py::_extract_check_recipe_body` |
| 4 | `checks/aggregate_completeness.py::_extract_check_recipe_body` |

plus a fifth reimplementation documented in prose at `canonical_recipe_fidelity.py:233`.
`extract_targets_array_tokens` is duplicated the same way. **The copies keep agreement by
COPYING, and say so** — `_tool_backed_surfaces.py:41` reads *"mirrors
aggregate_completeness's parser so the two checks agree on what 'literal targets-array
membership' means"*. **A normative parsing rule in four places is what produced
`livespec-i04f`**, whose whole resolution was "state the set ONCE and cite it". Converting
two copies to `Result` and leaving four is worse than either converting all or deduplicating
first.

## 5. THE TABLE — all 75

Evidence columns are MEASURED. `convicted by` is the isolated disqualifying call for a LOCAL
conviction, the callee chain for a TRANSITIVE one, or `clause (e) only`.

### CHECK-FIX — 4

| # | file:line | function | returns | convicted by | why |
|---|---|---|---|---|---|
| 1 | `agent_hooks/_subagent_stop_guard_transcript.py:52` | `extract_created_worktree_paths` | `list[Path]` | `['Path']` | Convicted solely by `Path` CONSTRUCTION. `pathlib` is in `_IO_MODULES` at module granularity, so `Path(raw)` — a pure value construction — reads as a boundary. Function is string-in / list-of-Path-out with no I/O at all. |
| 2 | `checks/_no_except_outside_io_markers.py:92` | `comment_lines` | `dict[int, tuple[str, ...]]` | `['io.StringIO']` | Convicted solely by `io.StringIO` — an IN-MEMORY buffer, not a boundary. `io` is in `_IO_MODULES` by module NAME. Re-examine on the merits after the fix: `tokenize.generate_tokens` can raise `TokenError`, which is a different question. |
| 3 | `checks/_no_except_outside_io_markers.py:106` | `statement_colons` | `tuple[tuple[int, int], ...]` | `['io.StringIO']` | Same `io.StringIO` conviction as `comment_lines`; same re-examination owed. |
| 4 | `fleet/_snapshot.py:290` | `memoized_snapshot` | `SnapshotResult` | `['record']` | ALREADY on the railway: `SnapshotResult = IOResult[TreeSnapshot, SnapshotUnavailable]` (_snapshot.py:148). `_is_railway_compliant` matches the annotation's TERMINAL NAME, which a type ALIAS defeats. Not a violation; the check cannot see through an alias. |

### CONVERT — 38

| # | file:line | function | returns | convicted by | why |
|---|---|---|---|---|---|
| 1 | `checks/_ci_matrix_parse.py:153` | `load_canonical` | `tuple[str, ...]` | `['(cwd / canonical_from).resolve', '_placeholder.read_text']` | `(cwd / canonical_from).resolve().read_text()` and `json.loads` both raise, UNCAUGHT, on a missing or malformed override file. Genuine inhabited failure track. Note the existing comment: an empty tuple is already load-bearing as 'malformed override', so the conversion must NOT collapse a read failure onto it. |
| 2 | `checks/_ci_matrix_parse.py:175` | `extract_check_recipe_body` | `str \| None` | `clause (e) only` | `None` = no `check:` recipe. EVERY caller names it as a distinct FAILURE MODE (`check_recipe_not_found`) and returns violations — never an ordinary answer. |
| 3 | `checks/_ci_matrix_parse.py:188` | `extract_targets_array_tokens` | `list[str] \| None` | `clause (e) only` | LOSSY: `None` covers BOTH 'no `targets=(...)` array' and 'array never closed'. Callers report only the first, so an UNTERMINATED array is diagnosed as an absent one. The `discover` sentinel shape exactly (9sl0 conversion 3). |
| 4 | `checks/_primary_checkout_git_probes.py:31` | `is_inside_work_tree` | `bool` | `['subprocess.run']` | Unguarded `subprocess.run`: git absent raises. The bool cannot distinguish 'not a work tree' from 'git failed', and the docstring's 'the command always exits 0' is a PRECONDITION on the caller, not a guarantee. |
| 5 | `checks/_primary_checkout_git_probes.py:51` | `is_git_repo_at_all` | `bool` | `['subprocess.run']` | Unguarded `subprocess.run`. This is THE discriminator the check uses to tell 'not a repo' (skip) from 'bare-flag regression' (fail) — so collapsing a git-absent failure onto False routes a broken environment to SKIP. |
| 6 | `checks/_primary_checkout_git_probes.py:70` | `core_bare_is_true` | `bool` | `['subprocess.run']` | Unguarded `subprocess.run`; git-failed and key-unset both yield empty stdout → False. |
| 7 | `checks/_primary_checkout_git_probes.py:89` | `sandbox_exempt_is_true` | `bool` | `['subprocess.run']` | Same as `core_bare_is_true`, and this one gates an EXEMPTION — a git failure silently yields 'not exempt', which is the safe direction here but is still indistinguishable. |
| 8 | `checks/_primary_checkout_git_probes.py:113` | `git_common_dir` | `Path` | `['(cwd / candidate).resolve', 'Path', 'subprocess.run']` | `subprocess.run(..., check=True)` — raises `CalledProcessError` DELIBERATELY, and the docstring says so ('raises rather than silently returning a sentinel'). An inhabited, uncaught failure track stated in prose. The strongest convert candidate in this module. |
| 9 | `checks/_primary_checkout_git_probes.py:136` | `work_tree_root` | `Path` | `['Path', 'subprocess.run']` | Same `check=True` raise-by-design as `git_common_dir`. |
| 10 | `checks/_primary_checkout_worktree_pack.py:219` | `inspect_worktree_pack` | `list[tuple[str, str]]` | `['(pack_dir / name).is_file', 'script_path.is_file', 'script_path.read_text']` | `script_path.read_text` uncaught on a present-but-unreadable pack file. Every OTHER failure it models is already an explicit `(file, failure_mode)` tuple — so the ONE unmodelled failure is the read, and it is the odd one out in a function whose whole design is naming failure modes. |
| 11 | `checks/_red_green_replay_trailers.py:30` | `head_red_awaiting_green` | `bool` | `['subprocess.run']` | `subprocess.run` with NO `shutil.which` guard: git absent raises `FileNotFoundError`, uncaught. And a non-zero git exit yields empty stdout → reads as 'no Red trailers' → the commit ritual silently takes the wrong branch. A fail-WRONG, not fail-closed. |
| 12 | `checks/_red_green_replay_trailers.py:53` | `head_trailer_value` | `str` | `['subprocess.run']` | Same unguarded `subprocess.run`; docstring already concedes 'or empty if absent', conflating absent-trailer with git-failed. |
| 13 | `checks/_red_green_replay_trailers.py:64` | `current_head_sha` | `str` | `['subprocess.run']` | Same; 'or empty on failure' in its own docstring is the sentinel stated aloud. |
| 14 | `checks/_tool_backed_surfaces.py:53` | `extract_check_recipe_body` | `str \| None` | `clause (e) only` | Byte-equivalent DUPLICATE of `_ci_matrix_parse`'s. Same disposition; convert together or deduplicate first — see the duplication finding. |
| 15 | `checks/_tool_backed_surfaces.py:72` | `extract_targets_array_tokens` | `list[str] \| None` | `clause (e) only` | Duplicate of `_ci_matrix_parse`'s, same lossy `None`. |
| 16 | `checks/_tool_backed_surfaces.py:133` | `collect_ci_matrix_targets` | `set[str]` | `['path.read_text', 'workflows_dir.glob']` | `workflows_dir.glob` + `path.read_text`, uncaught. Genuine `IOResult`. |
| 17 | `cross_repo/_pin_directory_scan_formats.py:78` | `read_pin_text` | `str` | `['path.read_text']` | THE shared reader; raises `OSError` by design, caught one level up by the already-`IOResult` `pin_autodiscovery.discover`. Converting it is what lets the walkers convert without each re-deciding the diagnostic. Do this one FIRST — the other 8 depend on it. |
| 18 | `cross_repo/_pin_directory_scan_formats.py:135` | `walk_github_workflow_uses` | `list[dict[str, str]]` | `['workflows_dir.glob', 'workflows_dir.is_dir']` | `workflows_dir.is_dir` / `.glob` + `read_pin_text`; raises into `discover`'s single `OSError` arm. The railway already exists ONE LEVEL UP; this pushes it down to the seam. |
| 19 | `cross_repo/_pin_directory_scan_formats.py:175` | `walk_fabro_workflow_docker` | `list[dict[str, str]]` | `['workflows_dir.glob', 'workflows_dir.is_dir']` | Same shape as `walk_github_workflow_uses`. |
| 20 | `cross_repo/_pin_directory_scan_formats.py:230` | `walk_github_workflow_container_image` | `list[dict[str, str]]` | `['workflows_dir.glob', 'workflows_dir.is_dir']` | Same shape as `walk_github_workflow_uses`. |
| 21 | `cross_repo/_pin_directory_scan_formats.py:281` | `walk_codex_acp_docker_arg` | `list[dict[str, str]]` | `['dockerfile.is_file']` | Same shape; `dockerfile.is_file` + `read_pin_text`. |
| 22 | `cross_repo/_pin_single_file_formats.py:66` | `walk_livespec_jsonc` | `list[dict[str, str]]` | `['path.is_file']` | ⛔ READ `2j2l` FIRST. This walker emits the IN-BAND `pin_format='unrecognized'` SENTINEL record that `_rows_pin_currency._records_for` then silently DROPS, turning an unparseable pin file into a PASS. The conversion is the natural place to remove that fail-open — but it needs the §'Pin-currency severity policy' decision `2j2l`/`xhbp` are blocked on. |
| 23 | `cross_repo/_pin_single_file_formats.py:151` | `walk_pyproject_toml` | `list[dict[str, str]]` | `['path.is_file']` | `path.is_file` + `read_pin_text`. Same family as the other walkers. |
| 24 | `cross_repo/_pin_single_file_formats.py:202` | `walk_vendor_jsonc` | `list[dict[str, str]]` | `['path.is_file']` | Same family; also carries an `unrecognized` sentinel path — see `2j2l`. |
| 25 | `driver_checks/_plugin_structure_claude.py:64` | `fenced_invocation_violations` | `list[str]` | `['skill_md.read_text']` | `skill_md.read_text` uncaught. Returns a violations LIST, so a read failure can only become 'no violations' — a fail-open in a packaging check. |
| 26 | `driver_checks/_plugin_structure_claude.py:161` | `claude_profile_violations` | `list[str]` | `['skills_dir.glob']` | `skills_dir.glob` uncaught, plus it aggregates `fenced_invocation_violations`. Convert with it — same module, coupled by clause (d). |
| 27 | `driver_checks/_plugin_structure_codex.py:226` | `codex_profile_violations` | `list[str]` | `['skills_dir.glob']` | Mirror of `claude_profile_violations` and calls the SAME shared `fenced_invocation_violations`. The two Driver profiles must convert in lockstep. |
| 28 | `fleet/_connection.py:101` | `parse_document` | `dict[str, object] \| None` | `try` | LOSSY: `None` covers 'unparseable JSONC' AND 'root is not an object'. Its own docstring names them as two shapes; the caller reports ONE message for both. |
| 29 | `fleet/_connection.py:141` | `connection_block` | `dict[str, object] \| None` | `_connection.py::parse_document  [try]` | THREE meanings in one sentinel, and the docstring admits it: unparseable, not-an-object, and 'carries no connection block (the member is not beads-backed)' — the last a LEGITIMATE ABSENCE. A failure and an absence sharing one `None` is this epic's own subject. |
| 30 | `fleet/_context.py:134` | `default_gh_runner` | `GhResult` | `['shutil.which', 'subprocess.run']` | THE `gh` boundary. Guards `shutil.which` and returns a synthetic 127 result, so 'binary absent' is already modelled in-band — but `subprocess.run` itself still raises (`PermissionError`, `OSError`) UNCAUGHT. Convert the residue, do not re-model the 127. |
| 31 | `fleet/_context.py:171` | `resolve_owner` | `str \| None` | `_context.py::_origin_remote_match  [io]` | ESTABLISHED ON `qndn` BY READING. Its `None` collapses THREE distinct failures — no origin remote, `git remote get-url` failing, a non-github remote. Reaches `subprocess` via `_origin_remote_match`, so member 1 does not exempt it and clause (e) refuses `X \| None`. ⛔ `dx8l` SHAPE: beads-fabro's `codex_yolo_gate.py` hook imports it — consumer wiring lands FIRST, dual-shape, in that repo. |
| 32 | `fleet/_context.py:177` | `resolve_repo_name` | `str \| None` | `_context.py::_origin_remote_match  [io]` | Identical mechanism to `resolve_owner` (same `_origin_remote_match`, same three collapsed failures). Convert in ONE pair with it — clause (d) couples them and a split PR would measure no movement, the `vzwa` arithmetic. |
| 33 | `fleet/_local_context.py:54` | `default_command_runner` | `CommandResult` | `['shutil.which', 'subprocess.run']` | Mirror of `default_gh_runner`, same residual uncaught `subprocess.run` failure. Convert in lockstep — the two are deliberately parallel and drift is the risk. |
| 34 | `fleet/_rows_github.py:79` | `member_matrix_targets` | `set[str] \| None` | `clause (e) only` | LOSSY, stated in its own one-line docstring: `None` when 'unreadable/empty'. Unreadable is a failure; empty is an answer. |
| 35 | `fleet/_rows_pin_currency.py:180` | `open_bump_prs_for` | `list[OpenBumpPullRequest] \| None` | `clause (e) only` | `None` = the PR list is UNREADABLE — a genuine failure. The `6ge` principle ('a can't-read never escalates a finding') is about SEVERITY, not representation: a `Failure` the caller folds to warning preserves it exactly and stops 'unreadable' being spelled the same as 'no bump PR'. |
| 36 | `fleet/_snapshot.py:151` | `default_gh_downloader` | `DownloadOutcome` | `['shutil.which', 'subprocess.run']` | Same shape, plus `dest.open('wb')` which raises on an unwritable destination. |
| 37 | `testing/_cli_e2e_discovery.py:95` | `discover_skills` | `dict[str, tuple[str, ...]]` | `_cli_e2e_discovery.py::_read_plugin_prefix  [try,io]` | Transitive via `_read_plugin_prefix`; same module and same cross-repo blast radius as `discover_fixtures`. A plugin dir whose manifest is unreadable is SKIPPED silently, so a broken install reads as 'that plugin ships no skills'. |
| 38 | `testing/_cli_e2e_discovery.py:125` | `discover_fixtures` | `dict[str, FixturedSkill]` | `['child.is_dir', 'expected_path.is_file', 'expected_path.read_text', 'fixtures_root.is_dir', 'fixtures_root.iterdir', 'prompt_path.is_file', 'prompt_path.read_text']` | ⛔ `dx8l` SHAPE — FOUR siblings reach this as `cli_e2e.discover_fixtures` through a re-export (this repo's own `pyproject.toml` comment names them). Consumer wiring lands FIRST, dual-shape, in each consuming repo. `prompt_path.read_text` is uncaught, and an unreadable fixtures root currently yields `{}` — 'no fixtures' — which is a PASS. |

### DECLARE — 4

| # | file:line | function | returns | convicted by | why |
|---|---|---|---|---|---|
| 1 | `checks/_no_except_outside_io_markers.py:157` | `sanctioned_marker_flavor` | `str \| None` | `clause (e) only` | `None` = this clause carries no sanctioned marker. An ordinary answer the caller acts on, not a failure — the `tag_version_component` shape. |
| 2 | `checks/_role_key_gate.py:133` | `role_absence_exit_code` | `int \| None` | `clause (e) only` | `None` = 'no early exit — carry on'. The absence of a gate decision, not a failed one. Every caller reads it as control flow. |
| 3 | `fleet/_connection.py:116` | `impl_plugin_name` | `str \| None` | `clause (e) only` | `None` = the document declares no `implementation.plugin`. A legitimate absence: not every member has one. |
| 4 | `fleet/_connection.py:127` | `named_plugin_connection` | `dict[str, object] \| None` | `clause (e) only` | `None` = no named-plugin connection block. Legitimate absence; `connection_block` deliberately falls back to scanning when it is None. |

### COUPLED — 1

| # | file:line | function | returns | convicted by | why |
|---|---|---|---|---|---|
| 1 | `fleet/_rows_pin_currency.py:220` | `persisting_bump_pr_number` | `int \| None` | `clause (e) only` | Today LOSSY — `None` means both 'no qualifying PR' (absence) and 'open_prs was unreadable' (inherited failure). Once `open_bump_prs_for` converts, the inherited half disappears and the remaining `None` is a legitimate ABSENCE → then DECLARE under member 2. Do NOT declare it before that, or the declaration would cover a failure. |

### TYPE-SLICE — 23

| # | file:line | function | returns | convicted by | why |
|---|---|---|---|---|---|
| 1 | `fleet/_adopter_lane.py:120` | `run_adopter_rows` | `AdopterRowsResult` | `_rows_claude_plugin.py::assert_claude_plugin_currency -> _rows_claude_plugin.py::_claude_plugin_currency_outcome -> _rows_claude_plugin.py::_settings_currency_outcome -> _rows_claude_plugin.py::_settings_payload  [try]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 2 | `fleet/_reconcile.py:178` | `reconcile_secret_names` | `RowOutcome` | `_reconcile.py::_secret_value_from_env  [io]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 3 | `fleet/_rows_baseline.py:148` | `assert_acceptance_mode_declared` | `RowOutcome` | `try` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 4 | `fleet/_rows_baseline.py:213` | `assert_baseline_harnesses` | `RowOutcome` | `try` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 5 | `fleet/_rows_beads.py:52` | `assert_tenant_connection_consistency` | `RowOutcome` | `_connection.py::connection_block -> _connection.py::parse_document  [try]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 6 | `fleet/_rows_claude_plugin.py:168` | `assert_claude_plugin_currency` | `RowOutcome` | `_rows_claude_plugin.py::_claude_plugin_currency_outcome -> _rows_claude_plugin.py::_settings_currency_outcome -> _rows_claude_plugin.py::_settings_payload  [try]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 7 | `fleet/_rows_files.py:248` | `assert_dev_tooling_pin` | `RowOutcome` | `_rows_files.py::_pinned_tag  [try]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 8 | `fleet/_rows_github.py:179` | `assert_branch_protection` | `RowOutcome` | `try` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 9 | `fleet/_rows_github.py:266` | `assert_delete_branch_on_merge` | `RowOutcome` | `_rows_github.py::_delete_branch_on_merge_severity  [io]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 10 | `fleet/_rows_local.py:92` | `assert_worktree_pack` | `RowOutcome` | `['path.is_file', 'path.read_text']` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 11 | `fleet/_rows_local.py:185` | `reconcile_beads_dir_perms` | `RowOutcome` | `['beads.is_dir']` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 12 | `fleet/_rows_local_beads.py:54` | `reconcile_beads_bd_binary` | `RowOutcome` | `_rows_local_beads.py::_beads_applicable  [io]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 13 | `fleet/_rows_local_beads.py:80` | `reconcile_beads_dolt_server` | `RowOutcome` | `_rows_local_beads.py::_beads_applicable  [io]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 14 | `fleet/_rows_local_beads.py:105` | `reconcile_beads_tenant_secret` | `RowOutcome` | `_rows_local_beads.py::_beads_applicable  [io]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 15 | `fleet/_rows_local_beads.py:122` | `reconcile_beads_config_committed` | `RowOutcome` | `_rows_local_beads.py::_beads_applicable  [io]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 16 | `fleet/_rows_local_beads.py:138` | `reconcile_beads_metadata_present` | `RowOutcome` | `["(ctx.checkout / '.beads' / 'metadata.json').is_file"]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 17 | `fleet/_rows_local_jsonc.py:118` | `reconcile_livespec_jsonc_complete` | `RowOutcome` | `['beads_path.exists', 'beads_path.read_text', 'jsonc_path.exists', 'jsonc_path.read_text']` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 18 | `fleet/_rows_pin_currency.py:336` | `assert_livespec_compat_pin_currency` | `RowOutcome` | `_rows_pin_currency.py::_pin_currency_outcome -> _rows_pin_currency.py::_records_for  [io]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 19 | `fleet/_rows_pin_currency.py:341` | `assert_github_workflow_uses_pin_currency` | `RowOutcome` | `_rows_pin_currency.py::_pin_currency_outcome -> _rows_pin_currency.py::_records_for  [io]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 20 | `fleet/_rows_pin_currency.py:348` | `assert_fabro_sandbox_image_pin_currency` | `RowOutcome` | `_rows_pin_currency.py::_pin_currency_outcome -> _rows_pin_currency.py::_records_for  [io]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 21 | `fleet/_rows_public_api_conformance.py:210` | `assert_cross_repo_public_api_declared` | `RowOutcome` | `_rows_public_api_conformance.py::fleet_consumption -> _rows_public_api_conformance.py::_build  [try]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 22 | `fleet/_rows_required_role_keys.py:122` | `assert_required_role_keys_declared` | `RowOutcome` | `_rows_required_role_keys.py::_required_role_declared_keys -> _rows_required_role_keys.py::_declared_role_keys_from_pyproject  [try]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |
| 23 | `fleet/_rows_role_key_spellings.py:153` | `assert_role_key_spellings_conformant` | `RowOutcome` | `_rows_role_key_spellings.py::_spelling_outcome -> _rows_role_key_spellings.py::_tool_table  [try]` | Returns `RowOutcome = RowPass \| RowFinding \| RowSkip` (`_context.py:111`) — a HAND-ROLLED sum in which `RowSkip` IS the failure track ('the row could not be definitively evaluated'). See the RowOutcome ruling below: this is one type-level decision spanning both engines, not 22 independent conversions. |

### OPEN — 5

| # | file:line | function | returns | convicted by | why |
|---|---|---|---|---|---|
| 1 | `checks/_docs_only_change.py:70` | `is_docs_only_change` | `bool` | `_docs_only_change.py::_dump_without_docstrings  [try]` | Returns `bool`; the docstring states the fail-closed collapse ('False for a revision git cannot produce, an unparseable version on either side, or any real source change'). A genuine failure DELIBERATELY collapsed onto the safe value. Converting forces every caller to unwrap and then choose the same `False`. NOT the `holds_app_class_credential` case — there the failure track was uninhabited; here it is inhabited and discarded on purpose. |
| 2 | `checks/_heading_coverage_tier_resolution.py:192` | `scenario_tier_violations` | `list[dict[str, object]]` | `_heading_coverage_tier_resolution.py::_node_id_resolves_with_marker  [try,io]` | Transitive via `_node_id_resolves_with_marker`, which catches `(OSError, SyntaxError)` and returns False 'so the prefix path governs'. Same deliberate-collapse question as `is_docs_only_change`. Decide the two together — one ruling covers both. |
| 3 | `checks/_no_except_outside_io_ruff.py:49` | `find_ruff_backstop_gaps` | `list[tuple[Path, str]]` | `_no_except_outside_io_ruff.py::_explicit_ruff_lint_select_configured  [io]` | Transitive via `_explicit_ruff_lint_select_configured` (`pyproject.is_file` + `read_text`, uncaught). An unreadable `pyproject.toml` currently yields `[]` — NO GAPS — which is a FAIL-OPEN in a backstop check, not a fail-closed one. That direction makes it materially different from the two above and it is likely a CONVERT; flagged OPEN only because the fail-open may itself be the bug worth filing separately. |
| 4 | `fleet/_credential_preflight.py:79` | `preflight_credential` | `PreflightOutcome` | `['sleep']` | Convicted solely by `sleep(...)` — an INJECTED PARAMETER (`sleep: Sleeper = time.sleep`). Not a machinery defect: a bare-name call is DOCUMENTED doubt and doubt disqualifies by design. But the module's own docstring says an injected seam is not a boundary, and its real I/O (`ctx.api_object`) is a seam too. Decide whether a bare call to a PARAMETER is resolvable rather than doubtful. |
| 5 | `fleet/_public_api_graph.py:217` | `cross_member_consumption` | `ConsumptionGraph` | `_public_api_graph.py::_edges_for  [io]` | Transitive via `_edges_for`. This is `5cai`'s own oracle — the row registered THREE DAYS ago and currently the epic's load-bearing central check. It already carries unparsed sources IN-BAND (`ConsumptionGraph.unparsed`) as a deliberate 'the absence is part of the value' design, argued in its own docstring. Converting would put that decision in two places. Read that argument before ruling. |

## 6. WHAT THIS FILE DOES NOT DO

- **It does not drop the skip and does not arm.** Dropping it before remediation turns
  `just check` RED at 75 and lefthook then blocks the very commit that fixes it — THE
  ORDERING TRAP, and `qndn` names it in the place `8o8e` originally did.
- **It does not settle 4 of the 5 `OPEN` rows.** `is_docs_only_change` and
  `scenario_tier_violations` turn on ONE question — *is a deliberate fail-closed collapse of
  an inhabited failure a violation of the rule, or a sanctioned design?* — and one ruling
  covers both. `preflight_credential` poses the narrow bare-call-to-a-parameter question in
  §4b. `cross_member_consumption` needs its own docstring's absence-is-part-of-the-value
  argument read first.
- **It DOES settle the fifth, and it is not a triage question at all.**
  **`find_ruff_backstop_gaps` fails OPEN, and that makes it a bug rather than a disposition**
  (supervisor brief 53). `_explicit_ruff_lint_select_configured` reads `pyproject.toml`
  uncaught; an unreadable one returns `False`, so the function returns `[]` — **NO GAPS** —
  from a check whose entire job is to find gaps in the ruff BLE001 backstop. The other two
  OPEN rows fail CLOSED, which is the safe direction; this one fails toward silence.
  **⛔ GATE: none — it blocks no gate, which is exactly why it must be filed rather than
  carried in a triage table.** A fail-open in a backstop check is a defect on its own
  timetable and should not wait on the railway question that surfaced it.
- **It does not narrow an `__all__`, adjust the universe, or add a declaration to make 75
  become 0.** The count after this triage is 75, disposed as 4 + 38 + 4 + 1 + 23 + 5.

### 6a. ⛔ EVERY FINDING IN THIS FILE CARRIES THE GATE IT BLOCKS

Required by supervisor brief 52, for the reason `qndn` itself demonstrated: it sat correctly
written in `handoff.md` for days as an OBSERVATION and was never re-asked as a PRECONDITION
of the gate it invalidated. **A finding with no gate named beside it outlives the epic built
to close it.**

| finding | filed as | GATE it blocks |
|---|---|---|
| the `_`-prefixed FILE skip is wider than v178 clause 0 | `qndn` | **ARMING.** The first gate. |
| CHECK-FIX ×4 — alias blindness, `io.StringIO`, `Path()` | **`8o8e.4`** (P1) | **ARMING.** Arming with them outstanding reports violations against conformant code, in the arming commit itself. |
| `RowSkip` conflation, live in a registered central row | **`8o8e.2`** (P1) | **NO ARMING GATE — and that is the point.** It reds every central run fleet-wide the moment the beads-backed population reaches zero. Fix it on its own timetable; do NOT couple it to the 23. |
| `5cai` re-export blind spot | **`8o8e.3`** (P1) · **FIXED** | **ARMING — via the THIRD AXIS, not via under-declaration.** Measured: `_undeclared` is `()` fleet-wide before AND after, because clause 3 structurally exempts every re-exported name. What it broke was the dx8l precondition — the oracle answered 1-of-75 while missing four sibling consumers of `discover_fixtures`. |
| `find_ruff_backstop_gaps` fails OPEN | **`8o8e.5`** (P2) | **NO GATE.** A backstop check that reports "no gaps" when it cannot read the config. |
| justfile `check:` parser duplicated 4× | **`8o8e.6`** (P2) | **NO GATE.** It makes the CONVERT work larger and inconsistent if half the copies convert; it stops nothing. |
| declaration gates unreachable behind the `pure_trees` gate | `ueni` (P1) | **ARMING, indirectly.** Bound 1 REJECTS, and its gate first becomes reachable in the arming commit — the one commit that must not go red. |

**Three of these seven block NOTHING, and each is filed rather than carried here for exactly
that reason: a defect that gates nothing has no queue pushing it forward.**

### 6b. ⛔ THE ARMING COMMIT MUST CARRY A DISPOSITION DENOMINATOR

Supervisor brief 52 constraint 2, and it is the `5cai` discipline applied to this gate. `5cai`
made its zero quotable by publishing its denominator — 9 members, 9 READ, 0 skipped, 0
unparsed, 58 edges. **After remediation, "0 offenders" and "0 because the remainder was
declared" are indistinguishable, and that indistinguishability is this epic's entire
subject.** So the arming commit states, of the 75:

| | |
|---|---|
| CONVERTED (code moved to the railway) | |
| RESTRUCTURED (the I/O left the function) | |
| DECLARED under v179 member 2 | |
| exempt by COMPUTED member 1 after the change | |
| measurement ARTIFACTS (the CHECK-FIX class) | |

**A reader must be able to tell how much of the zero was bought by code and how much by
declaration.** A bare zero was never evidence — that is why this thread exists.

## 7. SUGGESTED ORDER FOR THE REMEDIATION HALF

1. **CHECK-FIX (4)** — first, because arming with them outstanding reports violations against
   conformant code, and because the alias fix is a one-line predicate with a fixture.
2. **DECLARE (4)** — cheapest real movement; each needs a written reason under member 2's
   bound 2, and bound 1 REJECTS a non-`X | None` entry rather than skipping it.
3. **CONVERT, `read_pin_text` FIRST** — the 8 pin walkers all route through it, and
   `pin_autodiscovery.discover` is ALREADY `IOResult`, so the railway exists one level up.
4. **CONVERT the two `dx8l`-shaped ones LAST within their families** — `resolve_owner` /
   `resolve_repo_name` (convert as ONE pair; clause (d) couples them, so a split PR measures
   no movement — the `vzwa` arithmetic) and `discover_fixtures` / `discover_skills`, each
   after its consumers are wired dual-shape.
5. **TYPE-SLICE (23)** — the largest single block, and the one that needs its decision taken
   before any of it is written.
6. **Then** drop the skip, re-measure at BOTH ends, and arm — carrying the `995m` known-gap
   statement AND the §6b disposition denominator in the arming commit's own text.

**⛔ AND TWO ITEMS ON THIS LIST ARE DELIBERATELY *NOT* ON IT.** The `RowSkip` conflation and
the `5cai` re-export blind spot are **not** steps 1–6 and must not be sequenced behind them.
Neither gates arming; both are live in registered, currently-gating code. **Coupling a live
defect to a long queue is how `qndn` survived as an observation for days** — the whole reason
§6a exists.

**Item boundaries in this list are places to REPORT, not to WAIT.**
