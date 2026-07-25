---
topic: role-key-declaration-required
author: claude-fable-5-rop-sweep-fleet-policy
created_at: 2026-07-25T00:15:00Z
---

## Proposal: Role-key declaration required

### Target specification files

- SPECIFICATION/contracts.md

No `## ` heading is added, renamed, or removed by this change (the amended
`## Consumer configuration schema` heading is unchanged; the two edited
subsections are `### ` level), so no `tests/heading-coverage.json` co-edit is
required.

### Ratification status — the file-early gate is now DISCHARGED

Filed 2026-07-25 under epic `livespec-dev-tooling-e9j` (maintainer ruling
2026-07-24; supervisor CALL #1: file-early / ratify-after). The gate this
proposal set for itself — slices L and D MERGED before accept — is satisfied,
and slice C landed alongside them:

- **L** — undeclared-role-key hard ERROR + fallback retirement: PR #633, released v0.54.12.
- **D** — declaration-presence enforcement: PR #644, released v0.54.13.
- **C** — `_IMPL_PREFIXES` derived from declared role keys: PR #648, released v0.54.14.

All eight fleet repos sit on v0.54.14 with every master CI green, so this text
describes shipped, fleet-verified behavior rather than intent.

Every FIND anchor below was re-grepped against `origin/master` at ratification
and resolves verbatim.

### Three corrections to this proposal's own earlier text, made at ratification

Recorded rather than silently fixed, because each was wrong in a way that would
have codified a false contract:

1. **The slice-D scope criterion was WRONG as filed.** The earlier text scoped
   the declaration-presence enforcement to "repos consuming livespec-dev-tooling
   via `pyproject.toml`". Measured against origin/master, that criterion
   *includes* `livespec-console-beads-fabro` — it has a `pyproject.toml` and
   consumes livespec-dev-tooling as a git dependency — and would therefore red
   the one repo the clause named as excluded. The shipped and correct criterion
   is **repos wiring at least one layout-dependent (`load_config`-consuming)
   check**. Console wires only `primary_checkout_commit_refuse_hook_installed`
   and `plugin_resolution`, neither of which calls `load_config`; its own
   justfile records them as "layout-independent (consumes no
   `[tool.livespec_dev_tooling]` role keys)".
2. **CALL #2 is no longer pending.** It was ruled: fleet-conformance placement
   only, with NO `/livespec:doctor` extension surface. EDIT 5 is finalized on
   that ruling.
3. **The enforcement-universality OVERCLAIM, caught in independent review and
   ruled by the maintainer.** An earlier draft of EDIT 2 stated the per-check
   hard ERROR as though it fired for every role-key consumer. It does not: the
   gate ships in the checks that GATE on a key, while other consumers read a
   role key only to classify severity or scope an exemption and derive their
   inspection universe elsewhere — those still inspect the full universe when
   the key is absent, so they are not silently disarmed and carry no gate.
   **The maintainer ruled: keep the DECLARATION mandate universal, fix only the
   ENFORCEMENT wording.** No scope reduction — the requirement that every
   consumer wiring a layout-dependent check declares every role key is
   unchanged and is what shipped slice D enforces. The contract is therefore
   universal on DECLARATION and precise on ENFORCEMENT, and EDIT 2 now says so
   by describing the gating property structurally rather than enumerating which
   checks currently gate (an enumeration would rot the moment the set changes).

### Summary

Amend `SPECIFICATION/contracts.md` §"Consumer configuration schema" to replace
the absent-key-no-op regime with the maintainer-ruled (2026-07-24)
declaration-required policy: every consumer of the layout-dependent checks MUST
carry the `[tool.livespec_dev_tooling]` block and MUST declare every structural
role key explicitly. An UNDECLARED role key consumed by a wired check is a hard
ERROR. A DECLARED-EMPTY key is the sanctioned, visible opt-out. The
whole-block-absent fallback to livespec-core's historical layout is RETIRED.
Declaration presence is additionally enforced mechanically fleet-wide.

### Motivation

