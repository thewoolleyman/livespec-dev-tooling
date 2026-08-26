---
topic: invocation-set-inventory
author: claude-opus-5
created_at: 2026-08-26T01:48:37Z
---

## Proposal: Model the invocation set in `release_bump_classification`'s inventory

### Target specification files

- SPECIFICATION/contracts.md

### Summary

v051's `release_bump_classification` derives its public-surface inventory from module-level `__all__` entries alone. That models an EXPORT surface. It does not model an INVOCATION surface — the `python -m livespec_dev_tooling.checks.<slug>` and `python -m livespec_dev_tooling.workflow_checks.<slug>` sets — which are the first two entries of this specification's own §"Semver discipline" enumeration, the second of them added by v051 itself.

Extend the check to inventory module PRESENCE under consumer-declared invocation-set directories, alongside the `__all__` names it already inventories, so that adding, deleting, or renaming a slug reads as a surface addition or removal. Introduce one new OPTIONAL role key to declare those directories, and correct the ratified section's over-broad description of what it detects.

### Motivation

Measured against the real `v1.32.1` → `v1.33.0` changeset immediately after v051 shipped: the check exited `0` with `inventory 714 → 714, added 0, removed 0, required none, declared minor`. It passed VACUOUSLY — because `required` was `none`, not because it verified anything about the release.

The cause is that 56 of the 60 SLUG modules under `livespec_dev_tooling/checks/` declare an EMPTY `__all__`, as do both slug modules under `livespec_dev_tooling/workflow_checks/`. (Slug modules are the direct children excluding `__init__` and underscore-prefixed helpers — the only ones that are invocation-set elements.) A check module's consumer-facing surface is its INVOCATION form, not its exports, so adding or removing one moves the `__all__` inventory by ZERO names.

The concrete failure this leaves open: deleting `livespec_dev_tooling/checks/all_declared.py` REMOVES an element of an enumerated surface and is therefore MAJOR under §"Semver discipline". The check computes `required` = `none` and passes a `fix:`-typed PATCH release. That is precisely the failure shape `release_bump_classification` was ratified to prevent, occurring in the repository that ships it.

A RENAME is the same event and is already known to break consumers. §"Shared check inventory"'s canonical-set derivation is a filesystem walk, and this repository's own `canonical_checks` module records the consequence: once `checks/<old>.py` is renamed to `checks/<new>.py` the old slug falls out of the walk, and a consumer's justfile and CI matrix — auto-wired back when the old slug WAS canonical — then bump past the rename and run a recipe importing a module that no longer exists, failing with `ModuleNotFoundError` on an otherwise routine bump PR. That is a breaking change to an enumerated surface element, and it is exactly what this extension makes visible to the gate.

This is NOT the "honest limit" the ratified section already declares. That limit is scoped to BEHAVIOR-only breaks — "a tightened parse contract, a narrowed glob, a changed return shape behind an unchanged name". A deleted or renamed module is not behavior-only; it is a surface element disappearing, which the section positively CLAIMS to detect: "It detects a surface element appearing or disappearing". The section therefore OVERCLAIMS relative to its implementation, and this proposal closes the gap by strengthening the implementation rather than by narrowing the claim.

Scope of the defect, stated so the correction is not over-applied: the blind spot affects repositories whose public surface is an INVOCATION set. A consumer whose surface is an EXPORT set is already modelled faithfully — livespec-runtime exports 173 names via `__all__`, and the check is effective there today.

### Proposed Changes

**1. Add one OPTIONAL role key to §"Consumer configuration schema" → §"Role keys".**

ADD `invocation_set_trees` — array of strings, repo-root-relative directory paths. Each declared directory's DIRECT-CHILD `.py` modules constitute an invocation-set surface: one element per module, named by its module stem.

It MUST be declared OPTIONAL, and its absence MUST behave exactly as `[]`: no invocation-set modelling, i.e. today's ratified behavior. This is load-bearing for the bump rule below and for the fleet — the key is additive, no existing consumer is obliged to declare it, and no consumer's gate changes verdict until it opts in. It MUST be recorded as read by `release_bump_classification`, per §"Role keys"'s rule that a check beginning to read a role key MUST be reflected in that key's consumer list in the same change.

Because it is optional with a declared-absent default, this key MUST NOT be added to the set of keys a consumer is required to declare, and MUST NOT be enumerated in `partition_completeness` or `source_trees_scoped_to_consumer` per the standing exclusion rule for those two structural meta-checks.

