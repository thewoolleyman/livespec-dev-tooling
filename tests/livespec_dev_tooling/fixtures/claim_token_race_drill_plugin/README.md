# claim_token_race_drill_plugin — a stand-in for the released orchestrator plugin

`tests/livespec_dev_tooling/test_claim_token_race_drill_playbook.py` commits
this tree into a throwaway git repository, tags it, and points
`ansible/claim-token-race-drill.yml` at it, so the committed play clones,
stages and races against a package shaped like the released one without a
Dolt server. The package keeps its records in ONE JSON file named by
`.beads/fake-store-path` (written by the test), under an exclusive lock, so
the two writer processes the play launches contend on a real compare-and-swap
and exactly one of them wins — the same shape `bd close --reason` has on the
server. `bd-guard/` carries the guard shape the play installs in front of the
target's `bd`; nothing here ever runs `bd`.
