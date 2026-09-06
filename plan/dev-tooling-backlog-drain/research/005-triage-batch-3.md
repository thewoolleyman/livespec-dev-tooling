# 005 — Triage batch 3: the 183 open snapshot items after tier 1 and tier 2

Written 2026-09-06 ~20:10Z by the plan session that resumed at 15:50Z, ran the
maintainer's 16:20Z throughput back-off, and resumed at one item. Presented as
DECIDED, per the maintainer's standing ruling of ~11:55Z ("your plan should be
clear unless there are blockers") and this repository's decision-authority rule.
Every disposition below is a finding with its reasoning; none is a question.

## 1. Where the drain actually stands

Read fresh from the ledger at 19:58Z against the frozen 258-id snapshot in
`research/002`, not from any file:

| bucket | count |
|---|---:|
| closed | 75 |
| backlog | 150 |
| ready | 22 |
| blocked | 11 |
| **open total** | **183** |

75 of 258 is 29% of the frozen scope. Tier 1 (factory-path defects) and the
tier-2 first wave (enforcement-suite correctness) are drained; what remains is
overwhelmingly the long tail plus two large fleet clusters.

## 2. The ordering hazard this batch found and closed

`livespec-dev-tooling-crl2` ("Re-land 46c5dab: un-gate public_api_result_typed
from pure_trees") was sitting at status `ready` with NO blocking edge, so the
dispatcher could have taken it on any tick. Its own description says: *"LAST
step of epic idlx. Do NOT start this until every adoption child is closed."*
Re-landing 46c5dab is precisely the change that turned FIVE fleet repos' master
CI red and was reverted as PR 1285. Landing it now would violate both
`AGENTS.md`'s ordering rule (adoption first, then arming) and
`plan/rop-railway-enforcement/`'s standing constraint "Do not arm the check
anywhere".

Its only edges were a `parent-child` to `idlx` and two `blocks` edges to items
that are already CLOSED, so nothing mechanical stood in the way.

**Decided and executed:** `crl2` moved `ready -> blocked`, labelled
`blocked-reason:ordering-adoption-before-arming`, with the reasoning on the
item. An attempt to add a `blocked-by` edge to the fleet ROP epic `8o8e` was
REFUSED by the store — *"tasks can only block other tasks, not epics"* — so the
constraint rests on status plus the recorded reason, not on an edge. That
refusal is itself a modelling gap: the ledger cannot express "this task waits on
that epic", which is the single most natural shape for an adoption-before-arming
constraint. If it bites again, it is a cross-tenant item.

This is a conformance repair to what the item already said, not a new ruling.

## 3. The two big clusters — HELD, with the condition named

### 3a. The fleet ROP railway epic `8o8e` (P1 epic, 25+ open children)

`8o8e` is "arm it, then remediate SEVEN repos / 338 distinct functions". Its
arming children `8o8e.7`–`.13` are per-repo counts. **HELD as a cluster**, for
two independent reasons, either sufficient:

- `plan/rop-railway-enforcement/` carries the standing constraint "Do not arm
  the check anywhere". Arming is the cluster's terminal step.
- `8o8e.7` (livespec-overseer) is already held by reference to the console
  plan's overseer-freeze scope event, which has not landed (batch 1 ruling).

**Reconsidered when** the rop-railway-enforcement plan lifts its constraint. The
REMEDIATION children (converting functions onto the railway) are not blocked by
the arming constraint in principle, but they are fleet fan-out into other
tenants and belong to their owning repos under charter §6 — this drain does not
work them here. `8zv3.4` (fleet fan-out) and `jjb` (mechanize the ROP boundary
rules) are held with the same cluster.

### 3b. The `pure_trees` role-key cluster (`8zv3` epic, `kmdn`, `m50u`, `ueni`)

Same shape: a shared role key with five real consumers, where the decision in
each repo is an architectural judgement. `kmdn`, `m50u` and `qv3k` are all
already `blocked` / needs-human and each says so in its own description
("WHICH copy becomes canonical is a judgement call across eight divergent
files"). **HELD as filed.** They are correctly blocked; this batch does not
unblock them and does not need to.

## 4. Cross-tenant — referred, never worked around here (charter §6)

`0aru`, `0n2a`, `4ihw`, `k4km`, `ve7w`, `tljy`, `usi0`, `vojo` name livespec
CORE or livespec-runtime surfaces. The batch-2 precedent is the pattern: file or
link in the owning tenant, record the id here, close here. **Decided:** referred
in a later pass rather than this one, because each needs its owning tenant's id
before it can be closed here and the referral itself costs a cross-tenant write.
They are not dispatchable here in the meantime and are not blocking anything.

## 5. Filed cross-tenant BY this drive, and now load-bearing

Two orchestrator defects were measured by this drain today and both bound how
fast any drain in this fleet may run:

- `bd-ib-m1av` — `reconcile-runs` cancels a SIBLING engine's just-launched run
  as `superseded-run` during the ~40 s window before `dispatch-run-stamp`,
  whenever the item carries an older journaled run id. Every re-dispatch on a
  multi-engine host is exposed.
- `bd-ib-2vda` — `wip_cap` is enforced per-admission-pass with NO cross-engine
  exclusion, so N loops admitting in the same instant each take the SAME free
  slot. **Measured**: three admits at the identical second while claims already
  stood at 5 against a cap of 4.

`bd-ib-2vda` is the honest answer to the maintainer's "isn't there a cap that's
supposed to be observed?": the cap WAS observed by every engine individually,
and no cap VALUE can bound total concurrency until that defect lands.

## 6. Contention, and what it cost — recorded so it is not re-triaged

Between 15:49Z and 17:30Z, with 7 sandboxes concurrent on a host at load
22–29/18 cores, FOUR implement stages died at the ACP layer (`6e83`, `8zv3.5`,
`eihv`, `sh71`, two of them 30-minute `ACP turn timed out`), TWO post-merge
janitors went red on `check-per-file-coverage`, and the GitHub App installation
exhausted its API rate limit, turning master CI red on `check-fleet-conformance`.

None of these was a defect in the item that carried it:

- The janitor red was **measured non-reproducible** — the same target re-run by
  hand in the janitor's own kept checkout, tree unchanged: 3297 passed, 42194
  statements, 100.00%.
- The master red was a rate limit, whose own JSON says
  `read_failure_cause: rate-limited`.
- `8zv3.5` subsequently merged GREEN through the factory under lower load, and
  `jtrt.2` completed cleanly end-to-end at load ~5. That is the control: the
  same factory, the same ritual, no contention, no ACP death.

**Decided:** `6e83`, `eihv` and `sh71` are re-dispatched ONE AT A TIME under the
resumption rule in §7, not as a wave, and a repeat failure at the same stage
sends that item to `groom` per charter §3.

### 6a. A cascade worth naming

The suite contains `test_master_ci_green.py::test_real_repo_passes`, which
asserts master CI is green against the REAL repository. While master is red,
that test fails in EVERY PR's coverage lane, so no PR can go green — including
one that would repair master. It cleared on its own here, but it means a red
master is a full merge stop, not a degraded mode. Not filed: the scope is
frozen and this is a property of an existing check, recorded for whoever reads
`aa7`'s neighbourhood next.

## 7. The dispatch rule this batch adopts

The 16:20Z back-off stands, revised once at 19:03Z with the revision recorded on
the epic. The operative rule:

> Launch at most ONE item at a time. Launch only when the 15-minute load average
> is under 12, this drain has no live run, and total live dev-tooling runs
> including other sessions stay at or below 3, keeping the tenant under the
> merged `wip_cap` of 4.

It is procedural, not enforced — `bd-ib-2vda` is why. A SECOND session
(`plan-session:livespec-sab5gn`) dispatches into this same tenant; its items
(`u44yfd`, `75vm7n`, `bobdhc`, `2ww4e7`, `oqasja`, `bv3yfc`, `nzhceg`) are NOT
this drain's and are not worked here.

**Dispatch order for the ready tail**, one at a time, criteria authored from each
item's own text before dispatch (the engine refuses an item with none):

1. `klvy` (in flight at time of writing), then `1jqm`, `5ug6`
2. `6e83`, `eihv` — the ACP-death re-measures, one at a time
3. `y6e2`, `qh0e`, `x7ml`, `j2qa` (P1 ready, criteria needed)
4. `hgfnqd`, `6e65`, `dpqd`, `dqfmjr`, `zm5cbp`, `y6m2xn.1`
5. `tem4t2` — NOT an impl dispatch; it is a `spec-op` (a doctor-static gate that
   needs the contracts.md revise), routed through the spec lane

**Excluded from dispatch regardless of readiness:** `crl2` (§2), `7us.7` (needs
an idle host by its own criteria), `py9` and `675skf` (need `groom` — both are
oversized as filed), `xx1y` (host half done, repo half needs a worker).

## 8. What this batch does NOT do

- It does not file the two charter §7 mechanical children (item-provenance
  ratchet, factory-bypass red gate). They remain unfiled, so §3 and §4 bind by
  prose only. That has now been true for three batches and is the single
  largest gap between this plan's design and its enforcement.
- It does not re-open the frozen scope. Nothing here admits a new item; the
  two cross-tenant defects were filed in the ORCHESTRATOR tenant, which the
  charter's §4 does not govern.
- It does not rule on the `jtrt.1` mixed-diff exemption. That one IS a genuine
  question of enum design and is stated as three costed options on the item;
  it is the one item in this batch where a maintainer ruling would change the
  answer rather than confirm it.
