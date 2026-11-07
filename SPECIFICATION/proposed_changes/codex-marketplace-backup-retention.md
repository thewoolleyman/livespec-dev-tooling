---
topic: codex-marketplace-backup-retention
author: claude-opus-5-5
created_at: 2026-11-07T17:48:36Z
---

## Proposal: Dev host retention reclaims Codex CLI's leftover marketplace backups

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add one leg to §"Dev host disk retention": each run removes a `marketplace-backup-*` directory under the retention user's Codex marketplace staging root once it has not been modified for longer than the scratch retention period. The run removes them only while it holds Codex's own staging lock, so a backup an upgrade in flight still needs is never removed. A scenario states the observable behaviour.

### Motivation

Measured on the dev host vmi3006760 on 2026-11-07 (plan dev-host-disk-retention, epic livespec-dev-tooling-qgwxo4; the finding came from the codex-plugin-hook-path-regression seat through legacy-coordinator-agent).

- `~/.codex/.tmp/marketplaces` held 3.0 G. 29 `marketplace-backup-<random>` directories accounted for about 2.5 G of it, and the five live marketplaces for about 0.6 G.
- Each backup holds a single `root/` that is a full copy of a plugin marketplace checkout, up to 322 M.
- They date from 2026-07-01 to 2026-11-06, and have accumulated at about two per day since 2026-10-20 (about 100-150 M/day).
- Codex CLI 0.166.0 creates one during each marketplace upgrade and never removes it. Nothing references them afterwards: none is named in `config.toml`, and none is a live marketplace.

The Codex hosts are exactly the `dev_hosts` group of `ansible/dev-host.yml`, which applies both `codex_config` and `dev_host_retention`, so the existing role is the right owner. No other leg reclaims this path, so it grows without bound.

The upstream root cause is Codex CLI not removing its own upgrade backups. It belongs to whoever owns this host's Codex CLI pin, and this leg is the host-side mitigation until that is fixed upstream.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Dev host disk retention", in the list under **What one run reclaims, and what it leaves.**, insert this bullet immediately after the pytest base temp bullet:

> - It MUST remove a Codex CLI marketplace backup directory, an entry named `marketplace-backup-*` directly under the retention user's `~/.codex/.tmp/marketplaces`, only when that directory has not been modified for longer than the scratch retention period. It MUST remove these directories only while it holds Codex's staging lock, `~/.codex/.tmp/marketplaces/.staging.lock`, as an exclusive lock, and when it cannot take that lock without waiting it MUST log that it skipped the backups and continue with its remaining steps, never abort and never wait. It MUST leave every other entry under `~/.codex/.tmp/marketplaces`, including every live marketplace directory and the staging directory, in place. When the retention user has no such directory, the run MUST log that it found none and continue.

The scratch retention period already governs this leg, and its role variable and `HOST_VARS.md` documentation already exist. The role MUST NOT introduce a separate period for it.

In `SPECIFICATION/scenarios.md`, immediately after `## Scenario: dev host retention removes a dead session's scratch directory and leaves a live one`, add:

```
## Scenario: dev host retention removes an aged Codex marketplace backup and leaves the live marketplaces

Given the retention user's `~/.codex/.tmp/marketplaces` holding a `marketplace-backup-*` directory unmodified for longer than the scratch retention period

And a `marketplace-backup-*` directory modified within the scratch retention period

And a live marketplace directory unmodified for longer than the scratch retention period

And no process holding `~/.codex/.tmp/marketplaces/.staging.lock`

When one run of the dev host retention script completes

Then the aged backup directory MUST be removed

And the recent backup directory and the live marketplace directory MUST remain in place

And the run's log MUST name the removed directory
```

The new H2 scenario heading MUST be registered in `tests/heading-coverage.json` in the revise commit that accepts this proposal.
