# State correction, 2026-08-19 — the plan's core claim was STALE, and the sequencing was BACKWARDS

This note supersedes the live-state claims in
`local-llm-execution-route.md` §4 and the first ledger handoff entry of
2026-08-19. Both were written from the 2026-08-04 record without re-deriving it.
The measurements in the older notes remain good; the STATE they assert does not.

## 1. What I asserted, and why it was wrong

The 2026-08-19 handoff named `livespec-dev-tooling-8zv3.1` as the next action and
told the next session **not** to convert, on the grounds that the ROP check
"scans zero files in all nine repos" so conversions would be unenforced.

**`8zv3.1`, `8zv3.2` and `8zv3.3` are all CLOSED** — since 2026-08-04, before the
hold was even recorded. I named a done item as the next action. `bd ready`
returns nothing on that chain.

## 2. WHAT ACTUALLY HAPPENED — the decoupling landed, broke the fleet, and was reverted

This is the fact the whole plan turns on, and neither the plan files nor the
`8zv3.3` closure record it:

| step | commit / item | outcome |
|---|---|---|
| decouple the scan universe from `pure_trees` | **`46c5dab`** (PR #1248) | merged, positive-controlled in both directions |
| shipped to consumers | **v1.18.8**, fan-out bumped pins v1.17.1 → v1.18.9 in ONE step | |
| consequence | **FIVE fleet repos' master CI went RED** — `livespec`, `livespec-runtime`, `livespec-orchestrator-git-jsonl`, `livespec-orchestrator-beads-fabro`, `livespec-overseer` | |
| remedy | **`f4247110`** — full revert of `46c5dab` + `3e0b745` | all four touched files byte-identical to pre-`46c5dab` |
| incident item | `livespec-dev-tooling-irtt` (P0) | **CLOSED** 2026-08-05 |
| the re-land, behind adoption | — | **NEVER HAPPENED** |

**Verified on master today rather than taken from the record:** the shipped
`public_api_result_typed.py` still carries the live `pure_trees` role-absence
gate at lines 463–483, and running it here emits
`role_key_spelling=not_applicable`, `"flat-layout library has no pure-module
subtree"`, exit 0, **zero files scanned**.

⚠️ **`8zv3.3` IS CLOSED ON EVIDENCE THAT WAS SUBSEQUENTLY REVERTED.** Its close
reason describes the positive control in detail and does not mention the revert,
because the revert came after it. This is exactly the trap the archive rule
names: *closed can also mean superseded*. **Do not read `8zv3.3` as "the
decoupling is done."**

## 3. ⛔ THE SEQUENCING WAS BACKWARDS, AND THE INCIDENT PROVES IT

My handoff said: don't convert, the check is unarmed, so conversions are
unenforced. **That inverts the actual lesson.**

`46c5dab` armed the check *before* the consumers had adopted the rule, and that
is precisely what turned five repos red. `livespec/.ai/ci-gate-discipline.md`
names this failure mode — **enforcement-before-adoption** — and prescribes
revert-and-reland, which is what `f4247110` did.

**So the check being unarmed is NOT a reason to defer conversions. It is the
reason conversions must come FIRST.** Remediate, then arm. Arming first is the
one move already proven to break the fleet. `8zv3.4` ("per-repo
remediate-then-arm") carries that ordering and is still open.

▶️ **The conversion work is therefore not blocked — it is the critical path**,
and it is exactly the work the local-inference route was authorized for.

## 4. THE ONE DECISION THAT MUST PRECEDE CONVERSIONS — `8zv3.5`, worth 2.8x

Before converting anything, the `_`-prefixed FILE skip must be decided, because
it determines *which functions are offenders at all*:

| basis | fleet offenders |
|---|---:|
| WITH the `_`-file skip (shipped) | **160** |
| WITHOUT it | **446** |
| attributable to the skip alone | **286 (64%)** |

Converting before this is decided means converting an unknown fraction of the
real set and costing the fan-out at up to 2.8x error.

### My finding: the skip is UNRATIFIED, and I measured it rather than arguing it

**The ratified text binds NAMES, not FILES.** `livespec`
`SPECIFICATION/non-functional-requirements.md` §"What counts as public for this
rule", clause 0:

> *"A single leading underscore disqualifies outright. A `_`-prefixed **name** is
> NOT public regardless of its presence in `__all__`..."*

It adopts the private-helper definition from §"Typechecker rule set", which is
likewise name-based ("single-leading-underscore prefix or not in `__all__`").
**Nothing in the ratified rule skips a `_`-prefixed FILE.** The shipped
`_scan()` skip at `public_api_result_typed.py:387` is therefore wider than the
rule it implements.

**And the functions it hides are genuinely consumed across boundaries — MEASURED,
2026-08-19.** In `livespec-orchestrator-beads-fabro`, the single module
`commands/_config.py` is imported by **17 distinct non-test product modules**
(`next.py`, `migrate_tenant.py`, `close_work_item.py`, `rebalance_ranks.py`,
`_reflector_filing_store.py`, `_dispatcher_factory_ledger.py`, and 11 more).
Under clause 1 (**product import** — non-test first-party code across a module
boundary) those are public API by the ratified criterion, and the shipped check
never looks at the file.

**The fleet has already ACTED on this reading.** `8o8e.21`'s merged conversion —
this thread's own `research/8o8e21-green.patch` — converts
`commands/_config.py`'s `resolve_store_config`, `_read_root_mapping`,
`_read_connection_block` and `_read_plugin_sub_block` to the IO railway. The
fleet paid to convert an `_`-file's functions while the check that governs them
was structurally unable to see them.

▶️ **Recommendation: DROP the `_`-file skip; the honest remediation target is
~446, not 160.** This is a TIGHTENING, so it does not hit the never-weaken-a-check
boundary. It is the maintainer's decision to ratify, and it is `8zv3.5`'s
deliverable — but the evidence above is measurement, not inference.

⚠️ **Note the interaction with §3:** dropping the skip makes the fleet-wide
adoption debt ~2.8x larger, which makes remediate-before-arm *more* important,
not less. `livespec-orchestrator-beads-fabro` alone moves 17 → 157 offenders (9x)
and `livespec-overseer` 115 → 249.

## 5. The corrected next action

1. **Decide `8zv3.5`** (the `_`-file skip) — evidence above; maintainer's call.
2. **Then remediate per repo** under `8zv3.4`, using the local-inference route.
3. **Then arm**, per repo, only behind that repo's adoption — never fleet-wide
   ahead of it.

The `8o8e.19`–`.29` children remain deferred pending disposition and still block
archive; that is unchanged.
