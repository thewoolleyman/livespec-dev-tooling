---
topic: sweep-fleet-hosts-daily-for
author: claude-opus-5-5 (no-local-agent-memory seat)
created_at: 2026-11-15T07:15:18Z
---

## Proposal: A daily fleet sweep files a migration item for each agent memory file

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a clause to the interactive fleet seat profile requiring a daily, read-only sweep of every agent-seat host's Claude Code and Codex memory stores, run from the control node, that files one de-duplicated migration work item per resolved file in the owning repository's ledger and names unreachable hosts and unresolved files in its output; add three scenarios stating that behaviour.

### Motivation

Maintainer ruling 2026-11-15, relayed by plan no-local-agent-memory (hetzner-xubuntu-info, epic hxi-7ituzy): keep Claude Code auto-memory on and back the no-local-memory rule with mechanisms, not prose. The managed memory-write guard (livespec-dev-tooling-pik7f2, merged in #4762) prevents most writes, but not on hosts or runtimes it does not cover yet (the Macs, Codex) or by writes that predate it. The manual RULE K sweep of 2026-11-14 found 10 stale notes across 4 repositories on 2 hosts. This proposal automates that sweep. It carries work item livespec-dev-tooling-jk54mp, whose spec-change-tier filing named this topic.

### Proposed Changes

Append the following paragraph to `non-functional-requirements.md` §"Interactive fleet seat profile", after the paragraph **The protocol is linked from agent guidance.**, and extend that section's **Scope.** paragraph with the sentence: "The daily agent-memory sweep under \"A daily sweep finds agent memory files.\" also reaches every agent-seat host it names, not only the dev host."

**A daily sweep finds agent memory files.** This repository MUST carry one Ansible role, `fleet_memory_sweep`, applied to the control node `vps` by a committed playbook, that installs a systemd timer which runs the sweep at least once a day. The sweep's host list MUST be one committed variable that names every host that runs agent seats: every member of `interactive_claude_hosts`, `hetzner-xubuntu`, and the Macs `chads-macbook-pro`, `macbook-air`, `macbook-m4-max` and `macmini`. Naming a host there makes it a sweep target only; it MUST NOT add that host to this repository's inventory. On each run the sweep MUST, for every listed host, list every file under `~/.claude/projects/*/memory/` and `~/.codex/memories/` of the seat user, reaching the host over tailnet `BatchMode` SSH with read-only commands only; the sweep MUST NOT delete, move or edit any file it finds.

For each Claude Code memory file, the sweep MUST resolve its owning repository from the project directory name: it MUST find, on that host, the git checkout or worktree whose absolute path Claude Code encodes to that name, and read that checkout's `origin` remote. When the remote names a repository of the fleet, the file resolves to that repository. A Codex store file, or a Claude Code file whose project does not resolve to a fleet repository, MUST be listed in the run output as unresolved, naming the host and the full path, and MUST NOT file a work item.

For each resolved file, the sweep MUST file one migration work item in the owning repository's ledger, through that repository's own ledger access on the control node. The item MUST name the host, the full path and the file name, MUST instruct that durable guidance in the file be migrated into the repository's `AGENTS.md` or a referenced `.ai/<topic>.md` by pull request and that the local copy then be deleted and the directory read back, and MUST carry the marker `memory-sweep: <host>:<full path>`. Before filing, the sweep MUST query that ledger for an open item carrying the same marker, and while one exists it MUST NOT file a second item for that host and path.

A host the sweep cannot reach, and a ledger it cannot read or write, MUST appear in the run's output with the failure reason the attempt reported. Such a failure MUST NOT stop the sweep from covering the remaining hosts and files.

Add three scenarios to `scenarios.md`, immediately after "## Scenario: a seat may type into a Claude seat's pane and is guided to prefer SendMessage":

## Scenario: a memory file on an agent-seat host becomes one migration item in its owning repository

Given the `fleet_memory_sweep` role is applied to the control node

And an agent-seat host the sweep lists holds a file under `~/.claude/projects/<slug>/memory/` whose project is a checkout of a fleet repository

When the sweep runs

Then that repository's ledger holds one open work item that names the host, the full path and the file, and carries the marker `memory-sweep: <host>:<full path>`

And the file is still present on the host

## Scenario: a repeated sweep files no second migration item while the first is open

Given the sweep has filed an open migration item carrying `memory-sweep: <host>:<full path>`

And the file is still present at that path

When the sweep runs again

Then the owning repository's ledger still holds exactly one open item carrying that marker

## Scenario: an unreachable agent-seat host is named in the sweep's output with its reason

Given the sweep lists a host that refuses or times out its SSH connection

When the sweep runs

Then the run's output names that host and the failure reason the SSH attempt reported

And every other listed host is still swept

The revise that ratifies this MUST add rows for the three new scenario headings and for the new clause to `tests/heading-coverage.json`, owned by livespec-dev-tooling-jk54mp, and regenerate the debt register in the revise commit. These scenarios MUST be stated with the clause in one atomic revision.
