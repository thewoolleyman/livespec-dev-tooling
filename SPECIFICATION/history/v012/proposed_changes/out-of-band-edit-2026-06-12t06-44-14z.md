---
topic: out-of-band-edit-2026-06-12t06-44-14z
author: livespec-doctor
created_at: 2026-06-12T06:44:14Z
---

## Proposal: out-of-band-edit-2026-06-12t06-44-14z

doctor detected drift between HEAD-active spec content and the
HEAD-history-vN snapshot; this auto-backfill records the active
state as the new canonical version.

### Proposed Changes

```diff
--- history/vN/README.md
+++ active/README.md
@@ -16,4 +16,4 @@
 
 ## Governance
 
-The active implementation plugin (`livespec-impl-plaintext` per this repo's `.livespec.jsonc`) tracks work items and memos in `work-items.jsonl` and `memos.jsonl` at the repo root. The `compat` block under the `livespec-dev-tooling` top-level key in `.livespec.jsonc` declares the supported livespec semver range and the currently-pinned livespec release tag per `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump".
+The active implementation plugin (`livespec-impl-beads` per this repo's `.livespec.jsonc`) tracks work items and memos in this repo's per-repo beads Dolt tenant (tenant name `livespec-dev-tooling`). The `compat` block under the `livespec-dev-tooling` top-level key in `.livespec.jsonc` declares the supported livespec semver range and the currently-pinned livespec release tag per `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump".
--- history/vN/contracts.md
+++ active/contracts.md
@@ -70,7 +70,7 @@
 
 Algorithm:
 
-1. Read the canonical branch name from `.livespec.jsonc`'s `livespec-impl-plaintext.canonical_branch` config key (or any other configured impl plugin's equivalent key). Default: `git symbolic-ref --short refs/remotes/origin/HEAD`, with hard-coded fallback `master`.
+1. Read the canonical branch name from `.livespec.jsonc`'s `livespec-impl-git-jsonl.canonical_branch` config key (or any other configured impl plugin's equivalent key). Default: `git symbolic-ref --short refs/remotes/origin/HEAD`, with hard-coded fallback `master`.
 2. Enumerate local refs: `git for-each-ref --format='%(refname:short)' refs/heads/spec/`.
 3. For each branch in the enumeration:
     - Run `git rev-list --left-right --count origin/<canonical>...<branch>`.
@@ -177,7 +177,7 @@
 
 Some checks have layout-dependent inputs that are project-wide invariants rather than check-specific role keys (e.g., the canonical branch name `master` / `main`). Such checks read directly from `.livespec.jsonc` rather than the `[tool.livespec_dev_tooling]` role-key inventory, to avoid duplicate config. The list of carve-out keys is currently small:
 
-- `canonical_branch` — read from `.livespec.jsonc`'s `livespec-impl-plaintext.canonical_branch` (or equivalent impl-plugin block's key, per the impl plugin's spec).
+- `canonical_branch` — read from `.livespec.jsonc`'s `livespec-impl-git-jsonl.canonical_branch` (or equivalent impl-plugin block's key, per the impl plugin's spec).
 
 Future carve-outs require explicit propose-change documentation; the default for new layout-dependent inputs is the role-key inventory.
 
@@ -234,7 +234,7 @@
 
 - **`livespec-core`** — MAY omit the block entirely (the fallback matches its historical layout). If the block is added, every key MUST be bit-identical to the fallback values above.
 - **`livespec-dev-tooling`** (self-application) — MUST publish `source_trees = ["livespec_dev_tooling"]`, `target_dirs = ["livespec_dev_tooling"]`, `source_tree_prefixes = ["livespec_dev_tooling/"]`, `mirror_pairings = [{ source_tree = "livespec_dev_tooling", test_tree = "tests/livespec_dev_tooling" }]`. The other role keys (`io_trees`, `commands_trees`, `supervisor_entry_files`, `dataclasses_tree`, `pure_trees`, `covered_trees`) default to empty/null since the library has a flat package layout without the ROP-layered architecture livespec-core has. The corresponding checks (`no_except_outside_io`, `no_raise_outside_io`, `public_api_result_typed`, `no_write_direct`, `newtype_domain_primitives`) no-op against this library; their structured `info` log entries document the no-op.
-- **`livespec-impl-plaintext`** — MUST publish its own block once Phase G.7 wiring lands. The exact values are the picking-up agent's call at that phase; the schema accommodates whatever layout that consumer adopts.
+- **`livespec-impl-git-jsonl`** — MUST publish its own block once Phase G.7 wiring lands. The exact values are the picking-up agent's call at that phase; the schema accommodates whatever layout that consumer adopts.
 
 Future siblings (any repo carrying the `livespec-sibling` GitHub topic that depends on this library) MUST publish their own block; omitting the block falls back to livespec-core's defaults, which will silent-no-op against any non-livespec-core layout (the trade-off the v0.x backward-compat guarantee accepts).
 
--- history/vN/spec.md
+++ active/spec.md
@@ -25,7 +25,7 @@
 
 ### Governance
 
-This library dogfoods livespec at the LIBRARY scale (distinct from the plugin scale via livespec-core itself, and the impl-plugin scale via livespec-impl-plaintext). Its own `SPECIFICATION/` tree is the live spec; its work-items + memos are tracked by the active `livespec-impl-*` plugin per `.livespec.jsonc`. Pin-and-bump against livespec applies identically to this library as it does to any `livespec-impl-*` consumer per `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump" (generalized in livespec v070 to cover sibling libraries).
+This library dogfoods livespec at the LIBRARY scale (distinct from the plugin scale via livespec-core itself, and the impl-plugin scale via livespec-impl-git-jsonl). Its own `SPECIFICATION/` tree is the live spec; its work-items + memos are tracked by the active `livespec-impl-*` plugin per `.livespec.jsonc`. Pin-and-bump against livespec applies identically to this library as it does to any `livespec-impl-*` consumer per `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump" (generalized in livespec v070 to cover sibling libraries).
 
 ## Definition of Done
 
```
