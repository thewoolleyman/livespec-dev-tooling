---
topic: spec-amendments-from-doctor-followup-findings
author: claude-opus-4-7
created_at: 2026-05-26T00:00:00Z
---

## Proposal: reconcile-constraints-tools-list

### Target specification files

- SPECIFICATION/constraints.md

### Summary

`constraints.md` §"Dependencies" lists permitted subprocess tools in two adjacent paragraphs with mismatched contents. Line 11 names "(ruff, pyright, pytest, git)" describing the current shell-out set; line 17 (within §"No network I/O") names "(git, ruff, pyright, pytest, mise)" describing the permitted-subprocess envelope. The mismatch — `mise` is only on line 17 — leaves a reader unable to tell whether the discrepancy is intentional partitioning (current vs envelope) or oversight.

### Motivation

Detected during a `/livespec:doctor` LLM-objective phase run on 2026-05-26 (internal-contradiction sweep). The two lists co-occur within seven lines of the same section, but their differing contents are not explained inline.

### Proposed Changes

Rewrite line 11 to acknowledge that the broader envelope (per §"No network I/O") includes `mise`, and clarify that the line 11 list is the current shell-out subset:

Current line 11 (within §"Dependencies"):

> Every check shells out to project-local tools (ruff, pyright, pytest, git) via `subprocess.run` with fixed argv lists; the tools themselves are pinned by each consuming repo's own `.mise.toml` and `[dependency-groups].dev`, not by this library.

Revised:

> Every check shells out to project-local tools via `subprocess.run` with fixed argv lists. The current tool set is `ruff`, `pyright`, `pytest`, and `git`; the broader permitted envelope per §"No network I/O" additionally includes `mise`. Tool versions are pinned by each consuming repo's own `.mise.toml` and `[dependency-groups].dev`, not by this library.

NO change required to line 17 — that statement is the permitted envelope and remains the authority.

This propose-change documents the SPEC change. Implementation work: none. The reconciliation is pure prose disambiguation; no code references either list.


## Proposal: define-or-eliminate-v1-temporal-token

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md

### Summary

The token "v1" appears 5+ times across the spec as a temporal qualifier — "in v1's scope", "the v1 fallback", "OUT OF SCOPE for v1", "consumed exclusively via `uv` git source in v1" — but is never explicitly defined. A reader cannot determine whether "v1" means the 1.0.0 MAJOR release line, the entire pre-1.0 0.x evolution, or the current release tag at time of reading.

### Motivation

Detected during the same `/livespec:doctor` LLM-objective phase (undefined-term sweep) and corroborated by the NLSpec-conformance template-extension phase (conceptual-fidelity dimension) on 2026-05-26.

### Proposed Changes

Define "v1" once in `spec.md` §"Project intent" and let downstream citations resolve to that definition. Insert a new paragraph after the existing §"Project intent" paragraph in `spec.md`:

> Throughout this spec, the token "v1" refers to the library's first MAJOR release line (semver `1.x.x`). Pre-1.0 `0.x` releases are bootstrap territory and do not satisfy any rule scoped to "v1"; "v1" rules become binding at the `1.0.0` cutover. Rules without a "v1" qualifier are unconditional and bind every release.

The reviser MAY alternatively (Option 2) rewrite each citation inline — replacing "v1" at `spec.md:39`, `spec.md:43`, `contracts.md:172`, `contracts.md:173` with "the first MAJOR release line" or "the `1.x.x` line". Option 1 (the single definition site) is preferred for diff economy and to anchor future "v1"-qualified prose to a single reference point.

This propose-change documents the SPEC change. Implementation work: none.


## Proposal: normalize-check-identifier-naming

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

`non-functional-requirements.md` uses three distinct identifier styles for the same check artifacts within a few paragraphs:

- **Bare slug** (matches `contracts.md` §"Shared check inventory" canonical form): `assert_never_exhaustiveness`, `no_direct_tool_invocation`.
- **`check-` prefix** (just-target convention): `check-red-green-replay` (line 20), `check-commit-pairs-source-and-test` (line 21), `check-coverage` (line 21), `check-pbt-coverage-pure-modules` (line 25), `check-pre-commit` (line 78), `check-pre-push` (line 78).
- **`<slug>.py` suffix** (Python filename convention): `assert_never_exhaustiveness.py` (line 66), `no_direct_tool_invocation.py` (line 74).

`contracts.md` §"Shared check inventory" uses bare-slug exclusively as the canonical form. NFR should match unless the decoration carries semantic load.

### Motivation

Detected during the same `/livespec:doctor` LLM-objective phase on 2026-05-26 (internal-contradiction sweep). The three styles co-occur within a few lines of each other and create ambiguity about whether the spec means the Python module, the just-target wrapper, or the abstract check identity.

### Proposed Changes

Adopt **bare slug** as canonical wherever the spec refers to the check's identity (not its filename or invocation form). Per-line edits in NFR:

