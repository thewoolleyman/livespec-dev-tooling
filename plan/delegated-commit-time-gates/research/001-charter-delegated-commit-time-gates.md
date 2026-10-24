## The maintainer's statement of what done means

2026-10-24 ~18:5xZ, verbatim: '0. The pre-push should be enabled on all of the livespec repos and any repo for which a CI image already exists that could be used for this. Why is it only on those two repos? 1. Yes we should delegate this work and go ahead and create a plan and work it in a session. Add this to your queue to get done. This is in the theme of moving the load off of the host onto the cluster. Tell me if there's a reason not to do this. 2. Start a subagent to investigate this further. If it's a good idea and won't break anything, then we should do it but just for the live spec ecosystem. 3. Yes if you're only touching a single test file and not any test helper, and not any other configuration or any other code, then you should be able to run only that test. Make a plan to make this change and drive it too. 4. Before you proceed with the above I want you to first explain to me why we needed to modify a test at all for a configuration-only change. This should not be necessary.'

## Definition of Done assertions derived from that statement

- A commit made from the VPS in a repository opted into delegated gates runs its red-green-replay Red, Green and suite-green test runs as a Job in the cluster's gates namespace against the staged tree, and the VPS runs no pytest for those legs.
- The TDD trailers that commit carries name the gates Job that produced each verdict and the checksum of its output, keyed to the staged tree's hash, so the evidence a local run would have stamped is the evidence the delegated run stamps.
- When the cluster returns no verdict for a commit-time leg, the commit runs that leg locally on the committing host by actually executing that leg's tests, records its trailers from that local run and never from the absent verdict, says so in its output, and is never refused for the cluster's absence alone.
- A commit made from a Fabro sandbox, or from any host that cannot read the gates kubeconfig, runs its commit-time legs locally.

# Charter — delegated-commit-time-gates

## Why

The pre-push gate already delegates to the cluster (contracts.md §"Delegated pre-push gate"), but the commit-time
red-green-replay legs always run pytest on the committing host. On 2026-10-24 a configuration-only commit in
livespec-orchestrator-beads-fabro sat 21+ minutes in its commit-msg hook (the test-only suite-green leg runs the
full suite) before the harness backgrounded it; the push then re-ran the aggregate on the cluster, so the work ran
twice. This plan moves the commit-time test legs onto the cluster. It is in the theme of moving load off the host
onto the cluster (maintainer, below).

## Design constraints

- Same evidence model as the pre-push green token: a verdict is keyed to the staged tree's hash, and the trailers
  record the Job that produced it and its output checksum.
- FALL BACK TO LOCAL, NEVER REFUSE, on no verdict. The pre-push contract refuses a push on no verdict; copying that
  to commits would let one cluster outage stop every commit on the host. A commit has a local path that is always
  correct, so the absence of the cluster degrades speed, not correctness.
- CONFLICT RESOLVED BY COORDINATOR RULING, for the revise to take as a MODIFY: livespec's pending proposal
  delegated-commit-time-gate (PR #2941) applies v229 "The verdict" ("Refusal, not fall-through") to commits. This
  plan departs from that for commits only. A commit-time leg has a local path that produces REAL evidence (it runs
  the test), so falling back to it degrades speed, not correctness. Refusing instead would turn a cluster outage
  into a host-wide commit outage. The limit that holds either way: the fallback actually executes the tests, and a
  TDD-Red (or Green) trailer is never recorded from an absent verdict. Pre-push keeps v229 refusal unchanged.
- Sandboxes and hosts without the gates credential gate locally, exactly as pre-push does.
- Gated on livespec's revise of its pending proposal delegated-commit-time-gate (livespec PR #2941), with the
  trailer-evidence addition, and on this repository ratifying the client contract.

## Carrier

livespec-dev-tooling-sewnfp, re-parented here from the delegated-gate-fleet-rollout plan (livespec-dev-tooling-mvalxq),
which filed it on 2026-10-24.

## Driver

The delegated-gate-fleet-rollout session drives this plan; it owns the gate client and the livespec proposal.

## Derivation note

The assertions were derived by the coordinator session from the maintainer's direction below and created without a
confirmation round under the maintainer's 2026-10-24 direction not to block on prompts; recorded as session-derived
in the first handoff, for objection.
