---
topic: every-sessionstart-plugin-reconcile-on
author: claude-opus-5-5
created_at: 2026-11-12T21:14:15Z
---

## Proposal: Every fleet clone's SessionStart plugin reconcile on the dev host holds an existing orchestrator install record

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The Orchestrator build adoption rules hold a clone's orchestrator build only where the clone's SessionStart hook runs this library's `ensure-plugins`. The **Reach.** bullet says outright that a repository running its own reconcile is "not reached by them at all", so three fleet adopters (homelab, resume, openbrain) still move their orchestrator build on every session start. This proposal adds a **Fleet-wide hold.** bullet. Every fleet member's clone whose committed settings enable the orchestrator plugin MUST either run this library's `ensure-plugins` as its SessionStart plugin reconcile, or run a reconcile of its own that applies the same hold to an existing orchestrator install record, or run no SessionStart plugin reconcile at all. **Reach.** is amended to point at the new bullet instead of excluding those repositories, and one scenario covers an own-reconcile adopter.

### Motivation

livespec-dev-tooling-gpo5cp (plan gmktec-factory-placement, livespec-dev-tooling-me5aqz) asks for the dev-host-wide outcome that a session start leaves an existing orchestrator install record unchanged in every project that has one. Its launch judgement on 2026-11-12 at 21:10:33Z (spec v206) held it as spec-change tier, verdict unstated, generalization target ## Cross-repo coordination automation surface, with linked topic every-sessionstart-plugin-reconcile-on. The judgement is right. The ratified hold (**Session reconcile.**, **Absent install.**, **Single adoption path.**) binds only this library's `ensure-plugins`, and **Reach.** says a repository whose SessionStart hook does not run that recipe is not reached. An inventory on 2026-11-10 of the /data/projects clones whose committed settings enable the orchestrator plugin found 12 that run `just ensure-plugins`, 3 that run their own reconcile (homelab's .claude/hooks/ensure_plugins.py, resume's .claude/hooks/ensure-plugins.ts with session-plugin-freshness.ts, and openbrain's scripts/ensure-plugins.ts, each of which runs `claude plugin marketplace update` and then `claude plugin update <plugin> -s project` for every enabled plugin on every start), and 1 with no SessionStart reconcile (livespec-tdd-proof). Under orchestrator spec v337 the release branch advances only at a roll, so a session-start update moves an own-reconcile clone to the last rolled build. That is the intended default for a non-canary clone, but it breaks two things. A clone that a roll hand-adopts at a full commit (the v0.320.0 and v0.323.1 rolls of 2026-11-12 hand-adopted all three) can be moved by its next session start to whatever the marketplace offers. And livespec-dev-tooling-7upzav's host-captured proof of the hold, which starts a fresh session, cannot be captured on the dev host safely while any adopter's start can rewrite records. legacy-coordinator-agent ruled on 2026-11-12 at about 21:2xZ that this topic is filed and revises directly after a-new-orchestrator-release-s, and that gpo5cp is cut into one carrier per adopter in that adopter's own tracker.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Cross-repo coordination automation surface", subsection "Orchestrator build adoption", insert this bullet immediately AFTER the bullet that begins "- **Absent install.**":

"- **Fleet-wide hold.** Every fleet member's clone whose committed settings enable the orchestrator plugin MUST satisfy one of the following for its SessionStart plugin reconcile: (a) the clone's committed SessionStart hook runs this library's `ensure-plugins`, which holds as **Session reconcile.** states; (b) the clone runs a SessionStart reconcile of its own that, when `installed_plugins.json` has an install record for the orchestrator plugin whose project path is the working directory, runs neither `claude plugin update` nor `claude plugin install` for that plugin, leaves that record unchanged, and prints one line naming the plugin and the held build; or (c) the clone runs no SessionStart plugin reconcile at all. A reconcile under (b) MAY install the orchestrator plugin when no such record exists, as **Absent install.** provides, and MAY reconcile every other enabled plugin as it chooses. A clone under (b) or (c) is not a canary clone: **Tag adopt.**'s hold probe refuses it, and that is unchanged."

In the bullet that begins "- **Reach.**", replace the sentence "A repository whose SessionStart hook does not run this library's `ensure-plugins` is not reached by them at all." with:

"A repository whose SessionStart hook does not run this library's `ensure-plugins` is not reached by them, and is held instead to **Fleet-wide hold.**'s (b) or (c), which that repository's own hook implements."

In SPECIFICATION/scenarios.md, insert this scenario immediately after `## Scenario: an orchestrator build adopted outside ensure-plugins is reported and never downgraded`:

"## Scenario: an own-reconcile fleet clone's session start keeps its existing orchestrator install record

Given a fleet member's clone whose committed settings enable the orchestrator plugin and whose SessionStart hook runs a plugin reconcile of its own rather than this library's `ensure-plugins`

And `installed_plugins.json` has an install record for the orchestrator plugin whose project path is that clone, at a build other than the one the marketplace offers

When a session starts in that clone

Then the install record's `gitCommitSha` MUST be unchanged

And the reconcile MUST print one line naming the orchestrator plugin and the held build

And every other enabled plugin MAY be reconciled"

The revise pass that accepts or modifies this proposal MUST co-edit tests/heading-coverage.json with one entry for the new scenario heading. The entry MAY be a spec-first "test": "TODO" row whose reason names the host-captured tier, plus a "work_item" key naming livespec-dev-tooling-gpo5cp, and the debt register MUST be regenerated in the same commit. The hooks belong to other repositories and run against the dev host's real plugin registry, which no factory sandbox reaches, so the owed test is host-captured.
