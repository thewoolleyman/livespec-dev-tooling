---
topic: release-bump-classification-check
author: claude-opus-5
created_at: 2026-08-26T00:09:45Z
---

## Proposal: Define the `release_bump_classification` release-workflow check

### Target specification files

- SPECIFICATION/contracts.md

### Summary

v050 widened §"Shared check inventory" to admit RELEASE-workflow checks but named no member, so the category is currently empty. Define its first member: `release_bump_classification`, a check that compares the public-surface delta between the last release tag and `HEAD` against the semver classification the Conventional-Commit types on those same commits declare, and REFUSES when the declared classification is weaker than the surface delta requires. Add its `### release_bump_classification check` section to §"Shared check inventory" alongside the existing per-check sections, and name it as the Release-workflow kind's member in that category's bullet.

Purely additive: no canonical slug is added, no existing check changes, and adoption stays per-consumer opt-in per the category's own wording, so no consumer is reddened.

### Motivation

Nothing binds a repository's ratified §"Semver discipline" bump rules to the version its release automation actually computes. livespec-runtime released `0.21.5` for a change its own ratified versioning rule classifies as Major, because release-please derives the bump purely from the Conventional-Commit type and the commit was typed `fix:`. It was caught only by a human reading the release PR title with auto-merge already armed, and corrected out-of-band. The accidental `0.21.4` had the same root.

No per-commit aggregate check can observe this: the mismatch exists only between a RANGE of commits and a tag, and only at the moment a version number is about to become final. That is precisely the workflow step the release-workflow category was ratified to serve.

The check MUST NOT live in `livespec_dev_tooling/checks/`. The canonical set is filesystem-derived and every canonical slug obliges EVERY consumer to wire it into `just check` AND its CI matrix, so a module placed there would redden the whole fleet on its next pin bump. §"Shared check inventory" already records this hazard for both `workflow_checks/` and `charters/`.

### Proposed Changes

**1. Name the member in the category bullet.**

In §"Shared check inventory", in the "**Workflow checks (`livespec_dev_tooling/workflow_checks/`).**" bullet, the "Release-workflow checks" sub-bullet MUST name `release_bump_classification` as its member, in the same shape the "Revise-workflow checks" sub-bullet names `no_stale_revise_branches`. It MUST state that this check's enforcement point is whatever release-gating step the consumer wires it into, and that — unlike the revise-workflow member, whose `/livespec:revise` pre-step is mandatory and load-bearing — the release-workflow member has NO mandated caller, because adoption is per-consumer opt-in.

**2. Add a `### release_bump_classification check` section**, positioned among the existing per-check sections of §"Shared check inventory". It MUST state the following.

**Kind and placement.** A release-workflow check per §"Shared check inventory", NOT a canonical per-commit aggregate check: it lives under `livespec_dev_tooling/workflow_checks/`, is invoked by a consumer's release-gating step, and is never wired into the `just check` aggregate.

**Invocation.** `python -m livespec_dev_tooling.workflow_checks.release_bump_classification`. Zero positional arguments, per §"CLI shape".

**Inputs.** The `source_trees` role key from the consumer's `[tool.livespec_dev_tooling]` block (§"Consumer configuration schema") supplies the trees whose public surface is inventoried. This check MUST be added to that key's behavioral-consumer list in the same change, per the rule in §"Role keys" that a check beginning to read a role key MUST be reflected in that key's list.

**What "public surface" means for this check.** The inventory is the set of `<module-path>:<name>` pairs formed from every module-level `__all__` entry in every `.py` file under the declared `source_trees`. It MUST be derived by parsing each file with `ast` and reading the `__all__` assignment's literal string elements — never by importing the module, which would violate the determinism the check depends on and could execute consumer code. A file with no module-level `__all__`, or one whose `__all__` is not a literal list/tuple of strings, contributes nothing to the inventory and is not itself an error.

**Algorithm.**

1. Resolve the last release tag: the highest tag matching `v[0-9]*` by version sort. When the repository carries no such tag, exit `0` with a structured `info` log (graceful skip — a repository before its first release has no baseline to compare against).
2. Build BOTH inventories from committed trees, never from the working tree: the tag side via `git show <tag>:<path>`, and the `HEAD` side via `git show HEAD:<path>`. Reading the working tree would be wrong at the named `pre-push` enforcement point, which commonly runs against a dirty tree: an uncommitted `__all__` edit would inflate the `HEAD` inventory while step 4's declared classification reads only the committed `<tag>..HEAD` range, producing a spurious refusal.
3. Compute the REQUIRED classification from the delta. Its `major` and `minor` legs follow this specification's §"Semver discipline" bump rules; the equal-inventories leg is the check's own floor rather than a restatement of them, since those rules classify a pure implementation change as PATCH:
    - any inventory entry present at the tag and absent at `HEAD` (a removal or a rename) → `major`;
    - otherwise, any entry absent at the tag and present at `HEAD` (an addition) → `minor`;
    - otherwise (the inventories are equal) → `none`.

    The equal-inventories case MUST yield `none` and not `patch`. A repository sitting at its release tag with only `chore:` / `docs:` commits since declares `none`, and `none` is strictly weaker than `patch`, so a `patch` floor here would REFUSE every repository whose public surface did not change — the overwhelmingly common case, and the exact opposite of what the check is for. This was measured against two real repositories before ratification, both of which the `patch` floor refused.
