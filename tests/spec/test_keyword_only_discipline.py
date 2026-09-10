"""The `non-functional-requirements.md` §"Keyword-only arguments" dataclass rule.

The section states three rules, and they are NOT enforced by the same thing:

- "Every function definition under `livespec_dev_tooling/` MUST use the `*`
  separator" — the shipped `keyword_only_args` check, a `just check` target
  (its wiring is asserted once, for every shipped slug at once, by
  `tests.spec.test_definition_of_done_gates`).
- "`match` destructures of project-owned dataclasses MUST use the keyword
  form" — the shipped `match_keyword_only` check, likewise a target.
- "Dataclasses MUST use `dataclass(kw_only=True)`" — **nothing**. That clause
  is unenforced, and the shipped check says so about itself: `keyword_only_args`
  records "Subsequent cycles widen to `@dataclass(frozen=True, kw_only=True,
  slots=True)` verification when fixtures demand it", and those cycles have not
  run. Reading the two def-level gates as covering the section leaves the
  dataclass clause covered by a check that explicitly declines it.

So this file is that clause's coverage, and it is asserted directly over the
package's AST rather than through a check that does not make the claim.

The clause is load-bearing for the same reason the `*` separator is: a
positionally-constructible dataclass is one whose call sites silently permute
when a field is inserted, reordered, or renamed — and for a frozen record of
diagnostics (a path and a detail, both `str`) the permutation type-checks,
so neither pyright nor the suite convicts it. `kw_only=True` makes that
mistake a `TypeError` at the call, which is the only point at which it is
still cheap.

Scope is the package, matching the section's own scope ("under
`livespec_dev_tooling/`"), with `_vendor/` excluded: vendored third-party code
is not this repository's to shape.
"""

from __future__ import annotations

import ast
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / "livespec_dev_tooling"

_DATACLASS_DECORATOR = "dataclass"
_KW_ONLY_KEYWORD = "kw_only"

# Directory names whose contents are not this repository's code to shape.
_SKIPPED_PARTS = ("_vendor", "__pycache__")


def _package_modules() -> list[Path]:
    """Every first-party `.py` module under the package the section scopes."""
    return sorted(
        path
        for path in _PACKAGE_DIR.rglob("*.py")
        if not any(part in _SKIPPED_PARTS for part in path.relative_to(_REPO_ROOT).parts)
    )


def _is_dataclass_decorator(*, decorator: ast.expr) -> bool:
    """True when `decorator` is `dataclass`, bare or called, plain or dotted."""
    named = decorator.func if isinstance(decorator, ast.Call) else decorator
    return ast.unparse(named).rsplit(".", maxsplit=1)[-1] == _DATACLASS_DECORATOR


def _declares_kw_only(*, decorator: ast.expr) -> bool:
    """True when the decorator passes `kw_only=True` explicitly.

    A BARE `@dataclass` (not a call) carries no keywords and is therefore a
    violation, which is the correct verdict: it is the positional spelling.
    """
    keywords = decorator.keywords if isinstance(decorator, ast.Call) else []
    return any(
        keyword.arg == _KW_ONLY_KEYWORD and ast.unparse(keyword.value) == "True"
        for keyword in keywords
    )


def _decorated_classes(*, module_path: Path) -> list[tuple[str, ast.expr]]:
    """Each `(class name, decorator)` pair in one module, in source order."""
    parsed = ast.parse(module_path.read_text(encoding="utf-8"))
    return [
        (node.name, decorator)
        for node in ast.walk(parsed)
        if isinstance(node, ast.ClassDef)
        for decorator in node.decorator_list
    ]


def test_every_dataclass_under_the_package_is_keyword_only() -> None:
    """No `@dataclass` in the package leaves its fields positionally constructible."""
    decorated = [
        (module_path, class_name, decorator)
        for module_path in _package_modules()
        for class_name, decorator in _decorated_classes(module_path=module_path)
    ]
    dataclasses_found = [
        (module_path, class_name, decorator)
        for module_path, class_name, decorator in decorated
        if _is_dataclass_decorator(decorator=decorator)
    ]
    assert dataclasses_found, (
        "the package must define at least one dataclass for this clause to bind — a scan "
        "that found none is a broken walk, not a compliant tree"
    )

    offenders = sorted(
        f"{module_path.relative_to(_REPO_ROOT)}::{class_name}"
        for module_path, class_name, decorator in dataclasses_found
        if not _declares_kw_only(decorator=decorator)
    )
    assert not offenders, (
        f'`non-functional-requirements.md` §"Keyword-only arguments" requires '
        f"`dataclass(kw_only=True)` on every dataclass under `livespec_dev_tooling/`, and "
        f"no shipped check enforces it — a positionally-constructible record silently "
        f"permutes its call sites when a field is inserted or reordered, and where the "
        f"fields share a type the permutation still type-checks; offenders={offenders}"
    )
