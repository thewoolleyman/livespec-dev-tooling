---
topic: a-shared-check-refuses-a-new-data-projects-clone-path
author: claude-opus-5-5
created_at: 2026-11-14T00:11:23Z
---

## Proposal: A shared check refuses a new /data/projects clone path

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a canonical per-commit check, `no_new_data_projects_path` (`check-no-new-data-projects-path`), that refuses any line a change ADDS which names `/data/projects` as a path, outside immutable history, vendored trees, and dated records. Add a central fleet-conformance row that applies the same rule to every fleet manifest member and adopter, including the instruction-only adopters that have no `just check` aggregate.

### Motivation

Maintainer ruling, 2026-11-14 (verbatim): "Fix this on all repos, everything should refer to $HOME/workspace as the place canonical project clones live, never in /data/projects, even if that's the rreal one workspace should always be syumlinked. Fix this across all livespec tenants." A seat on hetzner-xubuntu, where checkouts live in a real ~/workspace and /data does not exist, followed hard-coded /data/projects paths in instruction files and wasted turns failing. The fleet-wide sweep of 2026-11-14 (one draft PR per tenant repository) removes the existing references; without a mechanical refusal they return with the next copied runbook line. The check is diff-based so the history, vendored, and dated-record references that legitimately remain never redden a repository.

### Proposed Changes

In `SPECIFICATION/contracts.md`, add a new H3 section after §"`no_ambient_environment_loops` check":

```
### `no_new_data_projects_path` check

This is a canonical per-commit check under `livespec_dev_tooling/checks/`. Once a consumer's library pin reaches the release that ships this module, that consumer's `check-aggregate-completeness` and the fleet-conformance row `canonical-check-slugs-wired` MUST report the slug as unwired until the consumer either wires `check-no-new-data-projects-path` or declares a reasoned waiver under §"Shared check inventory" **Canonical-check waivers**.

Invocation: `python -m livespec_dev_tooling.checks.no_new_data_projects_path`, from the repository root. Canonical project clones live under `~/workspace` on every host; on a host whose data disk lives elsewhere, `~/workspace` is a symlink to that location. The check refuses a change that reintroduces the VPS data-disk path as a clone location.

Algorithm:

1. Resolve the base as `git merge-base HEAD origin/<canonical>`, where `<canonical>` is `git symbolic-ref --short refs/remotes/origin/HEAD` with the `origin/` prefix removed, falling back to `master`. When the base cannot be resolved, the check MUST emit a structured warning naming the failure and exit `0`; it MUST NOT fall back to scanning the whole tree.
2. Collect every line ADDED relative to the base, in tracked files, from `git diff --unified=0 --no-color <base>` (committed, staged, and unstaged changes alike).
3. A line is an offender when it contains the token `/data/projects` at an absolute-path start: at the start of the line, or immediately after whitespace or one of the characters `` ` `` `'` `"` `(` `[` `{` `=` `:` `,`. An occurrence preceded by any other character (for example the `current/data/projects/...` paths inside a root-filesystem backup mirror) is not an offender.
4. A line is exempt when its file path matches any of: `SPECIFICATION/history/**`, `SPECIFICATION/proposed_changes/**` (a pending proposal quotes the text it changes), `**/_vendor/**`, `archive/**`, `plan/archive/**`, `plan/*/research/**`, `**/*.jsonl`, or a basename carrying an ISO date (`YYYY-MM-DD`). These are immutable history, vendored trees, and dated records.
5. A line is exempt when it also names `~/workspace`, `$HOME/workspace`, or `/home/<user>/workspace`: such a line states the physical-layout rule (that `~/workspace` is a symlink to the data-disk location) rather than naming the data disk as the clone location.
6. Exit `0` when no offender remains; exit `4` otherwise.

Each finding carries `check_id` `no_new_data_projects_path`, `status` `fail`, `path` (repository-relative), `line` (the line number in the working-tree file), and a `message` naming the offending text and the replacement form: `~/workspace/<repo>` in prose, `"$HOME/workspace/<repo>"` in shell, and the explicit `/home/<user>/workspace/<repo>` in a systemd system unit, where `%h` resolves to `/root`.

**Fleet vantage.** The scheduled fleet-conformance sweep MUST carry a row, `no-new-data-projects-path`, that applies steps 3 to 5 to every manifest `fleet` member and every `adopter`, reading each member's default-branch tree. Because the row has no per-change base, it MUST compare against a baseline recorded in this repository: a per-member list of `(path, line text)` pairs present when this section is ratified. It reports any offender that is not in that baseline. A member whose tree cannot be read is skipped with a warning, never passed. This row is what covers the instruction-only adopters, which carry no `just check` aggregate into which the canonical slug could be wired.
```

In `SPECIFICATION/scenarios.md`, add:

```
## Scenario: a change that adds a /data/projects clone path is refused

Given a governed repository whose branch adds the line `git -C /data/projects/livespec status` to `AGENTS.md`
When `python -m livespec_dev_tooling.checks.no_new_data_projects_path` runs from the repository root
Then it exits 4 with a finding naming `AGENTS.md`, the added line's number, and the replacement form `"$HOME/workspace/<repo>"`

## Scenario: history, vendored, dated-record and layout lines pass the /data/projects check

Given a governed repository whose branch adds `/data/projects/livespec` only under `SPECIFICATION/history/v001/`, under `_vendor/`, in a file named `receipt-2026-11-14.md`, and in the line `~/workspace is a symlink to /data/projects on this host`
When `python -m livespec_dev_tooling.checks.no_new_data_projects_path` runs from the repository root
Then it exits 0
```

Arming order: the release that ships the module MUST be tagged only after the 2026-11-14 sweep pull requests have merged, or been dispositioned, in every consumer whose own diff would otherwise trip the check. The fleet row's baseline is recorded from the members' default branches after those merges.
