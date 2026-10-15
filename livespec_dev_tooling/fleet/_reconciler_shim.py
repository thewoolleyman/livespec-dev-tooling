"""The canonical master-health reconciler shim every fleet repository carries.

Child D of plan `red-master-self-healing` (epic `livespec-dev-tooling-zcp5vb`,
work-item `livespec-dev-tooling-dw7dzd`) — the DISTRIBUTION half of the
reconciler whose pure decision core child C1 shipped under
`livespec_dev_tooling/cross_repo/master_health_*.py` and whose decisions
`docs/master-health-reconciler.md` records.

THE SHIM IS DATA, NOT A FILE IN THIS TREE. It is the body `wire-fleet-member`
writes into a MEMBER repository at `MASTER_HEALTH_WORKFLOW`, so it lives here
as the one canonical rendering source: the install path and the conformance row
that convicts drift both read it, and a shim committed in a member repo that
differs from this body by one byte is a finding rather than a surprise. Charter
item 6 is what forbids the alternative — the shim is never configured by hand.

THE `uses:` REFERENCE AND THE WORKFLOW IT NAMES ARE ONE EDIT. The reusable
workflow's path is `REUSABLE_RECONCILER_WORKFLOW` and the shim interpolates it,
so renaming the central workflow cannot leave the fleet's shims pointing at a
path that no longer resolves.
"""

from __future__ import annotations

__all__: list[str] = [
    "MASTER_HEALTH_WORKFLOW",
    "RECONCILER_SHIM_TEMPLATE",
    "REUSABLE_RECONCILER_BODY",
    "REUSABLE_RECONCILER_WORKFLOW",
    "reconciler_shim_content",
]


# The member-side shim's committed path, and the central reusable workflow it
# calls. Both are the `uses:` JOIN between a member repo and this one, so each
# is a semver-stable identifier per `SPECIFICATION/contracts.md` section
# "Reusable workflows wire contract": renaming either breaks every member that
# has already been wired, silently, at trigger time rather than at install time.
MASTER_HEALTH_WORKFLOW = ".github/workflows/master-health-reconcile.yml"
REUSABLE_RECONCILER_WORKFLOW = ".github/workflows/reusable-master-health-reconcile.yml"

# The canonical shim body, as authored. `{owner}` is the member's own owner
# (resolved from its git remote by `wire-fleet-member`), never a hardcoded
# `thewoolleyman`, so a fork of the fleet reaches its own copy of the reusable
# workflow. The `@master` ref is the bootstrap-discipline ref the sibling
# pin-and-bump shims use; the bump-pin automation rewrites it to a tag on the
# next release.
_RECONCILER_SHIM_SOURCE = """\
# master-health-reconcile.yml — the red-master self-healing reconciler shim.
#
# Installed by wire-fleet-member per livespec-dev-tooling
# SPECIFICATION/contracts.md §"Reusable workflows wire contract"; the mechanism
# is plan/red-master-self-healing (epic livespec-dev-tooling-zcp5vb), child D.
#
# ⛔ NEVER EDITED BY HAND IN A MEMBER REPOSITORY. wire-fleet-member writes this
# body and the fleet conformance row `workflow-master-health-reconcile` convicts
# any repository whose copy differs from it by one byte.
#
# THREE TRIGGER FAMILIES, each covering what the others cannot:
#
#   - workflow_run on the CI workflow's COMPLETION is the EDGE that puts the
#     reconciler on a red branch within one CI cycle rather than within one
#     tick. It selects the workflow by its `name:` value, which is `CI` across
#     this fleet. A member that renames its CI workflow loses only the edge —
#     the schedule below still reaches every episode, one tick later.
#
#   - the pull_request family carries BOTH revert-side facts the decision
#     reads: the revert pull request's own CI verdict, which arrives with its
#     lifecycle events, and the fix-forward CLAIM, which is a LABEL on that
#     pull request and so arrives only as labeled / unlabeled. Dropping the
#     label events would leave a claimed fix-forward invisible, and the
#     reconciler would release a revert the claim was holding.
#
#   - the five-minute schedule is the MISSED-EVENT COVER and the deadline
#     clock. An event that never fired, a run that crashed mid-step, and the
#     hard cap on a red episode all need a tick that arrives whatever else
#     happened. Five minutes is GitHub's finest schedule granularity, so it is
#     both the floor and the requirement.
#
# workflow_dispatch is here for the scheduled end-to-end revert drill, which
# must be able to run the whole path against a throwaway branch on demand.

name: Master health reconcile

on:
  workflow_run:
    workflows: [CI]
    types: [completed]
  pull_request:
    types: [opened, reopened, synchronize, labeled, unlabeled, closed]
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch: {{}}

jobs:
  reconcile:
    uses: {owner}/livespec-dev-tooling/{workflow}@master
    secrets: inherit
"""


