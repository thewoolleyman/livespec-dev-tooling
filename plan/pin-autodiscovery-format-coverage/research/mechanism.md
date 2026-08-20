# Mechanism — the pin-autodiscovery walk's format coverage, and how it goes stale

**Ledger anchor:** epic `livespec-dev-tooling-ikeggh`. All mutable plan state — status, next
action, handoff entries — lives on that epic and its child items; this note is
write-once research and is never authoritative about what remains.

Measured 2026-08-20 against this repo's master. Re-measure before trusting any
path or count.

## Why this thread exists

`livespec_dev_tooling/cross_repo/pin_autodiscovery.py` is the walk that finds every
pin a consumer repo holds, so a bump can rewrite it and a pin-currency row can
report it stale. Its value is entirely a function of its COVERAGE: a pin format the
walk does not know is not merely unreported, it is invisible — never discovered,
never reported stale, never rewritten. The failure is silent by construction, and a
consumer pinned in an unknown format drifts indefinitely while every pin-currency
row for it passes.

Two such formats are known missing today, found independently and months apart.
That is the signal this thread exists to act on: the gap is not one oversight, it
is a class, and the walk has no mechanism that makes a missing format visible.

## The two carriers, and what is common between them

Both are "the walk does not know a format that consumers actually use". They differ
in sub-module and in format, which is why they are siblings rather than duplicates
and why neither closes the other.

- `livespec-dev-tooling-zct56w` — the Claude plugin pin held in the settings file
  under the extra-known-marketplaces entry's source ref. MEASURED: a count of that
  key's occurrences in `cross_repo/pin_autodiscovery.py` returns zero.
- `livespec-dev-tooling-ep8n` — workflow-template pins, missed on both directory
  and suffix, in `cross_repo/_pin_directory_scan_formats.py`.

**THIS THREAD IS THE FIRST HOME EITHER ITEM HAS HAD.** Neither was moved here from
another thread. `zct56w` was filed 2026-08-20 and parented here directly; `ep8n`
sat unparented in this tenant, having earlier been moved between TENANTS (from the
`livespec` tenant, where it was `livespec-4kwu`) but never into any plan. Do not
read this thread's creation as a re-organisation of existing plan structure — there
was none to re-organise.

## A false-negative trap that has already misled one investigation

Grepping the PACKAGE as a whole for the marketplace key returns hits, which wrongly
suggests `zct56w`'s gap is already closed. The only two hits are
`livespec_dev_tooling/fleet/ensure_plugins.py` and
`livespec_dev_tooling/fleet/_ensure_plugin_commands.py` — the plugin INSTALL
surface, a different concern from the pin-rewrite walk. Verified 2026-08-20 that
those two are the complete set of package hits.

Anyone re-checking either carrier must grep `cross_repo/pin_autodiscovery.py` and
its helper modules SPECIFICALLY. This generalises to the whole thread: the install
surface and the rewrite walk both legitimately mention pin formats, so package-wide
searches cannot answer coverage questions here.

## The count lives in TWO places and they must move together

This is what makes either carrier more than a pure code change, and it was the
detail that turned a blind dispatch into a planned one:

- `SPECIFICATION/contracts.md`, section "Pin autodiscovery rules", enumerates the
  formats the walk MUST cover ("The walk MUST cover the following formats:").
- `pin_autodiscovery.py`'s own module docstring states the walk "covers six
  formats, split across two cohesive helper modules", and then enumerates them.

Adding a format therefore requires amending the ratified spec prose AND the module
docstring. A change that updates only one leaves the two records disagreeing about
what the walk covers — which is the same class of defect as the walk itself having
a coverage gap, one level up.

## What the contract already requires, and must not be regressed

`contracts.md` already pins several properties that any format addition must
preserve. They are stated here because a new-format change is exactly where they
get broken by accident:

- The walk is TOLERANT of missing files: a consumer without a given pin file simply
  yields no records of that format.
- An UNRECOGNIZED format produces no record plus a human-visible annotation naming
  the file.
- A file PRESENT at a known format's path whose contents cannot be PARSED is NOT an
  unrecognized format. It must be a distinct, typed can't-parse outcome that a
  consumer cannot silently drop, and must NOT be carried as an in-band record in the
  normal record stream — because a record is precisely the carrier a
  record-filtering consumer discards without deciding about it.
- A pin-currency row MUST NOT return a passing outcome for a format it did not
  successfully evaluate. An absence of records is a pass ONLY when the walk
  completed and genuinely found no pin of that format.

That last pair is the reason a naive "add a format" change is risky: the easy
implementation returns no records for an unparseable file, which reads as a pass.

## Ordering note for the first implementer

Take `zct56w` first. It is `ready`, ungated, and its acceptance is already written
with a positive control on both directions. `ep8n` is at backlog and its own text
records a trigger that has fired and a candidate-fix split, so it wants reading
before it is sized.

Do them as SEPARATE changes even though they are siblings. Each adds one format;
neither is a refactor of the format registry, and merging them into one "make the
registry extensible" change is how a two-item thread becomes a rewrite.

## Deliberate non-membership

The plugin INSTALL surface (`fleet/ensure_plugins.py` and its command helper) is
NOT in scope. It legitimately reads the same settings file for a different purpose,
and conflating it with the rewrite walk is the false-negative trap above in reverse.

The pin-currency severity policy and the fan-out preflight that consumes these
records are separate concerns with their own contract sections; this thread changes
what the walk COVERS, not how consumers grade what it returns.