- Line 20: "the `check-red-green-replay` gate at commit-msg time" → "the `red_green_replay` check at commit-msg time"
- Line 21: "`check-commit-pairs-source-and-test`" → "`commit_pairs_source_and_test`"
- Line 21: "`check-coverage`'s 100% per-file gate" → reconciled per Proposal `reconcile-shared-check-inventory-with-impl` (the canonical name depends on whether `coverage` is `per_file_coverage`, `check_coverage_incremental`, or both)
- Line 25: "the `check-pbt-coverage-pure-modules` gate" → "the `pbt_coverage_pure_modules` check"
- Line 66: "`assert_never_exhaustiveness.py`" → "`assert_never_exhaustiveness`"
- Line 74: "`no_direct_tool_invocation.py`" → "`no_direct_tool_invocation`"

The `.py` suffix and `check-` prefix decorations remain visible at the implementation surface (Python filenames; just-target wrappers); the spec talks about check identity, which is the bare slug per `contracts.md` §"Shared check inventory".

Lines 78's `check-pre-commit` and `check-pre-push` are NOT check identities — they are aggregate just-target names that compose multiple checks. Those references stay as-is.

This propose-change documents the SPEC change. Implementation work: none.


## Proposal: reconcile-shared-check-inventory-with-impl

### Target specification files

- SPECIFICATION/contracts.md

### Summary

`contracts.md` §"Shared check inventory" enumerates 32 shared check slugs; `livespec_dev_tooling/checks/` currently contains 34 check modules. The two inventories diverge in both directions:

**Spec names 6 slugs absent as standalone modules from impl**: `complexity`, `coverage`, `format`, `imports_architecture`, `lint`, `tools`. Some may be aliases for renamed impl modules (e.g., `tools` → `check_tools.py`); others may never have materialized as wrapper modules (`lint`, `format`, `complexity` may be handled via direct `ruff` invocation through `just lint` / `just format` rather than dedicated check modules).

**Impl has 8 modules not enumerated in the spec inventory**: `check_coverage_incremental`, `check_mutation`, `check_tools`, `comment_line_anchors`, `file_lloc`, `per_file_coverage`, `rop_pipeline_shape`, `tests_mirror_pairing`.

The spec section self-declares as "the canonical authority"; the divergence means the canonical authority does not reflect the reality of `livespec_dev_tooling/checks/`.

### Motivation

Detected during the `/livespec:doctor` LLM-subjective spec-impl-drift phase on 2026-05-26. The drift is high-severity because the spec assigns itself canonical-authority role over the shared-vs-private partition.

### Proposed Changes

Reconcile the inventory in three sub-steps inside the first bullet of `contracts.md` §"Shared check inventory":

1. **Drop slugs that never materialized as standalone modules.** Specifically remove from the inventory: `complexity`, `format`, `imports_architecture`, `lint`. If `lint` / `format` / `complexity` are intended to remain as conceptual entries backed by `ruff` invocation (not dedicated check modules), document that explicitly in a clarifying sub-bullet rather than listing them alongside actual `python -m` invocable check modules.

2. **Rename or document the 2 likely-aliases.** Decide each:
   - `tools` → likely `check_tools`. State the canonical name and drop the legacy.
   - `coverage` — may be `per_file_coverage`, `check_coverage_incremental`, or both. State the canonical name(s) and drop the legacy.

3. **Add the 8 new check slugs to the inventory.** For each, place it in the correct functional category (AST-shape, I/O-discipline, style, test-infrastructure, CI-alignment, red-green-replay) inside the existing category list. The additions: `check_coverage_incremental`, `check_mutation`, `check_tools`, `comment_line_anchors`, `file_lloc`, `per_file_coverage`, `rop_pipeline_shape`, `tests_mirror_pairing`.

The revise pass MUST verify each impl module satisfies the project-agnosticism partition criterion (§"Shared check inventory" second bullet: "Shared (migrate to `livespec_dev_tooling/checks/`)… whose argv contract is project-agnostic — i.e., the check can run unmodified in any livespec-governed repo") before adding it to the shared inventory. Any module that asserts a property of this library's own layout, rather than a generic livespec-governed-project property, belongs in a livespec-private inventory or stays out of the shared list.

This propose-change documents the SPEC change. Implementation work: none directly — the impl is already what the spec needs to catch up to.


## Proposal: add-sys-path-insert-to-coverage-exclude-also-exact-list

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

`non-functional-requirements.md` §"Code coverage thresholds" mandates an exact 6-item `exclude_also` list and asserts "No other exclusions are permitted without a propose-change cycle." `pyproject.toml:227` declares an additional 7th exclusion, `"sys.path.insert"`, with the inline rationale that it matches the livespec-core exclusion pattern for vendored-path guards that are structurally dead when tests run via the project's pythonpath config. The 7th exclusion is a direct violation of the spec's exact-list rule.

### Motivation

Detected during the `/livespec:doctor` LLM-subjective spec-impl-drift phase on 2026-05-26. The exclusion has been in `pyproject.toml` for some time without a corresponding spec amendment. The drift is high-severity because the spec rule is hard ("MUST", "No other exclusions are permitted") and the violation is in the live `master` build.

### Proposed Changes

