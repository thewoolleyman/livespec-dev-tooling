---
topic: out-of-band-edit-2026-10-04t05-29-26z
author: livespec-doctor
created_at: 2026-10-04T05:29:26Z
---

## Proposal: out-of-band-edit-2026-10-04t05-29-26z

doctor detected drift between HEAD-active spec content and the
HEAD-history-vN snapshot; this auto-backfill records the active
state as the new canonical version.

### Proposed Changes

```diff
--- history/vN/contracts.md
+++ active/contracts.md
@@ -14,6 +14,8 @@
 - Perform no network I/O. Reading the local filesystem and invoking project-local subprocesses (git, ruff, pyright, pytest) is permitted; reaching out to a remote service is forbidden per `constraints.md` §"No network I/O".
 
 Beyond the check modules, the library exposes three operational CLI modules under the same semver-stable invocation contract. The first is the commit-refuse hook installer `python -m livespec_dev_tooling.install_commit_refuse_hooks`. It idempotently writes the canonical structural commit-refuse hook body to the primary checkout's shared `.git/hooks/pre-commit`, `pre-push`, AND `commit-msg` (resolved via `git rev-parse --git-common-dir`, so the install is worktree-safe — it lands in the primary's shared hooks directory even when invoked from a secondary worktree), makes each executable, and exits `0` on success. The module is the SINGLE source of truth for the canonical body (its module-level `CANONICAL_HOOK_BODY` string constant — wheel-carried because only the `livespec_dev_tooling/` package is packaged), so there is no second on-disk copy to drift. Consumers invoke it through the `just install-commit-refuse-hooks` recipe (also driven by `just bootstrap`). The second is the worktree-discipline pack installer `python -m livespec_dev_tooling.install_worktree_pack` (recipe `just install-worktree-pack`): it idempotently writes the canonical worktree-discipline pack — the `worktree-lib.sh` and `branch-protection.sh` scripts plus the `worktree.just` and `branch-protection.just` recipe fragments (its wheel-carried `CANONICAL_WORKTREE_LIB_BODY` / `CANONICAL_BRANCH_PROTECTION_BODY` / `CANONICAL_WORKTREE_JUST_BODY` / `CANONICAL_BRANCH_PROTECTION_JUST_BODY` constants) — into the checkout's `dev-tooling/` directory. The third is the neutral-shared-hook-body sync `python -m livespec_dev_tooling.install_no_shadow_ledger` (recipe `just install-no-shadow-ledger`): it idempotently writes the canonical neutral no-shadow-ledger Stop-hook body — `CANONICAL_NO_SHADOW_LEDGER_BODY`, the wheel-carried single source of truth exported from that module — to the consumer's configured `neutral_hook_body_path` (§"Consumer configuration schema"), or no-ops when that role key carries any of the four declared-absent variants (§"Declared-absent spellings for the union role keys") — that being the spelling a consumer without a neutral shared body now uses — or is declared empty (`""`, the retired transitional spelling) or undeclared — the installer is a provisioning surface, not a gating check, so it never hard-errors on an undeclared key. Like the commit-refuse installer it is the SINGLE source of its body, so there is no second on-disk copy to drift; the paired byte-identity Verifier is the `no_shadow_ledger_body_identical` check (§"Shared check inventory").
+
+Beyond those three installers the library exposes one operational CLI GATE under the same semver-stable invocation contract: `python -m livespec_dev_tooling.factory_provenance_gate <commit-message-file> [<factory-run-id>]`. It is the decision half of the hermetic factory-provenance commit gate, invoked by the canonical commit-refuse hook body at `commit-msg` time with the message file and whatever the body read from the `livespec.factoryRunId` git config marker. It writes a `Factory-Run-Id:` trailer onto the message when that marker is present; otherwise it classifies the staged tree against the same `config.derive_source_prefixes` universe the Red-Green-Replay gate uses (staged, non-deleted, non-vendored `.py` under a declared source prefix), treats a non-empty `Factory-Override: <reason>` message trailer as an AUDITED exception, and resolves its severity from the HOST-WIDE mode file `${XDG_CONFIG_HOME:-$HOME/.config}/livespec/factory-provenance-mode` — which sits outside every repository, so no checkout can arm or disarm the gate that judges its own commits, and which DEFAULTS TO `warn` (emit the record, do not refuse). It exits `0` to proceed and `9` to refuse. That `9` is deliberately absent from §"Exit-code table", whose reserved-range rule binds the CHECK modules: this module is not a check, is never wired into the `check:` aggregate, and the hook body refuses on that one code alone, so an absent interpreter, an unresolvable module, or any crash — each exiting something else — fails OPEN rather than turning a gate defect into a fleet-wide commit outage.
 
 ## Exit-code table
 
```