4. Compute the DECLARED classification from the Conventional-Commit subjects and bodies of the commits in `<tag>..HEAD`, taking the strongest across the range: a `!` before the `:` in the subject's type/scope prefix OR a `BREAKING CHANGE:` / `BREAKING-CHANGE:` footer → `major`; a `feat` type → `minor`; a `fix` or `perf` type → `patch`; any other type, and any subject that does not parse as a Conventional Commit, contributes nothing. When no commit in the range contributes anything, the declared classification is `none`.
5. REFUSE (exit `4`) when the declared classification is strictly weaker than the required one, ordering `none` < `patch` < `minor` < `major`. Exit `0` otherwise.

**The comparison is between CLASSIFICATIONS, not between version numbers, and that is load-bearing.** Under a pre-1.0.0 version, release-please maps a `major` classification onto a minor version bump and a `minor` classification onto a patch version bump (its `bump-minor-pre-major` / `bump-patch-for-minor-pre-major` behavior). A check that compared computed VERSION bumps would therefore refuse every correctly-typed `feat:` on a `0.y.z` repository, because such a commit legitimately produces a patch version bump. Comparing classifications is correct on both sides of `1.0.0` and needs no pre-major special case.

**The honest limit, which MUST be stated in the section and in the module docstring.** The required classification derived from the `__all__` inventory is a LOWER BOUND on what §"Semver discipline" requires, never the whole of it. It detects a surface element appearing or disappearing; it CANNOT detect a behavior-only break — a tightened parse contract, a narrowed glob, a changed return shape behind an unchanged name — which §"Semver discipline" independently classifies as MAJOR. A green result from this check therefore means "no surface element changed incompatibly", NOT "the declared bump is correct". Stating this is a requirement of the section rather than a courtesy: the incident that motivated the check was itself a case of a mechanically-verified signal being mistaken for the behavior it was assumed to guarantee, and a section that let a reader draw that inference again would reproduce the failure it exists to prevent.

**Exit codes.** `0` on pass or on the no-tag graceful skip; `2` on usage error; `4` on a refusal. No new code is added to §"Exit-code table".

**Each `fail` finding carries:**

- `check_id`: `release_bump_classification`
- `status`: `fail`
- `message`: `public surface requires a <required> bump but the commits since <tag> declare <declared>`
- `required_classification`: one of `major`, `minor` — a refusal is possible only when the surface delta demands more than `none`, so `none` never appears in a `fail` finding
- `declared_classification`: one of `minor`, `patch`, `none` — `major` never appears in a `fail` finding, because a `major` declaration is never strictly weaker than any required classification
- `baseline_tag`: the resolved tag name
- `added`: the sorted `<module-path>:<name>` entries present at `HEAD` and absent at the tag
- `removed`: the sorted `<module-path>:<name>` entries present at the tag and absent at `HEAD`
- `hint`: direction to retype the offending commit, or to record the intended release explicitly, so the automation derives the classification the surface delta requires
- `path`: empty (the finding is repository-topology, not file-system)
- `line`: 0

**Output discipline.** Structured `structlog` JSON to stderr, per the `workflow_checks/` package rule; `print` and `sys.*.write` are banned there.

**3. Extend the §"Semver discipline" surface enumeration to cover workflow-check invocations.**

This edit is REQUIRED by this change and is not optional polish. §"CLI surface" states that the §"Semver discipline" enumeration "is therefore the single test of whether an import is sanctioned — a module is importable by consumers because it is listed there, never because it happens to be reachable", and that "every module the enumeration omits remains an internal helper to which the prohibition applies unchanged". The enumeration currently names the `python -m livespec_dev_tooling.checks.<slug>` set but no `workflow_checks` form. Without this edit the resulting document would simultaneously MANDATE a consumer-facing invocation (`python -m livespec_dev_tooling.workflow_checks.release_bump_classification`, wired by the consumer into its own release-gating step, with no mandated caller) and leave that same invocation unsanctioned by its own single test — and unprotected, since `constraints.md` §"Semver discipline" shields only enumerated surface elements, so the form consumers are told to gate releases on could be renamed or removed in a PATCH.

The specification's own precedent governs: the charter detector API was added to the enumeration in the same change that admitted it, with the explicit note that this "is why §'CLI surface' scopes its internal-helper prohibition to modules this enumeration omits". This change names the first consumer-wired workflow-check invocation form, so it is the change that MUST carry the extension.

ADD to the §"Semver discipline" enumeration a bullet naming the `python -m livespec_dev_tooling.workflow_checks.<slug>` invocation set on the same terms as the `checks` set (argv contract and exit-code semantics per §"CLI surface" and §"Exit-code table"). It MUST state that enumeration here is what sanctions the consumer invocation, and it MUST state explicitly that enumerating these forms does NOT make them canonical, does NOT make them members of the `just check` aggregate, and does NOT subject them to the wiring-completeness invariant — that exclusion remains decided by the filesystem derivation in §"Shared check inventory". Without that disclaimer the extension could be misread as conscripting the fleet, which is the exact hazard §"Shared check inventory" exists to prevent.

AMEND the **MINOR** bump rule from "adding a new check" to "adding a new check (canonical or workflow)", so the enumeration's bump semantics cover the newly-enumerated forms.

**4. No `##` heading is added, renamed, or removed.** One `###` section is added under the existing §"Shared check inventory" heading, one existing sub-bullet gains its member name, one role key's consumer list gains one entry, and the §"Semver discipline" enumeration gains one bullet with its MINOR rule amended.
