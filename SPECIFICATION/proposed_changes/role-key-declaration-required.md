---
topic: role-key-declaration-required
author: claude-fable-5-rop-sweep-fleet-policy
created_at: 2026-07-25T00:15:00Z
---

## Proposal: Role-key declaration required

### Target specification files

- SPECIFICATION/contracts.md

No `## ` heading is added, renamed, or removed by this change, so no
`tests/heading-coverage.json` co-edit is required. The change edits prose under
several sections and adds one new heading, `### Declaration-presence
enforcement`, but that heading is `### ` level and the `## ` set is byte-identical
to `origin/master`. The co-edit rule keys off the `## ` set alone:
`livespec_dev_tooling/checks/heading_coverage.py` extracts a heading only when it
`startswith("## ")` AND not `startswith("### ")`, so `### ` headings are outside
the coverage map by construction. Verified both ways — by diffing the `## ` sets
and by reading the check — rather than assumed from the edit's shape.

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

### The exit-code question raised in review — ruled, and deliberately NOT changed here

This is recorded because after ratification the spec and the shipped code
DISAGREE on one number, on purpose. Anyone who later notices the disagreement
and "fixes" the spec to match the code will reintroduce the defect this ruling
exists to name.

`SPECIFICATION/contracts.md` §"`no_shadow_ledger_body_identical` check" documents
exit `4` for the `missing` and `body_mismatch` failure modes. The shipped module
returns `1` (`checks/no_shadow_ledger_body_identical.py`, `_FAIL_EXIT`). A draft
of this change had rewritten the spec to `4` → `1` to match the code. That
rewrite has been REVERTED: every `4` on those three lines is unchanged from
master, and the two algorithm-step lines are byte-identical to it. The invocation
line alone was later extended, in a separate repair, with a third outcome — the
§"Role keys" undeclared-key exit, which deliberately assigns no number. That is
an addition beside the `4`, not an edit of it, and the `4` this ruling is about
stands exactly as master has it.

**The maintainer ruled: the spec ratifies `4`; the shipped `1` is a tracked code
defect.** The reasoning, verified from git history rather than inferred:

