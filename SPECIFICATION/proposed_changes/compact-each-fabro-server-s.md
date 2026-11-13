---
topic: compact-each-fabro-server-s
author: claude:fabro-currency session 2032fcbc
created_at: 2026-11-13T01:39:19Z
---

## Proposal: Fabro server store compaction is opt-in, reports read-only, and rewrites a SQLite store only at zero runs

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add one clause to non-functional-requirements.md section "Fabro factory host provisioning" that governs compacting the SQLite store behind each Fabro server instance the fabro_server role manages, and add two scenarios to scenarios.md that exercise it. The step is reached only by an explicit request, so a routine fabro-hosts.yml apply is unchanged. It has a read-only report mode that stops nothing. A requested compaction refuses an instance with a non-terminal run, skips an instance whose storage holds no SQLite store, and otherwise stops the unit, writes a compacted copy with auto_vacuum INCREMENTAL, verifies it, swaps it in, restarts the unit, and restores the original on any failed step. Today no committed automation compacts a Fabro store, and the Driver's fleet-host mutation guard correctly forbids a hand VACUUM, so the fleet store's free pages cannot be returned to the disk at all.

### Motivation

Work item livespec-dev-tooling-iq7gnp ("Compact each Fabro server's SQLite store at a zero-run restart so its free pages return to the disk") is READY but held at the spec-change tier: the ratified specification has no compaction, vacuum or auto_vacuum clause, so the role change it asks for is unstated behaviour. Coordinator ruling R493 assigned the work to plan fabro-currency (livespec-orchestrator-beads-fabro epic bd-ib-6tcjfx), and legacy-coordinator-agent ordered this proposal filed under the topic compact-each-fabro-server-s. Measured read-only (Python sqlite3, mode=ro): gmktec-xubuntu's fleet store /home/cwoolley/.fabro/storage/db/fabro.sqlite3 is 102,208,323,584 B, byte-identical between 2026-11-08 and 2026-11-13 about 01:3xZ, with 13,530,777 of 24,953,204 pages free (54.2%, about 55 GB) and auto_vacuum 0 (NONE). The candidate store has grown to 1.38 GB and the mi-homelab store is 398 MB (67.2% free when read on 2026-11-08). With auto_vacuum NONE those free pages never return to the filesystem without a full VACUUM, which needs the store's exclusive lock and therefore a stopped server. `fabro system prune` only adds free pages inside the file. The vps instances run the legacy 0.254 object store and hold no SQLite file. Related history: bd-ib-h7kbco measured run deletions on this same store holding the SQLite write lock for up to 26.8 s and failing concurrent runs' appends with "database is locked", which is why this clause forbids any vacuum against a live server and rejects FULL auto_vacuum.

### Proposed Changes

### non-functional-requirements.md — §"Fabro factory host provisioning"

Append this clause to the section, after **Retired environments are a declared axis.**:

**Store compaction is opt-in and runs only at zero runs.** The `fabro_server` role MUST provide a store-compaction step for every instance in `fabro_server_instances`, reached only through an explicit request: a dedicated tag or variable that a routine `ansible/fabro-hosts.yml` apply does not set. An apply that does not request it MUST NOT stop, restart or reconfigure any `fabro-server` unit on its account, and MUST NOT open, write or replace any Fabro store file.

