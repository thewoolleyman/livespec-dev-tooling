"""Standard-library Result/IOResult railway used by the plugin-shipped hooks.

The Claude Code plugin installer copies ONLY `.claude-plugin/` into the install
cache (flattened to the plugin root) and ships NO `pyproject.toml`, `uv.lock`,
or virtualenv. Shipped hooks therefore execute under bare system `python3` with
no third-party packages importable — a module-scope `from returns.result import
...` raises `ModuleNotFoundError` BEFORE `main()`'s try/except can fail open,
and the hook denies nothing.

So the shipped hooks import this SIBLING module instead (plain `from _result
import ...`, resolved because Python puts the script's own directory on
`sys.path`). It re-implements, with the standard library alone, the narrow
dry-python/returns surface those hooks use: `Success` / `Failure` on the pure
rail, `IOSuccess` / `IOFailure` on the IO rail, and `.value_or(default=...)` to
collapse either rail to a plain value. `unwrap()` / `failure()` complete the
container contract and mirror the sibling `livespec-driver-codex` shim.

The IO rail is an ALIAS of the pure rail rather than a distinct container: the
hooks only ever collapse an IO rail through `.value_or`, so the extra `IO`
wrapper dry-python interposes carries no behavior here.

The repo-root `_vendor/returns` (the real dry-python/returns) stays in place for
the project-local, NEVER-shipped `.claude/hooks/livespec_footgun_guard.py`,
which runs from this checkout where that path exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, NoReturn, TypeAlias, TypeVar

__all__: list[str] = ["Failure", "IOFailure", "IOResult", "IOSuccess", "Result", "Success"]

_T = TypeVar("_T")
_E = TypeVar("_E")
_D = TypeVar("_D")


@dataclass(frozen=True)
class Success(Generic[_T]):
    """The success rail: carries a value that `value_or` always returns."""

    _inner_value: _T

    def unwrap(self) -> _T:
        return self._inner_value

    def failure(self) -> NoReturn:
        raise RuntimeError("Success container has no failure value")

    def value_or(self, *, default: object) -> _T:
        _ = default
        return self._inner_value


@dataclass(frozen=True)
class Failure(Generic[_E]):
    """The failure rail: carries an error; `value_or` returns the default."""

    _inner_value: _E

    def unwrap(self) -> NoReturn:
        raise RuntimeError("Failure container has no success value")

    def failure(self) -> _E:
        return self._inner_value

    def value_or(self, *, default: _D) -> _D:
        return default


Result: TypeAlias = Success[_T] | Failure[_E]

IOResult: TypeAlias = Success[_T] | Failure[_E]
IOSuccess = Success
IOFailure = Failure
