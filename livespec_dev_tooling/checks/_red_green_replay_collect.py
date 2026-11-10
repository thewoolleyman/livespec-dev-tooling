"""Range-validation collection of a Red+Green commit's recorded test.

`red_green_replay`'s commit-range validation used to judge a commit carrying
both `TDD-Red-*` and `TDD-Green-*` trailers by the PRESENCE of two keys, so a
commit whose recorded `TDD-Red-Test` module cannot even be imported on that
commit's own tree passed the branch-level gate. The commit-time hook is the one
place the test is actually run, and a history rewrite that bypasses hooks (a
rebase, a cherry-pick with `core.hooksPath=/dev/null`, a squash) keeps the
trailers while the tree around the test changes. Measured on
livespec-dev-tooling#3913: two replayed commits recorded
`tests/livespec_dev_tooling/test_incident_strict_json.py`, whose import of a
function master had since removed raised `ImportError` on each commit's own
tree, and the range gate passed the branch in about two seconds
(work-item livespec-dev-tooling-5be65c).

The rule is the "Range validation collects a Red+Green commit's recorded test"
bullet of the suite-green replay leg section of `SPECIFICATION/contracts.md`. It COLLECTS the
recorded module and never re-runs it: the commit-msg Green leg ran the test,
and the range head's full suite covers the final tree. Collection costs a
few seconds per commit where a module re-run costs about four times that.

Each commit's tree is materialized into a scratch directory through a PRIVATE
index file (`GIT_INDEX_FILE`) and `git checkout-index`, so the caller's working
tree, index and `.git` metadata are never touched. `git archive` is not used
because it honours `export-ignore`, which would leave out files a real checkout
has. The child is the interpreter running this check, with the scratch tree as
its working directory, its `--rootdir` and the head of `PYTHONPATH`, so the
commit's own first-party packages, `conftest.py` files and pytest configuration
are the ones in effect rather than an installed or editable copy.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
# Make the script's own directory importable so the sibling `_*` modules
# resolve when this module is loaded standalone (the importlib test path).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _red_green_replay_incident import (  # noqa: E402  — sibling private import
    admitted_by_recorded_incident,
)
from _red_green_replay_revert import (  # noqa: E402  — sibling private import
    is_forge_authored_revert,
)
from _red_green_replay_suite_runner import (  # noqa: E402  — sibling private import
    SuiteBound,
    SuiteRun,
    run_suite,
    suite_bound,
)
from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._config_load import load_config_or_report  # noqa: E402
from livespec_dev_tooling.config import derive_source_prefixes  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    import structlog.stdlib

__all__: list[str] = [
    "COLLECTION_CHECK_ID",
    "COLLECTION_HINT",
    "admitted_by_recorded_incident",
    "collect_recorded_tests",
    "is_forge_authored_revert",
]

COLLECTION_CHECK_ID: str = "red-green-replay-range-recorded-test-uncollectable"
COLLECTION_HINT: str = (
    "Every commit that carries both TDD-Red-* and TDD-Green-* trailers and touches product "
    "impl .py must have its TDD-Red-Test module collect by pytest on that commit's OWN tree. "
    "A rebase, cherry-pick or squash that bypassed the commit-time hook keeps the trailers "
    "while changing the tree around the test. Remedy: rewrite the range so that every "
    "in-scope commit's recorded module collects, redoing each offending change through the "
    "hook (Red, then the Green amend) so its trailers are earned on the tree it ships. "
    "There is no flag, skip or subject prefix that exempts a collection failure."
)
_RECORDED_TEST_RE = re.compile(r"^TDD-Red-Test:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)
_PAIR_KEYS = ("TDD-Red-Test-File-Checksum:", "TDD-Green-Verified-At:")
_NO_MODULE = "<none recorded>"
_NOT_UNDER_A_TEST_TREE = "the recorded path is not a .py file under a configured test tree"


@dataclass(frozen=True, kw_only=True)
class _Finding:
    """One in-scope commit whose recorded module did not collect on its own tree."""

    sha: str
    module: str
    error: str


def _git(*, args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False, env=env)


def _in_scope_message(*, sha: str, base_ref: str, impl_prefixes: tuple[str, ...]) -> str | None:
    """Return the commit's message iff the collection rule applies to it, else None.

    In scope: a commit touching product impl `.py` (the paths and the deletion
    carve-out `red_green_replay._commit_violates` uses) that carries the pair
    shape. A commit that already fails a trailer-shape check is reported by the
    trailer check and never reaches here. The two exemptions the range already
    has, a verified forge-authored revert and a recorded incident, keep a
    commit out of scope; a probe that could not start exempts nothing.
    """
    touched = _git(
        args=["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "--diff-filter=d", sha]
    ).stdout.splitlines()
    product_paths = [p for p in touched if p.endswith(".py") and p.startswith(impl_prefixes)]
    if not product_paths:
        return None
    message = _git(args=["log", "-1", "--format=%B", sha]).stdout
    if not all(key in message for key in _PAIR_KEYS):
        return None
    if admitted_by_recorded_incident(sha=sha, message=message):
        return None
    forge = is_forge_authored_revert(sha=sha, product_paths=product_paths, base_ref=base_ref)
    return None if is_successful(forge) and unsafe_perform_io(forge.unwrap()) else message


def _recorded_module(*, message: str) -> str:
    """Return the `TDD-Red-Test` path with any `::node-id` dropped, or "" when unrecorded."""
    found = _RECORDED_TEST_RE.search(message)
    return "" if found is None else found.group(1).split("::", 1)[0]


def _module_problem(*, sha: str, module: str, test_trees: tuple[str, ...]) -> str | None:
    """Return why the recorded path cannot be judged at all, or None when it can."""
    if not module:
        return "the commit carries no TDD-Red-Test trailer"
    path = PurePosixPath(module)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.suffix != ".py"
        or not module.startswith(test_trees)
    ):
        return _NOT_UNDER_A_TEST_TREE
    if _git(args=["cat-file", "-t", f"{sha}:{module}"]).stdout.strip() != "blob":
        return "the recorded module does not exist in the commit's tree"
    return None


def _collection_problem(*, run: SuiteRun, bound: SuiteBound) -> str | None:
    """Return the first collection error line of a finished run, or None when it collected."""
    if run.timed_out:
        return (
            f"collection was ended by the {run.kill_reason} bound "
            f"(stall window {bound.stall_seconds} seconds)"
        )
    if run.returncode == 0:
        return None
    lines = [line.strip() for line in run.output.replace("\r", "").splitlines() if line.strip()]
    errors = [line for line in lines if line.startswith("E ")]
    if errors:
        return errors[0]
    return lines[-1] if lines else f"pytest exited {run.returncode} with no output"


def _collect(*, sha: str, module: str) -> str | None:
    """Collect `module` on `sha`'s own tree; return the first problem, or None when it collects."""
    with tempfile.TemporaryDirectory(prefix="red-green-collect-") as scratch:
        tree = Path(scratch) / "tree"
        tree.mkdir()
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
        loaded = _git(args=["read-tree", sha], env=env)
        if loaded.returncode == 0:
            loaded = _git(args=["checkout-index", "-a", "-f", f"--prefix={tree}/"], env=env)
        if loaded.returncode != 0:
            return f"the commit's tree could not be materialized: {loaded.stderr.strip()}"
        bound = suite_bound(environ=os.environ)
        inherited = os.environ.get("PYTHONPATH")
        run = run_suite(
            argv=[
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "--color=no",
                "-p",
                "no:cacheprovider",
                "--rootdir",
                str(tree),
                module,
            ],
            bound=bound,
            cwd=tree,
            environ={
                "PYTHONPATH": os.pathsep.join([str(tree), *([inherited] if inherited else [])])
            },
        )
    return _collection_problem(run=run, bound=bound)


