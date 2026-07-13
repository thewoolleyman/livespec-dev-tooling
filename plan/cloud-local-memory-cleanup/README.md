# Cloud Local Memory Cleanup

Work item: `livespec-dev-tooling-2amr6x`.

This ledger records the disposition of every livespec-dev-tooling Claude
local-memory source file found in the repository. It preserves source-file
provenance so a later cleanup can remove or retain `.claude/` content without
losing durable guidance.

## Source Inventory

| Source file | Disposition | Durable destination or follow-up |
| --- | --- | --- |
| `.claude/CLAUDE.md` | Migrated and retained as a compatibility symlink. | The file is a symlink to `../AGENTS.md`, so its durable guidance already lives in `AGENTS.md`. No separate Claude-local prose remains. |
| `.claude/settings.json` | Retained operational config. | The Claude project-scoped plugin and hook wiring remains load-bearing runtime configuration. Durable Codex/Claude distinction and mutation discipline live in `AGENTS.md`; Claude plugin currency behavior is productized in `livespec_dev_tooling.fleet.ensure_plugins` and the fleet rows that require `mise exec -- just ensure-plugins`. The env timeout values are ephemeral Claude runtime configuration, not durable prose. |
| `.claude/hooks/livespec_footgun_guard.py` | Retained operational hook; durable guidance migrated. | The hook is Claude-specific fast feedback for three forbidden patterns. The `--no-verify` and `core.bare=true` bans were already durable in `AGENTS.md` and `SPECIFICATION/contracts.md` under `primary_checkout_commit_refuse_hook_installed`; this cleanup additionally migrated the `LEFTHOOK=0`/`false`/`off`/`no` bypass ban into `AGENTS.md`. The source memory IDs `feedback_sub_agent_dispatch_no_verify_ban` and `feedback_bare_flag_use_git_show_not_filesystem` remain in the hook as provenance for its denial text. |

## Deferred Work

No livespec-dev-tooling local-memory source file has deferred durable guidance
after this migration. The retained `.claude/` files are runtime integration
files, not the only home for durable contributor guidance.
