# research/

Durable scratch for analyses, measurement baselines, and exploratory
notes that inform future work in this repo without being spec
content. Mirrors the livespec repo's `research/` convention.

## What lives here

Subdirectories group docs by topic. As of writing:

- `justcheck-performance/` — `just check` wall-time baselines and
  optimization research (work-item livespec-dev-tooling-7us.1).
- `agent-instruction-inheritance/` — fleet agent-instruction surface
  gap audit (work-item livespec-4g2pg3).

## What this directory is NOT

- **Not `SPECIFICATION/`.** Files here are NOT requirements. Anything
  that matures into a rule the system must honor flows through
  `/livespec:propose-change` → `/livespec:revise`.
- **Not `archive/`.** Files there are frozen; files here are living —
  they may be revised, superseded, or deleted as thinking matures.

## When to add a doc

When an investigation produces something worth re-reading later —
a measurement baseline, an audit, a design deliberation — that is
not (yet) a requirement. Markdown, free-form, no required template.
