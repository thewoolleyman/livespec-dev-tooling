---
topic: the-expedited-matrix-call-site
author: claude-opus-5-5
created_at: 2026-11-12T14:05:00Z
---

## Proposal: The caller conformance check trusts the check matrix only at a release tag or master, and refuses an unreadable workflow by name

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds two sentences to the `incident-omitted` wire-contract paragraph in contracts.md, section "Reusable workflows wire contract". The first says which refs of `reusable-check-matrix.yml` count as a call of that workflow for the caller rule: a `vMAJOR.MINOR.PATCH` release tag or `master`, read as ASCII. Every other ref, a commit SHA included, is refused. The second says that a caller workflow which cannot be read as an unambiguous YAML mapping is refused with a named reason, whatever error made it unreadable, and never ends the check with an uncaught error. Adds one scenario to scenarios.md, after "an expedited PR defers coverage and spec work while master runs normally".

### Motivation

Work item livespec-dev-tooling-7axsxq (plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub, follow-up (e)) carries notes N1 and N2 from the coordinator's grade of livespec-dev-tooling#3966. On 2026-11-12 at 13:45:30Z the dispatch judgement classified it spec-change, verdict partial, linked topic `the-expedited-matrix-call-site`. Its rationale: the ratified text says the conformance check on callers refuses any wiring other than the incident-ci job's guarded output. It does not say which refs of reusable-check-matrix the check accepts. It also does not say that a YAML constructor error outside YAMLError must produce a named refusal rather than a traceback.

N1, the independent reviewer's finding: the check trusts the canonical matrix at ANY ref as a leaf it never walks, and that includes a 40-hex commit SHA. GitHub resolves a SHA anywhere in the fork network, so a SHA pin can name an "imposter commit" that any fork owner wrote. That copy could call the real matrix with literal inputs, which is exactly the wiring the caller rule exists to refuse. Fleet callers pin release tags. Accepting only `vMAJOR.MINOR.PATCH` or `master`, matched as ASCII, closes that path and the long-s case: a non-ASCII letter that a case-insensitive Unicode match folds to an ASCII one.

N2: a `!!timestamp` value or an `!!int` mapping key raises an error outside YAMLError, and today that escapes the workflow loader's catch. The text already says the omission is honoured only when the wiring is proved, so a workflow that cannot be read cannot prove it. This proposal states the refusal and requires it to be named, so the failure reads as a refusal and not as a crash.

Both rules fail safe. A refused call site is not honoured at run time, so every requested check runs. On 2026-11-12 no workflow in any fleet clone on the dev host calls the matrix by ref; the only matches are the `@vX.Y.Z` placeholder in comments. So no current caller is refused.

### Proposed Changes

In `SPECIFICATION/contracts.md`, section "Reusable workflows wire contract", in the paragraph that begins "The `incident-omitted` input carries, into this workflow, the omission that §"Expedited incident execution" defines", insert the following two sentences immediately after the sentence "A caller MUST wire `incident-omitted` only from its incident-ci job's guarded output, and a repository conformance check on callers MUST refuse any other wiring." and before the sentence that begins "Each omitted leg MUST report". No heading is added, removed or renamed in that file.

For that rule, a job calls this workflow only when its `uses:` names `thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-check-matrix.yml` at a release tag of the form `vMAJOR.MINOR.PATCH` or at `master`, with the ref matched as ASCII text; a call of that path at any other ref, a 40-hex commit SHA included, MUST be refused, because a commit SHA can name a commit that any owner in the repository's fork network wrote. A caller workflow, or a local workflow it calls, that cannot be read as one unambiguous YAML mapping MUST be refused with a named reason whatever error made it unreadable, and the check MUST NOT end with an uncaught error; at run time a refused call site is not honoured, so its omission is ignored and every requested check runs.

In `SPECIFICATION/scenarios.md`, insert the following scenario immediately after the scenario "an expedited PR defers coverage and spec work while master runs normally" and before the scenario "the first required master leaf failure fences incident recovery".

## Scenario: the caller conformance check trusts the check matrix only at a release tag or master

```gherkin
Given a caller workflow whose check-suite job wires incident-omitted and incident-ci-result from its incident-ci job's guarded output
When its uses: names reusable-check-matrix.yml at a vMAJOR.MINOR.PATCH release tag
Then the repository conformance check on callers accepts the call site, and at run time an omission on a trusted incident pull request is honoured as before.
And when the same job names reusable-check-matrix.yml at a 40-hex commit SHA, the check refuses the call site, and at run time every requested check runs instead of reporting omitted-by-incident-policy.
And when the ref is any other branch or tag, or carries a non-ASCII character such as a long s, the check refuses the call site in the same way.
And when the caller workflow's YAML raises a construction error outside YAMLError, such as for a !!timestamp value or an !!int mapping key, the check refuses it with a named reason and does not end with an uncaught error.
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the same commit. A spec-first `"test": "TODO"` row is acceptable when its reason names the integration tier and it carries `"work_item": "livespec-dev-tooling-7axsxq"`, with the heading-coverage debt register regenerated.
