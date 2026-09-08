---
topic: exit-contract-skip-outcome
author: claude-opus-5
created_at: 2026-09-08T03:05:00Z
---

## Proposal: The Python-package exit contract names THREE outcomes — pass, fail, and SKIP-with-a-stated-reason — and states where a SKIP is distinguishable from a pass

### Target specification files

- SPECIFICATION/spec.md

### Summary

§"Two consumption surfaces" declares the Python package's exit contract as a BINARY: each check
module "MUST exit `0` on pass or non-zero on fail". A third outcome — SKIP with a stated reason —
is already normative elsewhere in the ratified spec and already codified per-check in
`contracts.md`, but the architectural surface contract does not name it. This proposal adds it,
and — the load-bearing half — states the property that keeps a SKIP from collapsing into a pass:
because a SKIP shares exit `0` with a pass, the DISTINCTION MUST live in the structured stderr,
and a check that exits `0` carrying no stated reason has asserted a pass.

### Motivation

This is PRE-EXISTING looseness that v062 inherited rather than introduced. It is filed as a
follow-up, with the v062 ratification reviewer's explicit agreement that it is a follow-up and
NOT a ratification condition on that amendment.

**The two clauses do not currently meet.** v062 (`ledger-liveness-check-exception`) made SKIP
normative for an entire class of checks, in two places in `spec.md` itself:

> - **It MUST degrade honestly.** When the store is unreachable, unreadable, or does not answer,
>   the check MUST SKIP WITH A STATED REASON naming the id and why it could not be resolved. It
>   MUST NOT silently pass, and it MUST NOT hard-fail an offline build. (spec.md:48)

> - **No lever.** [...] The honest-degradation SKIP above is the ONLY way a check may proceed
>   without an answer, and it is a SKIP carrying its reason, never a pass. (spec.md:51)

Eight lines earlier in the same document, the surface contract offers a check only two exits:

> Each module is invocable as `python -m livespec_dev_tooling.checks.<slug>` and MUST exit `0` on
> pass or non-zero on fail (with structured stderr describing the failure). (spec.md:16)

A conforming implementer reading only §"Two consumption surfaces" has no exit to put a SKIP on.
Reading only the exception, they have a mandated outcome the surface contract does not admit.

**The practice already exists and is already inconsistent with the architecture clause.**
`contracts.md` has been writing the three-outcome contract per-check for some time, in the
SAME words each time:

- `primary_checkout_commit_refuse_hook_installed` — "Exit `0` on pass OR skipped, exit `4` with
  structured stderr findings on fail." (contracts.md:177)
- `plugin_resolution` — the same formula (contracts.md:222), with skipped paths at three distinct
  preconditions (contracts.md:196, 198, 239).
- `no_shadow_ledger_body_identical` — the same formula (contracts.md:257).
- `fleet_conformance` — "lever unset → the check logs 'skipped' and exits 0" (contracts.md:535).
- The cross-harness live-resolution smoke turns SKIP-vs-fail into an explicit ruling, citing
  work-item `livespec-mjnv`: "'can't run here' ≠ 'command failed'" (contracts.md:246-247).

So the gap is not that the fleet lacks a SKIP convention. It is that the convention lives only in
per-check contracts, was never lifted into the surface contract that governs all of them, and is
therefore invisible to anyone implementing a NEW check from the architecture section.

**The sharp edge, and why naming the outcome is not sufficient on its own.** A SKIP exits `0`.
So does a pass. At the exit-code level the two are THE SAME OBSERVATION, and the whole reason
v062 needed its honest-degradation clause is that an unanswerable question silently reported as
`0` is indistinguishable from compliance — the vacuous-gate defect. `contracts.md` already
handles this correctly for the checks it covers, and states the discriminator explicitly:

> (The `skipped` paths at steps 1, 2, and 4 emit a `warning`/`info` log carrying `check_id` plus
> a `hint`/`cwd` field respectively; only the `fail` paths carry the `status` field.)
> (contracts.md:216)

and, generalized, at contracts.md:447:

> A repo excluded by that scope rule MUST be reported as excluded-with-reason, never silently
> skipped: a silent skip is indistinguishable from a pass, which is the failure mode this whole
> section exists to eliminate.

An amendment that merely added "or skip" to the exit contract would ratify the ambiguity instead
of closing it. The contract has to say that the stated reason is the carrier of the distinction,
and that its ABSENCE means pass.

### Proposed Changes

In §"Architecture" → §"Two consumption surfaces", replace the first sentence of the **Python
package** bullet:

> Each module is invocable as `python -m livespec_dev_tooling.checks.<slug>` and MUST exit `0` on
> pass or non-zero on fail (with structured stderr describing the failure).

with:

> Each module is invocable as `python -m livespec_dev_tooling.checks.<slug>` and MUST report
> exactly one of THREE outcomes. **PASS** — exit `0`, emitting no finding. **FAIL** — exit
> non-zero, with structured stderr describing the failure. **SKIP** — exit `0`, with a structured
> stderr record STATING THE REASON the check could not reach a verdict, naming the check and the
> unmet precondition. A check MUST NOT report a SKIP for a question it can answer, and MUST NOT
> report a PASS for one it cannot.
>
> A SKIP and a PASS share exit `0`, so the exit code alone does NOT distinguish them: the stated
> reason on stderr is the ONLY carrier of the distinction, and a check that exits `0` emitting no
> stated reason has asserted a PASS. A check that cannot reach a verdict and exits `0` silently is
> non-conforming even when its own precondition logic is correct, because a silent skip is
> indistinguishable from compliance — the vacuous-gate failure mode. Per-check contracts in
> `contracts.md` MAY narrow this (for example by fixing a specific non-zero exit for fail, or by
> enumerating the exact preconditions on which that check SKIPs), but MUST NOT widen it, and MUST
> NOT introduce a fourth outcome.
>
> The SKIP outcome is not an escape hatch: it is available only where a check's own ratified
> contract names the precondition it skips on. It is NOT a lever, and §"Non-goals" governs where a
> SKIP is MANDATORY (the work-item-liveness exception's honest degradation) as against merely
> permitted.

### Rationale

- **It reconciles rather than changes.** Every clause cited above is already ratified or already
  shipped; nothing in this proposal alters what any existing check does. It lifts a convention
  `contracts.md` applies four times into the surface contract that should have carried it.
- **It closes the ambiguity in the direction the spec already chose.** spec.md:48's "MUST NOT
  silently pass" and contracts.md:447's "a silent skip is indistinguishable from a pass" are the
  same rule; this states it once, generally, where a new check's author will read it.
- **It keeps `contracts.md` authoritative per-check.** The narrowing-not-widening rule preserves
  the existing per-check exit codes (`4` for fail, the §"Role keys" undeclared-key exit) without
  restating them.
- **It does not create a lever.** The final paragraph is explicit, because "exit 0 with a reason"
  is exactly the shape a forgeable carve-out would take. A SKIP is admissible only on a
  precondition the check's own ratified contract names.

### Non-goals of this proposal

- It does NOT change any existing check's behaviour, exit code, or per-check contract.
- It does NOT introduce a machine-readable SKIP schema; the structured-stderr shape stays as
  `contracts.md` defines it per check.
- It does NOT revisit the v062 work-item-liveness exception, which is ratified and stands.
