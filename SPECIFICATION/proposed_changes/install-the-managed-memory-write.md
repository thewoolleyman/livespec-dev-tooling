---
topic: install-the-managed-memory-write
author: claude-opus-5-5 (no-local-agent-memory seat)
created_at: 2026-11-15T13:27:57Z
---

## Proposal: The managed memory-write guard is installed on every interactive Claude host, the Macs included

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend non-functional-requirements.md §"Interactive fleet seat profile" with a memory-write guard clause and a Mac delivery clause, plus two scenarios. One Ansible role, `claude_memory_write_guard`, installs a Claude Code managed-policy PreToolUse hook. The hook refuses Write and Edit calls into `~/.claude/projects/<project>/memory/` and Bash commands whose write target it positively identifies there, and routes the content to `AGENTS.md`, a referenced `.ai/<topic>.md` by pull request, or the ledger. It is applied to every member of `interactive_claude_hosts` through `/etc/claude-code/managed-settings.d/`. It is also applied to every member of a new inventory group, `interactive_claude_macs` (chads-macbook-pro, macbook-air, macbook-m4-max and macmini), through the macOS managed location `/Library/Application Support/ClaudeCode/managed-settings.d/`, by a committed, reversible converge that runs on each Mac. The refusal then holds in every session on every interactive host, whatever livespec Driver build a repository installs.

### Motivation

