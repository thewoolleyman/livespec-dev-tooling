# 006 — Triage batch 4: the untriaged long tail

Written 2026-09-07 by the plan session that resumed `kcoslm` at 04:12Z. Presented
as DECIDED, per the maintainer's standing ruling and this repository's
decision-authority rule: every disposition below is a finding with its evidence,
not a question.

## 1. Why this batch exists

Batches 1–3 drained tier 1, tier 2, and the two large clusters. What they did not
do is triage the long tail, and the consequence was measured rather than guessed:
of the 149 frozen-scope items sitting at `backlog`, **144 carried no
`intake:triaged` label** — including 2 at P0 and 65 at P1. They were not held for
stated reasons the way the 8 `ready` items are. They were simply never looked at.

That matters because several session handoffs reported "nothing is factory-ripe"
as though it were a fact about the world. It was a fact about work not done:
triage is what converts `backlog` into dispatchable, and triage is this drive's
own job. A session that resumes this plan, finds an empty dispatchable tail, and
parks is the stall the charter warns about.

## 2. The method, and why it is not optional

**Verify each item's premise IN THE TREE before disposing of it.** Close only what
is provably landed, quote the evidence in the close reason, and keep open anything
whose premise still holds.

This is the standing verify-the-premise-before-dispatch step applied to closure
rather than dispatch, and it earned its keep three times in this batch:

- **`otrq`** — the item names `cross_repo/fabro_image_pin_rewrite.py`. A grep of
  `checks/` returned nothing and the item looked fixed. The stale docstring is
  alive at line 214 of the file the item actually names. Nearly closed a live item
  by reading the wrong directory.
- **`995m`** — "config.py excludes ITSELF from every check universe" looked
  plausibly stale until `is_generated(config.py)` was actually executed and
  returned `True`. The defect is live.
- **`z45`** — every code path the item named is genuinely fixed, and closing on
  that alone would still have been misleading: this repo declares
  `pure_trees = NotApplicable`, so `check_mutation` takes the declared-absence
  exit and **mutation testing does not run here at all**. The close records that,
  because "the defect is fixed" and "the check protects this repo" are different
  claims.

A description is never sufficient evidence. Neither is a changelog.

## 3. Measured result: the tail is substantially stale bookkeeping

**26 items verified, 12 closed — a false-open rate near one half.**

Every closure below is on evidence read from current master:

| item | disposition | evidence |
|---|---|---|
| `r3ib` | landed | node-id resolution shipped in `29a49c05` / v1.52.13, and observed FIRING in three sibling repos |
| `aqmr` | landed | `_plan_ledger.py:127` passes `--status all`, with the reasoning recorded at :113 against regression |
| `ic0n` | premise void | rename re-landed as `89aa3a99`, released in v1.24.6+ |
| `kfp` | landed | hardcoded `_IMPL_PREFIXES` replaced by `config.derive_source_prefixes` |
| `rkdg` | dissolved | the per-repo enumeration that could omit a repo no longer exists |
| `bslp` | landed | `run_shellcheck` is Result-typed with an explicit `ShellCheckUnavailable` arm |
| `6j6` | landed | `_is_crashed_run` restores the `rc>=2` hard fail as its first disjunct |
| `z45` | landed | all four paths addressed; see the caveat in §2 |
| `hh4d` | landed | vendored `.py` excluded via the same `is_vendored_path` the first-party universe uses |
| `800` | landed | `required_aggregate_gates = (required & job_names) - matrix_targets` |
| `zbo` | resolved | justfile and module docstring now agree the pack is gitignored-and-installed |
| `1oa` | landed | coverage data file is `tempfile.mkdtemp()`, outside the `.coverage.*` combine glob |

**The finding this batch contributes:** a large share of this backlog is not work.
It is items nobody closed after the work landed. Verification is far cheaper than
dispatching an item that turns out to be done, so verification must precede
dispatch selection, not follow it.

## 4. Verified live — the premise still holds

Kept open with fresh evidence. Two have REGRESSED since filing, which is worth
more than their priority suggests:

- **`0yfo`** — config.py is **643 LLOC** against a 250 hard ceiling. Filed at 560.
- **`efxa`** — **2** `except ConfigParseError` sites across **107** check files.
  Filed as "30 of 31".
- **`1w5c`** — no non-increasing ratchet exists; `no_lloc_soft_warnings` is a scan
  with a severity lever, and the soft band currently holds **41 files** with
  nothing preventing regrowth.
- `otrq`, `g28`, `995m`, `65c`, `e5nz`, `y27`, `okz`, `9s2j`, `1aba`, `1a6w`,
  `l8d7` — premises confirmed live; see each item's comment.

## 5. The remaining tail, bucketed so it is actionable

A flat list of 79 unverified items is not a work queue. They sort into three
kinds, and the kinds take different routes:

1. **Factory-dispatchable** — a code defect in this repo with a checkable premise.
   These are the only ones `drive --action impl:` can take.
2. **Spec-lifecycle** — the deliverable is a `SPECIFICATION/` edit, so the route is
   `/livespec:revise`, NOT a factory dispatch. Known members: `1aba` (contracts.md
   exit-code table still reads `1 | internal bug`), `1a6w` (contracts.md:430 still
   reads "Three first-party consumers as of v0.2.x"), `3q2c`, `ckb`.
   Dispatching these to the factory would be a category error.
3. **Maintainer-decision** — not a defect at all. `vod6` self-declares "A DESIGN
   QUESTION, not a defect". These must never be dispatched at any priority; they
   belong with the standing decisions.

Held as clusters, unchanged from batch 3: the ROP `8o8e.*` family (20 items) plus
`8zv3`/`8zv3.4`/`ueni`, and the 8 cross-tenant referrals `0aru`, `0n2a`, `4ihw`,
`k4km`, `ve7w`, `tljy`, `usi0`, `vojo` — each still needs an owning-tenant id
before it can close here.

## 6. Adjacent defect found while verifying, recorded not filed

In `shell_quality._shellcheck_findings`, the failure arm returns early ONLY for
`ShellCheckUnavailable`. Any other failure type falls through to
`run_result.unwrap()` on an already-failed `Result`, which raises — reintroducing
the crash-instead-of-finding shape `bslp` existed to remove, for every failure
class except the one it was filed about. Whether another failure type is currently
reachable was NOT verified, so this is a latent shape, not a measured crash.

Not filed: charter §4 admits a new item only as a child, a `discovered-from` edge,
or a consolidation. If it is worth tracking it belongs as
`discovered-from:livespec-dev-tooling-bslp`, and that is the maintainer's call.

## 7. Position

Counted fresh against the frozen 258 at the time of writing, not accumulated:

| bucket | count |
|---|---:|
| closed | 101 |
| backlog | 137 |
| ready | 8 |
| blocked | 12 |
| **open total** | **157** |

101 of 258 is **39%** of the frozen scope, up from 86 (33%) when this session
resumed. Of that gain, 15 came from this session; only one (`y6m2xn.1`) predates
batch 4.
