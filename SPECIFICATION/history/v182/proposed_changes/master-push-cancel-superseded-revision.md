---
proposal: master-push-cancel-superseded.md
decision: modify
revised_at: 2026-11-10T08:03:27Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The proposal's measurement holds: superseded master push runs spent about 4,110 runner-min/day, 48% of master-lane CI, in two repositories that call no master-health reconciler. The maintainer then ruled B' over B. Keeping the run in progress and dropping only an older pending run removes most of that waste without cancelling a run that is already spending its minutes, and without leaving the commit in progress unverdicted. The revision restates the allowance in that form, gives release and expedited-incident commits groups of their own so they are never dropped, names the two adopting members, and keeps the reconciler guard and the interim retirement. Independent sonnet review recorded NO BLOCKERS on these exact bytes.

## Modifications

Re-cut from option B (cancel-in-progress true, which cancels the IN-PROGRESS superseded master run) to the maintainer's ruling B' ("OK B'", 2026-11-09, recorded on livespec-dev-tooling-6tgd2z and plan epic livespec-dev-tooling-ib3oe3). The constraints.md §"CI matrix shape" paragraph is replaced: a repository that calls no master-health reconciler MAY put its master push runs of a CI workflow in one concurrency group whose cancel-in-progress is false, so the run in progress MUST run to completion and only the newest pending run is kept. The group MUST apply only to push events on the default branch, so a pull_request or merge_group run is never held, cancelled or dropped. A push whose head commit's subject begins `chore(master): release`, or whose head commit carries a `Factory-Override` trailer whose value begins `EXPEDITED_INCIDENT_RESPONSE` (the form the fleet's expedited commits carry, for example `Factory-Override: EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-e62ss6`), MUST run in a group of its own. A dropped run MUST NOT be read as its commit's verdict. Rule K: the adopting members are named, livespec-dev-tooling and livespec-orchestrator-beads-fabro, as a ratification of the allowance for them, not a MUST on either repository's ci.yml, so this repository's ci.yml (no concurrency stanza today) conforms until livespec-dev-tooling-qzw2gf lands its stanza. The reconciler-caller refusal in `just check` (owned by livespec-dev-tooling-xtofr3) and the interim retire-when-the-reconciler-can-re-run sentence are kept. The proposal's three scenarios become four: the pending superseded run is dropped while the run in progress completes and the newest head runs the full aggregate; a release or expedited run is never dropped; a pull-request or merge-group run is never held or cancelled; and the reconciler-caller refusal.

## Resulting Changes

- constraints.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T08:01:31Z
verdict: NO BLOCKERS
proposal_stem: master-push-cancel-superseded
content_digest: 1b244f67cd0314ac45169f2a3286dc23ac39e6920f4fe04012c4c4005a17a0d9
