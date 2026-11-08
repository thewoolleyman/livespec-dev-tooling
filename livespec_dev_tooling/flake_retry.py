"""Retry failures only when the changed tree cannot have caused them.

The pytest-rerunfailures marker is deliberately added only after a conservative
working-tree analysis. An analysis failure therefore means ``touched`` rather
than granting a retry on incomplete evidence.
"""

from __future__ import annotations

import ast
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from livespec_dev_tooling._flake_retry_closure import conftest_chain, module_imports
from livespec_dev_tooling.flake_retry_changes import change_paths, withheld_reason
from livespec_dev_tooling.flake_retry_finalizers import preserve_finalizers
from livespec_dev_tooling.flake_retry_paths import path_literals

if TYPE_CHECKING:
    from collections.abc import Iterable

    from _pytest.terminal import TerminalReporter

__all__: list[str] = [
    "RETRY_ATTEMPTS",
    "RETRY_DELAY_SECONDS",
    "RetryResult",
    "announce_retries",
    "mark_untouched_tests",
    "record_report",
    "retry_marker_for",
    "retry_summary",
    "write_retry_records",
]

RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 60
_UNSAFE_NAMES = {"pyproject.toml", "uv.lock", "justfile", "conftest.py"}
_RESULTS: dict[str, RetryResult] = {}
_WITHHELD: list[str] = []
_WORKER_WITHHELD_KEY = "livespec_flake_retry_withheld"


@dataclass(frozen=True, kw_only=True)
class RetryResult:
    """The final outcome of a test pytest-rerunfailures has retried."""

    nodeid: str
    attempts: int
    outcome: str


@dataclass(frozen=True, kw_only=True)
class _ModuleFacts:
    """What one parsed source module contributes to any closure that reaches it."""

    imports: frozenset[Path]
    literals: frozenset[str]
    undeterminable_paths: bool