**2. Amend the `### `release_bump_classification` check` section.**

The section's "What "public surface" means for this check" clause MUST be widened to define the inventory as the UNION of two element kinds:

  - EXPORT elements, unchanged: `<module-path>:<name>` for every module-level `__all__` literal string entry under `source_trees`.
  - INVOCATION elements, new: one element per direct-child `.py` module of each directory declared in `invocation_set_trees`, formed so it cannot collide with an export element (for example `<tree>::<stem>`; the exact spelling is an implementation detail, the non-collision is not).

Invocation-element discovery MUST mirror the canonical-set derivation's own rules so the two cannot disagree about what a slug is: DIRECT children only, never recursive; `__init__` excluded; underscore-prefixed module names excluded as internal helpers. It MUST state that a directory declared but absent from the tree at a given revision contributes no elements and is not an error, so a tree introduced after the baseline tag reads as additions rather than a crash.

Algorithm step 3 is UNCHANGED in structure — removal → `major`, else addition → `minor`, else `none` — and now sees invocation elements as well as export elements, so a deleted or renamed slug yields `major` and a new slug yields `minor`.

The section MUST record that a RENAME appears as a removal PLUS an addition and therefore classifies as `major`, which is correct: consumers holding the old slug break.

**3. Correct the section's overclaim.**

The honest-limit clause MUST be amended so it no longer implies the inventory detects every surface element appearing or disappearing. It MUST state that the inventory models exactly the element kinds enumerated above, that a surface element of a kind NOT modelled — including an invocation set when `invocation_set_trees` is undeclared — is invisible to the check, and that a consumer whose surface is an invocation set MUST declare that key or knowingly accept the gap. The existing behavior-only-break limit is retained unchanged and MUST be kept distinct from this one: they are different failure modes, and collapsing them is what let the first overclaim pass ratification.

The requirement that the module docstring state the honest limit extends to this correction, and MUST be worded so it binds BOTH limits rather than only the behavior-only one. A docstring clause positionally attached to a single limit leaves the correction itself — the unmodelled-element-kinds limit — absent from the docstring, which is precisely the omission this proposal exists to repair.

**4. Widen the `fail`-finding `added` / `removed` fields to cover both element kinds.**

Those fields currently describe their entries as "the sorted `<module-path>:<name>` entries". Once invocation elements exist and are keyed so they cannot collide with export elements, that description and the union inventory are JOINTLY UNSATISFIABLE: on an invocation-only delta — deleting a slug module, the exact vacuous-pass scenario this change exists to fix — a conforming implementation must either omit the element that caused the refusal, leaving the `message` and `hint` with no supporting evidence, or violate the field contract. Two conforming implementations would diverge materially on the change's own motivating case.

The fields MUST therefore be widened to cover BOTH element kinds, and each entry MUST carry enough of its key to identify which kind it is.

**5. Name both role keys in the section's "Inputs:" clause.**

That clause currently names `source_trees` alone. The check now also reads `invocation_set_trees`, and §"Role keys" explicitly indicts approximate enumerative clauses — "These lists MUST NOT be softened into approximations" — so an Inputs clause that under-reports what the check reads is the very defect shape this specification already prohibits.

**6. Record the `Clean role keys retain `[]`` re-evaluation.**

That section requires UNION membership be re-evaluated whenever the role-key inventory changes. The re-evaluation MUST be recorded with its outcome: the new key is NOT a UNION key, because an empty declaration leaves the check inspecting its export universe rather than inspecting nothing.

**7. Bound the known divergence from the canonical derivation.**

The mirror-the-canonical-rules clause MUST NOT claim the two can NEVER disagree. `pkgutil.iter_modules`, which the canonical derivation uses, also yields non-underscore SUBPACKAGES, whereas an invocation element is a direct-child `.py` MODULE. No such subpackage exists under either invocation-set directory today. The clause MUST state the divergence, state that it is currently vacuous, and require re-evaluation in the same change that introduces such a subpackage.

**8. Amend §"Semver discipline"'s MINOR rule for the new key.**

The existing MINOR rule already covers "a new optional configuration key". This proposal ADDS such a key and makes an existing check read it without changing any verdict for a consumer that does not declare it, so this change is MINOR. The section MUST NOT be read as making the new key's introduction a MAJOR: no existing surface element is removed, renamed, or incompatibly reinterpreted.

**9. No `##` heading is added, renamed, or removed.** One `###` section is amended, one role key is added to the existing §"Role keys" inventory, and one bump-rule clause is confirmed.
