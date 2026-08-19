# Uninhabited failure tracks, measured fleet-wide 2026-08-19 — and a correction to my own claim

The triage note observed that `8o8e.19` and `8o8e.28` are the same defect from opposite
sides, and I drew a conclusion from it: *converting-for-conformance can manufacture the
dead failure track `.28` warns about.* **That was an assertion from one instance.** This
track's standing rule is to measure before believing, so I measured it — and the
measurement does not support the claim as I made it.

## Method

An AST detector over each repo's resolved check universe, counting a function only when
**all three** hold:

1. its return annotation is `Result[...]` or `IOResult[...]`;
2. its body constructs **no** `Failure(...)` / `IOFailure(...)` anywhere;
3. **every** `return` returns a direct `Success(...)` / `IOSuccess(...)` call.

Clause 3 is what keeps it tight rather than a soft upper bound: a function that returns
*a call* may be forwarding a callee's failure, so it is **not** counted. This is
deliberately conservative — the real number is at least this.

**Positive control:** the detector independently reproduced
`_check_segment_result` in `livespec-driver-codex`'s `_footgun_tmux.py` — the exact
function `8o8e.19` names, found without being told about it.

## MEASURED

| member | total | public-named | `_`-prefixed |
|---|---:|---:|---:|
| `livespec` | 12 | 2 | 10 |
| `livespec-driver-codex` | 6 | 0 | 6 |
| `livespec-runtime` | 1 | 1 | 0 |
| `livespec-dev-tooling` | 0 | 0 | 0 |
| `livespec-overseer` | 0 | 0 | 0 |
| `livespec-orchestrator-beads-fabro` | 0 | 0 | 0 |
| `livespec-orchestrator-git-jsonl` | 0 | 0 | 0 |
| `livespec-driver-claude` | 0 | 0 | 0 |
| **TOTAL** | **19** | **3** | **16** |

The three public-named: `livespec` `doctor/static/copier_template_workflow_coverage.py:189
run`, `doctor/static/parent_proposed_change_resolves.py:286 run`, and `livespec-runtime`
`github_budget_measurement.py:69 append_rate_limit_snapshot`.

## ⛔ THE CORRECTION — my claim was wrong in its causal direction

**16 of 19 are `_`-prefixed.** v178 clause 0 disqualifies `_`-prefixed names outright, so
`public_api_result_typed` **has never convicted a single one of them**. They were not
produced by conformance pressure, because the rule does not reach them. Someone chose the
railway there voluntarily.

▶️ **So the dead failure track is not primarily a conversion artefact. It is a property of
the IDIOM, arising where no check was pushing at all.** My "converting-for-conformance
manufactures dead tracks" was the wrong causal story, drawn from `.19` — which is itself
one of the 16 private cases, and therefore the weakest possible support for it.

## ▶️ THE SHARPER FINDING THE MEASUREMENT ACTUALLY SUPPORTS

**The check cannot see this defect, in either direction.**

`copier_template_workflow_coverage.py:189` is
`def run(*, ctx: DoctorContext) -> IOResult[Finding, LivespecError]` — public,
railway-typed, failure track uninhabited. It **PASSES** `public_api_result_typed`, because
the check tests the RETURN TYPE, not whether the failure track is INHABITED.

That is the whole point, and it is worse than the claim I retracted:

- **19 functions today satisfy the check while carrying a failure track nothing can
  produce.** The check reports green on every one.
- **Remediating 143 offenders will add an unknown number more, and the check will report
  green on those too.** Not because conversion causes it — the 16 show it happens
  without conversion — but because **nothing detects it either way.**

⚠️ **So "the check is green after remediation" MUST NOT be read as "the railway is
meaningful here."** Those are different claims, and this fleet already contains 19
counterexamples to conflating them. That is exactly this epic's founding lesson in a new
place: a check that reports green over something it structurally cannot evaluate.

## What this does and does not settle

**Does not settle:** whether each of the 19 is a defect. A function may legitimately be
total today and railway-typed for interface symmetry with siblings — that is
`8o8e.28`'s open question, and pricing it is the maintainer's. The 3 public-named ones
deserve reading first; `_`-prefixed helpers are the weaker case since nothing outside
consumes their failure track.

**Does settle:** the count is 19 by a conservative definition, the distribution is 16
private to 3 public, and **the enforcing check is blind to all of them.** Any remediation
acceptance criterion that is only "the check passes" inherits that blindness.

**Suggested, not filed:** if a detector for this is ever wanted, the definition above is
mechanical, ran fleet-wide in seconds, and reproduced a known instance without being
pointed at it.
