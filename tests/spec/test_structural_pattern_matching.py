"""§"Structural pattern matching" — `case _: assert_never(<subject>)`, argument included.

The section requires every `match` over a closed sum type to terminate with
`case _: assert_never(<subject>)`, "so pyright's exhaustiveness check fires".
The shipped `assert_never_exhaustiveness` check enforces the STRUCTURE of
that arm — final case is a wildcard, body is a single `assert_never(...)`
call — and stops one step short of the section, in writing: "Subsequent
cycles can tighten to verify the call's argument equals the match subject."
Those cycles have not run, so `<subject>` is unenforced. This file enforces
it.

The gap is not cosmetic, because the argument is the entire mechanism. What
makes the arm work is that pyright NARROWS the subject to `Never` once every
variant is handled, and `assert_never` accepts only `Never` — so an
unhandled variant becomes a type error at that call. Point the call at
something else (a loop variable, a neighbouring value, a stale name left
behind when the subject was renamed) and the narrowing is computed for a
value nobody is asking about. The arm still looks right, the shipped check
still passes, ruff still passes — and pyright checks exhaustiveness of the
wrong expression, which is to say it checks nothing.

The coverage configuration is the reason the failure is invisible at
runtime too: `[tool.coverage.report].exclude_also` carries `case _:`
precisely because these arms are unreachable by mandate (the sibling
§"Code coverage thresholds" spells that out), so an arm calling
`assert_never` on the wrong value is never executed and never measured. The
comparison here is textual — `ast.unparse` of the argument against
`ast.unparse` of the subject — which is the strictest reading available
statically and the one the section's `<subject>` placeholder states.
"""

from __future__ import annotations

import ast
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / "livespec_dev_tooling"

_ASSERT_NEVER = "assert_never"
_SKIPPED_PARTS = ("_vendor", "__pycache__")


def _package_modules() -> list[Path]:
    """Every first-party `.py` module under the shipped package."""
    return sorted(
        path
        for path in _PACKAGE_DIR.rglob("*.py")
        if not any(part in _SKIPPED_PARTS for part in path.relative_to(_REPO_ROOT).parts)
    )


def _match_statements() -> list[tuple[Path, ast.Match]]:
    """Every `match` statement in the package, with the module it lives in."""
    return [
        (module_path, node)
        for module_path in _package_modules()
        for node in ast.walk(ast.parse(module_path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Match)
    ]


def _terminal_assert_never_arguments(*, node: ast.Match) -> list[str]:
    """The rendered arguments of the `assert_never(...)` this `match` ends with.

    Empty when the final case is not the mandated `case _: assert_never(x)`
    arm at all — that structural half is the shipped check's, and reporting
    it as "no argument" is the honest rendering of "there is no such call".
    """
    wildcards = [
        case
        for case in node.cases[-1:]
        if isinstance(case.pattern, ast.MatchAs) and case.pattern.pattern is None
    ]
    bodies = [case.body[0] for case in wildcards if len(case.body) == 1]
    calls = [
        statement.value
        for statement in bodies
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
    ]
    named = [
        call
        for call in calls
        if ast.unparse(call.func).rsplit(".", maxsplit=1)[-1] == _ASSERT_NEVER
    ]
    return [ast.unparse(call.args[0]) for call in named if len(call.args) == 1]


def test_every_match_asserts_exhaustiveness_over_its_own_subject() -> None:
    """The `assert_never` argument IS the match subject, not merely some value."""
    statements = _match_statements()
    assert statements, (
        "the package must contain at least one `match` statement for this clause to "
        "bind — a scan that found none is a broken walk, not a compliant tree"
    )

    offenders = sorted(
        f"{module_path.relative_to(_REPO_ROOT)}:{node.lineno} "
        f"subject={ast.unparse(node.subject)!r} "
        f"assert_never={_terminal_assert_never_arguments(node=node)}"
        for module_path, node in statements
        if _terminal_assert_never_arguments(node=node) != [ast.unparse(node.subject)]
    )
    assert not offenders, (
        f'`non-functional-requirements.md` §"Structural pattern matching" requires '
        f"`case _: assert_never(<subject>)`, and the shipped check verifies only the "
        f"arm's SHAPE — its own docstring defers the argument to cycles that have not "
        f"run. The argument is the mechanism: pyright narrows the SUBJECT to `Never` "
        f"once every variant is handled, so a call pointed at anything else computes "
        f"that narrowing for a value nobody asked about and the exhaustiveness check "
        f"silently stops checking. The arm is coverage-excluded (`case _:`), so nothing "
        f"at runtime notices either; offenders={offenders}"
    )