Seven checks shared the early-return "role key absent — check no-ops, exit 0"
shape, and measurement showed the convention had silently disarmed most of the
structural gate suite across the fleet while CI reported green. The ratified
fleet ROP policy was being carried by gates structurally inert in the repos that
define it. A reported-count INFO line (PR #516) made the no-op visible but not
impossible to mistake: exit codes and CI status still read identically to a
pass. The maintainer ruled that absence becomes a hard error, and that
declaration presence becomes a first-class mechanical enforcement so the regime
cannot rot silently back in via the next fleet member.

### The normative role-key set

Transcribed from the merged `REQUIRED_ROLE_KEYS` in
`livespec_dev_tooling/config.py` (slice L's single exported source of truth),
not restated from memory — ten keys:

`source_trees`, `io_trees`, `commands_trees`, `supervisor_entry_files`,
`pure_trees`, `covered_trees`, `target_dirs`, `source_tree_prefixes`,
`dataclasses_tree`, `neutral_hook_body_path`.

Of the loader-recognized keys, `tests_tree_prefix` and `mirror_pairings` are
deliberately NOT members: `tests_tree_prefix` carries a meaningful non-empty
default (`"tests/"`), and neither is universally declared — requiring either
would red every fleet repo. `repo` is documented in the inventory but is NOT a
loader key at all (no parse branch, no `Config` field), so it cannot be a
member; this change marks the bullet accordingly.

### Proposed changes

**EDIT 1 — §"Consumer configuration schema" intro.** FIND the sentence
beginning "Missing keys MUST fall back to livespec-core's historical defaults"
through "keep its bit-identical pre-G.6 behavior." and REPLACE with:

> The block is REQUIRED for every consumer that wires any layout-dependent
> check, and every structural role key MUST be declared explicitly. There is no
> historical-defaults fallback: a consumer that wires such a check while omitting
> the block gets an empty configuration, and each wired check that GATES on a key
> then fails on that undeclared key per §"Role keys".

**EDIT 2 — closing paragraph of §"Role keys".** FIND the paragraph beginning
"Role keys absent from the schema mean" through "no-op MUST NOT degrade silently
to pass." and REPLACE with: (a) the universal DECLARATION requirement and the
statement that its enforcement has two distinct surfaces — declaration-presence
for all required keys, per-check gating for gating keys — and (b) the three-tier
semantics scoped to a GATING key, defined structurally as one a check cannot
proceed without because it supplies the tree walked or the file inspected.

The applied text is authoritative — read `contracts.md` §"Role keys" itself
rather than a quoted copy here. An earlier revision of this proposal quoted a
REPLACE block carrying the pre-ruling universal phrasing ("the check MUST exit
non-zero"), which contradicted correction 3 above; the quote is deliberately
not reproduced, because a second copy of normative text is exactly the drift
this epic exists to eliminate.

**EDIT 3 — the two scalar-key bullets.** In the `dataclasses_tree` and
`neutral_hook_body_path` bullets, replace the "string or null … When null, the
check no-ops" form with the declared-`""` form: the key MUST be declared, `""`
is the declared-none spelling that no-ops the consuming check, and absence is no
longer a sanctioned spelling of "not applicable".

**EDIT 4 — retire §"Default layout fallback".** Replace the section body (the
fallback TOML block and its bit-identical clause) with a retirement note naming
the retiring release and the reason. The heading is retained so no `## `/`### `
structure churns.

**EDIT 5 — declaration-presence enforcement (slice D).** Add contract text for
the `just check`-aggregate check plus the fleet-conformance row over
`.livespec-fleet-manifest.jsonc` members. Scope is **repos wiring at least one
layout-dependent (`load_config`-consuming) check** — see correction 1 above.
Repos outside that scope MUST be reported as excluded-with-reason, never
silently skipped. No `/livespec:doctor` extension surface (CALL #2, ruled).

**EDIT 6 — the drift sweep.** The five edits above name the sections the change
targets; they do NOT by themselves cover every clause the change falsifies. Both
independent reviewers found survivors the edit list never declared, so the full
sweep is enumerated here rather than left implicit:

- The `no_shadow_ledger_body_identical` five-slot **Exemption** clause, which
  sanctioned a consumer that "declares NO `neutral_hook_body_path`" as a
  legitimate no-op — it now names DECLARED-`""` as the exemption and an
  undeclared key as a hard error. (Found by the Opus reviewer; it contradicted
  the amended algorithm step six lines below it AND the shipped code.)
- That same section's algorithm step 1, converted to the declared-vs-undeclared
  split.
- Seven required-role-key bullets that read "Default empty array" or a literal
  default value — `io_trees`, `commands_trees`, `supervisor_entry_files`,
  `pure_trees`, `covered_trees`, `source_tree_prefixes`, `target_dirs`. "Default
  X" means "omit it and get X", which contradicts undeclared-is-an-ERROR; and
  the literal values on the last two came from the retired fallback, so they
  were also factually wrong about `Config()`. (Found by the Sonnet reviewer.)
- `mirror_pairings`' stated default, which described the retired fallback's two
  historical mirrors. It is NOT a required key, so this was a value-accuracy
  defect only.
- The `Config` sentence "defaulting to the historical fallback values" and the
  loader docstring "merge with built-in defaults".
- The `livespec-core` and `livespec-dev-tooling` consumer bullets, which
  asserted the MAY-omit allowance and empty/null defaults respectively.
- The "future siblings" paragraph, which asserted the fallback.

`tests_tree_prefix` retains its stated default deliberately: it is not a
required role key and its `"tests/"` default is accurate. `repo` is a different
case — the loader has no `repo` field and never parses the key, so it has no
default to state; its bullet is amended to say so.

**Known adjacent defect, partly fixed here.** `install_no_shadow_ledger` still
keys off absence rather than declared-ness, so its docstring's claim that the
check-side counterpart "no-ops identically" is false as of v0.54.12. The
divergence spans BOTH that module's docstrings AND spec text — §"CLI surface"
described the installer as no-opping "when that role key is null", which this
change amends, since a ratification must not leave the retired null vocabulary
describing a key it retypes. The CODE divergence is filed as
`livespec-dev-tooling-eihv` rather than folded into this ratification.

### Acceptance shape

After ratification, contracts.md describes exactly the shipped behavior: no
absent-key-no-op clause survives anywhere in the section, the fallback section
is retired, the declared-empty convention including the `""` scalar spelling is
documented, the three-tier semantics are normative, and the enforcement is
attributed mechanically with the correct scope criterion.
