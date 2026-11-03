## The maintainer's statement of what done means

why is ci so sl ow and expensive . c9verage gates look like culprit. root and non root . is overkill. move one to dschrduled master job. new plan for thus and any other low fruit (maintainer directive, verbatim, 2026-11-03 about 01:0xZ, relayed to this seat by legacy-coordinator-agent)

## Definition of Done assertions derived from that statement

- This plan's research ranks GitHub Actions runner-minutes by workflow and by job over 7 days across the seven fleet repositories (livespec, livespec-dev-tooling, livespec-orchestrator-beads-fabro, livespec-overseer, livespec-driver-claude, livespec-driver-codex, livespec-runtime), gives each job's share of the k3s/ARC churn slots, and names the gh api queries that reproduce every figure.
- On a pull request to livespec-orchestrator-beads-fabro, CI runs the per-file coverage pair under exactly one uid, while the other uid's coverage pair runs in a scheduled workflow on master that files a breakage work item when it fails.
- Every other low-hanging CI cost saving this plan's research measures is carried by a child work item, or by a relay to the repository that owns the workflow, and each carrier names its measured runner-minute saving.
- Over at least 20 pull-request CI runs of livespec-orchestrator-beads-fabro after the coverage move ships, the median runner-minutes per pull-request CI run is below the 7-day baseline recorded in this plan's research.

# Charter: ci-runtime-and-cost

Opened 2026-11-03 by the ci-runtime-and-cost seat at the direction of legacy-coordinator-agent, from the maintainer
directive recorded verbatim above. The Definition of Done assertions are SESSION-DERIVED from that directive (no
attended confirmation; the coordinator answers pickers under R301) and are reported for objection.

## Scope

1. MEASURE FIRST. 7-day GitHub Actions job durations and runner-minutes per workflow and job across the seven fleet
   repositories, read with `gh api --cache` (never a sleep loop), plus each job's share of k3s/ARC churn slots. Rank by
   total cost. Results go in research note 002.
2. FIRST CARRIER. The root/nonroot uid dimension lives in livespec-orchestrator-beads-fabro `.github/workflows/ci.yml`
   (bd-ib-sfa2): check-per-file-coverage and check-coverage each run under both uids, as do check-python and
   check-python-batch. Keep ONE uid's coverage pair on PR CI, chosen from measured value (what each leg uniquely
   catches, its duration, its flake history), and move the other to a scheduled master workflow that files a breakage
   item when red. This removes a gate from PR CI, so it is maintainer-tier under the workflow-edit tiers. The
   maintainer approved this move in the directive above; it is recorded verbatim on the carrier item, and
   `approval:workflow-edit` is set only by the maintainer's own act. The tracked `.livespec-workflow-edit-exemption`
   stays.
3. Then every other low-hanging fruit with measured savings (duplicated jobs, matrix legs re-running identical work,
   missing caches, path-filterable jobs), each filed as a child or a relay, additive where possible.

## Constraints read

- `.ai/fleet-and-secrets.md` before any push under `.github/workflows/`.
- `ci-runner/k3s/.../DERIVATION.md` and `.ai/ci-node-capacity-reads.md` for runner capacity context.
- bd-ib-sfa2's argument: with fail_under = 100, two independently gated uid legs convert a root/non-root divergence
  into a failure. Moving one leg to a scheduled master job keeps that detection, but on master and after merge rather
  than before it; the breakage item is what turns that lag into owned work.
