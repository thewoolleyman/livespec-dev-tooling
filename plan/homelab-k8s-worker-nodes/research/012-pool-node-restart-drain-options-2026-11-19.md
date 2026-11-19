# 012 — Pool-node k3s agent restart: may the play cordon and uncordon? Options for the maintainer

Plan `homelab-k8s-worker-nodes` (epic `livespec-dev-tooling-ko26ez`). Written
2026-11-19 by the homelab-k8s-worker-nodes seat at legacy-coordinator-agent's
request, for its FOR THE MAINTAINER list. Options only: no propose-change is
filed until the maintainer rules.

## The question

Work item `livespec-dev-tooling-346ays` (adopted into this plan 2026-11-19, held
at `pending-approval`) asks that `ansible/restart-k3s-agent.yml` cordon the node,
wait a bounded time for CI runner and gate pods to drain, restart the k3s agent,
and uncordon, so a pool-node restart needs no hand quiet window.

It contradicts two ratified paragraphs of
`SPECIFICATION/non-functional-requirements.md` §"Consent-gated pool-node
disruption" (read on origin/master `4b5fdc3e1`):

- Line 571, agent restart: the play "MUST NOT cordon, drain, evict or delete any
  pod", takes ONE pod read, and a CI runner pod or gate Job pod MUST refuse the
  restart.
- Line 577, node hold: a hold "MUST NOT be lifted by any other play, or by a
  timer, a schedule or a deadline", and ends only by the committed uncordon
  action with two confirmations (action and node).

Both are safety guarantees, so loosening either is a design change, not an
internal release.

## The need behind the item

On 2026-11-09 an approved gmktec window needed a node with no runner or gate
pods, but new ones land continuously, so the play's single read kept refusing.
The coordinator ruled a hand `kubectl cordon` for the window. That hand cordon
is itself a gap the spec's committed-play rule wants closed in automation.

## Options

### A. Keep the contract; add a separate drain-wait play (recommended)

Leave lines 571 and 577 untouched. Add one committed play, for example
`wait-pool-node-idle.yml`, that WAITS (bounded) for a named node to carry no
runner or gate pod and reports when it does. The operator composes the window
from three already-ratified plays: the committed cordon (needs only the action
confirmation), the wait play, then the restart play, then the committed uncordon
(two confirmations).

- Cost: three applies instead of one; the operator still ends the hold by word.
- Keeps: the hold ends only by consent, never by a clock; the restart play stays
  a pure idle-check-then-restart. The wait play only reads, so it needs no new
  consent rule beyond "reads, changes nothing".
- Spec change: additive only (one new paragraph); no MUST NOT is relaxed.
  `346ays` is rewritten to carry the wait play and drops the cordon and uncordon
  from the restart.

### B. Restart play cordons, waits, restarts, and leaves the node cordoned

The play cordons (permitted for a hold), waits for drain, restarts, and does NOT
uncordon; the operator runs the committed uncordon with both confirmations.

- Cost: lines 571's "MUST NOT cordon" is relaxed for this play, and the play
  creates a hold the operator must remember to end. A play that fails mid-wait
  leaves a hold with no one named as its holder.
- Keeps: line 577 unchanged.
- Spec change: one relaxation in the restart paragraph plus a rule that the play
  names itself as the hold's holder in its output.

### C. Item as filed: cordon, wait, restart, self-uncordon

- Cost: relaxes line 571 and carves a play-owned exception out of line 577's
  "ended only by the word of whoever holds the node". A bounded wait that
  uncordons on expiry is the timer the paragraph forbids. A node that failed to
  restart is uncordoned and takes work again unless the play adds more guards.
- Keeps: nothing of the two paragraphs' intent. Largest blast radius and the
  only option where a clock ends a hold.
- Spec change: two relaxations plus new failure-path rules.

### D. Reject: keep the hand cordon

The coordinator's reversible-host-mutation ruling stands; no code or spec
change. Cost: the 2026-11-09 gap stays open and every window repeats the hand
step, which the spec's committed-play rule says not to do.

## Recommendation

Option A. It closes the gap that caused the item without relaxing either
safety guarantee, and it reuses the ratified cordon and uncordon plays. If the
maintainer wants a one-command window, B is the next best, because it still
leaves the end of the hold to a person.

## What the maintainer needs to answer

One choice: A, B, C or D. On an answer of A or B, the next step is a
`/livespec:propose-change` and revise, then `346ays` is reworked to match and
its tier released. Until then `346ays` stays held with OWNER (this plan's
session) and END CONDITION (the maintainer's ruling plus the ratified revise).
