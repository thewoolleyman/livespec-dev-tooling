---
topic: arm-on-green-automation-honours
author: claude-opus-5-5 (seat ci-runtime-and-cost)
created_at: 2026-11-14T06:30:00Z
---

## Proposal: Arm-on-green automation honours a merge-quiet marker, and the release guard watches the release PR however many PRs are open

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a merge-quiet rule to non-functional-requirements.md section "Commit and merge discipline". A fleet member's merge-quiet window is a marker on that member, set and removed without a merge. While the marker is present, no automation arms auto-merge on any of the member's pull requests, readies one, or merges one: not the release guard, not the auto-enable-merge workflow, not a seat's loop. Removing the marker resumes arming on the next pass. The release guard MUST find and watch the member's release-please pull request however many pull requests are open. Two scenarios state this. This is the behaviour livespec-dev-tooling-lunexo (retro guard G8) implements.

### Motivation

On 2026-11-14 legacy-coordinator-agent held livespec-dev-tooling master for incident asxhj3 (livespec-dev-tooling#4629) and opened a merge-quiet window at about 04:32Z, announced by ledger comments.

- The interim release guard (release-guard.service on the VPS) logged "livespec-dev-tooling#4636 bc5d1fc PASS-ARMED" at 04:43:52Z. It armed auto-merge on the dev-tooling release-please pull request inside the window, because nothing it reads says a window is open. It re-arms on every new release-please head.
- Seats that ran `gh pr ready` on a passing grade also breached the window, because on this repository readying a pull request arms it.
- At 06:07Z the guard logged "ERROR more than 100 open PRs: a release PR beyond the newest 100 is NOT watched". livespec-dev-tooling had 102 open pull requests. The release-please PR was rank 14 and still watched, but only by luck.

A ledger comment is a human channel. Automation cannot read it, so a window that depends on every actor reading it fails silently.

The marker is a property, not a committed file. A file on the default branch cannot be added while that branch is held, because adding it is itself a merge. So the marker MUST be settable and removable without a merge into the held repository, and readable by GitHub Actions and by a host script without a ledger call. This proposal states that property and leaves the concrete form (for example a repository variable) to the implementing change.

The retro is the scope event on livespec-dev-tooling-r7iuj6. throughput-plans-coordinator directed this filing, and plan ci-runtime-and-cost (epic livespec-dev-tooling-ib3oe3) carries it.

### Proposed Changes

In non-functional-requirements.md section "Commit and merge discipline", append this paragraph:

> **A merge-quiet window stops every automatic arm.** A coordinator holds a fleet member's merges by setting that member's merge-quiet marker. The marker MUST be settable and removable without a merge into the member, and readable by GitHub Actions and by a host process without a ledger call. While the marker is present, no automation acting on that member — the release guard, the auto-enable-merge workflow, or an agent session's loop — MAY enable auto-merge on, ready, or merge any of its pull requests. Each MUST instead record that it skipped because of the marker. When the marker is removed, those automations MUST resume arming on their next pass, with no further action. The release guard MUST find and watch the member's release-please pull request however many pull requests are open, and it MUST NOT depend on that pull request being among the newest 100.

In scenarios.md, add these two scenarios:

## Scenario: no automation arms a pull request while a fleet member's merge-quiet marker is present

Given a fleet member whose merge-quiet marker is present

And its release-please pull request has a new head whose release diff is clean

When the release guard and the auto-enable-merge workflow each take their next pass

Then neither MUST enable auto-merge on any of that member's pull requests

And each MUST record that it skipped because of the merge-quiet marker

And when the marker is removed, the release guard MUST arm that release-please pull request on its next pass

## Scenario: the release guard watches the release pull request when more than 100 pull requests are open

Given a fleet member with more than 100 open pull requests, whose release-please pull request is older than the newest 100

When the release guard takes its next pass

Then it MUST find that release-please pull request and judge its release diff

And it MUST NOT report the release pull request as unwatched

The revise that ratifies this MUST add rows for both new scenario headings to tests/heading-coverage.json, owned by livespec-dev-tooling-lunexo, and regenerate the debt register in the revise commit.
