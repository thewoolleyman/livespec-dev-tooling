---
topic: workflow-edit-additive-means-logically-additive
author: claude:ci-runtime-and-cost
created_at: 2026-11-19T08:06:30Z
---

## Proposal: workflow-edit additive tier means logically additive, not a line diff with no deleted line

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Redefine the additive tier of the workflow-edit guard from 'the line diff deletes no line' to 'the edit runs the same work or more', so a runs-on routing change is admitted at the delegable tier, while every change that makes CI run less still goes to the maintainer.

### Motivation

The guard check-no-workflow-edits.sh implements the current text exactly, and so refuses a logically additive runs-on routing change such as the six modified runs-on lines of livespec-dev-tooling-lzkzwb (measured: the maintainer tier demanded approval:workflow-edit). The maintainer ruled otherwise, attended, recorded verbatim on livespec-dev-tooling-6tgd2z in the scope event of 2026-11-03T13:28:58Z: "Additive means LOGICALLY ADDITIVE. E.g., ADDS MORE STUFF TO RUN, NOT RUNS LESS STUFF. Adding OR MODIFYING a runs on is absolutitely ADDITIVE. FIX IT." Item livespec-dev-tooling-hz4dkk implements the guard change and is held until this proposal is ratified; throughput-plans-coordinator and legacy-coordinator-agent routed it as a spec-contradicting item (coordinator-duties section 12).

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` section "Hooks and CI", replace the paragraph that begins "A `change=additive` claim is checked against the change's committed, staged and unstaged workflow diff." with the paragraph below. The exemption-format paragraph before it, the tier definitions, the label rules after it and the maintainer-tier rules are unchanged.

```diff
-A `change=additive` claim is checked against the change's committed, staged and unstaged workflow diff. Any deleted line (a modification is a deletion plus an addition), any deleted file or any mode change makes the claim false, whatever label the work item carries. When the repository has a ledger, the named work item MUST carry a label that admits the tier:
+A `change=additive` claim is checked against the change's committed, staged and unstaged workflow diff, and ADDITIVE means LOGICALLY additive: the edit MUST make CI run the same work or more, and MUST NOT make it run less. A line diff that deletes a line is therefore NOT by itself a false claim. The claim MUST be accepted when every deleted or modified line is one of: a blank or comment-only line; a `runs-on` value (modifying or adding a `runs-on` value is additive, because it changes where the same work runs and not what runs); a value inside an `env:` mapping; a `group:` value under `concurrency`; or the `workflow_dispatch: {}` line rewritten to the mapping form that adds `inputs:`. The claim MUST be refused, and the refusal MUST name each offending line, when the diff deletes a job, a step, a `run:` line, a `needs:` entry or a `with:` argument; modifies a `run:`, `needs:`, `if:`, `timeout-minutes:`, `continue-on-error:` or `cancel-in-progress:` line; or adds an `if:`, `continue-on-error:`, `paths:`, `paths-ignore:` or `branches-ignore:` line or a `cancel-in-progress: true` line. A deleted workflow file or a changed workflow file mode MUST make the claim false. A change that reduces what CI runs is NOT additive and MUST go through the maintainer tier, which accepts `approval:workflow-edit` only, so the reduction still needs the maintainer. The `ci_runtime=no-significant-increase` attestation is required exactly as before. When the repository has a ledger, the named work item MUST carry a label that admits the tier:
```

In `SPECIFICATION/scenarios.md`, add this scenario (its heading is new, so the revise pass MUST co-edit `tests/heading-coverage.json` per the repository's revise co-edit discipline):

```gherkin
## Scenario: a workflow edit that modifies only runs-on values is admitted at the additive tier and one that deletes a step is refused

Given an exemption that carries change=additive and ci_runtime=no-significant-increase and names a work item labelled approval:workflow-edit-additive
When the change's workflow diff modifies six runs-on values and deletes no job, step, run line, needs entry or with argument
Then check-no-workflow-edits admits the change at the additive tier
And when the diff instead deletes one step, the check refuses it and names the deleted line
```

The guard `worktree_pack/check-no-workflow-edits.sh` (its `non_additive_lines` function) and `.ai/fleet-and-secrets.md` are brought in line by livespec-dev-tooling-hz4dkk after this proposal is ratified; that item stays held until then. `contracts.md` section "Expedited incident execution" is NOT changed: it states no additive definition.
