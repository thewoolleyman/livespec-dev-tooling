---
topic: generalize-cant-parse-severity-to-central-rows
author: claude-opus-4-8-drain
created_at: 2026-09-10T18:46:54Z
---

## Proposal: can't-PARSE-is-never-a-pass applies to every central row that parses a committed member file, not only pin-currency rows

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Generalize the ratified pin-currency severity rule -- a can't-PARSE of a member's committed bytes is never a pass and must be reported as a FINDING -- to the whole CLASS of central conformance rows that parse a committed member file, carrying the same context-scoping (error in the filter-consuming preflight, warning/finding elsewhere).

### Motivation

contracts.md section 'Pin-currency severity policy' (v039) ratifies: a can't-READ never escalates; a can't-PARSE is NOT a can't-read and is NEVER a pass -- it is a definitive, reproducible property of the member's committed bytes, so the row MUST report it as a FINDING. That text is scoped to PIN-CURRENCY ROWS. The same argument holds for any central row that parses a committed member file: a member whose file does not parse fails identically on every future run until someone edits it, so 'skip and retry later' is the wrong remedy shape and that member's property goes unchecked indefinitely while the sweep exits passed. Concretely, assert_tenant_connection_consistency (fleet/_rows_beads.py) parses each member's .livespec.jsonc and today renders a can't-PARSE as a RowSkip. Measured under work-item livespec-dev-tooling-9hpu, found while converting fleet/_connection.py to the Result/IOResult railway (epic livespec-dev-tooling-8o8e); that conversion deliberately preserved severity and only sharpened the reason string, because changing severity is a RATIFICATION, not a conversion. check-vendor-manifest-style shape checks never compare across the class, so nothing computes this today.

### Proposed Changes

In SPECIFICATION/contracts.md section 'Pin-currency severity policy', lift the can't-READ / can't-PARSE severity rule from a pin-currency-row-specific statement to a CLASS rule:

1. State the rule for the class 'central conformance rows that parse a committed member file': for any such row, a can't-READ of the member file never escalates (skip or stay at the lower severity); a can't-PARSE is NOT a can't-read and is NEVER a pass -- it MUST be reported as a FINDING, because it is a definitive, reproducible property of the member's committed bytes.
2. Preserve the existing context-scoping the pin rule already carries: a can't-PARSE is an ERROR in the filter-consuming preflight, and a WARNING/FINDING elsewhere.
3. Name the pin-currency rows as one instance of the class rather than the sole scope, and name the tenant-connection-consistency row (assert_tenant_connection_consistency over .livespec.jsonc) as another instance whose current RowSkip-on-parse-failure is non-conformant once this generalizes.

This is a spec proposal for the revise pass / maintainer to accept or reject. It changes the ratified severity contract for a class of rows; it does NOT itself arm or modify any check. If accepted, the implementation (making assert_tenant_connection_consistency and its siblings report a parse failure as a FINDING with the preflight/elsewhere context-scoping) follows as ordinary impl work, gated on re-measuring which members currently carry an unparseable file so no member is surprised by a newly-red central row.