Extend the NFR §"Code coverage thresholds" exact list to include `sys.path.insert`. Per-line edit:

Current (line 54):

> `fail_under = 100` line + branch. `exclude_also` MUST be minimal and limited to structurally-unreachable patterns matching livespec's exact list: `if TYPE_CHECKING:`, `raise NotImplementedError`, `raise ImportError`, `@overload`, `if __name__ == .__main__.:`, `case _:`. No other exclusions are permitted without a propose-change cycle.

Revised:

> `fail_under = 100` line + branch. `exclude_also` MUST be minimal and limited to structurally-unreachable patterns matching livespec's exact list: `if TYPE_CHECKING:`, `raise NotImplementedError`, `raise ImportError`, `@overload`, `if __name__ == .__main__.:`, `sys.path.insert`, `case _:`. No other exclusions are permitted without a propose-change cycle. The `sys.path.insert` entry covers vendored-path guards of the form `if str(X) not in sys.path: sys.path.insert(...)` that are structurally dead when tests run via the project's `pythonpath` config in `pyproject.toml`.

The rationale paragraph is included so future reviewers know why `sys.path.insert` was added to the exact list rather than treated as a one-off exemption.

**Cross-spec alignment caveat.** This proposal mirrors a likely-identical drift at livespec-core's NFR §"Code coverage thresholds" — the spec rule originates there per the dogfood-mirror discipline. The reviser MUST file a parallel propose-change against livespec-core's spec if its exact list does not already carry `sys.path.insert`; otherwise the two specs diverge in opposite directions.

This propose-change documents the SPEC change. Implementation work: none — the impl is already what the spec needs to allow.


## Proposal: relocate-ci-matrix-shape-rule-from-nfr-to-constraints

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/constraints.md

### Summary

`non-functional-requirements.md` §"Hooks and CI" line 78 declares consumer-observable CI matrix shape: "CI workflows MUST mirror the per-target matrix shape with zero-`.py` subsetting on `pull_request` events and unconditional full-aggregate on `master` and `merge_group` events." NFR §"Boundary" line 11 states "Constraints whose violation a consumer of this library could observe (runtime version, no-network-I/O, semver discipline, CLI shape) MUST stay in `constraints.md`." CI matrix shape is consumer-observable — consumers see GitHub status check shape on their CI runs invoking the reusable workflows — so per the boundary rule, the rule belongs in `constraints.md`, not NFR.

### Motivation

Detected during the `/livespec:doctor` LLM-subjective template-compliance phase on 2026-05-26. The misplacement is a category error: the rule is contractual to consumers, not contributor-only build discipline like the hook rules around it.

### Proposed Changes

Two coordinated edits:

1. **NFR §"Hooks and CI"** — strip the CI matrix shape sentence, leaving only hooks content. Current paragraph:

   > The lefthook configuration MUST mirror livespec's three-stage pre-commit ordering (`00-lint-autofix-staged`, `01-commit-pairs-source-and-test`, `02-check-pre-commit`), commit-msg gates (`00-no-commit-on-master`, `01-red-green-replay`), and pre-push gate (`check-pre-push` with zero-`.py` subsetting). CI workflows MUST mirror the per-target matrix shape with zero-`.py` subsetting on PR events and unconditional full-aggregate on `master` and `merge_group` events.

   Revised:

   > The lefthook configuration MUST mirror livespec's three-stage pre-commit ordering (`00-lint-autofix-staged`, `01-commit-pairs-source-and-test`, `02-check-pre-commit`), commit-msg gates (`00-no-commit-on-master`, `01-red-green-replay`), and pre-push gate (`check-pre-push` with zero-`.py` subsetting).

   (Final sentence removed; the pre-push zero-`.py` discipline stays here because pre-push is contributor-only and is not consumer-observable.)

2. **`constraints.md`** — add a new H2 §"CI matrix shape" after §"Self-application":

   > ## CI matrix shape
   >
   > CI workflows shipped by this library MUST mirror the per-target matrix shape with zero-`.py` subsetting on `pull_request` events and unconditional full-aggregate on `master` and `merge_group` events. The constraint is consumer-observable: any reusable workflow this library ships expects matrix consumers to see the same per-event shape on their own CI status checks. Deviating from the shape on a release would break consumers' branch-protection wiring that names individual matrix entries as required checks.

The reviser MAY alternatively fold the rule into `contracts.md` §"Reusable workflows wire contract" (under the existing `reusable-check-matrix.yml` sub-section) if a wire-contract framing reads more naturally than an architectural-constraint framing. The current draft prefers `constraints.md` because the rule is a meta-invariant over the reusable-workflow surface, not a wire-level input/output declaration.

**Heading-coverage pairing.** Adding a new H2 (§"CI matrix shape") to `constraints.md` requires a corresponding `tests/heading-coverage.json` entry in the same commit per the project's heading-coverage gate. The revise pass MUST land the test entry atomically with the spec change.

This propose-change documents the SPEC change. Implementation work: none directly — the existing CI workflow already follows the shape; the rule just needs to move to its correct semantic home.
