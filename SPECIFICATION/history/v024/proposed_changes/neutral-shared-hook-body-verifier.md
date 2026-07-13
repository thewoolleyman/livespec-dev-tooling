---
topic: neutral-shared-hook-body-verifier
author: claude-opus-4-8
created_at: 2026-07-13T10:00:00Z
---

## Proposal: Document the Neutral-shared-hook-body Verifier + `neutral_hook_body_path` role key

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Document the newly-shipped byte-identity machinery for the neutral shared `no_shadow_ledger.py` Stop-hook body: a new Verifier check (`no_shadow_ledger_body_identical`), its paired installer (`install_no_shadow_ledger` / `just install-no-shadow-ledger`), and the new consumer-config role key `neutral_hook_body_path` it reads. This realizes the **Neutral-shared-hook-body** Conformance-Pattern concern in dev-tooling's spec, mirroring the existing concern #1 (commit-refuse hook) precedent.

### Motivation

livespec-8zxu (slice S2 of epic livespec-9z8h, driver-hook-body). Both livespec Driver plugins ship `no_shadow_ledger.py` as a byte-identical neutral shared body; livespec core `contracts.md` §"Cross-Driver single-sourcing" (revise v164 / slice S1) narrowed the byte-identity mandate to that declared neutral body and pointed the no-drift guarantee at "a consumer-side byte-identity Verifier pinned-and-imported from `livespec-dev-tooling` … Its full five-slot expansion lives in `livespec-dev-tooling`'s own spec." This proposal lands that deferred five-slot expansion. The Verifier's shape mirrors concern #1's `CANONICAL_HOOK_BODY` + `primary_checkout_commit_refuse_hook_installed` (a packaged constant imported by a consumer-side, fail-closed check), and stays cycle-free per the No-Circular-Dependency Directive (dev-tooling reads no Driver repo; the check runs inside each consumer checkout). The concern is deliberately named "Neutral-shared-hook-body" and NOT "No-shadow-ledger" — that name is already taken in the core Conformance-Pattern concern registry by the planning-artifact discipline, a different concern (the S1 Fable review flagged this collision).

### Proposed Changes

Four body edits within existing sections of `SPECIFICATION/contracts.md` (one `### ` H3 heading added under the existing `## Shared check inventory` H2; NO `## ` H2 heading add/change/remove, so no `tests/heading-coverage.json` co-edit):

1. §"CLI surface": correct the exhaustive installer count from "one operational CLI module" (already stale on master — the `install_worktree_pack` installer landed undocumented) to "three operational CLI modules", naming all three: the existing commit-refuse hook installer (first); the previously-undocumented worktree-discipline pack installer `python -m livespec_dev_tooling.install_worktree_pack` / `just install-worktree-pack` (second — surfaced by this change's drift-sweep); and the new neutral-shared-hook-body sync `python -m livespec_dev_tooling.install_no_shadow_ledger` / `just install-no-shadow-ledger` (third) — the single wheel-carried source of `CANONICAL_NO_SHADOW_LEDGER_BODY`, writing to the consumer's configured `neutral_hook_body_path` or no-op when null.

2. §"Shared check inventory": add a new `### `no_shadow_ledger_body_identical` check` H3 subsection documenting the Verifier's five slots (Contract / Mechanism / Installer / Verifier / Exemption), its invocation, algorithm (no-op when the role key is absent; `missing` / `body_mismatch` fails at exit 4), and its cycle-free consumer-side dependency direction.

3. §"Consumer configuration schema" → §"Role keys": add the `neutral_hook_body_path` role key (string or null; repo-root-relative path to the consumer's neutral shared hook body; consumed by `no_shadow_ledger_body_identical`; no-op when null; default null).

4. §"Default layout fallback": add `neutral_hook_body_path = nil` to the fallback TOML block (livespec-core ships no neutral shared Driver hook body).

Adding the `neutral_hook_body_path` role key and the `install-no-shadow-ledger` CLI installer are additive surface elements → a MINOR version bump per §"Semver discipline". The paired code (the constant, installer, Verifier, role-key parsing, tests, and justfile + CI-matrix wiring) lands in the companion `feat:` PR.
