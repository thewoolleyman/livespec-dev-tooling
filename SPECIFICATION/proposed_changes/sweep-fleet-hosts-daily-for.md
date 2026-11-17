---
topic: sweep-fleet-hosts-daily-for
author: claude-sonnet-5-5
created_at: 2026-11-17T06:00:20Z
---

## Proposal: A daily sweep files a migration work item for every agent-memory file on each fleet seat host

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Extend §"Interactive fleet seat profile": committed host provisioning MUST install a scheduled job that, at least once a day on each fleet host that runs agent seats, lists every file under ~/.claude/projects/*/memory/ and ~/.codex/memories/ and files ONE migration work item per file in the owning fleet repository's ledger, deduplicated against open items, with unreachable hosts reported in the run output.

### Motivation

Maintainer ruling 2026-11-15 (keep auto-memory on, back the rule with mechanisms). The managed memory-write hook (claude_memory_write_guard) does not cover Codex and cannot be enforced on every Mac, so notes still accumulate. The manual RULE K sweep of 2026-11-14 found 10 stale notes in 4 repositories on 2 hosts. A scheduled sweep catches what the hook misses and automates that manual sweep. Plan: no-local-agent-memory. Implementation work item: livespec-dev-tooling-jk54mp, blocked waiting on this proposal.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Interactive fleet seat profile", insert a new paragraph after the paragraph beginning **The Macs take the same guard through the macOS managed path.** and before **The protocol is linked from agent guidance.**:

> **A daily sweep files a migration item for each local agent-memory file.** Committed host provisioning MUST install on each fleet host that runs agent seats (`vps`, `hetzner-xubuntu`, `gamingpc-xubuntu` and the members of `interactive_claude_macs`) a scheduled job that runs at least once a day and lists every file under `~/.claude/projects/*/memory/` and `~/.codex/memories/`. For each file whose project resolves to a fleet repository, the job MUST file ONE migration work item in that repository's ledger that names the host, the file's full path and the file. It MUST NOT file a second item while an open migration item for the same host and path exists. A host the job cannot reach MUST appear in the run output with the failure reason, and MUST NOT be silently skipped. The sweep complements the memory-write guard: it covers writes the guard cannot see, such as Codex and any Mac the guard has not reached. The job lists and files only; it MUST NOT delete or move a memory file.
