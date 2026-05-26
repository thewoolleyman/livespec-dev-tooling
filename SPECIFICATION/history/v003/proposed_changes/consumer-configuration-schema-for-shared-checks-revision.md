---
proposal: consumer-configuration-schema-for-shared-checks.md
decision: accept
revised_at: 2026-05-26T04:27:46Z
author_human: E2E Test <e2e-test@example.com>
author_llm: claude-opus-4-7
---

## Decision and Rationale

The schema is sound, comprehensive, and is THE unblocker for li-asybpo acceptance criteria #1, #2, #4, #5. It codifies the per-consumer [tool.livespec_dev_tooling] pyproject.toml schema, an explicit role-key inventory (source_trees, io_trees, commands_trees, supervisor_entry_files, dataclasses_tree, pure_trees, covered_trees, source_tree_prefixes, tests_tree_prefix, target_dirs, mirror_pairings, repo), and the load_config() loader contract. The fallback discipline preserves bit-identical pre-G.6 behavior for livespec-core (the block may be omitted). Three cross-spec citations into livespec-core's spec are introduced; these are legitimate documentation pointers that the companion livespec-core proposal reference-discipline-invariant.md explicitly handles via its retroactive sweep + per-sibling .livespec.jsonc external_references allowlist work-item. Not a landing blocker. Additionally appends a 'Configurability is the partition criterion' bullet to section Shared check inventory and sharpens constraints.md section CLI shape to point at the new schema (dropping the placeholder alternate file locations).

## Resulting Changes

- contracts.md
- constraints.md