def collect_recorded_tests(
    *, shas: list[str], base_ref: str, log: structlog.stdlib.BoundLogger
) -> int:
    """Collect every in-scope commit's recorded test; return 0, or 1 after logging the finding."""
    loaded = load_config_or_report(repo_root=Path.cwd(), log=log, check_id="red_green_replay")
    if not is_successful(loaded):
        return 1
    config = unsafe_perform_io(loaded.unwrap())
    impl_prefixes = derive_source_prefixes(config=config)
    test_trees = (
        config.tests_tree_prefix,
        *(f"{PurePosixPath(pairing.test_tree).as_posix()}/" for pairing in config.mirror_pairings),
    )
    findings: list[_Finding] = []
    for sha in shas:
        message = _in_scope_message(sha=sha, base_ref=base_ref, impl_prefixes=impl_prefixes)
        if message is None:
            continue
        module = _recorded_module(message=message)
        problem = _module_problem(sha=sha, module=module, test_trees=test_trees) or _collect(
            sha=sha, module=module
        )
        if problem is not None:
            findings.append(_Finding(sha=sha, module=module or _NO_MODULE, error=problem))
    if not findings:
        return 0
    log.error(
        "commits in origin/master..HEAD record a TDD-Red-Test module that does not collect "
        "on the commit's own tree",
        check_id=COLLECTION_CHECK_ID,
        failing_commits=[
            {"sha": found.sha, "module": found.module, "error": found.error} for found in findings
        ],
        hint=COLLECTION_HINT,
    )
    return 1
