# Triage batch 7 — stale statuses, and an unarmed lever, 2026-09-08

**Status: PROPOSAL.** Dispositions await the maintainer's ruling, per the
batch-1 precedent. What was done unilaterally is the reading: eleven items are
labelled `intake:triaged` and each carries its finding as a comment.

Session: `plan-session:dev-tooling-backlog-drain-2026-09-08-resume-0908g`.
Untriaged open snapshot items: **100 before, 89 after** (119 at session start —
**30 read this session** across batches 5, 6 and 7).

## The theme: a status that was true when written, and nobody re-reads it

Batch 6 found an **archived plan that left six children open**. This batch found
the same class twice more, in unrelated places. None of the three would ever have
detected itself, and each was cheap to detect once looked at.

That is the reusable output of this batch. Below are the three instances.

## Instance 1 — three children blocked on a trigger that had already fired

`y6m2xn.6`, `.7`, `.8` all sit at `blocked` on "when `livespec-dev-tooling` cuts
the release carrying the `plan_thread_* → plan_*` rename (`y6m2xn.1`)".

Measured: **`y6m2xn.1` is closed**, this repo's renamed recipes
(`check-plan-anchor-declared` / `check-plan-epic-parity` /
`check-plan-no-tombstone`) all exist, and `just --list | grep -c
check-plan-thread` returns **zero**. Siblings `.2`–`.5` already closed against
that same trigger.

Nothing re-evaluates a blocked-on-a-release precondition once the release exists,
so **two children that were finished and one that was merely ready all presented
identically as blocked.**

| child | target repo | measured at `origin/master` | proposed |
|---|---|---|---|
| `.6` | `livespec-driver-codex` | 0 old refs; new names in `ci.yml`, `check-targets.txt`, `justfile` | **CLOSE** |
| `.7` | `livespec-console-beads-fabro` | 0 old refs; new name in `justfile`; repo has no `check-targets.txt` | **CLOSE** |
| `.8` | `dolt-server` (adopter) | **4 old refs**, 0 new — definitions at `justfile:92,95`, references at `:45-46` | **UNBLOCK + REFER** |

On `.7`: the missing `check-targets.txt` is *the file not existing*, verified with
`git cat-file -e` — not a missed rename. A bare grep returning fewer hits than its
sibling looks like incomplete work and is not.

On `.8`: worth more than its four lines. dolt-server is the **adopter** running an
aggregate that names recipes under the *old* scheme while consuming a dev-tooling
release that ships the new ones. Whether its plan-anchor gates currently fail or
**silently skip** decides whether they are vacuous — this fleet's recurring
failure shape — and should be established on the other side. It has its own
`.beads/`, so a referral has somewhere to go; someone should confirm that is
dolt-server's own tenant rather than server-side storage, since it sits beside the
dolt databases this host serves.

`y6m2xn` (parent): keep open until `.8` is disposed, then close.

## Instance 2 — a retired check that still reports as a passing target

`pk2x` is about `check-plan-thread-anchor-declared` self-skipping on absent
config. That check was renamed by `y6m2xn.1` and then **retired outright**.
Running it today prints:

```json
{"check_id": "plan_anchor_declared", "disposition": "retired",
 "replacement": "plan_epic_parity",
 "reason": "ratified Planning Lane uses ledger-held plan epic metadata, not git anchor files"}
```

and exits 0 unconditionally. So `pk2x`'s premise — "armed in exactly ONE repo, the
one with no plan threads" — is no longer the state: it is armed **nowhere**
because it is retired **everywhere**.

Proposed: **rescope onto the surviving half, or consolidate into `d1j`.** Not
decided here, because it turns on a real judgement rather than a measurement:
whether a fleet census of handoffs lacking a concrete anchor still means anything
now that anchors are ledger-held rather than declared in `handoff.md`.

## Instance 3 — the lever that nothing sets

This is the batch's most consequential finding, and a **prior-art scan stopped it
from becoming a duplicate**: `d1j` already describes it. Nothing new was filed.

Re-measured today:

