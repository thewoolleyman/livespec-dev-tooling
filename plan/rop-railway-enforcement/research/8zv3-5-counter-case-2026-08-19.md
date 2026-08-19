# The case AGAINST my own `8zv3.5` finding — written for the panel

The maintainer deferred `8zv3.5` to a consensus panel for **adversarial vetting** of my
names-not-files reading. Every note in this directory argues FOR that reading, and they
were all written by the same session. **A dossier containing only the proponent's case is
not adversarial input; it is a brief.** So this is the strongest case against my own
finding that I can construct, written before the panel convenes and by the person with the
most to lose from it.

Where an argument fails, I say so — a steelman that quietly omits its own refutations is
worth less than nothing to a panel.

## Counter 1 — "`_` marks a PRIVATE MODULE, and the fleet means it" ❌ FAILS ON THE TEXT

**The case:** Python's convention is that `_name` is private. A `_`-prefixed *module* is a
private module; nothing inside it is API regardless of `__all__`. Clause 0 adopts "the
private-helper definition", and a reasonable reader takes that definition to be about
privacy-by-underscore generally, not about function names specifically.

**Why it fails, and I checked rather than assumed.** Clause 1 does not leave the boundary
to interpretation — it names it: *"imported by NON-TEST first-party code, in the declaring
repo **across a module boundary**, or in ANY governed sibling."* The **module** boundary is
the stated unit. `commands/_config.py` → `commands/next.py` crosses it by the text's own
definition. And §"Typechecker rule set" defines private helpers by *"single-leading-
underscore prefix **or not in `__all__`**"*, quantified over functions and dataclass fields
— a definition a `_`-module's `__all__`-listed functions do not satisfy.

**Verdict: this is the intuitive objection and the text forecloses it.**

## Counter 2 — "the `__all__` requirement is scoped, so it proves nothing" ⚠️ PARTIALLY SURVIVES

**The case:** I lean on §"Module API surface" — *"EVERY module MUST declare a module-top
`__all__`"* — to argue a `_`-module is compelled to publish an API surface. But that
sentence is scoped, in its own words, to `.claude-plugin/scripts/livespec/**`. Reading a
livespec-CORE layout rule as a fleet-wide statement about `_`-prefixed modules is a
stretch. A module may declare `__all__` purely to satisfy `check-all-declared`, which
enforces the declaration mechanically and cares nothing about the railway.

**How much survives:** the *positive* form of my argument is weaker than I wrote it. I
called the skip "self-contradictory against a requirement the rule states positively" —
that overstates it if the requirement is layout-scoped. **What survives is the original,
weaker form: nothing in the ratified text establishes a FILE-level skip.** Absence of
authority is still fatal for a skip that removes 387 functions from a rule's reach, but it
is a different and more modest claim than the one I made.

▶️ **This is a real hit and the panel should record it.** My addendum
(`underscore-file-skip-remeasure-2026-08-19.md`) claims the text "contradicts" the skip.
**"Does not authorise" is the defensible verb.**

## Counter 3 — the skip is a de-facto STAGING mechanism ✅ SURVIVES AS SEQUENCING

**The case:** whatever its provenance, the skip is currently the only thing standing
between the fleet and a 2.8× enforcement expansion. `46c5dab` proves what happens when this
check widens ahead of adoption: five repos red, a P0, and a revert. Removing the skip is
the same move at larger scale.

**Why it survives:** it is not a claim about the rule at all — it is about the
**enforcement basis**, and those are separable. The panel can accept names-not-files as the
RULE while keeping 214 as what the check ARMS on today. My notes conflate the two more
than they should.

⛔ **The strongest form of this counter is one my own data supports**: ~93% of convictions
under either basis are questions rather than conversions
(`first-unit-recheck-2026-08-19.md`). **Ratifying 601 buys 387 more open questions and
almost no additional actionable work.** That is an argument for deferring the basis change
on *value* grounds, entirely independent of correctness.

## Counter 4 — the measurement is mine, and it is young ⚠️ PARTIALLY SURVIVES

**The case:** the 214/601 figures come from a harness I wrote today, reproduced in one
note, run by one session. The plan's older figures had a positive control and a peer's
independent derivation; mine mostly do not.

**What defends it:** the harness reproduced `irtt`'s eleven independently-recorded
offenders exactly, and the foreman independently derived dev-tooling's 3 matching my
`WITH_skip=3`. **What does not:** the 601 side has NO independent check. Nobody has
reproduced it, and it is the number that would be ratified.

▶️ **Concrete ask for the panel: have someone re-derive 601 independently before it is
ratified.** I would not ratify a 2.8× expansion on one session's unreplicated number, and I
produced it.

## Counter 5 — `_config.py` may be atypical ❌ FAILS ON MEASUREMENT

**The case:** my strongest evidence is one file imported by 17 modules. One vivid example
may not generalise; perhaps most `_`-files really are private helpers.

**Why it fails:** the delta is 387 functions across the fleet, concentrated in two repos
(overseer +204, beads-fabro +155). Whatever those are, they are not one atypical module.
**But note the counter-counter**: I have NOT verified that those 387 are consumed across
module boundaries the way `_config.py` is. **The 17-importer evidence is one file deep.**
A panel could reasonably ask for that check across the 387 before ratifying.

## What I would tell the panel if I had one sentence

**Accept the rule reading, question my verb, and separate the rule from the enforcement
basis** — the text does not authorise a file-level skip, but "contradicts" overstates it,
601 is unreplicated, and ratifying it buys mostly questions rather than work.

## What this note is not

It is not a retraction. I still believe the names-not-files reading is right, and Counters
1 and 5 fail on the text and the measurement respectively. **But Counters 2, 3 and 4 are
live, and a panel that never heard them would be vetting a brief rather than a finding.**
