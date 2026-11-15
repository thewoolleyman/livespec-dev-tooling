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
| S12 | merge_queue rule added to livespec-dev-tooling ruleset 26758787 by API before its carrier PR (5foyvs) landed, under OVERRIDE-THEN-BACKFILL (TICK RECORD 10:58Z) | PR first | drift between the ruleset and the committed guard; livespec-dev-tooling commits staying refused after route (iii) lands | the livespec-dev-tooling commit lock lifted hours sooner |
| S13 | bd-ib-hnj3td (drive arms with `--delete-branch`, fatal on merge-queue repos) HAND-LANDED by this seat's helper, because hold-gmktec wedges the orchestrator factory route and the fix gates that hold's lift (16:44Z); landed as livespec-orchestrator-beads-fabro#5369, merged 18:02:56Z (8ec84818d) on an independent reviewer's PASS, inside v0.333.0 (178069b5c) | a factory run after the lift | a missed DoD bullet (4 factory-captured assertions, Scenario 119); a drive arm still failing on a queue repo after the roll | hours to the hold-gmktec lift (rides the #5350 release instead of a post-lift factory run plus a second release) |
| S14 | One independent reviewer's PASS instead of legacy-coordinator-agent's grade on stale-base and hold-gmktec PRs: seats grade their own, with ONE independent reviewer for spec, workflow and credential changes, and press their own valves (the ~17:4xZ delegation; first used on livespec-orchestrator-beads-fabro#5350, merged 17:37:09Z) | legacy-coordinator-agent's grade | a defect merged on a single-reviewer PASS that a second grade would have caught; a revert or re-do of a PR graded this way | hours of grade wait per PR on the critical path |
| S15 | A credential-role PASS given on livespec-dev-tooling#4803 at 705801be5 before the independent reviewer returned, under INCIDENT-FIRST (incident xyi5vu steps 1-2); the reviewer PASSED ~19:2xZ | wait for the reviewer, then grade | a reviewer finding forcing a re-apply on poweredge-xubuntu; a converge no longer reading changed=0; the reviewer's follow-ups (`follow: false`, python_root 0755) not landing | time to the poweredge apply (changed=0 at 18:39:52Z) and the 19:03Z mint |
| S16 | livespec-dev-tooling-h5r75q (the ARC org credential projection, PR A) hand-landed under incident livespec-dev-tooling-mzbt35 through the expedited lane, while hold-gmktec wedged the factory (it had sat `ready` and unbuilt from 16:32Z) | a factory run after the hold-gmktec lift | the personal Secret hash moving off prefix 2248e7a70706f79f; no org runner within 15 min of the flip; installation 182096616 under ~500 remaining; mzbt35's deferred obligations not backfilled | hours on the critical path to the CI_RUNNER_LABELS / CI_INCIDENT_RUNNER_LABELS flip (about 3 h was already lost waiting, per the 19:14Z scope event) |

Revert or end condition for S12-S16 (each also closes only on the +24 h no-bite
read below):

- S12: ends when the carrier PR has landed and the ruleset reads equal to the
  committed guard. The 16:5xZ handoff records route (iii)'s carrier as
  livespec-dev-tooling#4793, merged ~13:00Z; this epic does not state that #4793
  is 5foyvs's PR, so confirm before closing. Note the same ruleset was changed by
  API again at 19:45:45Z (`max_entries_to_build` 4 to 1) and bit (charter 001,
  the grep-the-readers lesson); that interim is tracked on incident zq2i4c, not
  here.
- S13: ends when the post-roll canary traverses a drive arm in the merge-queue
  repository (canary coverage record on bd-ib-ynnykl, traversal D) without the
  `--delete-branch` failure. Revert (proposed here; the ledger records none):
  re-place hnj3td on the factory if a DoD bullet is found missing.
- S14: ends when stale-base-merge-options (livespec-dev-tooling-xowhol) archives
  or the maintainer says otherwise (the 17:39Z ruling's reading). The maintainer,
  verbatim, 17:39Z: "I have told the legacy overseer that its number one job is
  to support you and finishing stale-base-merge-options.  You should not have had
  to wait on an approval for it.  If it stalls on anything you need YELL AT IT
  UNTIL IT RESPONDS." The ledger records no revert; a bite is routed to
  legacy-coordinator-agent, which made the delegation.
- S15: ends when #4803 merges and its follow-up (the 0775 fix, `follow: false`,
  python_root 0755, the ANSIBLE_PIPELINING README and guard, owned by
  stale-base-merge-options) lands on the fast lane. The ledger records no
  revert for this row; a reviewer finding against the applied role is routed
  to stale-base-merge-options as a bite.
- S16: revert triggers as written in the incident: no runner within 15 min of
  the label flip, or installation 182096616 under ~500 remaining, flips
  CI_RUNNER_LABELS / CI_INCIDENT_RUNNER_LABELS back to `["ubuntu-latest"]`.
  Ends when mzbt35's deferred obligations are backfilled and recorded on the
  incident item.

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
