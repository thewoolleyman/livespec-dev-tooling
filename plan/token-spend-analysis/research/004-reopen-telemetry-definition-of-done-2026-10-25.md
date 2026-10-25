# Reopen: the telemetry must answer account-burn questions (2026-10-25)

The maintainer reopened this plan on 2026-10-25 after it failed the first real question put to it.

## What happened

At about 15:50Z the maintainer asked why anthropic-6 was burning so fast. caam had selected it at 15:37:29Z with 5h 100% and 7d
100%; by the 15:53Z read it stood at 5h 71% and 7d 95%. The capacity coordinator routed the question to this plan: which
consumers spent anthropic-6 since 15:37Z, and how much each.

The plan's telemetry could not answer it:

- `livespec/claude-code` (factory Claude spans) carries no account field, and its column metadata showed no write since 13:20Z.
- `livespec/token-spend-local` showed no write since 2026-10-18. The local emitter had moved to `livespec/llm-spend` (research
  001), but nothing recorded the old dataset as retired, and nothing alarms when a feeding source goes quiet.
- No dataset records which account a response billed, so the question "who spent account X" has no direct query.

The session that owned the plan then started parsing transcripts by hand instead of fixing the telemetry. The maintainer called
that out: the whole point of the plan was that these answers come from Honeycomb, instantly.

The archived Definition of Done (research 001) asked for board pie charts and a running timer. It never asked that the telemetry
answer an account-attribution question, reconcile with caam, or announce its own staleness, so the archive passed while the
capability the maintainer wanted did not exist. Those four assertions stay; the ones below are added.

## The maintainer's statement, verbatim

"Why is the burn so fast? I'm already at 95% on the new account." / "maintainer here - the burn rate seemshigh - I just
provisioned -6 account and already 5% is gone.  WHY so fast?" / "Are you using Honeycomb observability to answer this question?
If not, why not? That was the whole point of your plan to set that up. You should get these answers instantly." / "Why the fuck
do you think it was okay to just ignore telemetry failures rather than fixing it, when that is literally the point of your
fucking plan?" / "We need to get you back on track so I can trust you..  You need to first rewrite your plan with a definition
of done so the Honeycomb telemetry actually fucking works and is automatically usable to answer these sorts of questions." /
"No, you can reopen this fucking plan because it's not done correctly."

## Definition of Done assertions added (5–11)

Assertions 1–4 from research 001 stand unchanged.

5. Every Claude and Codex LLM response, from the factory or from this host, lands in one `livespec` Honeycomb dataset as an
   event naming the account it billed (caam profile), the consumer (factory dispatch and workflow node, local session name and
   project, or ad-hoc `claude -p` subprocess), the model and effort, and tokens and USD.
6. One saved Honeycomb query, linked from the board, answers "which consumers spent account X since time T, and how much each"
   in under a minute, with no transcript parsing.
7. A response from any consumer appears in Honeycomb within 10 minutes, and the measured ingest lag is shown on the board.
8. For any hour, Honeycomb's per-account spend reconciles with caam's measured 5h and 7d drop for that account within a stated
   tolerance, and the board shows that reconciliation, so a coverage gap is visible.
9. A Honeycomb trigger alerts a named recipient when any feeding source — local emitter, factory Claude spans, Codex spans, caam
   reads — goes quiet past a stated threshold.
10. Assertions 5–9 keep holding with no session running and across a host reboot.
11. The question "who spent anthropic-6 since 2026-10-25T15:37:29Z, and how much each" is answered from Honeycomb, and that
    answer is delivered to the maintainer and to the capacity coordinator (gitops-fleet-capacity-monitoring, epic
    livespec-dev-tooling-dfixhe).

All are `host_captured`.
