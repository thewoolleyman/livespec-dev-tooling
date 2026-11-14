# Carriers without an owner, settled (2026-11-14)

The seventh independent review (session 934a13cd, 2026-11-14T12:34:54Z) reproduced assertions 1, 3 and 4 and failed
2 and 5. legacy-coordinator-agent decided at 12:57:28Z (on livespec-dev-tooling-q26e3c) that this plan does one more
fix round. This note closes the review's findings N1, N4, N5 and N9. N2 and N3 are closed by a new track summary
scope event on livespec-dev-tooling-q26e3c, written after this note. Where this note differs from notes 005 to 010,
it governs.

Two notes carry the number 007. In this tree "note 007-corrections" is
`007-corrections-after-independent-review-2026-11-14.md` and "note 007-metric" is
`007-docs-release-exclusion-lead-time-and-board-shape-2026-11-14.md`. Note 007-metric governs the metric: the
headline counts non-docs, non-release pull requests merged green, the frozen 7-day floor is FLEET 6.90/h, and the
charts live on the board `livespec throughput` (ytZuuVuT4BQ). Note 003's 9.64/h is the superseded all-PR figure.

## How each item was settled

Every item below was put to the session that owns the row or to the track coordinator on 2026-11-14 between
14:2xZ and 14:5xZ, by SendMessage. Each decided, and recorded the decision on its own epic. "Held" means
throughput-plans-coordinator (livespec-dev-tooling-r7iuj6) carries the item as a routing question for
legacy-coordinator-agent or the named candidate seat; the item is OFF the ranked rows and is no lever's carrier.

## The 25 parentless orchestrator items

