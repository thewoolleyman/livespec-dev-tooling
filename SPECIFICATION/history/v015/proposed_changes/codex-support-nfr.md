---
topic: codex-support-nfr
author: codex-gpt-5
created_at: 2026-06-19T17:36:54Z
---

## Proposal: Codex support and observability requirements

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

State the minimum Codex support requirement for livespec-dev-tooling contributors and the observability expectation for future agent-loop work.

### Motivation

The family-wide Codex audit found that livespec-dev-tooling has a governed spec but no active Codex-specific non-functional requirement, even though it owns shared enforcement-suite hooks/checks and has open agent-loop efficiency/observability work.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, add a Codex support paragraph under `## Hooks and CI` or `## Commit and merge discipline` without introducing a new H2. The text should require that AGENTS.md remains the Codex-facing source for repository mutation discipline, that Codex support is currently instruction-level plus repo-hook enforcement rather than a project-local livespec adapter, that any future Codex adapter in this repo must be thin over governed core prose/wrappers or dev-tooling CLIs rather than copying Claude-specific skill bodies, and that agent-loop observability work such as `livespec-dev-tooling-e60` treats Codex as a distinct runtime with tokens-primary evidence instead of inferring it from Claude Code spans.
