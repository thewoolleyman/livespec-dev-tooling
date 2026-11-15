"""Function bindings and call-site arguments for flake-retry root terms."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from functools import partial

from livespec_dev_tooling._flake_retry_parameters import Thunk, fixture_name, parameter_sites
from livespec_dev_tooling._flake_retry_root_terms import (
    NOT_ROOTED,
    Key,
    RootTerm,
    TermContext,
    base_term,
    binding_key,
    union,
)
from livespec_dev_tooling._flake_retry_scopes import Scope, owning_scope

__all__: list[str] = ["function_sites"]


def _returned_term(*, scope: Scope, context: TermContext) -> RootTerm:
    """What a function returns or yields, read in the function's own scope."""
    return union(
        terms=(
            base_term(expression=value, context=context)
            for value in context.index.returns.get(id(scope), [])
        )
    )


def _argument_term(
    *,
    function: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
    position: int,
    context: TermContext,
) -> RootTerm:
    """The values passed to a directly-called helper parameter in this module."""
    if isinstance(function, ast.Lambda):
        return NOT_ROOTED
    outer = context.index.scope_of[id(function)]
    values = [
        call.args[position]
        for call in context.index.nodes
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == function.name
        and len(call.args) > position
        and owning_scope(
            name=call.func.id, scope=context.index.scope_of[id(call)], index=context.index
        )
        is outer
    ]
    return union(terms=(base_term(expression=value, context=context) for value in values))


def function_sites(
    *, function: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda, context: TermContext
) -> Iterator[tuple[Key, Thunk]]:
    """Yield root terms for a function's return value, fixture and parameters."""
    body = function.body if isinstance(function.body, list) else [function.body]
    inner = context.index.scope_of[id(body[0])]
    outer = context.index.scope_of[id(function)]
    if not isinstance(function, ast.Lambda):
        returned = partial(_returned_term, scope=inner, context=context)
        yield binding_key(name=function.name, scope=outer, context=context), returned
        if outer.is_class:
            yield ("attribute", function.name), returned
        fixture = fixture_name(function=function)
        if fixture is not None:
            yield ("fixture", fixture), returned
    yield from parameter_sites(
        function=function,
        in_class=outer.is_class,
        key_of=lambda name: binding_key(name=name, scope=inner, context=context),
        context=context,
    )
    arguments = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
    for position, parameter in enumerate(arguments):
        yield (
            binding_key(name=parameter.arg, scope=inner, context=context),
            partial(_argument_term, function=function, position=position, context=context),
        )
