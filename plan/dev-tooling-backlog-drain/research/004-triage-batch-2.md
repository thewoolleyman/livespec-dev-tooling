# 004 — Triage batch 2: enforcement-suite correctness (tier 2)

Proposed 2026-09-06 ~11:00Z by the drain's loop session for the maintainer's
ruling, per charter §5 and §6. Every disposition is a PROPOSAL until the
ruling is a scope event on `livespec-dev-tooling-kcoslm`; the §6 ledger
actions execute only after that. Facts marked *measured* were read from the
source named; the rest is a reading of each item's own text.

## 0. Where tier 1 stands (measured from the ledger, 11:00Z)

Closed through the factory: `9yrr`, `9yb4`, `aa7`, `4j3`, `h7qp`, `iugc`,
`trfzkw`, `mmqe`, `lptplj`, `yxxzvj` (P0), `k169`. Closed by hand under an
exemption: `sc0z`, `a28f`, `l5gypl`. Provider casualties awaiting the 13:55Z
resumer: `to6hh2`, `7ix8`, `el7g`, `b7dbne`. Held: `7us.7` (idle-host
measurement), `py9` and `675skf` (need slicing), `xx1y` (repo half needs a
worker after the limit resets; host half verified clean).

The tier-2 class from charter §6: checks that pass vacuously, pass on a
half-pair, or fail on a true positive. A false green here poisons every later
tier's evidence, which is why this batch precedes the P1 epics.

## 1. KEEP — dispatchable tier-2 defects in this repo's checks

Ordered for dispatch. Each needs gradeable acceptance criteria authored from
its own text at dispatch time (the batch 1 lesson: the engine refuses an item
without them).

| id | P | defect | note |
|---|---|---|---|
| `zv78` | 1 | `red_green_replay` certifies a HALF-PAIR: `--amend -m/-F` destroys the `TDD-Red-*` trailers and the hook still exits 0 | first: it is also the factory's own commit path |
| `rav3` | 1 | `check-coverage-incremental` passes vacuously when its `git diff` fails; the returncode is never read | |
| `8t0i` | 1 | `heading_coverage` never resolves the node ids it is given; a row naming a nonexistent test passes | |
| `6vz` | 1 | `no_raise_outside_io` is vacuous in every consumer whose domain errors are not named like core's; hardcoded name set | fix shape: derive the set from a role key or the consumer's declared error module |
| `l5pw` | 1 | `public_api_result_typed` convicts pure functions: `replace` in the unresolved-receiver I/O verb set matches `str.replace` | true-positive failure |
| `yj09` | 1 | `public_api_result_typed` reads co-located test modules as public API | its text asks the maintainer to choose (a) producer-side or (b) consumer-side; **decided here: (a)**, the item's own preferred option, because a public-API check that reads tests is wrong in every consumer |
| `qknd` | 1 | `ci_yaml_canonical_reconcile` places a new metadata slug into the wrong step | pure-function fix with a hermetic fixture, per the item |
| `e2wv` | 2 | `branch_protection_alignment` treats a conditional leniency as unconditional; never verifies the required aggregate exists | |
| `eihv` | 2 | `install_no_shadow_ledger` and its check diverged at slice L; installer docstring asserts something false | survivor for `nauzq6` (§3) |
| `omcbgb` | 2 | restore the doctor-static baseline in dev-tooling (two pre-existing findings) | small; pairs with `tem4t2` (§3) |
| `4s2sey` | 2 | SubagentStop guard emits no valid Stop-hook JSON | already re-readied in batch 1; one abandoned run, re-dispatch |
| `6e83` | 2 | a second `CommandResult`/`CommandRunner` under the same names in `fleet/`, invisible to every check | quality, last |
| `sh71` | 2 | a partial blind-row red survives the `z4qi` credential preflight; "measure the causes, then decide" | re-scope at dispatch: acceptance = the measured cause list recorded on the item plus the one fix it names; if measurement shows two causes, it becomes two items |

Thirteen keeps. `8zv3` (epic, `pure_trees` shared role key) stays open with
its two live children `8zv3.4` (fleet fan-out) and `8zv3.5` (the `_`-prefixed
file skip); `8zv3.5` is a tier-2 correctness fix and is dispatchable now;
`8zv3.4` is fleet arming and waits for the ROP batch (§5).

## 2. Human valves in this class — decided here as findings

Charter §2 gives the maintainer the valves, and the decision-authority rule
says a question with a recommendation is a finding. Each below is proposed as
DECIDED; object if the decision is wrong.

