"""Function parameters, and which of them pytest feeds from fixtures.

SPECIFICATION non-functional-requirements.md "Untouched-test retry": a plain
function's parameter names no repository path (livespec-dev-tooling-bob7iv).
A parameter that pytest feeds -- one of a test function, a fixture function
or a test-class method, other than `self` or `cls` -- is the fixture it
requests, or the values a `parametrize` mark supplies. A requested fixture
the whole closure cannot resolve is a doubt, so it keeps the test touched.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from functools import partial

from livespec_dev_tooling._flake_retry_root_terms import (
    NOT_ROOTED,
    Key,
    RootTerm,
    TermContext,
    base_term,
    through,
    union,
)

__all__: list[str] = ["PYTEST_FIXTURES", "fixture_name", "parameter_sites"]

PYTEST_FIXTURES = frozenset(
    (
        "cache capsys capsysbinary capfd capfdbinary caplog doctest_namespace monkeypatch "
        "pytestconfig record_property record_xml_attribute record_testsuite_property recwarn "
        "request subtests testdir pytester linecomp LineMatcher tmp_path tmp_path_factory "
        "tmpdir tmpdir_factory worker_id testrun_uid cov no_cover"
    ).split()
)

_Function = ast.FunctionDef | ast.AsyncFunctionDef
Thunk = Callable[[], RootTerm]


def _decorator_name(*, decorator: ast.expr) -> str:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return str(getattr(target, "id", getattr(target, "attr", "")))


def fixture_name(*, function: _Function) -> str | None:
    """The name a fixture is requested by; `*` when it cannot be read; None for a plain function."""
    for decorator in function.decorator_list:
        if _decorator_name(decorator=decorator) != "fixture":
            continue
        keywords = decorator.keywords if isinstance(decorator, ast.Call) else []
        for keyword in keywords:
            if keyword.arg == "name":
                value = keyword.value
                literal = isinstance(value, ast.Constant) and isinstance(value.value, str)
                return str(getattr(value, "value", "")) if literal else "*"
        return function.name
    return None


def _argument_names(*, names: ast.expr | None) -> list[str]:
    if isinstance(names, ast.Constant) and isinstance(names.value, str):
        return [part.strip() for part in names.value.split(",") if part.strip()]
    elements = names.elts if isinstance(names, ast.Tuple | ast.List) else []
    return [
        element.value
        for element in elements
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    ]


def _parametrized(*, function: _Function) -> dict[str, ast.expr]:
    """Each argument a `parametrize` mark on the function supplies, with the values it takes."""
    supplied: dict[str, ast.expr] = {}
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call) or _decorator_name(decorator=decorator) != (
            "parametrize"
        ):
            continue
        keywords = {keyword.arg: keyword.value for keyword in decorator.keywords}
        positional = [*decorator.args, None, None]
        names = positional[0] or keywords.get("argnames")
        values = positional[1] or keywords.get("argvalues")
        supplied.update(
            (name, values) for name in _argument_names(names=names) if values is not None
        )
    return supplied


def _fed_parameters(*, function: _Function, in_class: bool) -> list[ast.arg]:
    """The parameters pytest fills: a test's, a fixture's or a test-class method's."""
    if fixture_name(function=function) is None and not function.name.startswith("test"):
        return []
    arguments = function.args
    positional = [*arguments.posonlyargs, *arguments.args]
    decorators = {_decorator_name(decorator=decorator) for decorator in function.decorator_list}
    receiver = 1 if in_class and "staticmethod" not in decorators else 0
    return [*positional[receiver:], *arguments.kwonlyargs]


def _parameter_term(
    *, name: str, default: ast.expr | None, requested: bool, context: TermContext
) -> RootTerm:
    """A parameter is rooted through a fixture of its name, a rooted default or supplied value."""
    keys: set[Key] = {("fixture", name), ("fixture", "*")}
    if requested:
        keys.add(("request", name))
    named = through(*sorted(keys))
    if default is None:
        return named
    return union(terms=(named, base_term(expression=default, context=context)))


def _not_rooted() -> RootTerm:
    return NOT_ROOTED


def parameter_sites(
    *,
    function: _Function | ast.Lambda,
    in_class: bool,
    key_of: Callable[[str], Key],
    context: TermContext,
) -> Iterator[tuple[Key, Thunk]]:
    """Bind each parameter a function takes, keyed in the function's own scope."""
    arguments = function.args
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults: dict[str, ast.expr] = {
        parameter.arg: default
        for parameter, default in zip(
            reversed(positional), reversed(arguments.defaults), strict=False
        )
    }
    defaults.update(
        (parameter.arg, default)
        for parameter, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)
        if default is not None
    )
    fed: set[str] = set()
    if not isinstance(function, ast.Lambda):
        fed = {parameter.arg for parameter in _fed_parameters(function=function, in_class=in_class)}
        defaults.update(
            (name, values)
            for name, values in _parametrized(function=function).items()
            if name in fed and name not in defaults
        )
    for parameter in (*positional, *arguments.kwonlyargs):
        name = parameter.arg
        term = partial(
            _parameter_term,
            name=name,
            default=defaults.get(name),
            requested=name in fed and name not in defaults,
            context=context,
        )
        yield key_of(name), term
    for parameter in (arguments.vararg, arguments.kwarg):
        if parameter is not None:
            yield key_of(parameter.arg), _not_rooted
