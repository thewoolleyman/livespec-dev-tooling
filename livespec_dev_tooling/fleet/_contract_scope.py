"""Declared-narrowing guard for the central fleet obligation table.

A row's `applies_to` decides WHO an obligation is asserted against, and until
this module existed it decided that SILENTLY. `agent-instruction-surface` was
registered at `TEMPLATE_BORN_CLASSES` — one of the seven `REPO_CLASSES` —
while the clause it enforces (livespec `SPECIFICATION/contracts.md` section
"Fleet agent-instruction core") names every governed repo, `livespec-dev-tooling`
and `livespec-runtime` explicitly among them. The row then reported PASS,
because it was green over the two members it could see, while eight of the ten
manifest members breached the obligation. Nothing in the run said "this verdict
covers 2 of 10" (livespec-dev-tooling-thw26i).

That defect had TWO halves and this module addresses the second one, which is
the one that generalizes. The first half is that one row is scoped too
narrowly. The second is that NOTHING MADE THE NARROWING VISIBLE: an
`applies_to` naming a subset is indistinguishable, at a glance and to every
engine, from an `applies_to` naming the whole fleet on purpose. The corroborating
evidence is in the table itself — the sibling `decision-authority-section` row
carries a comment justifying `ALL_CLASSES` "unlike the sibling
agent-instruction-surface row above", so the file already stated the principle
the narrow row violated, named the narrow row while doing it, and left it. A
comment cannot fail; a guard can.

So: EVERY row whose `applies_to` omits a class MUST declare that exclusion here,
and the declaration must say which of two things it is.

`CLAUSE_SCOPED` — the ratified clause itself names a narrower population, so the
row and the clause agree. `copier-answers` asserts that a copier scaffold's
answers file is committed, and only `impl-plugin` is scaffolded from the
template; `dev-tooling-pin` cannot bind the repo that publishes the pin.

`ADOPTION_DEBT` — the clause names MORE classes than the row runs against. The
row is narrower than the obligation it enforces, and the gap is unlanded
ADOPTION, not a scoping decision. This kind is a debt with a stated
measurement, never a permanent exemption, and it is the honest spelling of a
state this fleet reaches on purpose: `plan/rop-railway-enforcement/` carries
the standing constraint "Do not arm the check anywhere" because `46c5dab` armed
a check ahead of adoption, five repos went red, and `f4247110` reverted it.
Widening `applies_to` IS the arming. The debt is what the widening is waiting
on, written down and re-measurable, instead of a silent frozenset.

An `ADOPTION_DEBT` declaration therefore REQUIRES a `measured` field, because
the sequencing rule this fleet enforces is stated in offender counts on
origin/master rather than in intentions, and a debt recorded without one cannot
be discharged by anything but a fresh guess.

The guard is `undeclared_narrowings`, driven over the live table by
`tests/livespec_dev_tooling/fleet/test_contract_scope.py`, so a row narrowed
without a declaration — or a declaration that has drifted from the exclusion it
describes, in EITHER direction — fails `just check` rather than passing
quietly.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_dev_tooling.fleet._contract_classes import ALL_CLASSES
from livespec_dev_tooling.fleet._contract_model import ObligationRow

__all__: list[str] = [
    "ADOPTION_DEBT",
    "CLAUSE_SCOPED",
    "ROW_SCOPE_DECLARATIONS",
    "RowScopeDeclaration",
    "adoption_debt_row_ids",
    "undeclared_narrowings",
]

# The clause and the row agree: the ratified obligation itself names a
# population smaller than the fleet.
CLAUSE_SCOPED = "clause-scoped"
# The clause names MORE than the row runs against. A debt, not an exemption.
ADOPTION_DEBT = "adoption-debt"

_KINDS = frozenset({CLAUSE_SCOPED, ADOPTION_DEBT})


@dataclass(frozen=True, kw_only=True)
class RowScopeDeclaration:
    """Why one obligation row is asserted against less than the whole fleet.

    `excluded` is asserted against the row's ACTUAL exclusion set rather than
    trusted, so a later `applies_to` edit that widens or narrows the row
    without revisiting its reason is a finding. A declaration that merely
    tracked the row would document nothing.

    `measured` is the origin/master offender count behind an `ADOPTION_DEBT`,
    with its date. It is required for that kind and meaningless for the other.
    """

    row_id: str
    excluded: frozenset[str]
    kind: str
    clause: str
    reason: str
    measured: str = ""


ROW_SCOPE_DECLARATIONS: tuple[RowScopeDeclaration, ...] = (
    RowScopeDeclaration(
        row_id="workflow-release-dispatch",
        excluded=frozenset({"console"}),
        kind=CLAUSE_SCOPED,
        clause='livespec-dev-tooling SPECIFICATION/contracts.md section "Bump-pin policy"',
        reason=(
            "The console is a pin CONSUMER (livespec-oq9w Option B): it produces no "
            "consumable release for a downstream repo to pin, so there is no producer "
            "shim for it to ship. It still carries both RECEIVING shims and the "
            "dev-tooling pin, so the exclusion is one row wide, not a plane."
        ),
    ),
    RowScopeDeclaration(
        row_id="copier-answers",
        excluded=ALL_CLASSES - {"impl-plugin"},
        kind=CLAUSE_SCOPED,
        clause=(
            "livespec SPECIFICATION/non-functional-requirements.md section "
            '"Shared content sync — copier template"'
        ),
        reason=(
            "The obligation is that a copier scaffold's `.copier-answers.yml` is "
            "committed, and only `impl-plugin` is scaffolded from the template. This is "
            "the ONE row where how a repo was born is genuinely the criterion: a class "
            "with no copier scaffold has no answers file to commit, so the excluded "
            "classes cannot breach the obligation rather than being spared it."
        ),
    ),
    RowScopeDeclaration(
        row_id="dev-tooling-pin",
        excluded=frozenset({"enforcement-suite"}),
        kind=CLAUSE_SCOPED,
        clause='livespec-dev-tooling SPECIFICATION/contracts.md section "Bump-pin policy"',
        reason=(
            "livespec-dev-tooling is the repo the pin POINTS AT; it cannot carry a "
            "`[tool.uv.sources]` tag pin of itself. Every other class, the console "
            "included, does."
        ),
    ),
    RowScopeDeclaration(
        row_id="agent-instruction-surface",
        excluded=ALL_CLASSES - {"impl-plugin"},
        kind=ADOPTION_DEBT,
        clause='livespec SPECIFICATION/contracts.md section "Fleet agent-instruction core"',
        reason=(
            "THE CLAUSE NAMES EVERY GOVERNED REPO — 'livespec itself, every "
            "livespec-orchestrator-* plugin, livespec-dev-tooling, livespec-runtime, and "
            "every future sibling' — so the six excluded classes are IN the obligation "
            "and out of the row. `TEMPLATE_BORN_CLASSES` is not a scoping decision here: "
            "the obligation is not about how a repo was scaffolded, which is exactly what "
            "the sibling decision-authority-section row's comment says while naming this "
            "row. The row is already ARMED at error severity, so widening `applies_to` IS "
            "the arming, in one commit, with no disarmed intermediate to fall back to — "
            "the `46c5dab` / `f4247110` shape. Widen it when, and only when, `measured` "
            "reads zero (livespec-dev-tooling-thw26i)."
        ),
        measured=(
            "2026-09-06, all ten .livespec-fleet-manifest.jsonc members read on their own "
            "origin/master, BOTH halves of the predicate (the five REQUIRED_AGENTS_HEADINGS "
            "AND the beads-access-guard registration in .claude/settings.json): 8 of 10 "
            "fail. Passing: livespec-orchestrator-beads-fabro, livespec-orchestrator-git-jsonl "
            "— the two impl-plugin members the row already covers. Failing: livespec (5/5 "
            "headings, NO guard), livespec-dev-tooling (1/5, no guard), livespec-driver-claude "
            "(2/5), livespec-driver-codex (1/5), livespec-driver-pi (1/5), livespec-runtime "
            "(1/5), livespec-console-beads-fabro (2/5), livespec-overseer (2/5). STATE THE "
            "MATCHER NEXT TO THE COUNT: a headings-only measurement returns SEVEN and is "
            "wrong — livespec passes the headings and fails the guard."
        ),
    ),
)


def adoption_debt_row_ids(
    *, declarations: tuple[RowScopeDeclaration, ...] = ROW_SCOPE_DECLARATIONS
) -> tuple[str, ...]:
    """Row ids whose `applies_to` is narrower than the clause they enforce."""
    return tuple(d.row_id for d in declarations if d.kind == ADOPTION_DEBT)


def undeclared_narrowings(
    *,
    rows: tuple[ObligationRow, ...],
    declarations: tuple[RowScopeDeclaration, ...] = ROW_SCOPE_DECLARATIONS,
) -> tuple[str, ...]:
    """Findings for every narrowing this table does not honestly declare.

    Empty when every narrowed row carries a well-formed declaration matching
    its actual exclusion set. Drift is caught in BOTH directions: a row
    narrowed without a declaration, and a declaration describing an exclusion
    the row no longer has.
    """
    declared = {declaration.row_id: declaration for declaration in declarations}
    excluded_by_row = {row.row_id: ALL_CLASSES - row.applies_to for row in rows}
    findings: list[str] = []
    for row_id, excluded in excluded_by_row.items():
        if not excluded:
            continue
        declaration = declared.get(row_id)
        if declaration is None:
            findings.append(
                f"{row_id}: applies_to omits {_render(classes=excluded)} with no entry in "
                "ROW_SCOPE_DECLARATIONS — say whether the clause scopes it or the row is "
                "narrower than its clause"
            )
            continue
        findings.extend(_declaration_findings(declaration=declaration, excluded=excluded))
    findings.extend(
        f"{declaration.row_id}: ROW_SCOPE_DECLARATIONS declares an exclusion, but no row of "
        "that id is narrowed — the row was widened, renamed or removed, so delete the "
        "declaration rather than leaving it to describe nothing"
        for declaration in declarations
        if not excluded_by_row.get(declaration.row_id)
    )
    return tuple(findings)


def _declaration_findings(
    *, declaration: RowScopeDeclaration, excluded: frozenset[str]
) -> list[str]:
    """Findings for one declaration measured against the row's real exclusion."""
    findings: list[str] = []
    if declaration.excluded != excluded:
        findings.append(
            f"{declaration.row_id}: declared exclusion {_render(classes=declaration.excluded)} "
            f"does not match the row's actual {_render(classes=excluded)} — the scope moved "
            "and its recorded reason did not"
        )
    if declaration.kind not in _KINDS:
        findings.append(
            f"{declaration.row_id}: unknown scope kind {declaration.kind!r} — use "
            f"{CLAUSE_SCOPED!r} or {ADOPTION_DEBT!r}"
        )
    if not declaration.reason.strip():
        findings.append(f"{declaration.row_id}: scope declaration carries no reason")
    if declaration.kind == ADOPTION_DEBT and not declaration.measured.strip():
        findings.append(
            f"{declaration.row_id}: an {ADOPTION_DEBT!r} declaration must carry `measured` — "
            "the offender count on origin/master, with its date and the matcher it used, is "
            "what the widening is gated on"
        )
    return findings


def _render(*, classes: frozenset[str]) -> str:
    return ", ".join(sorted(classes))
