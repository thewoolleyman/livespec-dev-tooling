---
topic: branch-protection-fail-on-absent
author: claude-opus-4-8
created_at: 2026-05-29T05:00:00Z
parent_proposed_change: livespec#ci-as-a-merge-gate-branch-protection
---

## Cross-cutting parent

This PC is a child of the family-wide merge-gate hardening coordinated
from livespec (the new `livespec/SPECIFICATION/non-functional-requirements.md`
§"CI as a merge gate (branch protection)"). It closes a gap found this
session: three of four family repos were completely unprotected, so PRs
auto-merged before CI finished and a red PR landed on master.

## Problem statement

dev-tooling's `branch_protection_alignment` check verified that branch
protection was *aligned if it existed*, but did NOT fail when protection
was entirely ABSENT. A repo with no branch protection (master wide open,
CI advisory only) passed the check silently. The impl now FAILS when it
can definitively determine that master has no branch protection, while
preserving graceful-skip behavior when it merely cannot read protection.
The spec must document the new fail-on-absent branch so spec and impl
stay in lockstep.

## Proposal: branch_protection_alignment fail-on-absent

Add a `### branch_protection_alignment check` H3 section under
§"Shared check inventory" documenting:

- The two responsibilities (protection-present gate + alignment gate).
- The three gh-api outcomes and the load-bearing 404 ambiguity: a 404
  means "unprotected" OR "can't read" (GitHub returns 404 not 403 to
  avoid leaking existence). The disambiguator is the response body's
  `message` field — the canonical `Branch not protected` message is
  emitted only for an admin-scoped token reading a genuinely
  unprotected branch.
- Outcome 2 (`Branch not protected`) → exit 4 with `failure_mode`
  `protection_absent`, citing the merge-gate NFR.
- Outcome 3 (gh unavailable / unauthenticated / any OTHER api error,
  notably the permission/visibility 404 under the default Actions
  `GITHUB_TOKEN`) → exit 0 graceful skip; fail ONLY on a definitive
  "absent" answer, never on "couldn't read it".
- The alignment gate unchanged (required-check-missing-from-ci → exit
  4; extra ci.yml job → warning only). Both fail branches standardized
  on exit 4 per the §"Exit-code table".
- The CI-token caveat: the default Actions `GITHUB_TOKEN` cannot read
  branch protection, so the check always graceful-skips in a stock
  Actions job and is intentionally NOT a required CI matrix entry; it
  enforces via `just check` / pre-push under a maintainer's
  admin-scoped `gh` token. A consumer whose CI provides an
  admin-scoped token MAY wire it into CI.

The change is entirely under an H3 heading, so heading-coverage
(H2-only) is unaffected.

## Resulting Changes

- contracts.md
