---
topic: dev-host-retention-tmpfs-and-alert
author: claude-opus-5-5
created_at: 2026-11-01T16:52:46Z
---

## Proposal: Dev host retention covers /tmp, reports both filesystems, and alerts before full

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend §"Dev host disk retention" so one retention run also bounds dead agent sessions' scratch directories under the per-user Claude Code temp root and pytest's per-user base temp, so the uv prune completes in a cache that root-owned paths have contaminated, so bulk run dumps are bounded where they land and never land on tmpfs, so the root filesystem and /tmp are both reported, and so a separate frequent check alerts the maintainer through the host's ntfy topic when either filesystem passes a used-share threshold.

### Motivation

Measured 2026-11-01. The daily retention freed 1.0-1.6 G per run while the root filesystem lost about 8 G/day and reached 98% (16 G free). /tmp, a 48 G tmpfs, reached 100% at 13:50Z and broke Bash, gates and factory launches: 23 G of it was the scratch directory of a dead agent session, filled by an orphaned script writing 330-390 MB fabro event dumps per run, and 3.5 G was /tmp/pytest-of-ubuntu. A manual sweep removed 2275 dead-session directories (12.7 G) under /tmp/claude-1000. `uv cache prune` run as the cache's owner aborted on a root-owned .pyc under ~/.cache/uv/archive-v0 (Permission denied), the same abort fj6dm5 recorded on 2026-10-21, so the uv leg has never completed. No check warned before either filesystem filled: the incident was found when commands failed. The current section reports only / and covers none of these paths.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Dev host disk retention":

1. In **Scope**, after "the uv cache and the docker store its factory and gate work leave behind", add: "Its `/tmp` is a memory-backed tmpfs that agent sessions, pytest and factory tooling write scratch data into, so filling it breaks the shell of every session on the host."

2. Replace the uv bullet under **What one run reclaims, and what it leaves** with:

"- It MUST prune the uv cache AS THE USER THAT OWNS THAT CACHE. Before the prune it MUST restore that user's ownership of every path in the cache that another user owns. When the prune still cannot remove a path, the run MUST log that path and continue with its remaining steps, never abort."

3. Add these bullets to the same list, after the gate-run bullet:

"- It MUST remove a session scratch directory under the per-user Claude Code temp root (`/tmp/claude-<uid>/<project>/<session-id>`) only when no running process carries that session id in its `CLAUDE_CODE_SESSION_ID` environment variable AND the directory has not been modified for longer than the scratch retention period. It MUST leave the directory of a session a running process carries in place, whatever its age.
- It MUST remove an entry under pytest's per-user base temp directory (`/tmp/pytest-of-<user>`) only when it has not been modified for longer than the scratch retention period.
- It MUST hold the bulk-dump directory, a role variable on the root filesystem and never on a tmpfs, under its configured size cap by removing its oldest files first. Automation this repository provisions on the dev host MUST write run dumps (such as fabro event dumps) there and MUST NOT write them under `/tmp`."

4. Replace "Each run MUST log what it removed and the root filesystem's free space before and after." with: "Each run MUST log what it removed and the free space of the root filesystem and of `/tmp`, before and after."

5. Add a new paragraph before the closing cargo paragraph:

"**Alert before full.** A second systemd timer, installed by the same role, MUST run a capacity check at least every 15 minutes. When the used share of the root filesystem or of `/tmp` is at or above that filesystem's threshold, the check MUST publish a notification to the host's ntfy topic naming the filesystem, its used share and its free space. It MUST publish again while the condition holds no more often than once per role-configured repeat interval. The two thresholds, the scratch retention period, the bulk-dump directory and its size cap MUST be role variables documented in the role's `HOST_VARS.md`, with defaults of 85% for the root filesystem, 75% for `/tmp`, 6 hours for scratch retention and 20 G for the bulk-dump cap."

In SPECIFICATION/scenarios.md, after "## Scenario: dev host retention leaves an in-flight gate run and removes an aged terminal one", add:

"## Scenario: dev host retention removes a dead session's scratch directory and leaves a live one

Given a session scratch directory under `/tmp/claude-<uid>` unmodified for longer than the scratch retention period whose session id no running process carries

And a session scratch directory equally old whose session id a running process carries

When one run of the dev host retention script completes

Then the dead session's directory MUST be removed

And the live session's directory MUST remain in place

And the run's log MUST name the removed directory and the free space of the root filesystem and of `/tmp` before and after

## Scenario: the dev host capacity check alerts when /tmp passes its threshold

Given `/tmp` on the dev host with a used share at or above its configured threshold

When the capacity check runs

Then it MUST publish one notification to the host's ntfy topic naming `/tmp`, its used share and its free space

And a second run inside the repeat interval MUST NOT publish another"
