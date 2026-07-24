---
topic: role-key-declaration-required
author: claude-fable-5-rop-sweep-fleet-policy
created_at: 2026-07-25T00:15:00Z
---

## Proposal: Role-key declaration required

### Target specification files

- SPECIFICATION/contracts.md
- tests/heading-coverage.json (co-edit, only if the accepted form adds/renames/removes a `## ` heading)

### Status note — filed early by design, ratify only after the enforcing code merges

Filed 2026-07-25 under epic `livespec-dev-tooling-e9j` (maintainer ruling 2026-07-24;
supervisor CALL #1 decision: file-early / ratify-after, the dh9r pattern). This proposal
MUST NOT be accepted before the epic's slice L (undeclared-role-key hard ERROR + fallback
retirement) and slice D (declaration-presence enforcement) are MERGED, or the spec would
claim unshipped enforcement — the same reasoning as the jjb/PR-#516 merge-sequencing
precedent. At ratification time, re-grep every FIND anchor against then-current master
(the vantage-model stream edits contracts.md actively) and update this proposal's edits to
match the exact shipped mechanics before accept.

### Summary

Amend `SPECIFICATION/contracts.md` §"Consumer configuration schema" to replace the
absent-key-no-op regime with the maintainer-ruled (2026-07-24) declaration-required
policy: every consumer of the layout-dependent checks MUST carry the
`[tool.livespec_dev_tooling]` block and MUST DECLARE every structural role key
explicitly. An UNDECLARED role key consumed by a wired check is a hard ERROR (the check
exits non-zero naming the key and the two sanctioned outs). A DECLARED-EMPTY key — `[]`
for list keys, `""` for the scalar keys `dataclasses_tree` / `neutral_hook_body_path`
(the declared-none convention, since TOML has no null literal) — is the sanctioned,
VISIBLE opt-out: the check no-ops with the structured INFO event exactly as today. The
whole-block-absent fallback to livespec-core's historical layout is RETIRED (core has
declared its own block since livespec PR #1663; the fallback's only remaining consumer
was a repo it could never describe). Declaration presence is additionally enforced
mechanically fleet-wide (slice D): a dev-tooling check in the `just check` aggregate plus
a fleet-conformance row over `.livespec-fleet-manifest.jsonc` members, with
`livespec-console-beads-fabro` excluded MECHANICALLY (scope = repos consuming
livespec-dev-tooling via `pyproject.toml`) and named, never silently skipped.

### Motivation

Epic `livespec-dev-tooling-e9j`: seven checks share the early-return "role key absent —
check no-ops, exit 0" shape, and measurement (2026-07-19, re-measured 2026-07-24) showed
the convention had silently disarmed most of the structural gate suite across the fleet
while CI reported green — three checks had never enforced anything in any repo. The
ratified fleet ROP policy was being carried by gates structurally inert in the repos that
define it. A reported-count INFO line (PR #516) made the no-op visible but not
impossible to mistake: exit codes and CI status still read identically to a pass. The
maintainer ruled (2026-07-24): absence becomes a hard error, and declaration presence
becomes a first-class mechanical enforcement so the regime cannot rot silently back in
the next fleet member.

### Proposed changes (anchors verified against origin/master ba7acaf 2026-07-25; re-verify at ratification)

EDIT 1 — §"Consumer configuration schema" intro paragraph: FIND the sentence beginning
"Missing keys MUST fall back to livespec-core's historical defaults" (through "keep its
bit-identical pre-G.6 behavior.") and REPLACE with the declaration-required policy: the
block is REQUIRED for every consumer wiring any layout-dependent check; every structural
role key MUST be declared; the historical-defaults fallback is retired.

EDIT 2 — closing paragraph of §"Role keys": FIND the paragraph beginning "Role keys
absent from the schema mean "the check no-ops on this consumer"" and REPLACE with the
three-tier semantics: UNDECLARED consumed key → hard ERROR naming the key and the two
sanctioned outs (declare the real value, or declare it explicitly empty with a reason
comment); DECLARED-EMPTY → visible sanctioned no-op with the existing structured INFO
event; DECLARED non-empty tree that walks zero `.py` files → hard ERROR (an armed check
inspecting nothing is a configuration defect, not a pass). Include the declared-none
scalar convention: `""` for `dataclasses_tree` / `neutral_hook_body_path` parses as
declared-none (slice L0's loader widening).

EDIT 3 — `dataclasses_tree` and `neutral_hook_body_path` bullets: amend "string or
null … When null, the check no-ops" to the declared-`""` form (TOML has no null; absence
is no longer a sanctioned spelling of "not applicable").

EDIT 4 — retire the §"Default layout fallback" codification (the section the intro
cites): replaced by a short retirement note naming the retiring release and the reason
(core declares its own block; the fallback mis-landed on the one repo without a
`pyproject.toml`).

EDIT 5 — new contract text for the declaration-presence enforcement (slice D): the
`just check`-aggregate check and the fleet-conformance row, their scope rule
(consumes-livespec-dev-tooling-via-pyproject), the mechanical-not-silent exclusion of
non-Python members, and — PENDING the maintainer's CALL #2 answer — whether the same
check is additionally exposed on the fleet repos' own `/livespec:doctor` surface.
Finalize this edit's text against the merged slice-D implementation.

The exact `REQUIRED_ROLE_KEYS` membership (the single exported source of truth slice L
ships) is normative for EDITs 1–2 and MUST be transcribed from the merged code at
ratification, never restated from memory.

### Acceptance shape

After ratification, contracts.md describes exactly the shipped behavior: no
absent-key-no-op clause survives anywhere in the section, the fallback section is
retired, the declared-empty convention (including the `""` scalar spelling) is
documented, and the enforcement (checks + conformance row) is attributed mechanically —
with `tests/heading-coverage.json` co-edited if any `## ` heading changed.