- `just check-plan-epic-parity`, run **under the credential wrapper** so
  `BEADS_DOLT_PASSWORD` was present, still self-skipped and exited 0:
  `skipped — set LIVESPEC_RUN_PLAN_EPIC_PARITY and provide BEADS_DOLT_PASSWORD to arm`.
  The credential is not the binding constraint; **the run lever is.**
- `LIVESPEC_RUN_PLAN_EPIC_PARITY` **is set nowhere** in this repo. Grepping every
  `.yml`, `.yaml`, `justfile`, `.just`, `.toml`, `.sh` and `.txt` finds only two
  justfile *comments* describing the lever and the source that reads it. **There
  is no setter.**
- The target is nonetheless in the aggregate — `check-targets.txt:43`,
  `justfile:247` — so it **runs in every `just check` and in CI and always exits
  0**. A green aggregate reports it as passing.
- `check-plan-record-conformance` delegates to the **same** lever
  (`_DELEGATE_LEVER`, `plan_record_conformance.py:89`). Two targets, one dead
  lever.

**What is new, and why `d1j` is proposed for P3 → P1:** this is not a latent
invariant with no known violations. **Four unarchived plans carry the literal
string `unassigned`** in `associated_work_item_id` — `mutation-testing-keystone`,
`pure-trees-role-key-scope`, `rgr-cycle-agent-efficiency`,
`rop-railway-enforcement` (seven archived plans do too; eleven in total). Nothing
can compute those plans' completion, and three of their subject epics (`8zv3`,
`8o8e`, `8o8e.26`) are items this drive has been triaging all session.

Class: the same shape as `8o8e.20` — a documented lever no CI sets — which
`rop-railway-enforcement`'s own disposition note named *"enforcement that does not
enforce"* and said deserves its own track. This is a second live instance, and
unlike `8o8e.20` it has known violations to point at.

## The rest of the batch

- **`8zv3`** — subject epic of the live plan `pure-trees-role-key-scope`;
  **deferred**, like batch 5's `8o8e`. Its plan's anchor file says `unassigned`,
  so the repair is cheap and mechanical — but it is that plan's to make, and doing
  it here would be writing into another plan's state with no gate able to verify
  the result.
- **`8zv3.4`** — the cross-repo fan-out; **refer** per-repo, batch 5's shape. Its
  own stop condition should travel with it: as of 2026-08-04 two repos could not
  accept work at all, and it says *verify before pushing anywhere*. That check is
  a month old and this drive did not re-run it.
- **`7us`** — live umbrella; **keep**. This session supplied two fresh data points
  for its thesis (`x7ml` timed out at 151 tool calls, `675skf` at 134 while
  running its *final gate* on a docs-only changeset), and PR #2038 supplied
  material new evidence for its child `7us.7`.
- **`fy02`** — **keep**, but `ready` overstates it: a 6217-char epic with zero
  acceptance criteria whose own text splits into supervisor-owned design and
  factory-eligible mechanical PRs.

## A ninth implementation nobody listed

`fy02` describes one rule with eight implementations. This session found a ninth,
and it is not code: **the factory's GitHub App token cannot push
`.github/workflows/` at all** (`bd-ib-nga9`, two independent live reproductions).
That is why `37p0`'s bot PR #2028 carried no `.github/` files while the
human-identity PR #2027 did.

A consolidation that unifies eight code paths and leaves the token scope
unmodelled will still produce the split-PR behaviour seen today — and a valve
(`fy02.2`) that grants approval *in the ledger* does not grant the *token scope*,
so an approved item dispatched to the factory still yields a PR missing its
workflow half. Those two need modelling together.

## What this batch asks for

1. Close `y6m2xn.6` and `.7` (measured landed); unblock and refer `y6m2xn.8`.
2. Raise `d1j` P3 → P1, and decide `pk2x`: rescope or consolidate into it.
3. The standing question, which decides throughput rather than any single item:
   **may this drive close measurement-falsified items directly and report**,
   reserving the ratification round for consolidations, re-parenting and
   referrals — the ones that really do change ownership?
