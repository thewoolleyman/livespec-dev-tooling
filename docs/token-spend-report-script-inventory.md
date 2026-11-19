# Token-spend-report script inventory (vps vmi3006760)

Work item: livespec-dev-tooling-qsa576 (plan `token-spend-analysis`, epic livespec-dev-tooling-6lv7ze).
Measured 2026-11-19 over read-only ssh to the vps, on the `~/token-spend-report/scripts` directory (64 entries,
counting `__pycache__` and `systemd/`) and the user units under `~/.config/systemd/user`.

## How the role pins scripts

The `token_spend_report` role (`ansible/roles/token_spend_report/defaults/main.yml`) copies a script to the vps only
when it appears in `token_spend_report_scripts`, which names a SHA-256 per file under one vps-info commit
(`12cf60f0d6bd`, vps-info#97). A script outside that map is hand-installed: the vps copy is the only copy, and the
directory is a local git repository with no remote, so nothing outside the vps can recover it.

Pinned by the role (12 files): `attribution.py`, `build_board.py`, `build_triggers.py`, `emit_factory.py`,
`emit_nodes.py`, `emit_spend.py`, `emit_spend_key.py`, `hcq.py`, `quota_triggers.py`, `quota_triggers_check.py`,
`spend_staleness.py`, `tenant_watch.py`.

## Scripts that a unit runs

Every timer-run script is executed with `python3 -I` from `%h/token-spend-report/scripts/`.

| Script | Run by | Pinned |
| --- | --- | --- |
| `cache_events.py` | `token-spend-events.service` (`--days 9`) | gap |
| `caam_source.py` | `token-spend-fast.service` | gap |
| `emit_spend.py` | `token-spend-fast.service` (`--days 2`) | pinned |
| `emit_caam.py` | `token-spend-fast.service` | gap |
| `emit_codex_credits.py` | `token-spend-fast.service` (`--probe`) | gap |
| `emit_factory.py` | `token-spend-fast.service` (`--hours 3`) | pinned |
| `quota_guard.py` | `token-spend-fast.service` | gap |
| `tenant_watch.py` | `token-spend-fast.service` | pinned |
| `emit_nodes.py` | `token-spend-local.service` (`--hours 24`) | pinned |
| `emit_codex_runs.py` | `token-spend-local.service` | gap |
| `build_board.py` | `token-spend-local.service` (`--if-changed`) | pinned |
| `quota_triggers.py` | `token-spend-quota-triggers.service` (role-started oneshot, no timer) | pinned |

Gaps that run on a clock without a pin: `cache_events.py`, `caam_source.py`, `emit_caam.py`,
`emit_codex_credits.py`, `quota_guard.py`, `emit_codex_runs.py` (6 scripts).

Also run, not by a unit: `quota_triggers_check.py` (pinned) is run by the role's read-back after an apply, and
`tenant_usage_read.py` is run as a subprocess by `tenant_watch.py` (`READER` constant) with the tenant token bound
only inside its wrapper. It is not pinned.

## Import dependencies of the run scripts

Modules imported by a unit-run script, and whether the role pins each:

| Dependency | Imported by | Pinned |
| --- | --- | --- |
| `emit_spend_key` | `emit_spend`, `emit_caam`, `emit_codex_credits`, `emit_factory`, `emit_nodes`, `emit_codex_runs`, `build_triggers` | pinned |
| `build_triggers` | `quota_triggers`, `quota_triggers_check` | pinned |
| `quota_triggers` | `quota_triggers_check` | pinned |
| `attribution` | `emit_spend`, `emit_factory` | pinned |
| `hcq` | `emit_factory`, `emit_codex_runs` | pinned |
| `spend_staleness` | `tenant_watch` (lazy import) | pinned |
| `prices` | `emit_spend`, `emit_factory`, `emit_nodes` | gap |
| `accounts` | `emit_spend`, `emit_caam`, `emit_codex_credits`, `emit_factory`, `emit_nodes` | gap |
| `node_join` | `cache_events`, `emit_factory`, `emit_nodes` | gap |
| `caam_source` | `emit_caam`, `quota_guard`, `tenant_watch` | gap (also run by a unit) |
| `codex_idle` | `emit_factory` | gap |
| `journal_slots` | `emit_factory` | gap |
| `tenant_usage_read` | `tenant_watch` (subprocess, not an import) | gap |

The pinned `emit_spend.py`, `emit_factory.py`, `emit_nodes.py` and `tenant_watch.py` all depend on unpinned siblings
(`prices`, `accounts`, `node_join`, `codex_idle`, `journal_slots`, `caam_source`, `tenant_usage_read`), so a role
apply of those four does not by itself reproduce a working collector. `build_board.py` and `caam_source.py` import no
sibling module.

## Scripts that no unit runs and nothing imports

These are analysis, backfill and one-off tools. None is run by a timer or imported by a unit-run script, and none
is pinned except `spend_staleness.py`, which is pinned and imported lazily by `tenant_watch.py`.

- Analysis and reporting: `agg.py`, `board_capture.py`, `build_page.py`, `burn.py`, `burn_levers_q.py`,
  `cache_rewrite_q.py`, `cache_rewrite_report.py`, `codex_allowance.py`, `codex_join_check.py`, `codex_reset.py`,
  `codex_run_mix.py`, `codex_runs_by_day.py`, `collect.py`, `collect_node_models.py`, `combined_budget.py`,
  `dod_capture.py`, `emit_local_spend.py`, `emitter_cadence.py`, `factory_join.py`, `first_turn_report.py`,
  `hc_board.py`, `hc_columns.py`, `hc_url.py`, `hc_urls.py`, `node_report.py`, `parse.py`, `reconcile_local.py`,
  `restate_hc.py`, `restate_sonnet_cache.py`, `runs.py`, `spend_watch.py`, `tables.py`, `wait_lag_clear.py`.
- Backfills: `backfill_caam_drops.py`, `backfill_consumer_repair.py`.
- Shell: `regenerate.sh` (rebuilds the static report page from `data/`; run by hand) and `burn_hour.sh`
  (waits for a fresh caam read and re-snapshots; run by hand).
- Notes: `board-notes.md`.
- `systemd/`: copies of the three hand-installed `token-spend-*` units and timers; nothing reads them.
- `__pycache__/`: bytecode.

Some of these may still be used by hand. This inventory records that no unit or unit-run script reaches them, and
that none is pinned, which makes them unrecoverable from a remote.

## User units under `~/.config/systemd/user`

| Unit | Provisioned by |
| --- | --- |
| `token-spend-events.service`, `token-spend-events.timer` | hand-installed |
| `token-spend-fast.service`, `token-spend-fast.timer` | hand-installed |
| `token-spend-local.service`, `token-spend-local.timer` | hand-installed |
| `token-spend-quota-triggers.service` | installed by the role (livespec-dev-tooling-caejh2); no timer, no `[Install]` |

## Other host-local script locations that a fleet unit executes from

`ExecStart` lines of `/etc/systemd/system/*.service` on the vps, matched against `ansible/`:

- Role-installed, referenced by a role: `/usr/local/libexec/*` (host_unit_alert, fabro_server, gha_runner,
  reconcile_runs, container/storage reclaim), `/usr/local/sbin/*` (arq snapshots, restic, dev-host retention and
  capacity check), `/usr/local/lib/livespec/pressure-telemetry.sh`, `/opt/livespec-incident/venv` (incident_observer),
  `/usr/local/libexec/livespec/claude_scratch_mover.py` (dev_host_memory_bounds),
  `/usr/local/bin/vnc-desktop-start.sh` (vnc_desktop).
- Run from a git checkout on the vps, not from a role-installed copy:
  `/home/ubuntu/workspace/vps-info/services/honeycomb-trigger-recipients-check/check-trigger-recipients.sh`
  (role `honeycomb_trigger_recipients_check` references it),
  `/home/ubuntu/workspace/livespec-dev-tooling/.venv/bin/python -m livespec_dev_tooling.flake_retry_filer` (role
  `flake_retry_filer`), and
  `/home/ubuntu/workspace/livespec-orchestrator-beads-fabro/.claude-plugin/scripts/bin/dispatcher.py` via
  `/usr/local/libexec/livespec-tenant-wrap.sh`.
- Referenced by no role under `ansible/` (a grep of the path found nothing): `/data/projects/dolt-server/scripts/*`
  (owned by the dolt-server repository's own checkout), `/usr/local/bin/homelab-reconcile-installed-scripts`, and
  `/var/lib/acfs/upgrade_resume.sh`.

This item did not verify the provisioning of the checkouts or the three unreferenced paths beyond that grep.

## Follow-ups this inventory names

Per the item, pinning each script or adding a unit is filed per script. The ordered gap list is: the six unpinned
timer-run scripts above, the seven unpinned dependencies, the three hand-installed unit pairs, and the unpinned
manual tools.
