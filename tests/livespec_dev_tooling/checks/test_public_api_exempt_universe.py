"""The exempt-set assembly, pinned once so a second copy of it cannot drift silently.

`public_api_result_typed._scan` used to assemble the public and exempt universes
inline, and the armed re-derivation of that scan — the measurement this fleet uses
to decide which modules are worth converting — was written by COPYING those lines.
The copy went stale the day a third `total |= …` contribution landed: the
re-derivation reported `livespec-dev-tooling` at 18 offenders instead of 3, FIFTEEN
of them phantoms, and a phantom offender is indistinguishable from a real one.

So the assembly now lives in one module with two callers, and this file is what
stops the extraction from being undone by accident. Two assertions, and BOTH are
required:

- **THE PIN** — one fixture, one exact answer, for both sets. Every one of the FIVE
  readers is uniquely load-bearing in it (verified by ablation while it was
  written): drop `repo_local_public_names` and the public set collapses to
  `exported` alone; drop `declared_public_names` and `exported` leaves it; drop
  `functions_without_expected_failure_mode` and `settle` leaves the exempt set; drop
  `declared_absence_names` and `absent` leaves it; drop `declared_variant_names` and
  `render` leaves it. A re-derivation that misses a contribution therefore cannot
  pass this test, which is the exact failure that cost the 15.
- **⚠️ THE DENOMINATOR** — the PUBLIC set is asserted too, not just the exempt one.
  An exempt set of three over an EMPTY public universe is byte-identical green to
  an exempt set of three over a correct one, and an assembly that silently computed
  nothing would satisfy the exempt half alone. The public assertion is what makes
  the exempt assertion mean something.

Both sets are asserted by EQUALITY rather than by membership or by count. A
membership assertion cannot see a contribution that was ADDED wrongly, and a count
cannot see two errors that cancel.
"""

from __future__ import annotations

import ast
from pathlib import Path

from livespec_dev_tooling.checks import public_api_result_typed
from livespec_dev_tooling.checks._public_api_exempt_universe import (
    resolve_public_and_exempt_names,
)
from livespec_dev_tooling.config import (
    Config,
    CrossRepoPublicApi,
    SingleMeaningVariant,
    TotalAbsenceReturn,
)

__all__: list[str] = []


_PRODUCE = Path("pkg/produce.py")
_CONSUME = Path("pkg/consume.py")

# One producer whose five functions make each of the five readers independently
# visible in the pin below — drop any one reader and the pinned answer moves:
#
# - `settle`   — no raise, no try, no I/O, not `X | None`: member 1 alone exempts
#                it, so it witnesses `functions_without_expected_failure_mode`.
# - `absent`   — `str | None`, which member 1's clause (e) REFUSES; only the
#                declared `total_absence_returns` entry can exempt it.
# - `render`   — its narrow handler RECORDS and continues, which livespec v186's
#                limb (iii) deliberately still convicts, so member 1 refuses it
#                too; only the declared `single_meaning_variants` pair exempts it.
# - `exported` — imported NOWHERE locally, so only the declared
#                `cross_repo_public_api` entry can make it public.
# - `emit`     — consumed locally and disqualified from member 1 by its `raise`:
#                PUBLIC, NOT exempt. It witnesses `repo_local_public_names`, which
#                is also what carries the other three into the public set, and it
#                is the fixture's control — without a name that nothing exempts, a
#                wiring bug that exempted the whole universe would still pass.
_PRODUCE_SOURCE = """from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = ["absent", "emit", "exported", "render", "settle"]


@dataclass(frozen=True, kw_only=True)
class Ok:
    note: str = ""


@dataclass(frozen=True, kw_only=True)
class Bad:
    message: str


Outcome = Ok | Bad


def emit(*, raw: str) -> str:
    if not raw:
        raise ValueError(raw)
    return raw


def settle(*, raw: str) -> str:
    return raw.upper()


def absent(*, raw: str) -> str | None:
    return raw or None


def render(*, raw: str) -> Outcome:
    bad: list[str] = []
    notes: list[str] = []
    for part in raw.split(","):
        try:
            notes.append(str(int(part)))
        except ValueError:
            bad.append(part)
    return Bad(message=",".join(bad)) if bad else Ok(note=",".join(notes))


def exported(*, raw: str) -> str:
    if not raw:
        raise ValueError(raw)
    return raw
"""

