---
topic: workflow-retry-semantics
author: claude-fable-5
created_at: 2026-06-12T04:42:28Z
---

This propose-change adds a new subsection §"Retry semantics (rerun vs
fresh dispatch)" to `contracts.md` §"Cross-repo coordination automation
surface", codifying when a failed event-triggered workflow run may be
retried via `gh run rerun` versus when it MUST be re-triggered as a
fresh event, plus a mechanical guard commitment on
`reusable-bump-pin-from-dispatch.yml` that detects the invalid kind of
retry and fails fast.

## Proposal: Add §"Retry semantics (rerun vs fresh dispatch)" to contracts.md §"Cross-repo coordination automation surface"

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Insert a new `###` subsection, "Retry semantics (rerun vs fresh
dispatch)", into §"Cross-repo coordination automation surface" —
immediately after §"Fallback to known-good pin" and before
§"Self-hosting". The subsection codifies that a rerun replays the
ORIGINAL event payload pinned to the original `github.sha` and can
never observe later commits; that a rerun is the correct retry only for
transient/flake failures on an unmoved branch; that any retry intended
to pick up a post-event fix MUST be a fresh event (with the canonical
`gh api .../dispatches` form for the bump fan-out); and that
`reusable-bump-pin-from-dispatch.yml` SHALL mechanically refuse the
invalid retry shape.

### Motivation

Observed 2026-06-12: livespec-impl-beads' v0.12.1 bump run failed on a
tracked-gitlink defect. After the fix merged (livespec-impl-beads
PR #12, 04:32:11Z), `gh run rerun --failed` at 04:32:42Z still built
the pre-fix SHA `322947b` — labeled as `origin/master` by
`actions/checkout` — and failed identically. A fresh `sibling-released`
dispatch succeeded immediately (livespec-impl-beads PR #13).

The failure mode is structural, not incidental: `gh run rerun` (and the
Actions UI re-run button) re-executes the workflow with the original
event payload, and `actions/checkout` maps the event's pinned
`github.sha` onto the branch ref. A rerun therefore can NEVER pick up a
fix merged after the original event, yet nothing in the family's
surfaces distinguishes the two retry shapes — one sibling spec/skill
surface previously taught an unqualified "`gh run rerun --failed`" for
failures. This subsection is the single canonical home for the
distinction; sibling surfaces reference it rather than restating it.

### Proposed Changes

Insert the following subsection into §"Cross-repo coordination
automation surface", immediately after §"Fallback to known-good pin"
and before §"Self-hosting":

````markdown
### Retry semantics (rerun vs fresh dispatch)

`gh run rerun` (and the Actions UI re-run button) re-executes a
workflow run with the ORIGINAL event payload. `actions/checkout`
resolves the event's pinned `github.sha` onto the branch ref, so the
rerun literally builds the stale commit labeled as `origin/master`. A
rerun therefore can NEVER observe commits merged to the target branch
after the original event.

Consequently:

- **Rerun is the correct retry ONLY for transient/flake failures**
  where rebuilding the same SHA is the point — e.g., the known GitHub
  release-CDN 504 and uv cache hardlink flakes.
- **Any retry intended to pick up a fix merged to the target branch
  after the event MUST be a fresh event, not a rerun.** For the bump
  fan-out, the canonical form is:

  ```
  gh api repos/<owner>/<repo>/dispatches \
    -f event_type=sibling-released \
    -f 'client_payload[source_repo]=<repo>' \
    -f 'client_payload[tag]=<tag>' \
    -f 'client_payload[release_url]=<url>'
  ```

  with the payload shape per §"`repository_dispatch` payload contract".
- **This rule applies to every event-triggered workflow in the
  family** (`repository_dispatch`, `release`, `push`) — when the fix
  landed post-event, re-trigger the event; never rerun.

Mechanical guard: `reusable-bump-pin-from-dispatch.yml` SHALL detect
the invalid retry — when `github.run_attempt > 1` AND the consumer's
default-branch HEAD no longer equals the event-pinned SHA, the workflow
MUST fail fast with an actionable error that includes the
fresh-dispatch command for the in-flight tag. A flake rerun on an
unmoved branch proceeds normally. Refusal on ANY post-event movement —
related to the failure or not — is correct: building a stale HEAD also
produces BEHIND PRs, which is undesirable regardless of why the branch
moved.
````

Semver classification: the mechanical guard is a behavioral addition to
an existing reusable workflow that adds no inputs and breaks no
compatibility — the implementing commit carries a `feat:` Conventional
Commits subject (MINOR) per §"Semver discipline".
