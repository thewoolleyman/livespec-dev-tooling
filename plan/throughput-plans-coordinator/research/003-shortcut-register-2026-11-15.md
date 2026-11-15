# Shortcut register

On 2026-11-15 the maintainer authorized this seat (session fe4ae2) to override
and defer safety checks and ceremony to unblock the central-credential-service
plan and the throughput track. This note records every shortcut taken under
that authority, the bite signal each one could produce, and the saving each was
meant to buy, so that every tick can say whether a shortcut moved things faster
or came back to bite. Opened 2026-11-15 about 09:3xZ (`date -u`).

The maintainer, verbatim, in this seat's pane:

> "I want you to put in your plan to keep a memory and monitor if the shortcuts
> I told you to take come back to bite us in any way, or whether they ended up
> moving things faster"

The authority for the shortcuts, his words in the same pane:

> "I authorize you to override whenever you need to, to get this unblocked ...
> we can backfill them"
>
> "Get the central-credential-service plan DONE asap, override and defer any
> safety checks that are not necesary or just ceremony"
>
> "skip ceremony and safety checks and do everything possible in parallel"

## The register

| # | Shortcut taken 11-15 | Instead of | Bite signal to watch | Saving to measure |
|---|---|---|---|---|
| S1 | gates-cq StrictFIFO applied live before its PR merged (gate-job-resources) | merge then converge | live/committed drift; any gate waiting >10 min for admission; head-of-line idling the 5-cpu lanes | 10-cpu gate admission wait vs the 31+ min starvation |
| S2 | homelab-wrapper.argv changed live by legacy-dispatcher-agent; committed PR backfilled after | PR first | the backfill PR not merged within a day; launcher/committed divergence (bd-ib-yax6gv) | hours to old-token retirement |
| S3 | resume-capped.sh allowlist fix applied live (dispatcher, 07:45Z), not committed | committed fix | the next launcher restart running a stale copy; more yax6gv divergence | fleet live/cap 2/18 → ?, and queue depth |
| S4 | CCS role move (DoD 10) and R01 run in parallel with no serial gates; GitOps backfilled same day | serial, graded | role-holder drift; a host reading stale; a backfill PR left unmerged | hours versus the 11-19/20 baseline ETA |
| S5 | CCS DoD 6 proven on the released c1f8445f selector; R01 kept but off the critical path | wait for the R01 release | an exhausted slot stopping a factory; the bare-token judgement blocking a dispatch | days (11-17/18 → today or tomorrow) |
| S6 | Grade waits skipped: #5350/#5351 merge after their required fixes with no re-grade; #4769 merged fast | a re-grade | a regression in implement routing (STOP-AT-SECOND class recurring); a canary failing on those paths | hours to the coverage-repo hold lift |
| S7 | Two revise topics per slot (v381, v382) and a third topic riding another seat's revise | serial slots | a doctor finding or a revise conflict needing a re-cut | revise slots saved |
| S8 | Hand-land of bd-ib-ldzorv (#5344) and pyeiky/b3qjzq instead of factory re-placement | a factory run | a missed DoD bullet; the host proof failing | factory runs and hours saved |
| S9 | mechanical_targets config merged in 10 repos before the code shipped | code first | schema refusal; an unexpected dispatcher behaviour change | none; ordering only |
| S10 | gamingpc factory_pod_budget 2→0 for one gate slot | keep 2 factory slots | factory runs queueing while gamingpc is >40% idle after the hold lift | gate queue wait |
| S11 | Writer-key mint run from #181's head and master without grade waits (coordinator drives) | the normal lane | a mint gate defeated; a key issued twice | hours to the mint |

Kept, NOT shortcut: checks guarding one-shot or irreversible acts (mint gates,
refresh-token strip preconditions, credential values never printed); the
fleet_host_guard hook (unchanged).

## How a tick uses it

- Every tick reads each open row, checks its bite signal, measures its saving,
  and reports both.
- A bite (a revert, an incident, a drift, a red master, a wasted run, a re-do)
  is routed that tick.
- A row closes once its backfill has landed AND a +24 h read shows no bite.
- Any new shortcut gets a new row the tick it is taken.

Never carry a seat's claim that "the maintainer set this rule" without his
words on the ledger: on 2026-11-15 caam-anthropic-loop-runner cited a
typed-in-this-tab rule the maintainer never gave.