# The boundary crossing. `run` itself is never public here — nothing imports it —
# and member 1 refuses it too, because clause (d) propagates `emit`'s `raise`.
_CONSUME_SOURCE = """from __future__ import annotations

from pkg.produce import absent, emit, render, settle

__all__: list[str] = []


def run() -> None:
    _ = emit(raw="x")
    _ = settle(raw="x")
    _ = absent(raw="x")
    _ = render(raw="1")
"""

_SOURCES = {_PRODUCE: _PRODUCE_SOURCE, _CONSUME: _CONSUME_SOURCE}
_CONFIG = Config(
    cross_repo_public_api=(
        CrossRepoPublicApi(
            file=_PRODUCE, function="exported", reason="a governed sibling imports it"
        ),
    ),
    total_absence_returns=(
        TotalAbsenceReturn(
            file=_PRODUCE, function="absent", reason="the None is a legitimate absence"
        ),
    ),
    single_meaning_variants=(
        SingleMeaningVariant(file=_PRODUCE, union="Outcome", variant="Ok", meaning="exactly one"),
        SingleMeaningVariant(file=_PRODUCE, union="Outcome", variant="Bad", meaning="exactly one"),
    ),
)

# The readers the assembly wires together. `public_api_result_typed` must reach
# them THROUGH the extracted helper and never bind one itself again — and binding
# is what a copy needs, so the IMPORTS are what this file pins.
_ASSEMBLY_READERS = frozenset(
    {
        "repo_local_public_names",
        "declared_public_names",
        "functions_without_expected_failure_mode",
        "declared_absence_names",
        "declared_variant_names",
    }
)


def _imported_names(*, source: str) -> frozenset[str]:
    """Every name a module binds via `from … import …`, as the AST reports it.

    Read from the AST rather than by substring, because the module's PROSE names
    these readers — a text search cannot tell the docstring recording why the
    extraction happened from the call it forbids, and would fail on the comment
    explaining itself.
    """
    bound: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            bound.update(alias.asname or alias.name for alias in node.names)
    return frozenset(bound)


def test_the_assembly_pins_both_universes_for_a_known_fixture() -> None:
    """THE CONTROL. One fixture, one exact answer, both sets — denominator included."""
    resolved = resolve_public_and_exempt_names(config=_CONFIG, sources=_SOURCES)

    assert resolved.public == frozenset(
        {
            (_PRODUCE, "emit"),
            (_PRODUCE, "settle"),
            (_PRODUCE, "absent"),
            (_PRODUCE, "render"),
            (_PRODUCE, "exported"),
        }
    ), (
        f"the PUBLIC universe is the denominator — an exempt set measured over an empty "
        f"one is byte-identical green to one measured over a correct one; "
        f"public={sorted((str(p), n) for p, n in resolved.public)!r}"
    )
    assert resolved.exempt == frozenset(
        {(_PRODUCE, "settle"), (_PRODUCE, "absent"), (_PRODUCE, "render")}
    ), (
        f"each of member 1 (`settle`), member 2 (`absent`) and v183 (`render`) contributes "
        f"exactly one name here, so a dropped contribution cannot hide; "
        f"exempt={sorted((str(p), n) for p, n in resolved.exempt)!r}"
    )
    assert (_PRODUCE, "emit") not in resolved.exempt, (
        "`emit` raises, so nothing may exempt it — without this the pin above would "
        "also be satisfied by an assembly that exempted the whole universe"
    )


def test_the_check_holds_no_second_copy_of_the_assembly() -> None:
    """THE ANTI-DRIFT ASSERTION — one implementation, two callers, never two copies.

    The 15 phantom offenders came from a copy that was correct when written. Pinning
    the values alone cannot catch that: a copy passes every value assertion until the
    day the original gains a contribution. So this pins the STRUCTURE — that
    `public_api_result_typed` reaches the five readers only through the extracted
    helper — which is the property the value pin cannot express.
    """
    source_path = Path(str(public_api_result_typed.__file__))
    bound = _imported_names(source=source_path.read_text(encoding="utf-8"))

    assert "resolve_public_and_exempt_names" in bound, (
        f"`public_api_result_typed` must consume the extracted assembly; {source_path} "
        f"imports {sorted(bound)!r}"
    )
    assert not (bound & _ASSEMBLY_READERS), (
        f"`public_api_result_typed` still binds an assembly reader itself, which is what a "
        f"second copy of the construction needs: {sorted(bound & _ASSEMBLY_READERS)!r}"
    )
