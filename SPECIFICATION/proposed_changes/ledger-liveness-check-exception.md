---
topic: ledger-liveness-check-exception
author: claude-opus-5
created_at: 2026-09-07T14:40:00Z
---

## Proposal: A check MAY resolve the liveness of a work-item id it stands down on, as a named exception to the network-I/O non-goal

### Target specification files

- SPECIFICATION/spec.md

### Summary

Carve ONE narrow, named exception into the §"Non-goals" bullet **"Network I/O from any
check"**: a check that stands down on an explicitly named work-item id MAY resolve that id's
existence and open/closed state against the repository's own work-item store, and MUST degrade
honestly when the store is unreachable. Every other remote access from a check stays forbidden,
and the exception is scoped to a liveness answer about an id the check ALREADY names — never to
fetching the thing being checked.

### Motivation

Work-item `livespec-dev-tooling-x7ml`, and its consolidated duplicate `livespec-dev-tooling-klvy`.

Three gates in this library accept a named work-item id as their reason to stand down, and
NOTHING verifies that the id exists or is still open: `no_lloc_soft_warnings`,
`no_todo_registry` / `check-no-todo-registry`, and `required_role_keys_declared` (the
`unarmed_until = "<ledger-id>"` arm in `_role_key_gate.py`). A closed, superseded, or mistyped
id keeps the gate silently off forever while reporting green with no live owner. Two of the
three grew the identical UNIMPLEMENTED liveness seam independently, with the same docstring
wording, which is why the defect is the missing shared mechanism rather than any single gate.
Measured 2026-08-19 by the livespec-overseer test-and-gate-integrity thread: 3 of 27
`no_todo_registry` entries in that repo were orphaned by closed owners.

This is the vacuous-gate defect in its purest form: a concession mechanism that was designed to
keep a named work-item ACCOUNTABLE for a deferral instead permanently silences the gate, and
the silence is indistinguishable from compliance.

**The amendment is required because x7ml cannot be implemented without it.** x7ml's ratified
acceptance requires a shared resolver answering "does `<ledger-id>` exist and is it open", with
the tenant resolved from the consuming repo's own config. This repository's work-item store is a
beads/Dolt tenant reached over TCP `127.0.0.1:3307`. A check that queries it performs network
I/O from a check, which the current non-goal forbids without qualification. The two clauses
cannot both stand unchanged: either the gates keep silently lying, or the non-goal admits this
one lookup. This proposal chooses the latter, narrowly.

**The determinism cost is real and is stated rather than hidden.** The non-goal's stated reason
is that "every check MUST be deterministic against its input file tree". A liveness lookup is
NOT deterministic against the file tree: the same tree yields a different verdict after someone
closes the named work-item. That is not an accident of the design — it is the entire point, because
the condition being checked ("is this deferral still owned by live work?") is a fact about the
ledger and cannot be answered from the tree at all. What the amendment must therefore preserve is
not determinism but HONESTY: the check must never convert an unanswerable question into a pass.

### Proposed Changes

In §"Non-goals", replace the bullet

> - **Network I/O from any check.** Every check MUST be deterministic against its input file
>   tree; reaching out to a remote service from a check is forbidden.

with a bullet that keeps the prohibition as the rule and names exactly one exception. It MUST
state all of the following, normatively:

1. **The rule is unchanged in general.** Every check MUST be deterministic against its input
   file tree, and reaching out to a remote service from a check is forbidden, EXCEPT as stated
   in (2). In particular a check MUST NOT fetch, over the network, any artifact it is checking
   or checking against — not the specification, not a sibling repository's tree, not a release
   payload, not a configuration file. The exception is a lookup ABOUT a name the check already
   holds, never a retrieval OF the thing under check.

2. **The single exception — work-item liveness.** A check that stands down, weakens, or exempts
   on the basis of an EXPLICITLY NAMED work-item id MAY resolve that id against the repository's
   own configured work-item store, for the sole purpose of determining whether the id exists and
   whether it is open. The resolved answer MAY be used only to decide whether the stand-down
   remains in force. No other query, field, or use is permitted under this exception.

3. **It MUST degrade honestly, and this is the load-bearing clause.** When the store is
   unreachable, unreadable, or does not answer, the check MUST SKIP WITH A STATED REASON naming
   the id and the reason it could not be resolved. It MUST NOT silently pass, and it MUST NOT
   hard-fail an offline build. A ledger-dependent gate that no-ops when the store is away
   reintroduces the vacuous-gate defect this amendment exists to remove, and a gate that reds an
   offline developer's tree makes the store a build dependency it is not.

4. **The verdict is discriminating in both directions.** A stand-down on an id that resolves to
   CLOSED (or that does not exist) MUST surface — red or warning per the consuming gate's own
   contract — NAMING the id and its resolved status. A stand-down on an id that resolves to OPEN
   MUST stay quiet. A gate that can only report one of these two outcomes has not adopted the
   exception.

5. **One shared mechanism, not per-gate hand-rolls.** The resolution MUST be provided by a single
   shared resolver that consuming gates call. A gate hand-rolling its own lookup is the pattern
   this amendment exists to end, and is non-conforming even if its behaviour is otherwise correct.

6. **No lever.** No environment variable, CLI flag, configuration key, or per-repository
   exemption may disable the liveness resolution, force it to pass, or convert a CLOSED verdict
   into a quiet one. The honest-degradation path of (3) is the ONLY way a check may proceed
   without an answer, and it is a SKIP carrying its reason, never a pass.

Also state that the non-determinism admitted by (2) is bounded to the stand-down decision alone:
a check's verdict on the tree itself MUST remain a function of the tree, so a liveness answer may
only remove a stand-down, never introduce, suppress, or alter a finding about the tree's contents.
