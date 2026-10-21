# Reading a plan's next action without moving it

`resume_directive(...)` in livespec-orchestrator-beads-fabro is not a pure read.
When it observes the epic's `required_result` as SATISFIED, it treats the pointer
as stale and PERSISTS a derived replacement: a new epoch, a new `next_action`,
and a `plan-progress-event` comment recording both. Nothing errors and nothing
asks. Calling it "to see where the plan is" can therefore move the plan.

## The case that made this matter (2026-10-21, orchestrator v0.229.7)

An `item_comment` required result satisfied ITSELF.
`_plan_result_ledger.py` observes the marker with a substring test over EVERY
comment on the item (`if target.marker not in comment.text`). Every sanctioned
pointer write appends a `plan-progress-event` comment whose payload embeds the
new `required_result`, marker string included. So the moment a pointer awaiting
marker M is written, the ledger already carries M.

On epic `livespec-dev-tooling-mvalxq` this cascaded with no error at any step:

1. 09:12Z, a `plan-resume` write set "await marker `Plan Proof of Done`"
   (event comment `01a15dbb`). That comment itself satisfied the wait.
2. 13:58Z, a session called `resume_directive` to inspect the plan. It read the
   pointer as satisfied and persisted a derived `review` pointer (epoch 19)
   awaiting marker `plan-completeness-review-evidence`. That event comment
   carries the new marker too, so the next read would derive `archive`.

In reality no plan Proof of Done existed and four children were open. The
coordinator accepted a stop-the-line (R476) and routed the fix, fleet-wide, to
fabro-currency.

## How to apply

- To INSPECT a plan, read `bd show <epic> --json` (the `next_action` metadata)
  and `read_timeline(...)`. Call `resume_directive` only when you intend to act
  on its decision.
- Before trusting any `item_comment` required result, check that the
  orchestrator fix for the self-match has shipped in the build this project has
  installed. Until it has, an `item_comment` "satisfied" is not evidence. An
  `item_status` result does not have this flaw.
- Do not hand-correct a falsely advanced pointer. Only a sanctioned writer,
  after the orchestrator owner's ruling, restores it. Hold further pointer
  writes meanwhile: each write emits another comment that can self-match.