def _module_facts(*, repo_root: Path, path: Path) -> _ModuleFacts | None:
    """Parse one module once and keep its imports and path-bearing literals."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        return None
    path_component_nodes = {
        id(component)
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
        for component in ast.walk(node)
        if isinstance(component, ast.Constant) and isinstance(component.value, str)
    }
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        if id(node) not in path_component_nodes or Path(node.value).suffix
    }
    path_names, path_is_undeterminable = path_literals(tree=tree, repo_root=repo_root)
    return _ModuleFacts(
        imports=frozenset(module_imports(repo_root=repo_root, path=path, tree=tree)),
        literals=frozenset(literals | path_names),
        undeterminable_paths=path_is_undeterminable,
    )


def _closure(
    *, repo_root: Path, test_path: Path, memo: dict[Path, _ModuleFacts | None] | None = None
) -> tuple[set[Path], set[str], bool] | None:
    """Read imports and string literals without executing the test tree.

    `memo` holds each module's parsed facts for the caller's whole collection
    pass, so a module many tests import is parsed once rather than once per
    collected item (livespec-dev-tooling-pprfq2).
    """
    facts_by_path = {} if memo is None else memo
    pending = [test_path, *conftest_chain(repo_root=repo_root, test_path=test_path)]
    modules: set[Path] = set()
    literals: set[str] = set()
    undeterminable_paths = False
    while pending:
        path = pending.pop()
        if path in modules:
            continue
        if path not in facts_by_path:
            facts_by_path[path] = _module_facts(repo_root=repo_root, path=path)
        facts = facts_by_path[path]
        if facts is None:
            return None
        modules.add(path)
        literals.update(facts.literals)
        undeterminable_paths = undeterminable_paths or facts.undeterminable_paths
        pending.extend(facts.imports - modules)
    return modules, literals, undeterminable_paths


def _changed_names(*, paths: set[Path]) -> set[str]:
    """Produce whole literal spellings that can identify changed code or data paths.

    A literal may name the changed file, its filename, or an entire directory
    prefix. Individual directory components are deliberately not candidates:
    a common name such as ``livespec_dev_tooling`` is not a path to every
    directory that happens to contain that segment.
    """
    names: set[str] = set()
    for path in paths:
        names.update((path.as_posix(), path.name))
        names.update(parent.as_posix() for parent in path.parents if parent != Path())
        if path.suffix == ".py":
            names.add(".".join(path.with_suffix("").parts))
    return names


def retry_marker_for(
    *,
    repo_root: Path,
    test_path: Path,
    change_paths: set[Path],
    memo: dict[Path, _ModuleFacts | None] | None = None,
) -> dict[str, int] | None:
    """Return a rerun marker only when no changed path touches the closure."""
    if any(path.name in _UNSAFE_NAMES or path.name == Path(__file__).name for path in change_paths):
        return None
    analyzed = _closure(repo_root=repo_root, test_path=test_path, memo=memo)
    if analyzed is None:
        return None
    modules, literals, undeterminable_paths = analyzed
    if undeterminable_paths:
        return None
    relative_modules = {path.relative_to(repo_root) for path in modules}
    if relative_modules & change_paths or literals & _changed_names(paths=change_paths):
        return None
    return {"reruns": RETRY_ATTEMPTS, "reruns_delay": RETRY_DELAY_SECONDS}


def mark_untouched_tests(
    *, root: Path, items: list[pytest.Item], can_retry: bool = True
) -> str | None:
    """Mark only tests proven untouched by this session's complete change set.

    `flaky` is pytest-rerunfailures' marker. A consumer can load this plugin
    through its entry point without that package installed, and there the
    marker is unregistered and `--strict-markers` kills collection
    (livespec-dev-tooling-he3pf2). With no rerunfailures in the session nothing
    is marked: an untouched failure then simply stands, unretried.
    """
    if not can_retry:
        return None
    paths = change_paths(repo_root=root)
    if paths is None:
        return withheld_reason()
    memo: dict[Path, _ModuleFacts | None] = {}
    markers: dict[Path, dict[str, int] | None] = {}
    for item in items:
        test_path = Path(str(item.path))
        if test_path not in markers:
            markers[test_path] = retry_marker_for(
                repo_root=root, test_path=test_path, change_paths=paths, memo=memo
            )
        marker = markers[test_path]
        if marker is not None:
            item.add_marker(pytest.mark.flaky(**marker))
    return None


def record_report(*, report: pytest.TestReport) -> None:
    """Keep final outcomes for rerunfailures' individual retry reports."""
    if report.when != "call":
        return
    previous = _RESULTS.get(report.nodeid)
    outcome = cast(str, report.outcome)
    if outcome == "rerun":
        _RESULTS[report.nodeid] = RetryResult(
            nodeid=report.nodeid,
            attempts=(previous.attempts if previous else 0) + 1,
            outcome="rerun",
        )
    elif previous is not None:
        _RESULTS[report.nodeid] = RetryResult(
            nodeid=report.nodeid, attempts=previous.attempts + 1, outcome=outcome
        )


def write_retry_records(*, repo_root: Path, results: Iterable[RetryResult]) -> Path:
    """Write one JSON line for each retried node id beneath the repository tmp tree."""
    output = repo_root / "tmp" / "flake-retries" / "retries.jsonl"
    _ = output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(
        "".join(json.dumps(result.__dict__, sort_keys=True) + "\n" for result in results),
        encoding="utf-8",
    )
    return output


def retry_summary(*, results: Iterable[RetryResult]) -> str:
    """Render the loud terminal block required for every retry decision."""
    rows = [f"{result.nodeid}: {result.attempts} attempts, {result.outcome}" for result in results]
    return "FLAKE-RETRIED\n" + "\n".join(rows)


