# Report item keys (2026-11-13 throughput report). THE TRACK'S ONE METRIC: PRs per repo per hour merged to main and green.
Yield (48% of 788 factory runs succeed):
- Y1 assertions the sandbox cannot prove (needs push / live ledger tenant / missing toolchain / other repo); lever: file as host-proved, make filing check REFUSE (today advisory)
- Y2 scripts time out at 60-80 min in refresh and gate steps
- Y3 rebase conflicts from a stale base
- Y4 gate check failures inside runs
- Y5 review_fix runs out of attempts with Red commit open / Green amend never committed (checkpoint commit on top of Red)
Cycle time (median run 101 min; implement 75% of agent time; full suite runs 4-5x per change):
- C1 run the full suite ONCE per change: affected-tests-only in implement/pre-push/PR CI, one full coverage run guarding master (NOT GitHub merge queue); coverage is 71% of CI job time
- C2 don't re-run a gate on a tree that already passed (verdict reuse per tree hash, pre-commit -> pre-push); 9% of gate runs
- C3 shrink the suite: cut tests that kill no mutants, integration-heavy test files; ration the mutation matrix (591k CPU-s/week)
- C4 implement-turn duration / per-commit gate duration (11-21 min) itself
Contention (gmktec, poweredge, hp at high CPU pressure; gamingpc 85% idle; dev host vmi3006760 most pressured):
- N1 put gamingpc idle capacity to work (CI slots, gate lane, factory lane)
- N2 new capacity (added nodes) goes to gates and factory first; node pressure
- N3 dev host vmi3006760 (VPS) pressure: sessions, dispatcher, local gates
Measurement gaps:
- M1 factory failure category empty (closed set needed) (bd-ib-2h6cfl)
- M2 factory CPU by repository / stage not recorded
- M3 gate durations not recorded on gate outcome events
- M4 PR-side CI runs per change; CI durations (wrapped durations bug bt2cnw; pod CPU panel overcount ja7bv4)
- M5 the throughput metric itself + Honeycomb board panel
Other:
- G1 shared GitHub identity REST budget exhaustion from polling (gh run watch etc.) stalls factory launches
- X  anything else that directly limits PRs merged green per hour (e.g. merge holds, auto-merge, red master, flaky tests, credential/quota outages, dispatcher idle with ready work)
