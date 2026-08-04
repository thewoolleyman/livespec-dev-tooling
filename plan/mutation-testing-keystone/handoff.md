# mutation-testing-keystone

> **Ledger anchor:** epic `livespec-mutreal` (P2), with keystone `livespec-mutreal.1`
> (P2) — both in the **`livespec`** repo's ledger, NOT this repo's. The anchor is
> deliberately CROSS-TENANT; `check-plan-thread-epic-parity` parity-checks only
> same-tenant `livespec-dev-tooling-*` ids and ignores cross-tenant refs by design
> (decisions 41/44/45), so this thread is anchor-declared without falsely claiming a
> local epic. The ledger is authoritative over this file.
>
> ```bash
> /usr/local/bin/with-livespec-env.sh -- bd -C /data/projects/livespec show livespec-mutreal.1
> ```

## ⚠️ THIS THREAD IS HOUSED IN THE WRONG REPO ON PURPOSE — MOVE IT

The work belongs to **`livespec`**. It lives in `livespec-dev-tooling/plan/` only
because **`livespec` cannot currently land any PR**: every open PR fails
`check-doctor-static` (see `livespec-dev-tooling-8o8e.26` — a cross-repo justfile-refactor
breakage owned by a peer lane), and master CI is intermittently red.

**MOVE THIS THREAD TO `livespec/plan/mutation-testing-keystone/` as the first action once
that freeze clears.** Housing it here is a landability workaround, not a claim of
ownership. Verified 2026-08-04:

```bash
cd /data/projects/livespec && mise exec -- gh pr list --state open --limit 5 \
  --json number,statusCheckRollup \
  --jq '.[]|"#\(.number) failing=\([.statusCheckRollup[]?|select(.conclusion=="FAILURE")|.name]|join(","))"'
```

## Why this thread exists at all

`livespec-mutreal` was a P2 epic with **one child**, both in `backlog`, the epic untouched
since 2026-07-01 and the keystone since 2026-07-19 — and **no plan thread anywhere in the
fleet owned it**. Two of the three plan files that mention `mutreal` are **archived**; the
only live one was `rop-railway-enforcement`'s handoff, which named it purely as a blocker.

That is the shape this fleet keeps rediscovering: **a finding with no gate attached, and
now a blocker with no owner attached.** It was silently gating a P1 fleet epic.

## The work itself

From the ledger epic: mutation testing is **non-functional family-wide**.

- `livespec`'s mutmut layout is **broken** — `mutmut run` fails with
  `ModuleNotFoundError: No module named 'livespec.commands._next_ranking'` inside the
  instrumented `mutants/` copy → **0 mutants**. The committed `.mutmut-baseline.json` is a
  **0/0 placeholder**, and `check_mutation` treats `total=0` as a **pass**.
- `livespec-dev-tooling`, `livespec-impl-plaintext` and `livespec-runtime` have no
  `[tool.mutmut] paths_to_mutate` at all — mutation is a no-op placeholder there too.

📜 **Note the shape: a check that passes on `total=0`.** That is *precisely* the defect
`livespec-dev-tooling-8o8e` was founded on — a green check that scanned zero files. **The
mutation lane and the ROP lane are two instances of one class**, which is the strongest
argument for driving this rather than leaving it at P2 indefinitely.

Full diagnosis and the validated fix are in `research/mutation-testing/plan.md` (PR #434)
and the mutreal epic comment.

## ⛔ What this thread is NOT, and must not become

**It is NOT on the ROP critical path any more.** Three repos declare
`pure_trees = { unarmed_until = "livespec-mutreal.1" }`, which transitively gated the P1
ROP epic. **`livespec-dev-tooling-8zv3` removes that coupling at the other end** by
migrating the ROP check's scan universe off `pure_trees`.

**Do not rush, re-prioritise, or escalate this item on ROP's account.** Once `8zv3` lands,
ROP does not wait on this. Drive it on its own merits — which are real, per the class
argument above — or leave it at P2 honestly. **Manufacturing urgency from a coupling that
is about to be deleted is exactly the kind of stale-premise decision this fleet's records
keep warning about.**

## Suggested first actions

1. **Move this thread to `livespec/plan/`** once `check-doctor-static` clears.
2. Reproduce the `mutmut run` failure and confirm the `0/0` baseline is still committed —
   **do not trust this file's transcription of a 2026-07-19 diagnosis.**
3. Decide whether `check_mutation` treating `total=0` as a pass is its own filing. It very
   likely is, and it is the part that generalises beyond mutation testing.
4. Only then take the layout fix and the real baseline capture.

## Relationship to other threads

- **`plan/pure-trees-role-key-scope`** (`8zv3`) — removes ROP's dependency on this item.
  `pure_trees` remains legitimately load-bearing for `check_mutation`'s `paths_to_mutate`,
  so the two threads still touch the same key for different reasons.
- **`plan/rop-railway-enforcement`** (`8o8e`) — ON HOLD; no longer waiting on this.
