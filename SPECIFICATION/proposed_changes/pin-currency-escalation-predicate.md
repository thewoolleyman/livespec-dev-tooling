---
topic: pin-currency-escalation-predicate
author: claude-opus-5
created_at: 2026-07-31T06:48:44Z
---

## Proposal: A can't-parse pin file is a finding, and staleness partitions exhaustively

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Two amendments to the pin-currency contract, batched because they are one
question arriving twice (`livespec-dev-tooling-vt61`): a pin-currency row must
not report PASS for a state it could not evaluate, and it must not report
NORMAL OPERATION for a state in which the self-heal mechanism never ran at all.

1. §"Pin autodiscovery rules" — narrow the ratified unrecognized-format
   tolerance to what it means: a format the walk does not RECOGNIZE. A file at a
   KNOWN pin-format path that the walk cannot PARSE is a distinct outcome, and
   its trace MUST NOT be droppable by a consumer.
2. §"Pin-currency severity policy" — the escalation predicate MUST partition
   staleness EXHAUSTIVELY. Today it names only the "fired and could not land"
   failure mode; the "never fired" mode — the worse of the two — is classified
   as normal operation for an unbounded time.

### Motivation

**The measured facts, both from live incidents rather than from reasoning.**

On 2026-07-30 a bare `returns` import in a `python -m` entry point broke the
`livespec-dev-tooling` release fan-out. Seven of eight members sat at `v1.8.4`
while this repo released through `v1.12.0`. The three pin-currency rows FIRED,
correctly and continuously, for seven hours, naming the exact file and the exact
stale ref — and stopped nothing. At the time of writing, the `livespec` v0.21.1
fan-out published 2026-07-30T14:04Z is STILL unrepaired: seven of eight siblings
carry `.livespec.jsonc` `compat.pinned` at `v0.21.0`, no bump PR exists in any
member, and the central sweep exits `passed` with `blind_rows: 0`.

**The cause is the escalation PREDICATE, not the severity.** Two claims recorded
in `livespec-dev-tooling-0j3i` are retracted, having been re-measured against the
code on master `cb81910`:

- "All three rows are registered via `_warning_committed_file_row`, so every
  finding is `severity=warning`" is FALSE. `_warning_committed_file_row` and
  `_manual_committed_file_row` are behaviourally identical and neither sets
  severity; severity comes from each row's own `RowFinding(severity=...)`, and
  `_rows_pin_currency._pin_currency_outcome` already escalates via
  `severity="error" if ctx.filter_consuming_preflight else "warning"`. The
  lane-scoped escalation `vt61` recommends ALREADY EXISTS, is wired, and matches
  the ratified text. No severity change is proposed here.
- "No row covers the `pyproject.toml` `[tool.uv.sources]` dev-tooling pin for
  CURRENCY" is FALSE. `assert_dev_tooling_pin` → `_freshness_outcome` compares
  that pin to the latest release and escalates identically. The deciding pin IS
  covered, and this section already names it as one of four evaluated formats.

What is actually true is narrower and worse. **All four rows escalate on exactly
one condition — `persisting_bump_pr_number(...) is not None`** — that is, stale
AND a bump PR for the latest release is ALREADY OPEN. The ratified text calls
that "the mechanism fired and could not land", which is accurate. But a stale pin
with NO open bump PR is currently classified as "normal operation — the
minutes-long window between a release and its bump PR merging", with no time
component and no release-distance component. **The 2026-07-30 outage's state was
exactly that.** The module that broke the fan-out runs at
`.github/actions/bump-pin-rewrite/action.yml:364`; `Open auto-merge PR` is at
line 463, four steps later. A failure there means **no PR is ever opened** — so
the outage could never enter the escalating class at all, whatever severity that
class carried.

Given staleness, the two modes are exhaustive: a bump PR for the latest release
is open, or it is not. The predicate names only the first, and the second is the
one that produced both incidents.

**And the data a bounded predicate needs is already fetched and discarded.**
`_rows_pin_currency._latest_release_tag` and `_rows_files._latest_dev_tooling_tag`
both call `repos/<owner>/<repo>/releases/latest` and read only `tag_name`. The
same payload carries `published_at`. A release-age component therefore requires no
new API call and introduces no local state: the age is derived from the release's
own publish time, so every evaluating context computes the same answer from the
same payload.

**The second amendment closes the same hole one layer down.** A pin-currency row
reports PASS for a member whose pin file it could not parse
(`livespec-dev-tooling-2j2l`, reproduced): the walk emits an in-band sentinel
record whose `pin_format` is the literal `"unrecognized"`,
`_rows_pin_currency._records_for` filters records by `pin_format`, the sentinel
matches no spec, and it is silently dropped — after which zero records reach the
staleness comparison and "no stale pins" renders as `RowPass()`. A member with a
truncated `.livespec.jsonc` and a member with no `.livespec.jsonc` at all are
indistinguishable at the row.

This section's own carrier never created that fail-open
(`livespec-dev-tooling-xhbp`): §"Pin autodiscovery rules" already says an
unrecognized format produces NO RECORD plus an annotation, and an annotation is
not something a row can silently drop. The impl chose an in-band sentinel record
instead, and a record is exactly the thing a consumer filters. The divergence is
resolved here in the spec's favour on that ground, and by distinguishing the two
inputs the current wording conflates: a format the walk does not RECOGNIZE
(genuine tolerance, ratified, unchanged) versus a file at a KNOWN pin-format path
that the walk cannot PARSE (a definitive property of the member's committed
bytes, and never a pass).

