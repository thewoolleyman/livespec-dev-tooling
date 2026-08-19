# resolve_canonical_branch probe, 2026-08-19 — the escape is real but NOT free

The functional-core / imperative-shell redesign does **not** remove resolve_canonical_branch's conviction under the shipped analyzer (functions_without_expected_failure_mode) when the function is retained as a public shell, even when factoring in a pure composer helper. Only Variant B—removing resolve_canonical_branch entirely and inlining its probe logic into each caller—eliminates the conviction, because the convicted function no longer exists.

| variant | exempt set | is the conviction removed? |
|--------|------------|----------------------------|
| SHIPPED | [] | ❌ no |
| VARIANT A (shell retained, pure composer added) | [compose_canonical_branch] | ❌ no |
| VARIANT B (shell deleted, probes inlined) | [compose_canonical_branch] | ✅ yes (function gone) |

The probe logic (config read + git symbolic-ref + origin/ prefix strip) must be duplicated into both calling modules: `work_item_merge_evidence.main` and `migration/merge_evidence_backfill.py` (line 113, which imports at line 57). Since `resolve_canonical_branch` is listed in the check module’s `__all__`, that export must be updated as well. Additionally, `merge_evidence_backfill.py`’s docstring currently cites “the check module’s resolve_canonical_branch chain” as the shared contract, so that documentation must be revised under Variant B.

**Method:** ran the SHIPPED analyzer (`functions_without_expected_failure_mode`) over the real git-jsonl universe, substituting rewritten source into the sources mapping *in memory*. No files changed on disk. Exact function bytes read from `.claude-plugin/scripts/livespec_orchestrator_git_jsonl/checks/work_item_merge_evidence.py`, never retyped. A name in the returned set is exempt (not convicted).

## Adjudication — what this means for `8o8e.28`

**`8o8e.28`'s premise is refuted for this exemplar too, but not in the shape it was
argued.** The proposal was recorded as "split into a pure composer taking probe
RESULTS as parameters, with the probes assembled at the caller inside `main()`'s IO
context." Read naturally, that is **Variant A** — and Variant A does not work. It
manufactures a new exempt pure function and leaves the convicted one exactly as
convicted as before. Only the strong form, deleting the public shell outright, moves
the needle, and it does so by removing the subject rather than by fixing it.

⚠️ **THE TIDY READING IS THE WRONG ONE, and that is the trap worth recording.**
"Add a pure composer" feels like the whole refactor; it is measurably half of it. A
session that stopped at Variant A would have reported the escape as proven while the
check still convicts.

**And Variant B is not free — it trades a conviction for a single-sourcing
violation.** The three-way precedence chain is a RATIFIED contract
(`git-jsonl SPECIFICATION/contracts.md`, the `canonical_branch` clause). Today it is
expressed once, in one function, imported by both consumers. Variant B duplicates the
config read, the `git symbolic-ref` probe and the `origin/` strip into two modules,
and deletes the shared chain the migration module's own docstring points at. Two
copies of a ratified precedence rule can drift; one cannot.

▶️ **So the honest finding is not "the exemption is unnecessary" — it is that the
escape exists and costs a duplicated ratified contract.** Whether that price is worth
paying is a maintainer call, and it is a different question from the one
`8o8e.28` was opened on. What is now settled by measurement is only this: **"no
legitimate escape" is false.** What replaces it is a trade, not a free fix.

⚠️ **`main` is out of scope here and was not measured.** Under Variant B the inlined
`subprocess.run` lands in each caller's body; whether those callers are themselves
convicted is a separate question this probe does not answer. Do not read
`exempt = [compose_canonical_branch]` as "everything else is clean."