# The template `_reconcile_shims` PUTs and `reconciler_shim_content` renders —
# ONE string, so the install path and the drift-detecting conformance row can
# never disagree about what the canonical bytes are. The `{workflow}` slot is
# resolved HERE rather than left to each caller: the reusable workflow's path is
# a property of this repository, not of the member being wired, and only
# `{owner}` is.
RECONCILER_SHIM_TEMPLATE = _RECONCILER_SHIM_SOURCE.replace(
    "{workflow}", REUSABLE_RECONCILER_WORKFLOW
)


def reconciler_shim_content(*, owner: str) -> str:
    """The canonical reconciler shim body rendered against `owner`."""
    return RECONCILER_SHIM_TEMPLATE.format(owner=owner)


# The canonical body of this repository's OWN reusable reconciler workflow —
# the central half of the distribution, which every member's shim calls.
#
# ⛔ AUTHORED HERE RATHER THAN AS A COMMITTED WORKFLOW FILE, and the reason is a
# boundary rather than a preference: a FACTORY branch may not create or modify
# anything under `.github/workflows/` (the dispatch credential carries no
# `workflows` grant, and `check-no-workflow-edits` enforces it), so the body is
# authored where the branch may carry it and the committed file lands
# maintainer-side from this text. `tests/livespec_dev_tooling/fleet/
# test_reconciler_shim.py` applies a proven byte-comparator to the committed
# path, so from the moment the file lands the two cannot drift.
REUSABLE_RECONCILER_BODY = r"""
# reusable-master-health-reconcile.yml — the red-master self-healing reconciler.
#
# Authority: plan/red-master-self-healing/research/001-charter-red-master-self-
#   healing.md (epic livespec-dev-tooling-zcp5vb), approved design items 2, 3
#   and 6; docs/master-health-reconciler.md records the decisions child C1 took.
#   Called by each fleet member's `master-health-reconcile.yml` shim, which
#   wire-fleet-member installs and the `workflow-master-health-reconcile`
#   conformance row keeps byte-honest.
#
# WHAT ONE RUN DOES. It RECORDS current forge truth about the watched branch,
# asks the pure decision core for AT MOST ONE next step, and performs that one
# step. It holds no durable state: GitHub is the state, so a crashed run loses
# nothing, a missed run only delays the step, and a duplicate run recomputes a
# step whose effect the first run has already removed from the table.
#
# WHY GITHUB-HOSTED RUNNERS, AND IT IS LOAD-BEARING. The self-hosted k3s pool
# can itself BE the failure the reconciler is healing. A reconciler queued
# against a broken pool never runs, which is exactly the moment it is needed, so
# `runs-on: ubuntu-latest` is a requirement of the design and never a default to
# be "optimised" onto fleet capacity.
#
# WHY THE FLEET APP TOKEN AND NOT `github.token`. Two independent reasons. A
# pull request opened or merged with GITHUB_TOKEN does NOT trigger CI, and this
# workflow exists to open a revert whose own CI must speak before it may land —
# with GITHUB_TOKEN that revert would sit forever with no verdict. And the
# auto-merge mutation needs admin-level access that `github-actions[bot]` lacks
# regardless of declared `permissions:`, which is the finding
# auto-enable-merge.yml already records.
#
# WHERE THE DECISION IS, AND IS NOT. The modules under
# livespec_dev_tooling/cross_repo/master_health_*.py are network-I/O-free, and a
# test walks their AST to keep them so; `master_health_state.py` records the
# consequence — "the gathering lives in the reusable workflow". That is this
# file. Every judgement, including which commit is the culprit and whether a
# revert may be released, is made by `master_health_step` over the recording.
# Nothing in the shell below branches on forge state.

name: reusable-master-health-reconcile

on:
  workflow_call:
    inputs:
      target_branch:
        description: >-
          The branch to keep green. A PARAMETER rather than the literal
          `master` so the scheduled end-to-end drill can exercise the whole
          path against a throwaway branch instead of reddening a real master.
        required: false
        type: string
        default: master
      window:
        description: >-
          How many commits of the watched branch to record. The culprit rule
          walks parent links inside this window and REFUSES to act when the
          window is truncated, so a larger value buys patience, never a guess.
        required: false
        type: number
        default: 30
      ci_workflow:
        description: >-
          The CI workflow FILE whose per-commit conclusion is the branch's
          verdict. A file name rather than a display name because the Actions
          API addresses workflows by file.
        required: false
        type: string
        default: ci.yml
      infra_outage_markers:
        description: >-
          Newline-separated substrings that identify a failure as an
          infrastructure OUTAGE rather than a regression. They are committed
          configuration because the alternative is asking a model to judge the
          failure text, and no LLM may reach this decision path.
        required: false
        type: string
        default: |
          No runner matching the labels
          The job was not acquired by a runner
          received request to deprovision
          unauthorized: authentication required
          error parsing HTTP 429 response body

permissions:
  actions: write
  contents: read
  issues: write
  pull-requests: write

concurrency:
  # One reconcile per repository and branch at a time, and NEVER
  # cancel-in-progress: a cancelled run that had already opened a revert would
  # leave the forge in a state the next run reads correctly but no operator can
  # explain. Queuing is the right behaviour for an at-most-one-step reconciler.
  group: master-health-reconcile-${{ github.repository }}-${{ inputs.target_branch }}
  cancel-in-progress: false

jobs:
  reconcile:
    name: master-health-reconcile
    runs-on: ubuntu-latest
    steps:
      - name: Mint the fleet App installation token
        id: app-token
        uses: actions/create-github-app-token@v3
        with:
          client-id: ${{ secrets.APP_ID }}
          private-key: ${{ secrets.APP_PRIVATE_KEY }}

      - name: Checkout the livespec-dev-tooling decision modules
        uses: actions/checkout@v5
        with:
          repository: thewoolleyman/livespec-dev-tooling
          path: .livespec-dev-tooling
          fetch-depth: 1

      - name: Record current forge truth about the watched branch
        env:
          GH_TOKEN: ${{ steps.app-token.outputs.token }}
          REPO: ${{ github.repository }}
          BRANCH: ${{ inputs.target_branch }}
          WINDOW: ${{ inputs.window }}
          CI_WORKFLOW: ${{ inputs.ci_workflow }}
          MARKERS: ${{ inputs.infra_outage_markers }}
        run: |
          set -euo pipefail

          # The commit window, newest first. `parent_sha` is what the culprit
          # rule walks — ancestry is read from the field, never from position.
          gh api "repos/${REPO}/commits?sha=${BRANCH}&per_page=${WINDOW}" --jq '
            [ .[] | { sha: .sha,
                      parent_sha: (.parents[0].sha // ""),
                      subject: (.commit.message | split("\n")[0]) } ]' > commits.json

          # Every CI run on the branch in ONE read. A commit with no run at all
          # is PENDING — undecided, not green — and `run_attempt` is how "have
          # this episode's failed jobs already been re-run once?" is answered
          # without the reconciler remembering anything between runs.
          runs_path="repos/${REPO}/actions/workflows/${CI_WORKFLOW}/runs"
          gh api "${runs_path}?branch=${BRANCH}&per_page=100" \
            --jq '[ .workflow_runs[] | { head_sha, conclusion, run_attempt, id } ]' > runs.json

          # The failing CHECK names per red commit are the failure SIGNATURE the
          # classifier compares across commits. Only red commits are read, so
          # this loop is one call per commit in the red block, not per window.
          echo '{}' > signatures.json
          red_shas=$(jq -r '[ .[] | select(.conclusion == "failure") | .head_sha ]
                             | unique | .[]' runs.json)
          for sha in ${red_shas}; do
            signature=$(gh api "repos/${REPO}/commits/${sha}/check-runs?per_page=100" \
              --jq '[ .check_runs[]
                      | select(.conclusion == "failure")
                      | .name ] | sort | join(",")')
            jq --arg sha "${sha}" --arg signature "${signature}" \
              '. + {($sha): $signature}' signatures.json > signatures.next.json
            mv signatures.next.json signatures.json
          done

          # Failing checks seen OUTSIDE this branch. A failure that also appears
          # here is not attributable to the merge under suspicion, which is one
          # of the three ways a red branch is classified as something no revert
          # would fix. Capped at ten open pull requests: this is a safety net,
          # and an unbounded sweep would make the reconciler the slow step.
          echo '[]' > unrelated.json
          for head in $(gh api "repos/${REPO}/pulls?state=open&per_page=10" --jq '.[].head.sha'); do
            gh api "repos/${REPO}/commits/${head}/check-runs?per_page=100" \
              --jq '[ .check_runs[] | select(.conclusion == "failure") | .name ]' > head-checks.json
            jq -s 'add | unique' unrelated.json head-checks.json > unrelated.next.json
            mv unrelated.next.json unrelated.json
          done

          # The revert pull request already in flight, if any. GitHub's own
          # revert branches are named `revert-<number>-<branch>`, which is what
          # ties a revert back to the pull request it reverts. The ref is
          # matched as a SHAPE rather than split on `-`: a hand-made branch
          # called `revert-something` would otherwise reach `tonumber` and take
          # the whole recording down with it. The fix-forward
          # CLAIM is a label on that pull request; only its presence is recorded
          # here, because judging a claim's PROGRESS is child C2's work.
          gh api "repos/${REPO}/pulls?state=open&per_page=100" --jq '
            [ .[]
              | select(.head.ref | test("^revert-[0-9]+-"))
              | { number: .number,
                  reverts_pull_request: (.head.ref
                                         | capture("^revert-(?<n>[0-9]+)-").n
                                         | tonumber),
                  auto_merge_armed: (.auto_merge != null),
                  fix_forward_claim: ([ .labels[].name
                                        | select(startswith("fix-forward")) ] | first) }
            ] | first // null' > revert.json

          revert_number=$(jq -r '.number // empty' revert.json)
          if [ -n "${revert_number}" ]; then
            revert_head=$(gh api "repos/${REPO}/pulls/${revert_number}" --jq '.head.sha')
            revert_checks="repos/${REPO}/commits/${revert_head}/check-runs?per_page=100"
            revert_conclusion=$(gh api "${revert_checks}" --jq '
              [ .check_runs[] | .conclusion ]
              | if length == 0 then "pending"
                elif any(. == "failure" or . == "timed_out" or . == "cancelled") then "failure"
                elif all(. == "success" or . == "skipped" or . == "neutral") then "success"
                else "pending" end')
            jq --arg conclusion "${revert_conclusion}" '. + {ci_conclusion: $conclusion}' \
              revert.json > revert.next.json
            mv revert.next.json revert.json
          fi

          # The needs-attention issues already open. Their TITLES travel rather
          # than parsed episode keys: `master_health_step` owns the title
          # convention, so one implementation answers both "does this episode
          # already have an issue?" and "what is a new one called?".
          issues_path="repos/${REPO}/issues?state=open&per_page=100"
          gh api "${issues_path}&labels=master-health-needs-attention" \
            --jq '[ .[].title ]' > issue-titles.json

          jq -n \
            --arg branch "${BRANCH}" \
            --arg markers "${MARKERS}" \
            --slurpfile commits commits.json \
            --slurpfile runs runs.json \
            --slurpfile signatures signatures.json \
            --slurpfile unrelated unrelated.json \
            --slurpfile revert revert.json \
            --slurpfile titles issue-titles.json '
            ($runs[0] | group_by(.head_sha)
                      | map({key: .[0].head_sha,
                             value: (max_by(.run_attempt))}) | from_entries) as $bysha
            | {
                target_branch: $branch,
                infra_outage_markers: ($markers | split("\n") | map(select(length > 0))),
                head_sha: ($commits[0][0].sha // ""),
                rerun_outcome: (
                  [ $commits[0][] | $bysha[.sha] // empty
                    | select(.run_attempt > 1) ] as $reran
                  | if ($reran | length) == 0 then "not-attempted"
                    elif any($reran[]; .conclusion == "failure") then "still-red"
                    else "passed" end),
                commits: [ $commits[0][] | {
                  sha: .sha,
                  parent_sha: .parent_sha,
                  pull_request: ((.subject
                                   | capture("\\(#(?<n>[0-9]+)\\)$").n
                                   | tonumber) // null),
                  ci_conclusion: (($bysha[.sha].conclusion) // "pending"),
                  failure_signature: (($signatures[0][.sha]) // null)
                } ],
                revert_pull_request: ($revert[0] // null),
                needs_attention_issue_titles: $titles[0],
                unrelated_failure_signatures: $unrelated[0]
              }' > state.json

      - name: Decide the ONE step this run takes
        run: |
          set -euo pipefail
          export PYTHONPATH=.livespec-dev-tooling
          python3 -m livespec_dev_tooling.cross_repo.master_health_step \
            --state state.json --step-out step.json
          jq -r '"step=\(.kind) reason=\(.reason)"' step.json

      - name: Perform the ONE step
        env:
          GH_TOKEN: ${{ steps.app-token.outputs.token }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail
          kind=$(jq -r '.kind' step.json)
          reason=$(jq -r '.reason' step.json)

          case "${kind}" in
            none)
              echo "nothing owed: ${reason}"
              ;;
            rerun-failed-jobs)
              # The cheap bounded classifier that separates a flake from a
              # genuine regression. Once per episode: the recording reports
              # `run_attempt`, so a second tick reads this as already attempted.
              run_id=$(jq -r '[ .[] | select(.conclusion == "failure") ] | first | .id' runs.json)
              gh run rerun "${run_id}" --repo "${REPO}" --failed
              ;;
            open-revert)
              # GraphQL `revertPullRequest`, with auto-merge HELD. The hold is
              # the gap in which classification and the revert's own CI get to
              # speak, and `auto_merge_held` travels as data so this step cannot
              # arm auto-merge by omission.
              test "$(jq -r '.auto_merge_held' step.json)" = "true"
              culprit=$(jq -r '.culprit_pull_request' step.json)
              pr_node=$(gh api "repos/${REPO}/pulls/${culprit}" --jq '.node_id')
              gh api graphql -f query='
                mutation($pr: ID!, $title: String!, $body: String!) {
                  revertPullRequest(input: {pullRequestId: $pr, title: $title, body: $body}) {
                    revertPullRequest { number url }
                  }
                }' -f pr="${pr_node}" \
                   -f title="revert: #${culprit} reddened $(jq -r '.target_branch' step.json)" \
                   -f body="Opened by the master-health reconciler. ${reason}"
              ;;
            release-revert)
              # Reached only when the revert's own CI is green and nothing is
              # claimed. Rebase strategy, matching the fleet's merge discipline.
              gh pr merge "$(jq -r '.revert_pull_request' step.json)" \
                --repo "${REPO}" --auto --rebase
              ;;
            needs-attention)
              # One issue per EPISODE, open-or-update rather than open-again. The
              # label is the JOIN with whatever reads the screen, so renaming it
              # silently empties that reader instead of erroring.
              title=$(jq -r '.needs_attention_title' step.json)
              open_issues="repos/${REPO}/issues?state=open&per_page=100"
              existing=$(gh api \
                "${open_issues}&labels=master-health-needs-attention" \
                --jq "[ .[] | select(.title == \"${title}\") | .number ] | first // empty")
              if [ -n "${existing}" ]; then
                gh issue comment "${existing}" --repo "${REPO}" --body "${reason}"
              else
                gh issue create --repo "${REPO}" --title "${title}" \
                  --label master-health-needs-attention --body "${reason}"
              fi
              ;;
            *)
              echo "::error::unrecognised reconcile step ${kind}"
              exit 1
              ;;
          esac
""".lstrip("\n")
