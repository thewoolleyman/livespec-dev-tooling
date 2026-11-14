---
topic: a-role-script-that-decides-whether-a-host-alerts-is-tested
author: claude-opus-5-5
created_at: 2026-11-14T13:21:49Z
---

## Proposal: A role script that decides whether a host alerts is tested in every alert state

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add one obligation to Host provisioning tree. When a role installs a script whose exit status decides whether the host alerts, a committed test must run that script in every alert state it distinguishes. Each state's exit status and alert-state file contents are asserted. The obligation is judged by review. A matching scenario is added.

### Motivation

On 2026-11-13 legacy-coordinator-agent graded livespec-dev-tooling#4563 (role reconcile_runs, livespec-dev-tooling-oxwre7) PASS. To do so it ran the role's dead-man script, `ansible/roles/reconcile_runs/files/livespec-reconcile-runs-staleness`, through nine alert-state cases by hand: fresh, a new stale set, a repeat inside the re-alert interval, a re-alert after it, a growing set, a shrinking set, a recovery, a missing marker, and a run without `--alert-state`. That script decides whether the dev host pages the operator, and no committed test holds any of those cases. A later edit could stop the page, or send one every five minutes, and every gate would stay green. The coordinator filed livespec-dev-tooling-ba7ypx for the test. Its pre-dispatch screen found no ratified clause that requires one, so ruled route (i) generalises the requirement here, in the section that already governs roles that install onto provisioned hosts. The failure mode is not hypothetical. At 12:12:34Z on 2026-11-14, that script's exit, routed through dolt-server's backup alert handler, reached the operator as "dolt-backup run failed" while every backup was succeeding. The cause was the routing, fixed by livespec-dev-tooling-l7f72q, and not a defect in the script. It still showed that a role script's exit is a page, and how much the page depends on code no test covered. The replacement handler, role `host_unit_alert`, ships with a test of its alert states (livespec-dev-tooling#4678). The clause is judged by review rather than enforced by a check, matching **Out-of-band preconditions fail at the start.** Recognising an alert-deciding script needs judgement: it can sit behind an `OnFailure=`, be the handler itself, or be a check whose non-zero exit a timer turns into a failed unit. A text-matching check would either miss shapes or flag scripts that alert nothing. In-flight alignment: `forward-only-forced-command-no-op` (livespec-dev-tooling#4623), `shared-gh-login-rest-spend-recorded`, `one-apply-under-either-sandbox` and `delete-the-dead-phase-1` also touch this section. Each adds or edits a different paragraph, so this proposal aligns with all of them. It and `one-apply-under-either-sandbox` both append at the end of the section; the order the revise takes them in sets which paragraph comes last. Plan dev-host-disk-retention (epic livespec-dev-tooling-qgwxo4) owns this proposal. Revise slot, as the coordinator ruled: after v217 and the expedited-incident-hardening revise, single topic, with independent review.

### Proposed Changes

**1. `non-functional-requirements.md` §"Host provisioning tree".** After the last paragraph of the section (**Enforced for managed authorized_keys entries.**), insert this paragraph:

> **A role script that decides an alert is tested in every alert state.** A role in the provisioning tree MAY install a script whose exit status decides whether the host raises an alert. Such a script is run by a unit whose `OnFailure=` names an alert unit, or it is itself the handler an `OnFailure=` starts. Each such script MUST be exercised by a committed test in this repository. The test MUST run the committed script itself, not a copy, with fakes standing in for the host surfaces it reads, such as the clock, marker files, the journal and network endpoints. It MUST cover every alert state the script distinguishes:
>
> - each condition that makes it exit non-zero, and so alert;
> - each condition under which it exits zero and stays silent;
> - each transition that any alert state it records goes through, such as a first alert, a repeat suppressed inside a re-alert interval, a re-alert after that interval, a changed set of subjects, and a recovery that clears the state.
>
> For each state the test MUST assert the script's exit status, and the contents of every alert-state file the script writes. A role whose alert script lacks such a test is a defect in the provisioning tree, never an accepted state. The script's failure is silent in both directions: a wrong exit either withholds a page the operator needs or sends one for nothing. This obligation is judged by review; it is not a member of the `just check` aggregate.

It goes at the end of the section, not next to **A held service is still installed by a role.**, so that the sentence "This obligation and the next are judged by review" in **Out-of-band preconditions fail at the start.** keeps naming the held-service paragraph.

**2. `scenarios.md`.** Append this scenario at the end of the file:

> ## Scenario: a role script that decides whether a host alerts is tested in every alert state
>
> Given a role under `ansible/roles/` that installs a script whose non-zero exit makes a unit's `OnFailure=` raise an alert
>
> And the script keeps an alert-state file so that one episode raises one alert
>
> When this repository's committed tests run
>
> Then a test runs that committed script, with its clock, markers and endpoints faked, once for each alert state it distinguishes
>
> And for a first alert, a repeat inside the re-alert interval, a re-alert after it, a changed set and a recovery, the test asserts the exit status and the alert-state file's contents
>
> And for each condition under which the script stays silent, the test asserts that it exits zero

**3. `tests/heading-coverage.json` (the revise commit, outside `resulting_files[]`).** Add a row for the new scenario heading. Its test runs `ansible/roles/reconcile_runs/files/livespec-reconcile-runs-staleness` in every alert state, and livespec-dev-tooling-ba7ypx owes it. Until that test is on master, the row is a spec-first `"test": "TODO"` row with `work_item` livespec-dev-tooling-ba7ypx. Its reason names the integration tier and ba7ypx, and it is registered in `tests/heading-coverage-debt.json`. `tests/livespec_dev_tooling/test_host_unit_alert.py` (livespec-dev-tooling#4678) already meets the paragraph for role `host_unit_alert`, whose handler keeps no alert-state file.