Plan no-local-agent-memory (hetzner-xubuntu-info, epic hxi-7ituzy), assertion 7: a local agent-memory write is refused in every repository that enables the livespec Driver. An independent host replay on 2026-11-15 (record 01a1df56) found it NOT reproduced, and the fleet read found why. Governed repositories on chads-macbook-pro (15 projects) and macbook-air (4 projects) run pre-fix Driver builds (v0.15.1 and v0.15.2), whose Bash hook lets `cd <memory dir> && cat > f.md <<EOF` through, and those Macs carry no managed guard. On vps and gamingpc-xubuntu the same stale Driver builds are harmless, because the managed guard that livespec-dev-tooling-pik7f2 (#4762) installed refuses the write whatever the Driver build. legacy-coordinator-agent ruled (2026-11-15) that the Mac fix is that same mechanism, work item livespec-dev-tooling-i76rv2, which was filed at spec-change tier with this topic and generalizes §"Interactive fleet seat profile". The ratified spec does not yet state the guard even for the Linux hosts that pik7f2 already converges, so this proposal states both. The maintainer's 2026-11-15 ruling keeps Claude Code auto-memory on and enforces the no-local-memory rule with mechanisms, not prose. macOS drop-in surface, as read on 2026-11-15. The managed-settings documentation (https://code.claude.com/docs/en/managed-settings) states: "File-based: `managed-settings.json`, an optional `managed-settings.d/` directory, and `managed-mcp.json` in the system directory: `/Library/Application Support/ClaudeCode/` on macOS, `/etc/claude-code/` on Linux and WSL", and "Claude Code merges `managed-settings.json` first, then every `*.json` file in the directory in alphabetical order". So the drop-in directory is documented for macOS exactly as it is for Linux, where it is measured on the fleet's hosts. Measured read-only on chads-macbook-pro: Claude Code 2.1.311 (~/.local/bin/claude -> versions/2.1.311), and `/Library/Application Support/ClaudeCode/` does not exist yet. That a hook declared only in a macOS drop-in fires in a fresh session is NOT yet measured. A session running on the Mac must measure it, because fleet_host_guard refuses a remote host change. The proof for the Mac scenario measures it on every converged Mac. If it does not hold, this clause is re-worded to a role-written, merged `/Library/Application Support/ClaudeCode/managed-settings.json`, keeping root:wheel ownership, the reversible removal and the drift read, before i76rv2 is accepted. In-flight: #4774 (sweep-fleet-hosts-daily-for) adds a separate section and scenarios after the same scenario anchor. This proposal aligns with it: the sweep finds what the guard did not prevent, and neither changes the other's text.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Interactive fleet seat profile", insert the following two paragraphs immediately after the paragraph beginning "**Where the policy is converged.**":

**Local agent-memory writes are refused by managed policy.** This repository MUST carry one Ansible role, `claude_memory_write_guard`, that installs a Claude Code PreToolUse hook as root-owned MANAGED policy on each interactive host it is applied to. In every Claude Code session on such a host, whether or not a livespec Driver plugin is enabled where the session started, the hook MUST refuse each Write or Edit into `~/.claude/projects/<project>/memory/` and each Bash command whose write target it positively identifies under that directory. The identified Bash write forms MUST include at least livespec core's minimum memory write-form set, judged per command segment and through `sh -c`, `bash -c` and `env` wrappers. A destination computed at runtime, such as a variable or a script file, is outside what the hook MUST refuse. The refusal reason MUST route the content to the repository's `AGENTS.md` or a `.ai/<topic>.md` file it references, by pull request, or to the ledger for trackable work. The hook MUST NOT refuse a read of that directory or a write outside it, including a write to a tracked `.ai/memory/` path in a repository. The role MUST NOT set `allowManagedHooksOnly` or `autoMemoryEnabled`. The playbook `ansible/claude-memory-guard.yml` MUST apply the role to every member of `interactive_claude_hosts`, installing its policy as a drop-in under `/etc/claude-code/managed-settings.d/`. `hetzner-xubuntu` MUST converge the same role from its own repository's committed provisioning at its pin of this repository.

**The Macs take the same guard through the macOS managed path.** The maintainer's Macs that run interactive Claude Code sessions MUST be the members of one inventory group, `interactive_claude_macs`: `chads-macbook-pro`, `macbook-air`, `macbook-m4-max` and `macmini`, each bound to its tailnet name and its interactive account. The memory-write guard MUST be applied to every member of `interactive_claude_macs` by a committed playbook that installs the same role's hook and policy under the macOS managed location `/Library/Application Support/ClaudeCode/`, with the policy as a drop-in under its `managed-settings.d/`, owned by root with group `wheel`. The converge MUST run on each Mac against its own host, not as a remote mutation from another fleet host, and MUST be reversible by a committed change that removes the drop-in and takes the Mac out of the group. A Mac on which the converge cannot obtain root MUST fail the converge naming the Mac and the missing precondition, as §"Host provisioning tree" **Out-of-band preconditions fail at the start.** requires. After the committed apply, the drift report for each converged Mac MUST read clean. A Mac in the group need not have a livespec Driver installed; the guard covers its sessions either way.

Add two scenarios to SPECIFICATION/scenarios.md, immediately after "## Scenario: a seat may type into a Claude seat's pane and is guided to prefer SendMessage":

## Scenario: a managed hook refuses a local agent-memory write on an interactive host

Given `ansible/claude-memory-guard.yml` has been applied to a member of `interactive_claude_hosts`

And a Claude Code session on that host runs in a repository whose installed livespec Driver predates the Bash memory-write fix

When the session attempts a Write, an Edit, a Bash output redirection, and a Bash `cd` into its `~/.claude/projects/<project>/memory/` directory followed by a here-document written to a literal file name

Then each attempt MUST be refused by the managed PreToolUse hook, with a reason that routes the content to `AGENTS.md`, a referenced `.ai/<topic>.md` by pull request, or the ledger

And a read of that directory and a write to a tracked `.ai/memory/` path MUST NOT be refused

## Scenario: a Mac converged for the memory-write guard refuses a local agent-memory write

Given the memory-write guard's committed playbook has been applied on a member of `interactive_claude_macs`

And a Claude Code session on that Mac is started in a directory where no livespec Driver plugin is enabled

When the session attempts a Write, an Edit, and a Bash `tee` whose literal target is under its `~/.claude/projects/<project>/memory/` directory

Then each attempt MUST be refused by a PreToolUse hook declared under `/Library/Application Support/ClaudeCode/managed-settings.d/`

And the drift report for that Mac MUST read clean

The revise that ratifies this MUST add `tests/heading-coverage.json` rows for both new scenario headings, owned by livespec-dev-tooling-i76rv2 (the Mac scenario) and livespec-dev-tooling-pik7f2 (the interactive-host scenario), and MUST regenerate the debt register in the revise commit.