- **Report mode.** The step MUST provide a read-only report mode. For each instance whose storage holds a SQLite store (`<home_dir>/storage/db/fabro.sqlite3`), the report MUST print the store's file size in bytes, its free-page share (free pages over total pages) and its `auto_vacuum` mode. It MUST open each store read-only, and it MUST NOT stop any unit or write any file. An instance whose storage holds no SQLite store MUST be reported as skipped, with that reason.
- **Preconditions.** A requested compaction MUST check each instance before stopping its unit. It MUST refuse an instance whose own server, queried on that instance's port and never through a default server, reports any run in a non-terminal state, or whose run count cannot be read. It MUST also refuse an instance whose store's filesystem has less free space than the store's live data (total pages minus free pages, times the page size) plus a margin that the role's `HOST_VARS.md` documents. A refusal MUST name the instance and the reason, and MUST leave that instance's unit running and its store unchanged. An instance whose storage holds no SQLite store MUST be skipped, with that reason, and its unit left running. A refusal or skip on one instance MUST NOT stop the step from processing another.
- **Compaction.** For an instance that passes the preconditions, the role MUST record the server's total run count, then stop the instance's unit. It MUST write a compacted copy of the store to a sibling path on the same filesystem, with `auto_vacuum` set to INCREMENTAL. It MUST verify the copy's integrity before it replaces the original, and it MUST keep the original until the read-back below passes. It MUST then start the unit.
- **Read-back and restore.** After the restart, the role MUST read back the compacted store's file size, free-page share and `auto_vacuum` mode, the unit's active state and the server's total run count. The compaction MUST be treated as failed unless the free pages are below 1 percent of the store's pages, `auto_vacuum` is INCREMENTAL, the unit is active, and the run count equals the count recorded before the stop. On any failed step from the stop onward, the role MUST restore the original store file, start the unit, and fail the apply naming the instance and the failed step.
- **No vacuum against a live store.** The role MUST NOT run `VACUUM`, `PRAGMA incremental_vacuum` or any other store rewrite while the instance's server is running, and it MUST NOT set `auto_vacuum` to FULL. A later compaction of a store already in INCREMENTAL mode MAY use `PRAGMA incremental_vacuum` in place of a full rewrite, under the same preconditions, stop, read-back and restore rules.
- **Tooling.** The role MUST NOT depend on a `sqlite3` command-line tool being present on the host. It MAY use the host's Python `sqlite3` module, or install the tool through the role itself.

The role's `HOST_VARS.md` MUST document the request switch, the report mode, the free-space margin and the operator procedure. That procedure MUST say that a requested compaction rides a cancel-to-idle restart window, and it MUST name the rollback (the kept original store file).

### scenarios.md — two new scenarios after "a Fabro instance that names its own binary and home renders a unit that runs them"

```markdown
## Scenario: a routine Fabro host apply or a store report leaves every server and store untouched

Given a factory host whose `fabro_server_instances` holds one instance with a SQLite store and one instance whose storage holds no SQLite store

When `ansible/fabro-hosts.yml` is applied without the store-compaction request, and then the compaction step runs in report mode

Then the routine apply MUST leave every `fabro-server` unit running and every Fabro store file unchanged

And the report MUST print, for the SQLite-backed instance, its store's file size, free-page share and auto_vacuum mode

And the report MUST list the other instance as skipped because its storage holds no SQLite store

And neither step MUST stop any unit

## Scenario: a requested Fabro store compaction refuses a busy instance and compacts an idle one to INCREMENTAL

Given a factory host with two SQLite-backed Fabro instances, one whose server reports a run in a non-terminal state and one whose server reports none, and the idle instance's store has more than 1 percent free pages and auto_vacuum NONE

When the store-compaction step is requested for both instances

Then the step MUST refuse the busy instance, naming it, and leave its unit running and its store unchanged

And the idle instance's store MUST report free pages below 1 percent of its pages and auto_vacuum INCREMENTAL

And the idle instance's unit MUST be active, and its server MUST report the same total run count it reported before the compaction

And when any step from the stop onward fails, the role MUST restore the original store file, start the unit, and fail naming the instance and the step
```

### Co-edits at revise time

Per this repository's heading-coverage co-edit discipline, the revise that accepts this proposal MUST add one `tests/heading-coverage.json` entry for each of the two new `## Scenario:` headings. Each entry MAY carry `test: "TODO"` with a non-empty reason until the role's consumer-tier tests land. No `## ` heading is added to non-functional-requirements.md.
