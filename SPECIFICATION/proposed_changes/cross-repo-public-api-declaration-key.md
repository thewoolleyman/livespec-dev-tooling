---
topic: cross-repo-public-api-declaration-key
author: claude-opus-5
created_at: 2026-07-29T11:05:11Z
---

## Proposal: A `cross_repo_public_api` role key — the consumer's declaration of the surface its SIBLINGS consume

### Target specification files

- SPECIFICATION/contracts.md

### Summary

`livespec` v178 (`non-functional-requirements.md` §"ROP composition", ratified as PR #1826 →
`d230c9ff`) redefines what "public API" means for the Result-return rule: a top-level function is
public **only when CONSUMED ACROSS A BOUNDARY**, and consumption is measured **FLEET-WIDE** in four
enumerated forms — product import, cross-repo TEST import, process entry point, and a live
non-Python distributed surface. That criterion's repo-local enforcement half is
`check-public-api-result-typed`, which runs inside ONE checkout and **structurally cannot see a
sibling's import**.

§"Role keys" MUST therefore gain a `cross_repo_public_api` key: the consumer's own declaration of
the names other governed repos consume, so the repo-local check can apply a fleet-wide criterion
from a repo-local vantage. Each entry names a file, a function, and a written reason. The key is
**TIGHTENING-ONLY** — it can only ADD names to the rule's scope, never remove one — and each entry
MUST resolve to an existing top-level function or the check MUST hard-fail.

### Motivation

**The declaration exists because the vantage is split, not because the rule is negotiable.** v178
states the enforcement split itself: the repo-local half is hermetic and runs in a pre-commit gate;
a central-vantage conformance row re-measures the fleet's actual consumption graph and fails when a
member's declared surface omits a name another member consumes. Neither half suffices alone. This
key is the INTERFACE between them — the repo declares, and the central row checks the declaration
against reality.

**Without it the repo-local half is measurably wrong in the dangerous direction, and that has
already been paid for.** `livespec_dev_tooling.fleet.contract.parse_manifest` has ZERO importers in
this repo and one in `livespec-orchestrator-beads-fabro` (`.claude-plugin/hooks/codex_yolo_gate.py`).
A purely repo-local oracle classifies it NOT PUBLIC — the exact function whose conversion turned a
sibling's master RED (`livespec-dev-tooling-dx8l`). A criterion that is right about the names nobody
imports and wrong about the ones that cross a repo boundary is worse than none, because it is
confidently wrong precisely where the blast radius is largest.

**TIGHTENING-ONLY is the property that keeps this from becoming `pure_trees = []` under a new
name**, and it MUST be stated normatively rather than left to the implementation. A key whose
absence RELAXES a check is the shape this repo spent an epic removing from the role-key schema. The
repo-local forms of consumption — an import across a module boundary inside this repo, and a
process entry point — are computed from the code on every run and are NOT affected by this key. An
absent or empty declaration therefore cannot silence a single name the local oracle already sees;
it can only fail to ADD one that only a sibling sees. That residual is real, is exactly what the
central-vantage row exists to catch, and is recorded here rather than presented as closed.

**It is deliberately NOT a required role key, and the reason is a measured hazard rather than
convenience.** Adding a key to `REQUIRED_ROLE_KEYS` makes an undeclared key a hard ERROR in every
governed repo on its next pin bump — the auto-merge fan-out delivers "consumed" within minutes with
nobody deciding — so a required key would redden eight sibling masters to express a declaration
that seven of them have no content for. Declaration-presence for this key belongs to the
central-vantage row, which can see whether a repo owes an entry; a repo-local hard error cannot,
and would only be able to demand ceremony.

**A DECLARATION NOBODY VERIFIES IS THIS REPO'S SIGNATURE DEFECT**, so the entry shape is bounded the
same way `livespec` v179 bounds `total_absence_returns`: a written reason per entry (a bare path is
not a declaration), and a HARD-FAILING staleness detector so a declaration cannot outlive its
subject. What this key CANNOT self-verify — whether the declared set is COMPLETE — is precisely
what the central row computes, and the two bounds together are what make the local half honest
about its own limits.

### Proposed Changes

§"Role keys" MUST gain a `cross_repo_public_api` bullet in the role-key inventory. It MUST state
all of the following:

- **Shape.** An array of objects, each `{"file": "<repo-root-relative .py path>", "function":
  "<top-level function name>", "reason": "<why this name crosses a repo boundary>"}`. `file` and
  `function` together identify one top-level function; `reason` names the consuming repo and the
  v178 consumption form (product import, cross-repo test import, process entry point, or declared
  distributed surface).
- **Consumed by `public_api_result_typed`**, which treats each declared function as PUBLIC API for
  the Result-return rule regardless of `__all__` membership, per v178's `__all__`-independent
  tightening clause.
- **NOT a required role key.** Absence is legal and parses to an empty declaration. It MUST NOT be
  added to `REQUIRED_ROLE_KEYS`, and an undeclared key MUST NOT be a local hard error.
- **TIGHTENING-ONLY, stated as a requirement.** The key MUST only ADD functions to the rule's
  scope. It MUST NOT be readable as an exemption, an allowlist, or a scan universe: a name the
  repo-local consumption oracle finds public remains public whether or not it is declared here, and
  an empty declaration MUST NOT be capable of removing any name from the check's scope. A later
  amendment that gives this key a relaxing reading would reintroduce the ambiguous-empty defect
  §"Declared-absent spellings for the union role keys" exists to remove, one level up in the
  schema.
- **A HARD-FAILING staleness detector.** `public_api_result_typed` MUST verify that every declared
  entry resolves to an existing top-level function of that name in that file, and MUST exit
  non-zero naming the entry when it does not. A declaration MUST NOT be allowed to outlive its
  subject.
- **A written reason per entry is REQUIRED, not advisory.** An entry whose `reason` is absent or
  empty MUST be rejected by the loader as a schema violation, for the same reason `unarmed_until`
  takes a ledger id rather than free silence: an unexplained declaration is indistinguishable from
  an inherited one.
- **Completeness is NOT verified locally, and the bullet MUST say so.** The repo-local check cannot
  tell whether the declared set omits a name a sibling consumes; that is the central-vantage
  conformance row's obligation under v178's split-enforcement clause. The bullet MUST name that
  limit explicitly rather than leave a reader to infer that a green local check means the declared
  surface is complete.

The `livespec-dev-tooling` self-application bullet in §"Consumer inventory" MUST NOT be changed to
list this key among the keys that "MUST be declared EXPLICITLY EMPTY": it is not a required key,
and adding it to that sentence would create exactly the required-key reading this proposal rejects.
