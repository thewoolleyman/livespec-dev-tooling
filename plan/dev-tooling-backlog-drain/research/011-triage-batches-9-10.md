# Triage batches 9–10 — the last P0/P1s, and a claim against this repo, 2026-09-08

**Status: PROPOSAL.** Dispositions await the maintainer's ruling. What was done
unilaterally is the reading.

**Milestone: every P0 and P1 in the open snapshot is now triaged.** Untriaged open
snapshot items: **78 → 61 of 145** (119 at session start — **58 read** across
batches 5–10). The remainder is 52 P2 + 9 P3. Position **113/258**.

## Batch 9 — the ROP/v179 measurement cluster

**Five referrals**, one shape: the code is in another repo's tree, and every
dispatch from this plan runs `--repo /data/projects/livespec-dev-tooling` with the
sandbox cloning only that repository.

| item | target |
|---|---|
| `0aru` | `livespec-runtime` — eight cross-repo-consumed functions needing a coordinated conversion |
| `vojo` | `livespec-runtime` — three genuinely-convicted functions |
| `oip9` | `livespec-overseer` — 49 `test_*.py` inside the product tree, so v178 promotes 24 helpers to public API |
| `0n2a` | `livespec-orchestrator-git-jsonl` — a vendored module whose `typing_extensions` dependency is neither vendored nor declared |
| `55ec` | `livespec-orchestrator-beads-fabro` — also blocked, see below |

**None was re-measured, deliberately.** `jecv` records that three durable records
already give three different fleet offender totals on incompatible bases
(432/338, 402/321, 429/328). Adding an unverified fourth from a tree this plan
cannot dispatch against makes that worse. **Settle the denominator before the
referrals are accepted** — that sequencing now covers eleven referred items.

### `55ec` — where I nearly made the error it warns about

Its own text says *"DO NOT SCHEDULE THIS … it reads as ready work and is not"*,
naming two blocks. One of them, `8o8e.22`, **is now closed** — measured in batch 5
— so a reader could reasonably conclude it is ready. It is not established that it
is: the peer lane's red PRs were **not** re-measured, because that means reading
another repo's forge state this drive cannot reach and must not assert from
memory.

**The honest state is "one block measured clear, one unverified."** Contrast batch
7, where three `y6m2xn` children were blocked on a trigger that *had* already
fired — this one must not be swept up with them.

### `ueni` — confirmed, and the check's own docstring says it verbatim

`public_api_result_typed.py:53-58`:

> ⛔ BOTH DECLARATION KEYS' STALENESS GATES SIT BEHIND THE `pure_trees`
> ROLE-ABSENCE GATE … That is an artifact of the gate ORDER, not of the detectors,
> and **it is stated here rather than left to be discovered.**

So it is acknowledged at the site and left deliberately, with a note anticipating
this exact rediscovery. **Disposition: downstream, not independent.** `8zv3`,
`crl2` and `ueni` share one root; un-gating is what makes the detectors reachable.
It cannot be pulled forward — `crl2` is blocked by design because `46c5dab` turned
five repos red.

One thing that could be done now without touching any gate: a **read-only report**
of which repos hold unverified declarations, derivable from already-declared
`pure_trees` role values.

## Batch 10 — the last P0/P1s

### `qndn` (the single P0) — blocking premise falsified

It says arming cannot proceed because the count is 0 or 75 "depending on whether
`_scan`'s `_`-prefixed FILE skip travels", and that "the ENTIRE difference is one
`if py_file.name.startswith("_"): continue` in `_scan`."

**That line is gone.** `_scan()` now reads:

```python
for py_file in iter_py_files(root=cwd / tree_rel):
    if _is_test_module(name=py_file.name):
        continue
```

The only surviving `startswith("_")` is line 324 — the ratified v178 clause 0
*function-name* rule. And the deciding item, `8zv3.5`, is **closed**. The choice
was made in the drop direction and implemented; only qndn's row was left behind,
at P0.

**It does not mean arming can proceed** — the blocker changed identity to the
standing "do not arm anywhere" constraint and the `idlx`/`crl2` sequencing, both
triaged in batch 8 as correctly blocking.

### `usi0` — spent by time, with a residual that is not

Explicitly time-boxed: *"re-derive your `resulting_files[]` AFTER v191 cuts"*.
livespec's history is at **v221**, and the addressee lane is gone from
`proposed_changes/`. Both trigger and addressee are spent.

But its title names a **mechanism** that does not expire: `resulting_files[]`
carries the whole file, so the second ratification silently reverts the first. A
prior-art scan across the tenant found **nothing** covering that as its own
subject. Closing usi0 as spent would make the mechanism untracked — recommended as
a `discovered-from:usi0` child, **not filed**, because filing one while proposing
to close its parent deserves a line of ratification.

### `xx1y` — verified live on this host

```
credential.https://github.com.helper = !/home/ubuntu/.local/bin/livespec-agent-github-credential-helper
  → exec … /data/projects/livespec-runtime/.venv/bin/livespec-github-credential-helper
```

Every fleet repo's `git push` resolves credentials through a binary in **another
repo's virtualenv** — invisible to pins, vendoring and pin-currency checks, with
no fallback. This drive depends on it: every push this session made went through
that path. The shim names "the livespec-runtime v0.8.0 helper" *in prose* but
resolves to whatever `.venv` holds.

### `8o8e.16` — not falsified by a healthy snapshot

`/tmp` reads 2% inode use today. **That does not falsify a leak** — a reading
taken between exhaustions says nothing about a leak rate, and drawing the opposite
conclusion is precisely the error this item exists to prevent. Lead, not
conclusion: a 100-million-inode tmpfs is a very large allocation and may itself be
a mitigation, in which case the defect is *masked* and returns on any normally
provisioned host — the CI runner case.

