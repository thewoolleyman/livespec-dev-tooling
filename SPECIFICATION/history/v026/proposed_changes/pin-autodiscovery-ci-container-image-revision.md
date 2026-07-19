---
proposal: pin-autodiscovery-ci-container-image.md
decision: accept
revised_at: 2026-07-19T04:49:25Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accepted after an independent Fable-model adversarial review returned NO BLOCKERS on this exact REPLACE payload. The first review round found two blockers -- singular phrasing plus a false 'distinguished by file_path' claim that would have led an implementer to the existing first-match-per-file walk and left jobs 2..N stale, and a specified 'container: image:' line form that exists nowhere in the fleet. Both were fixed in the amendment text rather than waived, and the redraft was re-reviewed clean. Replacement-target fidelity was verified programmatically: the FIND block occurs exactly once in the live contracts.md and the REPLACE differs by pure insertions only, every preserved clause byte-identical. No heading is added, changed, or removed, so no tests/heading-coverage.json co-edit is required.

## Resulting Changes

- contracts.md
