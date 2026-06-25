---
topic: commit-refuse-installer-and-baseline-profile
author: claude-opus-4-8
created_at: 2026-06-25T23:30:32Z
---

## Proposal: Document the commit-refuse installer CLI and the baseline profile

### Target specification files

- SPECIFICATION/contracts.md

### Summary

M2-1 of the Conformance Pattern added two new public surfaces to livespec-dev-tooling that contracts.md did not yet cover: the commit-refuse hook installer (python -m livespec_dev_tooling.install_commit_refuse_hooks, invoked via just install-commit-refuse-hooks) and the baseline profile accessor (canonical_checks.baseline_check_slugs()). Document both as semver-stable contract surfaces and tie the installer plus the livespec.sandboxExempt exemption into the commit-refuse check's section as the Conformance Pattern's five-slot Worktree-discipline concern.

### Motivation

Close the M2-1 (livespec-zs22.7.3) spec cycle: the structural commit-refuse installer and the baseline profile shipped in code (release 0.19.0) but were undocumented in contracts.md, leaving released public contract surface unspecified. The verifier's dual-fingerprint detection was already spec'd in v018; this adds the installer and baseline that the same milestone introduced.

### Proposed Changes

(1) Section 'CLI surface': add a paragraph documenting the installer as the library's one operational (non-check) CLI module under the same semver-stable invocation contract -- it idempotently writes the canonical structural body to the primary's shared pre-commit/pre-push/commit-msg (worktree-safe via git rev-parse --git-common-dir), is the single source of truth for the CANONICAL_HOOK_BODY constant, and is invoked via the just install-commit-refuse-hooks recipe. (2) Section 'Shared check inventory': add a paragraph documenting the baseline profile (canonical_checks.baseline_check_slugs()) as a static curated subset of the canonical set -- the universal worktree-discipline conformance floor (livespec core non-functional-requirements 'Conformance Pattern'), with check-primary-checkout-commit-refuse-hook-installed its sole member. (3) Section 'primary-checkout-commit-refuse-hook-installed check': name the installer as the documented bootstrap/corrective mechanism and record the livespec.sandboxExempt=true exemption, framing Mechanism/Installer/Verifier/Exemption as the Conformance Pattern's five-slot Worktree-discipline concern. No new H2 or H3 headings are added.