- The module shipped `_FAIL_EXIT = 4` from creation and was changed to `1` by
  slice L (`b8ea4e6`, "fix: enforce declared role keys", PR #633), whose commit
  message declares no exit-code change. It was an undeclared side effect of this
  epic's own enforcement slice, not a considered contract decision.
- Slice L introduced the shared `checks/_role_key_gate.py`, whose
  `role_key_gate_exit_code()` returns `1` for ITS condition — an undeclared role
  key. `_FAIL_EXIT` governs a DIFFERENT condition. The two appear to have been
  aligned despite being distinct failure classes.
- §"Exit-code table" defines `1` as "internal bug (uncaught exception)" and `4`
  as "check failed (structured findings on stderr)". A body mismatch is a
  structured finding, so `4` is the semantically correct code.
- §"Semver discipline" pins each slug's exit-code semantics as part of the
  library's semver-stable surface; the flip shipped in the `0.x` PATCH release
  v0.54.12 with no acknowledgment anywhere.

Documenting `1` here would have ratified a defect and destroyed the spec's
ability to name it. Leaving the contract at `4` keeps the spec correct and makes
the CODE the thing that is wrong — tracked as `livespec-dev-tooling-1aba`, which
also covers the wider split (three check modules return `1` for genuine
structured failures while four return `4`). Slice S stays spec-only: no code
change, no Red-Green-Replay, no release or fan-out.

Note for whoever fixes `1aba`: that module's own docstring already says `4`, so
on this point the docstring is RIGHT and the code is wrong. Its separate,
genuinely stale claim — that an undeclared key makes the check no-op — is
tracked as `livespec-dev-tooling-eihv`.

### Defects the review rounds introduced, and how they were caught

Recorded because the pattern matters more than any tally of it: repairs to
earlier defects in this change repeatedly introduced NEW defects, each caught
only by re-reviewing the amended bytes rather than the amended spots. Three are
described below as the clearest instances; they are illustrative of the pattern,
not an exhaustive count of it.

1. A repair to the config-block misattribution introduced the claim that livespec
   PR #1663 added "the first structural role keys". False — `dataclasses_tree`
   was declared two days earlier in PR #1497. Note the shape of the wrong
   evidence: `git log -S` on those three key names has the SAME EARLIEST hit for
   all of them, so the natural check — "did one of these keys land before the
   others?" — answers "no" and confirms the defective wording. Only the diff
   shows that the shared commit DECLARES `dataclasses_tree` while mentioning
   `source_trees` / `io_trees` inside a comment reading "deliberately NOT
   declared here". A string search and a diff disagreed, and the string search
   was the wrong instrument.
2. A rewrite of the `livespec-orchestrator-git-jsonl` bullet asserted that the
   keys not named as real-valued "are declared explicitly empty". False —
   `supervisor_entry_files` carries real values there.
3. Extending the check's invocation line with the undeclared-key exit silently
   falsified this record's own earlier sentence that the three exit-code lines
   were "unchanged from master". The contract text was right; the record sentence
   it expired was not, and is corrected above.

The operative lesson for anyone amending this spec: a fix is a prime suspect, not
a settled matter, and a re-review scoped to "just the changed spots" would have
missed defect 3 entirely — it lived in a different section from the edit that
broke it.

### The third consumer bullet — corrected here, with the rest left to its own item

Independent review found the `livespec-impl-git-jsonl` consumer bullet false in
two demonstrable ways, and this change corrects exactly those two:

1. **The repo name was pre-rename.** `livespec-impl-git-jsonl` names no fleet
   member — it occurs zero times in livespec core's
   `.livespec-fleet-manifest.jsonc`, which lists the repo as
   `livespec-orchestrator-git-jsonl`.
2. **The deferral had already expired.** The bullet read "MUST publish its own
   block once Phase G.7 wiring lands." That repo already publishes a complete
   block, backfilled by THIS epic's own Wave-1. So the change would otherwise
   have ratified a future-tense obligation that its own earlier slice had
   already discharged — the "claims that expire at ratification" class.

**Deliberately NOT corrected here, and why the boundary sits where it does.** The
enclosing "Three first-party consumers as of v0.2.x" enumeration — its count, its
`v0.2.x` qualifier, and the genuine question of what qualifies a repo as a
first-party CONSUMER (notably how to treat `livespec-console-beads-fabro`, which
depends on this library but wires no `load_config`-consuming check) — stays with
`livespec-dev-tooling-1a6w`, which owns it. That is a real determination with its
own failure modes, not a typo, and resolving it inside this ratification would
widen a change that is otherwise complete.

This does NOT contradict the earlier review note on `1a6w` recording that the
bullet's obligation was "not a defect". That note answered whether the
obligation's LOGIC is coherent under the new regime — it is, because the scope
rule makes wiring the trigger. What is corrected here is narrower and factual:
that trigger has already fired. Both hold at once.

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

After ratification, contracts.md describes exactly the shipped DECLARATION
behavior: no absent-key-no-op clause survives anywhere in the section, the
fallback section is retired, the declared-empty convention including the `""`
scalar spelling is documented, the three-tier semantics are normative, and the
enforcement is attributed mechanically with the correct scope criterion.

**Two known spec-ahead-of-code divergences, both deliberate and both tracked.**
In each the contract text is correct and the CODE is what should change; neither
is an error in this ratification.

1. **The exit code.** `no_shadow_ledger_body_identical`'s `missing` /
   `body_mismatch` failure modes are documented as `4`, while the shipped module
   returns `1`. Intended and ruled — see §"The exit-code question raised in
   review" above. Tracked as `livespec-dev-tooling-1aba`.
2. **The zero-`.py` error state.** §"Role keys" makes a DECLARED non-empty key
   whose paths contain no `.py` file a hard ERROR. The shared gate implements
   that for the checks routed through its paths-aware variant, but
   `newtype_domain_primitives` calls only the plain gate: a `dataclasses_tree`
   declared non-empty and pointing at a real directory holding no `.py` file
   inspects nothing and exits `0`, where the text mandates an error. Surfaced by
   independent review of this change and verified by reading the module. Tracked
   as `livespec-dev-tooling-njyx`. No consumer is in the triggering state today
   (every backfilled repo declares `dataclasses_tree` as the declared-none `""`,
   which correctly takes the sanctioned no-op path), so nothing is silently
   unenforced right now; it goes live the moment a consumer declares a real tree
   that is empty or wrongly rooted.

So "describes the shipped behavior" is asserted of the declaration regime this
change is about, and not of those two points. A future reader reconciling spec
against code should close both gaps by changing the CODE, not by weakening this
text — the whole purpose of this epic is to stop enforcement claims outrunning
enforcement, and silently restating the shortfall as the contract would be that
same failure in a new place.
