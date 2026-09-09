"""Consumer-tier: the `SPECIFICATION/constraints.md` §"CLI shape" wrapper contract.

The constraint holds every check to the wrapper shape `contracts.md` §"CLI
surface" codifies, and its load-bearing half — the half a consumer's wiring
depends on and the half that has no other guard — is where configuration comes
FROM: zero positional arguments by default, and configuration read from the
working directory's `[tool.livespec_dev_tooling]` block rather than from
positional argv. A check that grew a required positional would break every
`just check-<slug>` recipe, every `run-check` matrix entry, and every commit
hook that invokes it, all of which name the module and nothing else.

`test_no_shipped_check_takes_configuration_through_positional_argv` asserts
that from three angles, because the contract can break at three different
layers:

- **The entry point.** Every canonical check's `main` is callable with NO
  arguments — the in-process expression of `python -m
  livespec_dev_tooling.checks.<slug>` with a bare argv.
- **The parser.** No check DECLARES a positional argument. A check may still
  read an OPTIONAL positional (the commit-msg path a git hook passes
  `red_green_replay`, whose absence selects the range-validating default), and
  the constraint's words are "zero positional arguments BY DEFAULT" — so what
  is asserted is that no check declares one it would REQUIRE.
- **The configuration source.** Two fixture trees differing ONLY in their
  `[tool.livespec_dev_tooling]` blocks resolve to different configurations
  while argv is held identical and bare. Holding argv fixed is what makes this
  a proof rather than a coincidence: the only thing that varied is the file.

The companion `test_every_argv_parsing_check_exits_zero_on_help` covers the
`--help` clause where it is observable — on the checks that build a parser at
all. The checks that ignore argv entirely accept `--help` by never rejecting
it, so there is nothing there for a test to distinguish.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.canonical_checks import canonical_check_slugs
from livespec_dev_tooling.config import load_config

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECKS_DIR = _REPO_ROOT / "livespec_dev_tooling" / "checks"
_CHECKS_NAMESPACE = "livespec_dev_tooling.checks"

# Parameter kinds that absorb whatever they are given, so they impose no
# requirement on a caller invoking `main()` with nothing.
_VARIADIC_KINDS = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)

# The bare argv a consumer's `python -m livespec_dev_tooling.checks.<slug>`
# produces: the program name and nothing else.
_BARE_ARGV = ["check-fixture"]

# What makes a check an argv-PARSING one, and why it is the construction rather
# than the `argparse` import: several checks MATCH on `add_argument` while
# scanning a consumer's AST, so they name the module without ever building a
# parser of their own — and a check that builds none has no usage text to emit.
_PARSER_CONSTRUCTION = "ArgumentParser("


def _canonical_module_names() -> list[str]:
    """The package's canonical check modules, derived from the shipped slugs."""
    resolved = canonical_check_slugs()
    assert isinstance(
        resolved, IOSuccess
    ), f"the shipped checks package must be readable; got {resolved}"
    slugs = unsafe_perform_io(resolved.unwrap())
    return sorted(slug.removeprefix("check-").replace("-", "_") for slug in slugs)


def _required_parameters(*, entrypoint: Callable[..., int]) -> list[str]:
    """Parameter names `entrypoint` would demand from a no-argument call."""
    return [
        name
        for name, parameter in inspect.signature(entrypoint).parameters.items()
        if parameter.default is inspect.Parameter.empty and parameter.kind not in _VARIADIC_KINDS
    ]


def _declared_argument_names(*, source: str) -> list[str]:
    """The string-literal name every `add_argument` call in `source` declares."""
    return [
        argument.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("add_argument")
        for argument in node.args[:1]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    ]


def _write_config_fixture(*, root: Path, block: str) -> Path:
    """A consumer tree whose only content is a `[tool.livespec_dev_tooling]` block."""
    root.mkdir(parents=True, exist_ok=True)
    _ = root.joinpath("pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\n{block}", encoding="utf-8"
    )
    return root


def test_no_shipped_check_takes_configuration_through_positional_argv(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checks are invocable bare, declare no positional, and read config from the tree."""
    modules = _canonical_module_names()
    assert modules, "the library must ship at least one canonical check"

    demanded = {
        name: _required_parameters(
            entrypoint=importlib.import_module(f"{_CHECKS_NAMESPACE}.{name}").main
        )
        for name in modules
    }
    demanding = {name: required for name, required in demanded.items() if required}
    assert not demanding, (
        f"every check must be invocable as `python -m {_CHECKS_NAMESPACE}.<slug>` with "
        f"no arguments, so its `main` may demand none; demanding={demanding}"
    )

    positional = {
        name: sorted(
            declared
            for declared in _declared_argument_names(
                source=(_CHECKS_DIR / f"{name}.py").read_text(encoding="utf-8")
            )
            if not declared.startswith("-")
        )
        for name in modules
    }
    declaring = {name: names for name, names in positional.items() if names}
    assert not declaring, (
        f"configuration MUST NOT flow through positional argv, so no check may declare "
        f'a positional argument (constraints.md §"CLI shape"); declaring={declaring}'
    )

    monkeypatch.setattr(sys, "argv", list(_BARE_ARGV))
    alpha = load_config(
        repo_root=_write_config_fixture(
            root=tmp_path / "alpha",
            block='source_trees = ["alpha_src"]\ntests_tree_prefix = "alpha_tests/"\n',
        )
    )
    beta = load_config(
        repo_root=_write_config_fixture(
            root=tmp_path / "beta", block='source_trees = ["beta_src"]\n'
        )
    )

    assert (alpha.source_trees, alpha.tests_tree_prefix) == (
        (Path("alpha_src"),),
        "alpha_tests/",
    ), f"the declared block must govern; got {alpha.source_trees} {alpha.tests_tree_prefix!r}"
    assert (beta.source_trees, beta.tests_tree_prefix) == (
        (Path("beta_src"),),
        "tests/",
    ), f"an undeclared key must fall back to the baseline; got {beta.tests_tree_prefix!r}"
    assert sys.argv == _BARE_ARGV, (
        "argv was held bare and identical across both loads, so the differing "
        "configuration can only have come from each tree's pyproject.toml"
    )


def test_every_argv_parsing_check_exits_zero_on_help(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A check that builds a parser exits `0` on `--help` with usage on stdout.

    The exit-`0`-with-usage half of the wrapper shape, asserted where a parser
    makes it observable. `argparse` terminates via `SystemExit`, so the check
    body never runs and no working tree is touched.
    """
    parsing = [
        name
        for name in _canonical_module_names()
        if _PARSER_CONSTRUCTION in (_CHECKS_DIR / f"{name}.py").read_text(encoding="utf-8")
    ]
    assert parsing, "at least one shipped check must build an argv parser"

    for name in parsing:
        module = importlib.import_module(f"{_CHECKS_NAMESPACE}.{name}")
        monkeypatch.setattr(sys, "argv", [name, "--help"])

        with pytest.raises(SystemExit) as exited:
            _ = module.main()

        usage = capsys.readouterr().out
        assert exited.value.code == 0, f"{name} --help must exit 0; got {exited.value.code}"
        assert "usage:" in usage, f"{name} --help must write usage text to stdout; got {usage!r}"
