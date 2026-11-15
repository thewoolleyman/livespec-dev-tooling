---
topic: sweep-fleet-hosts-daily-for
author: claude-opus-5-5 (no-local-agent-memory seat)
created_at: 2026-11-15T07:15:18Z
---

## Proposal: A daily agent-memory sweep files a migration item for each local agent-memory file

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a new non-functional section, §"Fleet agent-memory sweep", after §"Dev host disk retention". It requires a role-installed daily timer on the control node. The timer reads, without changing anything, every agent-seat host's Claude Code and Codex memory stores. For each resolved Claude Code file it files one de-duplicated migration work item in the owning repository's ledger, and the item never carries the file's content. Every unresolved file, unreachable host and failed ledger is recorded in a fixed run summary, and persistent failures alert through `host-unit-alert@`. Six scenarios state the behaviour.

### Motivation

Maintainer ruling 2026-11-15, relayed by plan no-local-agent-memory (hetzner-xubuntu-info, epic hxi-7ituzy): keep Claude Code auto-memory on and back the no-local-memory rule with mechanisms, not prose. The managed memory-write guard (livespec-dev-tooling-pik7f2, merged in #4762) prevents most writes. It cannot cover hosts or runtimes it does not reach yet (the Macs, Codex), or files written before it was installed. The manual RULE K sweep of 2026-11-14 found 10 stale notes across 4 repositories on 2 hosts. This proposal automates that sweep. It carries work item livespec-dev-tooling-jk54mp, whose spec-change-tier filing named this topic.

Revised after legacy-coordinator-agent's grade on #4774, which required that the item never copy the file's content, and after a full doctor LLM pass. That pass moved the clause out of §"Interactive fleet seat profile" into its own section. It also defined the host list, the seat user, repository resolution, ledger access and the run summary; added scenarios for the unresolved, failed-ledger and read-only paths; and fixed the de-duplication field and the Codex disposition.

### Proposed Changes

Insert the following new section into `non-functional-requirements.md` immediately after §"Dev host disk retention" and before §"Fleet manifest adopter profiles":

## Fleet agent-memory sweep

**Scope.** This section states the standing sweep that finds agent guidance left in local agent-memory stores on the fleet's agent-seat hosts and routes each such file to its owning repository's ledger. Durable agent guidance MUST live in a repository's `AGENTS.md` or a `.ai/<topic>.md` file it references, never in a local agent-memory store: the Claude Code layout `~/.claude/projects/<project>/memory/` or the Codex store `~/.codex/memories/`. A file found in either store is therefore a defect to migrate, not a record to keep. This section does not govern the hooks that refuse new memory writes; it covers what those hooks did not prevent.

**Provisioned on the control node.** The agent-memory sweep MUST run at least once a day from a systemd timer that a role in the provisioning tree, `fleet_memory_sweep`, installs on the Ansible control node through a committed playbook, as §"Host provisioning tree" requires for every scheduled host job.

**The hosts it reads.** The hosts the agent-memory sweep reads MUST be the members of inventory group `interactive_claude_hosts` together with every entry of one committed role variable, `fleet_memory_sweep_extra_hosts`, which names the agent-seat hosts this repository does not converge. Every host the sweep reads, from either source, MUST carry its SSH target and the user whose stores are read, the seat user. Listing a host in `fleet_memory_sweep_extra_hosts` MUST NOT add it to this repository's inventory. The role's `HOST_VARS.md` MUST document both variables.

**Read-only reach.** The agent-memory sweep MUST reach each host over OpenSSH to the host's tailnet address with `BatchMode=yes`, and MUST run only commands that read: it MUST NOT create, delete, move or edit any file on a swept host. A host on which neither store directory exists for the seat user MUST count as holding zero files, not as a failure.

**Resolving the owning repository.** For each file under a Claude Code `projects/<project>/memory/` directory, the agent-memory sweep MUST find, on that host, every git checkout or worktree whose absolute path Claude Code encodes to `<project>`, and read each candidate's `origin` remote. The file MUST resolve to a repository only when exactly one candidate exists and its `origin` names a repository listed as a member in livespec core's `.livespec-fleet-manifest.jsonc`. A file with no candidate, more than one candidate, or a candidate whose remote names no fleet member MUST be unresolved. Every file in a Codex store MUST be unresolved, because a Codex memory carries no per-project path to resolve.

**One migration item per file, never its content.** For each resolved file, the agent-memory sweep MUST file one migration work item in the owning repository's ledger. The item MUST carry only the host, the full path, the file name, the file's size and the sha256 of its content, and MUST NOT contain any of the file's content, because a memory note may hold private or credential-adjacent text and the ledger is shared and durable. The item MUST instruct that the repository's seat read the file on the host, land its durable guidance in `AGENTS.md` or a referenced `.ai/<topic>.md` by pull request, delete the local copy, and read the directory back empty. The item MUST record the de-duplication key `memory-sweep:<host>:<full path>` in its `external_ref` field.

**No duplicate while one is open.** Before filing, the agent-memory sweep MUST query the owning ledger for an open item whose `external_ref` equals that key. While one exists it MUST NOT file another for that host and path, even when the file's size or sha256 has changed. Once that item is closed, a run that still finds the file MUST file a new item.

**Ledger access.** The agent-memory sweep MUST reach each repository's ledger only through one committed role variable, `fleet_memory_sweep_ledgers`, which maps each fleet repository to the ledger launcher on the control node that serves that repository's tenant. The role MUST assert at converge time that every launcher the map names exists and is executable on the control node, failing the converge with the missing path otherwise, as §"Host provisioning tree" requires of out-of-band preconditions. A credential MUST reach the ledger client only as `constraints.md` §"No credential in a process's argument vector" allows.

**The run summary and its alert.** Each run MUST write a summary, readable by its owner only, to `/var/lib/fleet-memory-sweep/last-run.json`, replacing the previous one. It MUST list every host read and its file count; every item filed and every key skipped as a duplicate; every unresolved file with its host, full path and, where any exist, its candidate checkout paths; every unreachable host with the reason the SSH attempt reported; and every ledger read or write that failed, with its repository and reason. A failure on one host, file or ledger MUST NOT stop the run from covering the rest. The run MUST exit non-zero when any ledger read or write failed, or when any host has been unreachable on three consecutive runs, and the timer's unit MUST name `host-unit-alert@.service` in `OnFailure=` per §"Host provisioning tree" **A role-installed unit alerts as itself**.

Add six scenarios to `scenarios.md`, immediately after "## Scenario: a seat may type into a Claude seat's pane and is guided to prefer SendMessage":

## Scenario: a memory file on an agent-seat host becomes one migration item in its owning repository

Given the `fleet_memory_sweep` role is applied to the control node

And a host the agent-memory sweep reads holds a file under `~/.claude/projects/<project>/memory/` whose project is exactly one checkout of a fleet repository

When the agent-memory sweep runs

Then that repository's ledger holds one open work item whose `external_ref` is `memory-sweep:<host>:<full path>` and which names the host, the full path, the file name, its size and its content sha256

And the filed item does not contain the file's text

## Scenario: a repeated agent-memory sweep files no second item while the first is open

Given the agent-memory sweep has filed an open migration item whose `external_ref` is `memory-sweep:<host>:<full path>`

And the file is still present at that path

When the agent-memory sweep runs again

Then the owning repository's ledger still holds exactly one open item with that `external_ref`

## Scenario: the agent-memory sweep changes nothing on the hosts it reads

Given a host the agent-memory sweep reads holds files in its Claude Code and Codex memory stores

When the agent-memory sweep runs

Then every file in both stores is present with its content unchanged

And no file was added to either store

## Scenario: an unresolvable memory file is recorded and files no item

Given a host the agent-memory sweep reads holds a Codex store file and a Claude Code memory file whose project is not a checkout of a fleet repository

When the agent-memory sweep runs

Then the run summary lists both files as unresolved with the host and full path

And no ledger holds an item for either file

## Scenario: an unreachable agent-seat host is recorded with its reason

Given a host the agent-memory sweep reads refuses or times out its SSH connection

When the agent-memory sweep runs

Then the run summary names that host and the reason the SSH attempt reported

And every other host is still read

## Scenario: a ledger the agent-memory sweep cannot write is recorded and alerts

Given a resolved memory file whose owning repository's ledger rejects the write

When the agent-memory sweep runs

Then the run summary names that repository and the reason

And items for other repositories are still filed

And the run exits non-zero, so `host-unit-alert@` raises an alert naming the sweep's unit and the host

The revise that ratifies this MUST add a `tests/heading-coverage.json` row for `## Fleet agent-memory sweep` and for each of the six new scenario headings, owned by livespec-dev-tooling-jk54mp, and regenerate the debt register in the revise commit. The section and its six scenarios MUST be ratified in one atomic revision.
