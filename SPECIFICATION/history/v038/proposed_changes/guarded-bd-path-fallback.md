---
topic: guarded-bd-path-fallback
author: codex-gpt-5
created_at: 2026-07-30T09:48:39Z
---

## Proposal: Let the Beads runtime probe use the guarded bd on PATH

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Align the local first-touch Beads probe with the guarded host entry-point contract: an explicit LIVESPEC_BD_PATH remains authoritative, while an unset override falls back to the executable bd resolved from PATH.

### Motivation

The current detector treats an unset LIVESPEC_BD_PATH as a missing Beads binary even when /usr/local/bin/bd is the installed lifecycle guard and resolves normally from PATH. That stale assumption produces false setup guidance after the mise shadowing installation has been removed.

### Proposed Changes

The beads-bd-binary local obligation MUST probe LIVESPEC_BD_PATH when it is non-empty and MUST otherwise resolve bd from PATH. It MUST pass when the selected command is executable and MUST emit warning guidance only when neither selection yields an executable command. The guidance MUST describe both supported resolution paths.