**Both costs are stated, because the reason the rows warn is real and must not be
dismissed as timidity.** Making these rows errors everywhere would block every PR
in an evaluating repo on a sibling's staleness — including the PR that would fix
it. That is the ordering trap in another spelling. This proposal therefore adds
NO severity lever, NO environment variable, and NO per-member exemption, and
changes no severity in any context: it keeps the EXISTING lane scoping verbatim
and only widens the set of conditions that reach it.

**Sequencing constraint, and it is load-bearing.** Implementing the escalation
half against today's fleet would red eight of nine members from an unrepaired
incident rather than from a policy defect (v034 carve-out 1). The `livespec`
v0.21.1 fan-out MUST be re-dispatched and the live sweep re-run BEFORE the
predicate is flipped in code.

### Proposed Changes

**1. §"Pin autodiscovery rules" — separate can't-PARSE from unrecognized.**

The closing tolerance paragraph currently reads:

> The walk MUST be tolerant of missing files — a consumer without a
> `.vendor.jsonc` simply yields no `.vendor.jsonc`-format records. The walk MUST
> also be tolerant of pin formats it does not recognize; an unrecognized format
> produces no record and a workflow annotation noting the unrecognized file for
> human inspection.

Retain both tolerances and add the distinction the current wording elides:

The walk MUST continue to be tolerant of MISSING files and of pin formats it does
not RECOGNIZE, and an unrecognized format MUST continue to produce no record plus
a human-visible annotation naming the file.

A file present at a path a KNOWN pin format claims, whose contents the walk cannot
PARSE, is NOT an unrecognized format and MUST NOT be reported as one. It MUST be
surfaced as a distinct, typed outcome that a consumer CANNOT silently drop. It
MUST NOT be carried as an in-band record in the walk's normal record stream: a
record is the one carrier a record-filtering consumer discards without a decision,
which is what made an unparseable pin file read as a passing row. The walk MUST
NOT infer a pin's value, absence, or currency from a file it could not parse.

**2. §"Pin-currency severity policy" — the escalation predicate partitions
staleness exhaustively.**

Replace the first two bullets of the two-tier policy. The two bullets currently
read (abridged): plain staleness is a WARNING because "a pin behind the latest
release with no open bump PR for that release is normal operation — the
minutes-long window between a release and its bump PR merging"; and a PERSISTING
gap — stale AND its bump PR already open — is an ERROR only where a per-member
remedy exists.

The replacement MUST state that, given a stale pin, exactly two states are
possible and BOTH are evaluated:

- **Fired and could not land.** A bump PR for the latest release is OPEN. The
  mechanism ran and the PR is the durable, stateless record that it could not
  land. This class escalates at ANY release age, exactly as ratified today —
  unchanged.
- **Never fired.** NO bump PR for the latest release is open. This is the
  ABSENCE of the self-heal mechanism having run, and it is the worse of the two
  states, because nothing exists that would eventually land. It MUST escalate
  once the latest release is older than a bounded SETTLE WINDOW.

Within the settle window, a stale pin with no open bump PR remains a WARNING —
this preserves the ratified reasoning verbatim, now bounded rather than unbounded:
the window between a release publishing and its bump PR opening and merging is
normal operation, and it is finite.

The settle window MUST be measured from the LATEST RELEASE's own publish time as
reported by the release payload the row already fetches, NOT from any local clock
reading of when the staleness was first observed. This keeps the predicate
STATELESS: every evaluating context — per-PR CI, the scheduled central sweep, the
fan-out preflight — derives the same verdict from the same payload with no stored
history and no new API call.

The settle window is a RATIFIED CONSTANT of **two hours**, not a configurable
threshold. Two hours is roughly an order of magnitude longer than a healthy
fan-out's dispatch-to-PR-open latency (seconds to a minute) and comfortably
longer than a slow member's PR CI, while both measured incidents — seven hours
and sixteen hours — clear it with a wide margin. A member whose PR CI legitimately
exceeds the window has an OPEN bump PR and is therefore in the first class, which
this window does not govern. There MUST be no lever, environment variable, or
per-member exemption that lengthens, shortens, or disables it; a settable window
is a severity lever wearing a different name.

The asymmetry between the two classes is DELIBERATE and MUST be stated as such: an
open bump PR is positive evidence the mechanism already ran, so it needs no
settling period, whereas the absence of a PR is genuinely ambiguous during
propagation and is bounded rather than instant.

**Both classes are subject to the EXISTING context scoping, unchanged.** A finding
in either class escalates to error ONLY in a context that can act on it per member
— the release fan-out preflight, whose per-member verdicts the dispatch-matrix
filter consumes — and is reported at WARNING severity in every other evaluating
context, per-PR CI and the scheduled central sweep alike. The diagnostic is
identical at both severities and names the member, the pin format, the stale
value, the latest release, and which of the two classes applies (the open bump PR
number, or that no bump PR exists and the release's age).

**3. §"Pin-currency severity policy" — a can't-parse is a finding, a can't-read
is not.**

The existing bullet "A can't-read never escalates" is retained unchanged and MUST
be read as covering exactly what it says: an unreadable PR list, release list, or
tree — a transport or environment failure, possibly transient, not attributable to
the member.

Add its counterpart: a pin file the walk found and could NOT PARSE is NOT a
can't-read. It is a definitive, reproducible property of the member's committed
bytes, and the row MUST report it as a finding rather than as a pass or a skip.
It carries the same context scoping as the staleness classes — error in the
filter-consuming fan-out preflight, warning elsewhere — which is the correct
remedy shape, since a member whose committed pin file does not parse is a member
whose bump rewrite cannot be applied and which the fan-out should exclude by
name rather than dispatch to blindly.

A pin-currency row MUST NOT return a passing outcome for a pin format it did not
successfully evaluate. Absence of records is a pass ONLY when the walk completed
and genuinely found no pin of that format.
