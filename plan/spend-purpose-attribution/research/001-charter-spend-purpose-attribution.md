## The maintainer's statement of what done means

Yes I approve both of the proposed plans. Go ahead and, under my mandate, define whatever makes sense from your research. Get them both started and running under the coordinator's supervision.

## Definition of Done assertions derived from that statement

- Every claude -p response sent to the Honeycomb llm-spend dataset after the fix carries a spend.purpose naming the role that launched it (for example judge, replayer, completeness reviewer or research), and on any full day after the fix less than 5% of claude -p cost carries no purpose.
- Every local session response sent to llm-spend after the fix carries the plan slug or work-item id its session works under, or a named standing role such as coordinator or overseer, and on any full day after the fix less than 10% of local session cost carries none of them.
- Every factory spend event sent to llm-spend after the fix carries the plan slug of the plan epic its work item belongs to, when it belongs to one.
- One Honeycomb query returns a day's spend per plan, summed across local sessions, claude -p and factory runs, and the llm-spend board shows that breakdown.
- Every local session response sent to llm-spend after the fix carries its context size in tokens, and the first response after a compaction is marked, so one query shows when and by how much a seat's context dropped.

# Charter: spend-purpose-attribution

Opened 2026-10-31 by the token-spend-analysis session (attended), on the maintainer's approval of the two plans proposed
from the 2026-10-31 audit of the coordinator's token-spend work. The assertions above are SESSION-DERIVED under the
maintainer's mandate ("define whatever makes sense from your research") and are reported to the maintainer for objection.

## Why (measured 2026-10-31, Honeycomb env livespec, dataset llm-spend)

- Local seats are the largest sink: about $5.7k over 7 days, about $107/h on 2026-10-31. The data names the seat
  (session.name), but nothing ties a seat to the plan or work item it serves, so "what did plan X cost" has no answer.
  The coordinator's own seat cost $505 over 7 days and nobody was watching it.
- claude -p is about $2.2k over 7 days. It is attributed only by working directory, so judges, replayers, completeness
  reviewers and research runs cannot be told apart. The audit could not check the coordinator's 55vxu5 judge claim
  (118k to 10.5k context per judgement) fleet-wide for this reason: per-response context only moved 108k to 86k.
- No context-size column or compaction marker exists. petri's auto-compaction at about 08:15Z (about 950k to 29k context,
  about $20 to $7 per two hours) was the day's largest real saving and went uncredited; it was found only by hand.

## Leads for scoping

- Seat names already often equal plan slugs (token-spend-analysis, factory-context-per-turn-reduction,
  llm-spend-pricing-correctness); a map from session.name to plan/ directories across the fleet repos may cover most seats.
- claude -p launches come from a small set of launchers (judge nodes, replayer and reviewer briefs, research runs); a
  purpose tag set by each launcher and recorded where the emitter can read it is the likely shape.
- Context size per response is input + cache_read + cache_creation tokens, already in each transcript record.

## Not in scope

- Price and cache-split correctness of factory events: plan factory-spend-accuracy.
- Unlisted-model pricing: plan llm-spend-pricing-correctness.
