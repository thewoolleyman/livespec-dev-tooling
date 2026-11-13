---
topic: forge-read-joins-the-composite-actions-minimum-set
author: claude-opus-5-5
created_at: 2026-11-13T04:57:28Z
---

## Proposal: forge-read joins the Composite Actions minimum set now that a release ships it

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Release v1.203.0 (commit c3bb01561) ships .github/actions/forge-read, so the composite Action joins the minimum set of §"Composite Actions wire contract", raising it from four to five, and its wire contract moves from §"Expedited incident execution" into that list unchanged.

### Motivation

v207 ratified the forge-read wire contract inside §"Expedited incident execution" and stated that the Action joins the minimum set of §"Composite Actions wire contract" in the first revise after a release ships it. It could not join at v207, because that set is the semver-stable surface every release must resolve, and tests/consumer/test_semver_stable_surface.py refused the first v207 cut's push while no release shipped the Action. livespec-dev-tooling#4401 (work item livespec-dev-tooling-levu6j) merged as db9a8cc9d and release v1.203.0 carries it, and the incident label workflow now references the Action at that tag (livespec-dev-tooling-pwabtl). Leaving it out of the minimum set would let a later release drop or rename the Action that consumers' workflows reference by path without the semver-stable surface test noticing. Work item livespec-dev-tooling-2cs5jj owns this step.

### Proposed Changes

In SPECIFICATION/contracts.md §"Composite Actions wire contract", the sentence "The library MUST ship at minimum four composite Actions:" becomes "The library MUST ship at minimum five composite Actions:", and the list MUST gain this bullet after **`publish-flake-retries`**:

- **`forge-read`**. Inputs: none. Outputs: none. Permissions: none of its own; each call authenticates with the calling job's `GH_TOKEN` and needs only the permission its endpoint needs. Performs: one step that adds the Action's own directory to the job's `GITHUB_PATH`, so that every later step of the job can run `livespec-forge-read <call-name> [--method <method>] [--field <name>=<value>]... [--idempotent] [--paginate] <endpoint>`, the retrying forge call that §"Expedited incident execution" defines, including its exit status 75 (`outcome-unknown`) for a non-idempotent write whose outcome is unknown. The command MUST need nothing beyond bash, the `gh` CLI and `python3`, so that it runs before the job installs any Python package. It MUST NOT print the token it calls with. A workflow that checks out this library's tree MAY reference it as `./.github/actions/forge-read`; every other workflow MUST reference it as `uses: thewoolleyman/livespec-dev-tooling/.github/actions/forge-read@vX.Y.Z`.

In §"Expedited incident execution", the paragraph that begins "The `forge-read` composite Action's wire contract:" MUST be replaced by the single sentence "The `forge-read` composite Action's wire contract is the `forge-read` entry of §\"Composite Actions wire contract\"." The sentence "It joins the minimum set of §\"Composite Actions wire contract\" in the first revise after a release ships it, because that set is the semver-stable surface every release must resolve, and an Action no release ships cannot be named there." is removed with that paragraph. No other requirement in either section changes, and no scenario is added: the existing semver-stable surface scenario already requires every element the minimum set enumerates to resolve at the declared version, so naming forge-read there brings it under that scenario and its test.

## Proposal: the expedited pull-request CI records are idempotent by identity

### Target specification files

- SPECIFICATION/contracts.md

### Summary

In §"Expedited incident execution", the records clause "The records are append-only and idempotent by binding and digest" becomes "The records are append-only and idempotent by identity", because an unpublished record carries no aggregate digest.

### Motivation

The same clause already defines a published record's identity as its key and its aggregate digest, and an unpublished record's identity as its key and its content. Saying the records are idempotent "by binding and digest" contradicts that for the unpublished kind, which has no digest. legacy-coordinator-agent named the wording at its v207 grade (2026-11-12), and work item livespec-dev-tooling-2cs5jj carries it.

### Proposed Changes

In SPECIFICATION/contracts.md §"Expedited incident execution", in the paragraph that begins "Every expedited pull-request CI run MUST be recorded on the incident work item", the words "The records are append-only and idempotent by binding and digest:" MUST become "The records are append-only and idempotent by identity:". The rest of that sentence and paragraph is unchanged: a repeated publication of the same aggregate MUST answer the retained record and write nothing, and a different aggregate for the same run attempt MUST be recorded as a conflict record naming both digests, never as a replacement. This is a wording correction that changes no behaviour, so no scenario is added.