| Item | State at 14:2xZ | Decision | Decided by, recorded on |
|---|---|---|---|
| bd-ib-08ehv | backlog | ACCEPTED, carrier of row 3 (Y1); adopted under bd-ib-ft26pi | factory-run-yield, bd-ib-ft26pi |
| bd-ib-yq55nk | ready | ACCEPTED, carrier of row 3 (Y1); adopted under bd-ib-ft26pi | factory-run-yield, bd-ib-ft26pi |
| bd-ib-cp2x | backlog | ACCEPTED on a condition, carrier of row 4 (M1, M2): it waits on bd-ib-welwbc and is closed as a duplicate if welwbc's terminal span gives per-run wall time; adopted under bd-ib-ft26pi | factory-run-yield, bd-ib-ft26pi |
| bd-ib-2flry2 | ready | REFUSED, not a carrier of row 3 (it labels References coverage; it is not about an assertion's proof surface). Held; home is the plan that owns the governing-heading judgement | factory-run-yield, bd-ib-ft26pi; held on r7iuj6 |
| bd-ib-gv6uwy | backlog | REFUSED, not a carrier of row 3 (host-only items spend no factory run). Held; candidate home hp-factory-failure-follow-ups (bd-ib-qieqc6) | factory-run-yield, bd-ib-ft26pi; held on r7iuj6 |
| bd-ib-tqzazn | pending-approval | REFUSED, not a carrier of row 4 (step-span attributes are not the run-level failure category). Held; candidate home factory-run-correlation-observability (bd-ib-qfv9) | factory-run-yield, bd-ib-ft26pi; held on r7iuj6 |
| bd-ib-svw54x | blocked | ACCEPTED, carrier of row 6 (Y2); adopted under bd-ib-3goerg | sandbox-commit-gate-follow-ups, bd-ib-3goerg |
| bd-ib-ckocwc | ready | ACCEPTED, carrier of row 6 (Y4); adopted under bd-ib-3goerg | sandbox-commit-gate-follow-ups, bd-ib-3goerg |
| bd-ib-bx5rf2 | acceptance | ACCEPTED, carrier of row 6 (Y4); adopted under bd-ib-3goerg | sandbox-commit-gate-follow-ups, bd-ib-3goerg |
| bd-ib-m26pql | blocked | ACCEPTED, carrier of row 5 (C1, M4). The item is in the orchestrator tenant, so no parent edge to livespec-dev-tooling-ib3oe3 exists; the owner names it on its epic | ci-runtime-and-cost, livespec-dev-tooling-ib3oe3 |
| bd-ib-eq5ics | acceptance | ACCEPTED, carrier of row 5, named on the epic; the owner closed its own bd-ib-p622hp as this item's duplicate | ci-runtime-and-cost, livespec-dev-tooling-ib3oe3 |
| bd-ib-fapmpq | ready | ACCEPTED, carrier of row 5, named on the epic | ci-runtime-and-cost, livespec-dev-tooling-ib3oe3 |
| bd-ib-k6cq6e | ready | ACCEPTED, carrier of row 5, named on the epic; carried as coverage correctness, not as a throughput lever | ci-runtime-and-cost, livespec-dev-tooling-ib3oe3 |
| bd-ib-2wni | backlog | ACCEPTED, carrier of row 2b, named on the epic (other tenant). It needs a twin in the livespec-dev-tooling tenant before dispatch; the owner raises that after tig7vu and 7uq5ri | red-master-self-healing, livespec-dev-tooling-zcp5vb |
| bd-ib-aibd3u | ready | REFUSED, not a carrier of row 2b (incident-time launch-path behaviour). Held; candidate home expedited-incident-response or the dispatch plan | red-master-self-healing, livespec-dev-tooling-zcp5vb; held on r7iuj6 |
| bd-ib-f6yp7t | pending-approval | REFUSED, not a carrier of row 10: it duplicates livespec-driver-claude-mbg4zg.1, which is closed. Held; the routing question is who closes it once the released guard is confirmed to carry the fix | github-request-budget-discipline, livespec-httc; held on r7iuj6 |
| bd-ib-avv4 | backlog | REFUSED, not a carrier of row 10: it duplicates livespec-driver-claude-mbg4zg.2, which is closed. Held, as f6yp7t | github-request-budget-discipline, livespec-httc; held on r7iuj6 |
| bd-ib-busjvz | acceptance | OFF the track (launch path). Held; candidate home legacy-dispatcher-agent | throughput-plans-coordinator, r7iuj6 (14:20:48Z) |
| bd-ib-keuuwi | ready | OFF the track (launch path). Held; candidate home legacy-dispatcher-agent | throughput-plans-coordinator, r7iuj6 |
| bd-ib-5k2yq2 | pending-approval | OFF the track (launch path). Held; candidate home legacy-dispatcher-agent | throughput-plans-coordinator, r7iuj6 |
| bd-ib-3ozwp2 | blocked | OFF the track (credential). Held; candidate home central-credential-service or llm-provider-manager | throughput-plans-coordinator, r7iuj6 |
| bd-ib-wqxgjf | pending-approval | OFF the track (credential). Held; same candidates | throughput-plans-coordinator, r7iuj6 |
| bd-ib-xqgeav | ready | OFF the track (lost sandbox). Held; candidate home factory-run-work-preservation | throughput-plans-coordinator, r7iuj6 |
| bd-ib-i3ygrq | ready | OFF the track (quota refusal read as a credential failure). Held; candidate home kubernetes-sandbox-backend; it looks like a duplicate of ko5kxf | throughput-plans-coordinator, r7iuj6 |
| bd-ib-ko5kxf | blocked | OFF the track. Held, as i3ygrq | throughput-plans-coordinator, r7iuj6 |

Note 010 already holds the other three of that list (bd-ib-3bbdrh, bd-ib-crgpkk, bd-ib-rz2vhj) on r7iuj6.

Result: of the 17 that sat on on-track rows, 11 now have an owning plan that accepted them, and 6 were refused by
the row's owner as not carriers and are held for routing. No report item or lever lost or gained an owner.

## Carriers that another plan already holds

The data records' per-item overlap bullets name items that touch a report item from inside a plan that does not
own that item's row. Each already sits in exactly one plan (parent read from the ledger at 14:2xZ). None is moved,
and none makes its plan a second owner of the row: the row owner in note 010's table is unchanged, and the item
stays with the plan that holds it. throughput-plans-coordinator reads them as neighbours of the row, not as its
carriers.

| Item | Report item it touches | Stays with | State |
|---|---|---|---|
| bd-ib-jb53pu | Y4 | checkpoint-commit-hook-failures (bd-ib-hcwmnq) | acceptance |
| bd-ib-6y26nx | Y4 | hp-factory-failure-follow-ups (bd-ib-qieqc6) | blocked |
| bd-ib-woiqjm | Y4 | factory-run-work-preservation (bd-ib-nckst7) | acceptance |
| bd-ib-tnxcka | Y4 | kubernetes-sandbox-backend (bd-ib-nmuyjc) | blocked |
| bd-ib-ia6zbf | Y4 | kubernetes-sandbox-backend (bd-ib-nmuyjc) | blocked |
| bd-ib-3lxeqf | Y4 | fabro-currency (bd-ib-6tcjfx) | ready |
| bd-ib-dirscy | C4 | Anthropic token burn mitigation (bd-ib-b2jzxw) | acceptance |
| bd-ib-k4ltmr | C4 | Anthropic token burn mitigation (bd-ib-b2jzxw) | ready |
| bd-ib-zl3qcz | C4 | kubernetes-sandbox-backend (bd-ib-nmuyjc) | ready |
| bd-ib-d3pdrv | C4 | factory test-first enforcement (bd-ib-q622ls) | pending-approval |
| bd-ib-5k6eal | C4 | factory test-first enforcement (bd-ib-q622ls) | pending-approval |
| bd-ib-bwwkne | C4 | factory-run-work-preservation (bd-ib-nckst7) | closed; nothing left to own |
| bd-ib-c3txja | C4 | pr-stage-backgrounded-push-fault (bd-ib-ctagnf) | acceptance |
| bd-ib-crtnzx | C4 | spec-implementation-lockstep (bd-ib-ax3rds) | blocked |
| livespec-dev-tooling-ja7bv4 | M4 | kubernetes-observability (livespec-dev-tooling-s2aqob), which has a tab on the track as the deliverer of row 1 | ready |
| livespec-dev-tooling-5y3luz | C4 | ci-runtime-and-cost (livespec-dev-tooling-ib3oe3) | ready |
| livespec-dev-tooling-3su2nx | C4 | token-spend-analysis (livespec-dev-tooling-6lv7ze) | blocked |
| livespec-dev-tooling-h2i4u2 | Y2 | fleet-flaky-tests (livespec-dev-tooling-zwveqp), owner of row 11 | active |
| livespec-dev-tooling-q4ahay | Y2 | dev-host-test-gate-load (livespec-dev-tooling-6vuiwe) | closed; nothing left to own |
| livespec-dev-tooling-dpkz32 | Y4 | fleet-flaky-tests (livespec-dev-tooling-zwveqp) | blocked |
| livespec-dev-tooling-e34ks3 | Y4 | fleet-flaky-tests (livespec-dev-tooling-zwveqp) | pending-approval |
| livespec-dev-tooling-wj45qt | Y4 | dev-host-test-gate-load (livespec-dev-tooling-6vuiwe) | acceptance |
| livespec-dev-tooling-cetyrq | X, CI infrastructure | ci-runtime-and-cost (livespec-dev-tooling-ib3oe3) | blocked |
| livespec-dev-tooling-uqmdor | X, CI infrastructure | ci-cache-optimization (livespec-dev-tooling-7zozck) | pending-approval |
| livespec-dev-tooling-ddcvyd | X, CI infrastructure | ci-cache-optimization (livespec-dev-tooling-7zozck) | ready |

This plan did not ask those holding plans to give the items up. A proposal to move one is the track
coordinator's to make when a row's measurement shows the item limits the metric.

## The plan github-rate-limit-guard-false-positives (N4)

livespec-driver-claude-mbg4zg, classed CORE for G1 in the other-repositories record: a DEPENDENT that
github-request-budget-discipline coordinates with, by that owner's decision on livespec-httc (2026-11-14 ~14:3xZ).
It keeps its own work, the guard's false-positive rate and rollout. G1, the shared login's REST budget, has one
owner: github-request-budget-discipline. This replaces note 005's D9 line "decided by coordinator".

## Overlaps O7, O9 and O10 of note 010, now answered

- **O7.** livespec-dev-tooling-hatvwq against ci-cache-optimization's e2gv6n and n622ze. Note 010 said the fleet
  coordinator would be asked; nobody asked. It is now held by throughput-plans-coordinator (r7iuj6, 14:20:48Z) and
  put to legacy-coordinator-agent on livespec-dev-tooling-6tgd2z; ci-cache-optimization's seat decides. All three
  items are off the track.
- **O9.** ci-runtime-and-cost answered: livespec-dev-tooling-5ua57h does NOT fully supersede 8o8e.23. The jobs-API
  502 at `per_page=100` is still live, so 8o8e.23 stays open in rop-railway-enforcement, narrowed to that.
- **O10.** ci-runtime-and-cost answered: 227glz and vrpwyw are the same failure and are merged into 227glz; vrpwyw
  is marked a duplicate and closes when its spec-tier hold clears.

## Row 6b

publish-draft-green-work-loss (bd-ib-acrr56) was asked on its epic at 11:29:35Z and again at ~14:4xZ to accept or
refuse row 6b (Y3). Its seat is on vmi3006760 and cannot be reached by SendMessage from this plan's session.
legacy-coordinator-agent ruled at 12:57:28Z that the acceptance is that plan's. Its answer, or the coordinator's
ruling in its place, is recorded on bd-ib-acrr56 and in the track summary scope event, not in this note.