| id | block | decision |
|---|---|---|
| `jtrt.1` (P1) | an ad-hoc config re-parse pointed at the wrong TOML table reported a confident zero; "asserted enforcement, measurement side" | **ready**: the fix is the measurement helper asserting the table it read is non-empty when the commit under measurement added entries, or naming the table it read in its output; no design call remains |
| `fp5yfv` (P2) | `_IMPL_PREFIXES` under-covers configured source trees; recommends deriving impl paths from `source_tree_prefixes` | **ready, survivor for `30g`** (§3): adopt the recommendation as the criterion; `30g`'s `.claude-plugin/hooks/` case is one row of it |
| `xaxj5w` (P2) | must `check-agents-ai-references-resolve` detect `.ai/` ABSENCE? | **ready, decided: yes as a distinct verdict**: when AGENTS.md names zero `.ai/` paths the check reports `vacuous` at warning level with the count, never a bare pass; it does not fail a repo that legitimately has no `.ai/` tree. A gate that structurally cannot fire must say so |
| `thw26i` (P1) | agent-instruction-surface runs over 1 of 7 fleet classes; 7 of 10 members breach the ratified clause and the row reports PASS | **ready, re-scoped**: run over all 7 classes as the clause says; report breaching members at WARNING with a per-member remediation until a fleet backfill lands, then ERROR. Adoption first, then arming, this repo's standing rule |
| `nauzq6` (P2) | installer and check disagree on an undeclared `neutral_hook_body_path`; remedy is "a design call" | **consolidate into `eihv`** (§3): the design call is the one `eihv` already frames; the check's declared-ness gate is the ratified side (slice L), so the installer follows it |
| `tem4t2` (P2) | dev-tooling CI does not gate doctor-static | **ready**: wire `check-doctor-static` into this repo's aggregate exactly as core does, after `omcbgb` restores the baseline; dependency edge `tem4t2` blocked-by `omcbgb` |
| `qn3pgi` (P2) | retire the legacy justfile target mirror once core drops its fallback | **hold, cross-tenant condition**: the trigger is a livespec-core change; keep the carrier open, blocked-by nothing here, reconsidered when core's resolver drops `targets=(...)` |
| `5o6ssu` (P2, at acceptance) | accept valve on the fan-out supersession classifier | **needs a read before accepting**: the item has no PR metadata and has sat at acceptance since 2026-07-20; the loop verifies whether its PR merged and either accepts on evidence or returns it to ready. Not decided blind |
| `c5byjh`, `t4fosw` | host-only, ci-runner-cache-tiers plan items gated on storage moves and an offered-not-required tier | **hold**: they belong to that plan's own scope events; the drain records them and does not rule |

## 3. CONSOLIDATE

| survivor | absorbs | why |
|---|---|---|
| `fp5yfv` | `30g` | same root cause (`_IMPL_PREFIXES` hardcoded); `fp5yfv` is the wider, later statement and names the fix |
| `eihv` | `nauzq6` | the same installer/check divergence filed twice from two angles |

## 4. CLOSE — superseded or landed

| id | reason |
|---|---|
| `ivd8` (P2) | *measured*: `plan_epic_parity` on master no longer reads prose anchors; the plan-record migration (`a67bd086`) and the eleven conformance checks (`yxxzvj`, `252c2855`) read `plan/<slug>/associated_work_item_id`. The regex the item describes is gone; a thread's visibility no longer depends on prose formatting |

## 5. DEFER and REFER

- **Cross-tenant, refer to livespec core and close here**: `ganj` (spec CLIs
  no-op under `python -m`), `jzoz` (revise's `modifications` unenforced),
  `vno1` (the drift sweep is a term-based grep). Each is filed or linked in the
  core tenant with a comment here naming the id; batch 1 already deferred
  `jzoz` to this step.
- **ROP epic `8o8e` and its ten open children** (`8o8e.24`, `8o8e.27` among
  them, plus `8zv3.4`'s fan-out): a batch of their own, after this one, because
  arming decisions are fleet-wide and the console-freeze hold on `8o8e.7`
  still stands.
- **`jjb`** (mechanize ROP boundary rules): a new check, not a false green;
  tier 3, rides with the ROP batch.
- **`i3ub`** (per-commit unowned-TODO tier): blocked behind a fleet backfill of
  304 entries; hold until the backfill is a filed item somewhere.

## 6. Ledger actions this batch authorizes, once ruled

1. Move the 13 keeps in §1 (and `8zv3.5`) to `ready` with criteria authored at
   dispatch; dispatch in the listed order under the wip cap, `zv78` first.
2. Resolve the valves in §2 as decided: `jtrt.1`, `fp5yfv`, `xaxj5w`, `thw26i`,
   `tem4t2` to `ready` (with `tem4t2` blocked-by `omcbgb`); `qn3pgi`,
   `c5byjh`, `t4fosw` stay blocked with the hold recorded; `5o6ssu` read then
   accepted or returned.
3. Close `30g` into `fp5yfv` and `nauzq6` into `eihv`, survivors commented.
4. Close `ivd8` as superseded, citing `a67bd086` and `252c2855`.
5. Refer `ganj`, `jzoz`, `vno1` to the livespec core tenant and close here with
   the cross-tenant id.
6. Record the `8o8e` deferral so the ROP batch is the next proposal.

Net effect: 6 closures (3 referred, 2 consolidated, 1 superseded), 5 valves
resolved without a maintainer turn, 14 items enter the ready set.

## 7. What this batch does NOT decide

- Nothing in `8o8e` beyond naming it as the next batch.
- Nothing about workflow-file-only changes (`jeqp`, a maintainer-decided bug
  in `reusable-release-dispatch.yml`): the factory cannot push
  `.github/workflows` edits (the App token lacks the permission, measured
  today on `yxxzvj`'s first run and filed as `bd-ib-cvge`), so `jeqp` needs a
  hand path. The charter's exemption enum has no row for "workflow-only
  change"; the closest reading is `infra-in-person` (a credential act no
  sandbox can perform). **Ask**: ratify that reading for `jeqp` and any later
  workflow-only item, or add a third enum value. This is the one genuine
  question in the batch.
