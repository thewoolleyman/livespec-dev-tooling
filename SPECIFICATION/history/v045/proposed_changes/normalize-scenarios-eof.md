---
topic: normalize-scenarios-eof
author: gpt-5.6
created_at: 2026-08-14T00:50:04Z
---

## Proposal: Normalize scenario file EOF

### Target specification files

- scenarios.md

### Summary

Remove the extraneous terminal blank line introduced by the rate-control scenario revise.

### Motivation

The static whitespace verifier requires no blank line at EOF.

### Proposed Changes

The revised `scenarios.md` MUST end after the final Gherkin assertion rather than with an additional blank line.
