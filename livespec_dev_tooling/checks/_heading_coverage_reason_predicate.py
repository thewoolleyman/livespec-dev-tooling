"""_heading_coverage_reason_predicate — is a TODO `reason` an acknowledgment?

The ratified acknowledgment predicate of charter D4, plan
`fleet-heading-coverage-convergence` (epic `livespec-dev-tooling-0bse`), as
amended into this repository's `SPECIFICATION/non-functional-requirements.md`
at v064:

> The `reason` MUST acknowledge that a real test at the required tier is owed
> and MUST name nothing else. A `reason` asserting that the heading is not
> testable, is enforced elsewhere, or is prose without behavior MUST be
> rejected by `heading_coverage`. There is no non-testable category: a heading
> a repository believes has no behavior is a specification-structure defect to
> be fixed in the specification, never a coverage exemption.

WHY A PREDICATE AT ALL. The `reason` slot's ratified purpose (v009) was to
ACKNOWLEDGE the owed test. The 2026-09-06 fleet resolution inverted it into an
EXEMPTION: 373 rows across 11 repositories carrying wordings like *"No
independently testable assertion at runtime"*, and the gate accepted every one
because owned-`TODO`-with-a-reason is its legal state. The maintainer's ruling,
verbatim: *"there should be absolutely no cop-outs [...] There is absolutely no
reason that it should not be testable at some level, even if mocking/doubles
are used."* This module is the mechanical half of that answer; the sibling
`_heading_coverage_reason_guard` owns which of its findings a given run JUDGES,
and says so.

THE PREDICATE IS A CONJUNCTION, and both halves are load-bearing:

- NEGATIVE — the reason MUST NOT assert one of the three ratified cop-out
  families (not testable / enforced elsewhere / prose without behavior). Each
  family carries its own phrase table so the diagnostic can name WHICH claim it
  refused rather than emitting one undifferentiated verdict.
- POSITIVE — the reason MUST acknowledge an owed test at the required TIER: a
  tier word, an owed word, and a test word. The negative half alone would be a
  wording blocklist any new phrasing routes around; the positive half is what
  makes an acknowledgment the only passing shape.

⛔ THE TIER VOCABULARY IS RESTATED HERE RATHER THAN SHARED WITH
`_heading_coverage_tier_resolution`. That module's `_TIER_REASON_KEYWORDS` is
module-private and answers a DIFFERENT question — "does this `scenarios.md`
TODO acknowledge the integration-tier requirement", direction 4, which governs
`scenarios.md` alone. This predicate governs EVERY spec file and is strictly
stricter (tier AND owed AND test, minus the cop-out families). Importing a
private name across a module boundary is refused by `private_calls` and by
pyright's `reportPrivateUsage`; promoting one shared table would fuse two
questions that are ratified separately and may diverge (charter D9 retires this
one at zero and leaves direction 4 standing).

Output discipline: this module DECIDES and emits nothing — every diagnostic for
its findings is the guard sibling's, so `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) have nothing to ban here.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_dev_tooling.heading_coverage_debt import todo_rows

# Names in `__all__` mark this private sibling's public surface to its sole
# importer, `_heading_coverage_reason_guard.py`, so pyright's per-file analysis
# does not flag them unused across the package boundary.
__all__: list[str] = [
    "ReasonFinding",
    "reason_defect",
    "reason_findings",
]


# The three ratified cop-out families, each as (defect code, phrase table). The
# phrases are the wordings the 2026-09-06 fleet resolution actually produced
# (plan research `003`) plus their near neighbours; matching is on a lowered,
# whitespace-normalized reason, so casing and line wrapping do not evade them.
_COP_OUT_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "asserts-non-testability",
        (
            "no independently testable",
            "not independently testable",
            "no testable",
            "not testable",
            "untestable",
            "nothing to test",
            "cannot be tested",
            "can't be tested",
            "impossible to test",
            "no test is owed",
            "no test is possible",
        ),
    ),
    (
        "asserts-enforced-elsewhere",
        (
            "enforced by checks",
            "enforced by the check",
            "enforced elsewhere",
            "covered elsewhere",
            "asserted elsewhere",
            "rather than a test",
            "rather than a pytest test",
            "instead of a test",
        ),
    ),
    (
        "asserts-prose-without-behavior",
        (
            "orientation prose",
            "prose only",
            "purely prose",
            "descriptive prose",
            "narrative prose",
            "prose without behavior",
            "prose without behaviour",
            "no behavior",
            "no behaviour",
            "documentation only",
            "informational only",
            "non-normative",
        ),
    ),
)

# The positive half: an acknowledgment names the TIER the owed test sits at,
# says it is OWED, and says it is a TEST. All three must appear; each token
# family is a disjunction. `missing` in the diagnostic names the families that
# did not, so an author is told what to write rather than only what not to.
_ACKNOWLEDGMENT_TOKENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "tier",
        (
            "tier",
            "integration",
            "e2e",
            "consumer",
            "pyramid",
        ),
    ),
    (
        "owed",
        (
            "owed",
            "owes",
            "awaits",
            "awaiting",
            "pending",
            "replace todo",
            "will land",
            "lands",
            "landing",
            "must land",
            "is required",
            "are required",
            "to be written",
            "not yet written",
            "follows in",
        ),
    ),
    (
        "test",
        (
            "test",
            "proof",
            "coverage",
        ),
    ),
)

_UNACKNOWLEDGED = "does-not-acknowledge-an-owed-test"


@dataclass(frozen=True, kw_only=True)
class ReasonFinding:
    """One registry row whose TODO `reason` is not an acknowledgment.

    `entry` is carried whole rather than reduced to its key: the guard needs
    the row both to place it against `HEAD` (fingerprint) and to name it in the
    diagnostic. `defect` is the discriminator, `evidence` the operator-facing
    detail — the matched cop-out phrase, or the acknowledgment families the
    reason omitted. The two are separate so a diagnostic can name the cause
    without a reader parsing prose.
    """

    entry: dict[str, object]
    defect: str
    evidence: str


def _normalized(*, reason: str) -> str:
    """`reason` lowered with runs of whitespace collapsed to single spaces.

    Collapsing is what makes a phrase table survive the registry's real
    formatting: a reason wrapped across JSON-escaped newlines still reads as
    one sentence to a substring match.
    """
    return " ".join(reason.lower().split())


def _cop_out(*, normalized: str) -> tuple[str, str] | None:
    """The (family, matched phrase) `normalized` asserts, or `None`."""
    for defect, phrases in _COP_OUT_FAMILIES:
        for phrase in phrases:
            if phrase in normalized:
                return (defect, phrase)
    return None


def reason_defect(*, reason: str) -> tuple[str, str] | None:
    """The (defect code, evidence) in `reason`, or `None` when it acknowledges.

    The cop-out families are tested FIRST and short-circuit: a reason that both
    asserts non-testability and mentions a tier must be refused for the
    assertion it makes, not accepted for the vocabulary it happens to carry.
    """
    normalized = _normalized(reason=reason)
    asserted = _cop_out(normalized=normalized)
    if asserted is not None:
        return asserted
    missing = [
        family
        for family, tokens in _ACKNOWLEDGMENT_TOKENS
        if not any(token in normalized for token in tokens)
    ]
    if missing:
        return (_UNACKNOWLEDGED, "missing: " + ", ".join(missing))
    return None


def reason_findings(*, entries: list[dict[str, object]]) -> list[ReasonFinding]:
    """Every `test: "TODO"` row in `entries` whose `reason` is not an acknowledgment.

    A row with an absent, non-string, or blank `reason` is SKIPPED: that is
    `heading_coverage`'s direction 3 ("TODO registry entry missing reason"), and
    reporting one defect twice under two names leaves an author fixing the
    wrong thing.
    """
    out: list[ReasonFinding] = []
    for entry in todo_rows(rows=entries):
        reason = entry.get("reason")
        if not (isinstance(reason, str) and reason.strip()):
            continue
        defect = reason_defect(reason=reason)
        if defect is not None:
            out.append(ReasonFinding(entry=entry, defect=defect[0], evidence=defect[1]))
    return out