def announce_retries(
    *, terminalreporter: TerminalReporter, root: Path, withheld: str | None = None
) -> None:
    """Persist and announce retry evidence without changing pytest's final verdict."""
    annotate = os.environ.get("GITHUB_ACTIONS") == "true"
    if withheld is not None:
        _ = terminalreporter.write_sep("=", "FLAKE-RETRY-WITHHELD")
        _ = terminalreporter.write_line(f"no failing test is retried this session: {withheld}")
        if annotate:
            _ = terminalreporter.write_line(f"::warning::FLAKE-RETRY-WITHHELD {withheld}")
    results = list(_RESULTS.values())
    if not results:
        return
    _ = write_retry_records(repo_root=root, results=results)
    _ = terminalreporter.write_sep("=", "FLAKE-RETRIED")
    for line in retry_summary(results=results).splitlines()[1:]:
        _ = terminalreporter.write_line(line)
    if annotate:
        for result in results:
            _ = terminalreporter.write_line(f"::warning::FLAKE-RETRIED {result.nodeid}")


def _workeroutput(*, holder: object) -> dict[str, object] | None:
    """Return xdist's optional worker-output mapping without importing xdist."""
    candidate = cast(object, vars(holder).get("workeroutput"))
    return cast(dict[str, object], candidate) if isinstance(candidate, dict) else None


def _record_withheld(*, withheld: str | None) -> None:
    """Keep one withholding reason for the controller's terminal summary."""
    if withheld is not None and withheld not in _WITHHELD:
        _WITHHELD.append(withheld)


# PYTEST CALLS ITS HOOKS POSITIONALLY. pluggy reads a hook's argument names off
# its signature and passes them by position, so a keyword-only hook receives
# nothing, and a `*args` hook receives nothing either (that shape INTERNALERRORed
# every session, run 01M6GVFTX08S). Each hook is therefore the bound `__call__`
# of a small adapter: the dunder takes pytest's fixed positional convention, and
# it hands straight on to the keyword-only function that does the work.
class _CollectionHook:
    def __call__(
        self, session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
    ) -> None:
        withheld = mark_untouched_tests(
            root=Path(str(session.config.rootpath)),
            items=items,
            can_retry=config.pluginmanager.hasplugin("rerunfailures"),
        )
        _WITHHELD[:] = []
        _record_withheld(withheld=withheld)


class _ConfigureHook:
    def __call__(self, config: pytest.Config) -> None:
        """Adapt pytest's positional hook call to the keyword-only setup helper."""
        preserve_finalizers(config=config)


class _SessionFinishHook:
    def __call__(self, session: pytest.Session, exitstatus: int) -> None:
        """Send a worker's withholding reason to xdist's controller."""
        del exitstatus
        workeroutput = _workeroutput(holder=session.config)
        if workeroutput is not None and _WITHHELD:
            workeroutput[_WORKER_WITHHELD_KEY] = _WITHHELD[0]


class _NodeDownHook:
    @pytest.hookimpl(optionalhook=True)
    def __call__(self, node: object, error: object | None) -> None:
        """Collect the worker withholding reason before the controller summarizes."""
        del error
        workeroutput = _workeroutput(holder=node)
        withheld = None if workeroutput is None else workeroutput.get(_WORKER_WITHHELD_KEY)
        _record_withheld(withheld=withheld if isinstance(withheld, str) else None)


class _ReportHook:
    def __call__(self, report: pytest.TestReport) -> None:
        record_report(report=report)


class _SummaryHook:
    def __call__(
        self, terminalreporter: TerminalReporter, exitstatus: int, config: pytest.Config
    ) -> None:
        del exitstatus
        announce_retries(
            terminalreporter=terminalreporter,
            root=Path(str(config.rootpath)),
            withheld=_WITHHELD[0] if _WITHHELD else None,
        )


pytest_collection_modifyitems = _CollectionHook().__call__
pytest_configure = _ConfigureHook().__call__
pytest_sessionfinish = _SessionFinishHook().__call__
pytest_testnodedown = _NodeDownHook().__call__
pytest_runtest_logreport = _ReportHook().__call__
pytest_terminal_summary = _SummaryHook().__call__
