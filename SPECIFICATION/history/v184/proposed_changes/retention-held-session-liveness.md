---
topic: retention-held-session-liveness
author: claude-opus-5-5:dev-host-disk-retention
created_at: 2026-11-10T09:57:41Z
---

## Proposal: Retention liveness comes from the session's own process holding its scratch directory

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

A session scratch directory is live when a running process holds it (working directory or an open file descriptor at or beneath it) or carries the session id in CLAUDE_CODE_SESSION_ID; the retention never removes a live session's directory. A scenario states the held-directory case.

### Motivation

Measured on the dev host vmi3006760 on 2026-11-10, by plan dev-host-disk-retention (epic livespec-dev-tooling-qgwxo4) at legacy-coordinator-agent's request. Recorded on livespec-dev-tooling-4rcuxp and livespec-dev-tooling-ovnrsv.

- The clause calls a session live only when some running process carries its id in `CLAUDE_CODE_SESSION_ID`. The Claude Code main process does NOT carry that variable: 0 of 31 running `claude` processes had it in `/proc/<pid>/environ`. Only its children do.
- What keeps every live session alive to the check today is an OPTIONAL child: the playwright MCP server, configured at user scope, which carries the id for the life of the session (31 of 31). Tool-call shells carry it only while a tool call runs.
- The age floor does not protect a long-lived session. A session directory's mtime changes only when a direct child entry is added or removed, so a live session's directory can be days old (this plan's own read 2026-11-05).
- So a live session whose MCP child has died, or that runs without that server, is read as dead, and the daily timer deletes its scratchpad: task outputs, background-task logs and scratch files. That is destructive and silent.
- Every one of the 31 running `claude` processes holds an open file descriptor beneath its own session directory (`<session-id>/tasks`). That is a signal the session's own process holds for its whole life.

The amended clause keeps the environment signal and adds the held-directory signal as a second, primary reason to keep a directory. That only narrows what is removed, within the clause's "only when". The scenario makes the new keep behaviour observable. livespec-dev-tooling-ovnrsv implements it.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Dev host disk retention", replace the bullet

> - It MUST remove a session scratch directory under the per-user Claude Code temp root (`/tmp/claude-<uid>/<project>/<session-id>`) only when no running process carries that session id in its `CLAUDE_CODE_SESSION_ID` environment variable AND the directory has not been modified for longer than the scratch retention period. The liveness check MUST read the environment of every running process on the host, whatever user owns it. It MUST leave the directory of a session a running process carries in place, whatever its age.

with

> - It MUST remove a session scratch directory under the per-user Claude Code temp root (`/tmp/claude-<uid>/<project>/<session-id>`) only when the session is not live AND the directory has not been modified for longer than the scratch retention period. A session is live when a running process holds its directory, as that process's working directory or through an open file descriptor whose target is the directory or lies beneath it, or when a running process carries the session id in its `CLAUDE_CODE_SESSION_ID` environment variable. The liveness check MUST read the working directory, the open file descriptors and the environment of every running process on the host, whatever user owns it, and a process entry that vanishes or cannot be read during the check MUST NOT stop it. It MUST leave the directory of a live session in place, whatever its age. The held-directory signal is the one a session's own process provides; the environment signal is carried by that process's children, and a session MUST NOT depend on an optional child process to stay live.

In `SPECIFICATION/scenarios.md`, immediately after `## Scenario: dev host retention removes a dead session's scratch directory and leaves a live one`, add:

```
## Scenario: dev host retention leaves an aged session scratch directory that a running process holds open

Given a session scratch directory under `/tmp/claude-<uid>` unmodified for longer than the scratch retention period, whose session id no running process carries

And a running process holding an open file descriptor beneath that directory, with no child process carrying the session id

When one run of the dev host retention script completes

Then that directory MUST remain in place
```

The new H2 scenario heading MUST be registered in `tests/heading-coverage.json` in the revise commit that accepts this proposal, owned by livespec-dev-tooling-ovnrsv.