### Referred to CORE's spec flow, for a different reason than batches 5 and 9

`4ihw` and `k4km` are not cross-repo *code* but **spec acts**: their resolution
changes what CORE's ratified prose says, which travels through propose-change,
independent review and revise. Dispatching them would at best PR the wrong repo
and at worst implement an unratified reading.

### Kept and in-repo

`fas6`, `h0g9` (**read its retraction first** — the original claimed the verb set
was wrong in *both* directions and is retracted in full), `izbq`, `k76y`
(recommend binding it to `5cai` as a blocks edge — a pre-implementation design
finding's value decays to zero the moment its parent is built the naive way).

## A generalisation earned across ten batches

Five separate findings are one error: **the check's configuration is implicit
where it should be declared.**

- `LIVESPEC_RUN_PLAN_EPIC_PARITY` — set nowhere; the target still passes
- `plan_anchor_declared` — retired to `exit 0` forever
- `bd ready` — renders a native status this store never uses; returns `[]` silently
- `fas6` — infers its plugin model from a directory *name*
- `x7ml` — three gates stand down on a work-item nothing verifies exists

Each was cheap to detect. **None detects itself.**

## A claim against this repo, disproved — and what it exposed here

The `ci-writer-ingress-hardening` session reported that dev-tooling v1.61.0 had
broken dolt-server's CI repo-wide at the mise install step.

**Three independent checks clear v1.61.0:** it touched no reusable workflow
(`git diff --stat` over `.github/workflows/reusable-*` is empty for
`v1.60.0..v1.61.0` *and* `v1.59.0..v1.61.0`); the failing step is in dolt-server's
own `ci.yml:66-69`; and the 404 URL carries no dev-tooling-derived value.

**Actual cause, upstream:** mise-action resolved mise `v2026.9.3` and 404'd.
`releases/tags/v2026.9.3` does not exist; `releases/latest` is `v2026.9.2` with 46
assets. That also disposes of "it re-fails on rerun" — a nonexistent release stays
nonexistent, so rerun-failure does not distinguish an upstream break from a local
one.

**What it exposed in this repo, and it is the reason this section is here.**
dev-tooling is exposed identically and is surviving only on a cache hit — run
`34225883243` shows `mise cache restored from key: mise-v1-linux-x64-ubuntu24-…`;
it never curled. There are **seven unpinned `jdx/mise-action` call sites, none
carrying a `version` input, and four are in workflows the whole fleet consumes**
(`reusable-pin-freshness` ×2, `reusable-bump-pin-from-dispatch`,
`reusable-release-dispatch`). On a cache eviction that does not break one repo's
checks — it breaks the fleet's **pin-freshness and release-dispatch lanes**, the
propagation machinery itself.

Against batch 8's fan-out cluster the irony is exact: `ve7w`/`zm5cbp`/`lmv2` are
about what the fan-out cannot propagate; this is the fan-out unable to **start**.

The fix is one line per call site. Landing it requires `approval:workflow-edit`,
which the guard states agents cannot set — so it is parked on the epic, not done.

### Two corrections that session made to this drive

Recorded because both improved the findings.

1. **`y6m2xn.8`'s mechanism.** Both recipe *bodies* already call the renamed
   modules, and dolt-server's aggregate loops an explicit `targets=()` array that
   **errors** on an unknown target. So it is four justfile lines of naming
   consistency, not a live hole.
2. **The `unassigned` anchors.** That string is a **sentinel the orchestrator
   writes by design** — `_plan_identity.py` declares itself "the WRITE side of the
   ratified plan-identity contract"; `migrate_plan_records.py` writes the anchor
   "`unassigned` when no epic carries the slug". Not neglect.

### What this drive contributed back, and how `d1j` got stronger

Their evidence — "the aggregate errors on an unknown target" — answers a
*different* question from "does the check compute anything". Measured:
`plan_no_tombstone` is **live**; `plan_anchor_declared` emits `disposition:
retired` and exits 0 **unconditionally**; `plan_epic_parity` has grep-count 0 in
dolt-server's justfile. That gate is vacuous there — **silent pass, not silent
skip**, which is why watching it run green cannot distinguish it from a working
gate.

Their "plugin/dev-tooling skew" is the crisp root: **one contract, three
components, no two agreeing which side is authoritative** — the plugin writes
filesystem anchors, dev-tooling retired the reader of those files, and the
successor that reads the authoritative ledger side never runs.

That gave my `d1j` claim a way to be false, so I re-tested it before repeating it.
`_plan_identity.py` says the two facts sit on opposite sides "so either side
resolves the other" — if the ledger carried the tags, the anchors would be merely
stale. Scanning every item's `metadata.plan_slug` across the tenant:

```
mutation-testing-keystone   -> NO EPIC TAGGED
pure-trees-role-key-scope   -> NO EPIC TAGGED
rgr-cycle-agent-efficiency  -> NO EPIC TAGGED
rop-railway-enforcement     -> NO EPIC TAGGED
```

Both sides say "unidentified" **and agree**, so neither resolves the other — the
state that seam exists to make impossible. `d1j` is therefore not "a lever nobody
set" but **the only component that could detect a three-way contract
disagreement, switched off.** The P3 → P1 proposal stands, on better evidence than
when it was made.

## What these batches ask for

1. `qndn`: rescope or close — it should not sit P0-blocked on a settled question.
2. `usi0`: close as spent, and rule on the `discovered-from` child for the
   whole-file `resulting_files[]` mechanism.
3. The five batch-9 referrals — after the `jecv` denominator is settled.
4. `d1j` P3 → P1.
5. **The mise pin**: `approval:workflow-edit` so the seven call sites can be
   pinned before a cache eviction becomes a fleet-wide outage.
