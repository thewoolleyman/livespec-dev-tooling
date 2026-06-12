---
topic: github-workflow-uses-pin-format
author: claude-fable-5
created_at: 2026-06-11T18:00:00Z
---

This propose-change extends the pin-autodiscovery walk with a fifth pin
format: `github_workflow_uses_ref`. It covers the `uses:` references in
GitHub Actions workflow files under `.github/workflows/`, which are the
canonical bootstrap pin location for shim workflows in sibling repos.

## Proposal: Add `github_workflow_uses_ref` to contracts.md §"Pin autodiscovery rules"

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Enumerate a fifth format in the "Pin autodiscovery rules" bullet list
within §"Cross-repo coordination automation surface". The new format
covers every `uses: <owner>/<repo>/<path>@<ref>` line in any YAML file
under `.github/workflows/`, emitting one record per match with
`source_repo` derived from the `<repo>` segment and `current_value` set
to `<ref>`.

### Motivation

The shim workflows in each sibling repo (`release-dispatch.yml`,
`bump-pin-from-dispatch.yml`, `pin-freshness.yml`) bootstrap by calling
reusable workflows at `livespec-dev-tooling@master`. The existing four
pin formats (`.livespec.jsonc`, `pyproject.toml [tool.uv.sources]`,
`.vendor.jsonc`, `.copier-answers.yml`) do not cover this location, so
the `@master` pins in shim workflows stay at `@master` permanently —
bypassing the cross-repo coordination automation surface that the spec
mandates for all family pin sites.

Adding a fifth format ensures that bump-pin automation discovers and
rewrites these pins on the first sibling release after this change lands,
completing the bootstrap cycle per §"Self-hosting".

### Proposed Changes

Insert the following bullet into the "Pin autodiscovery rules" list in
§"Cross-repo coordination automation surface", immediately after the
`.copier-answers.yml` entry:

```markdown
- **`.github/workflows/*.yml` / `*.yaml` `uses:` ref** — every line
  in any GitHub Actions workflow file (under `.github/workflows/`)
  matching the form `uses: <owner>/<repo>/<path>@<ref>`, where
  `<path>` is a non-empty path segment (distinguishing reusable-workflow
  calls from simple action references such as `uses: actions/checkout@v4`
  which have no path segment). The pin's source repo is derived from the
  `<repo>` segment verbatim. `current_value` is `<ref>`. `pin_key` is
  the full `uses:` reference excluding the `@<ref>` suffix
  (`<owner>/<repo>/<path>`), which uniquely identifies the line for
  targeted rewriting. Lines whose `<repo>` segment does not match the
  requested `--source-repo` filter are excluded per the standard
  source-repo-filter semantics.
```

Also extend the paragraph in the "Rewrite path" of the bump-pin
composite Action description to name the fifth format:

> Rewrite path: `github_workflow_uses_ref` pins are rewritten by
> replacing the literal `@<current_value>` suffix on the matched
> `uses:` line with `@<tag>` — equivalent to the sed-replace discipline
> used for other formats, but scoped to the specific `pin_key` prefix
> so that other `uses:` references in the same file are not modified.

## Proposal: Classify as MINOR in constraints.md §"Semver discipline"

### Target specification files

- SPECIFICATION/constraints.md

### Summary

Document that adding the `github_workflow_uses_ref` pin format is a
MINOR semver bump per the existing bump-rule enumeration in
`contracts.md` §"Semver discipline".

### Motivation

`contracts.md` §"Semver discipline" already enumerates "adding a new
pin-autodiscovery format" as a MINOR bump: "MINOR — adding a new check,
a new composite Action, a new reusable workflow, a new optional
configuration key, or a new pin-autodiscovery format." The constraint in
`constraints.md` §"Semver discipline" defers to `contracts.md` for the
canonical enumeration. No change to the constraint text is required; this
proposal documents the classification decision so the accepting revise
pass can confirm the version bump is correct.

### Proposed Changes

No textual amendment to `constraints.md` §"Semver discipline" is needed
— the pointer to `contracts.md` §"Semver discipline" already covers
this case. The accepting revise pass MUST classify the release bump as
MINOR (i.e., the implementing commit carries a `feat:` Conventional
Commits subject) so that `release-please` derives the correct version
increment per the existing Conventional Commits → semver mapping.
