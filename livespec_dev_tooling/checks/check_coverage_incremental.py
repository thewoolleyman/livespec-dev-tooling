"""check_coverage_incremental — path-scoped per-file 100% gate.

A path-scoped fast-feedback variant of `check-coverage` for the
Red→Green authoring loop. Invocation contract:

    just check-coverage-incremental --paths <impl_path> [<impl_path>...]

For each `<impl_path>` (repo-root-relative): resolve its
mirror-paired test path, then run pytest on the combined test
set with full `--cov` (no path filter — path-scoped `--cov=<dir>`
filters break under subprocess instrumentation because coverage's
`source=` resolves the relative path against the subprocess's cwd
at measurement time). Apply the per-file 100% line+branch gate via
`coverage report --include=<impl_paths> --fail-under=100`.

Both subprocess invocations always run; the script returns the
maximum of their return codes. This is intentional — running
both surfaces both failures simultaneously, which is the
fast-feedback role of v039 D3, and avoids the otherwise-untestable
"pytest failed, did we run coverage?" branch profile that would
require synthetic failing-test fixtures to exercise.

Wall-clock target: under 10 seconds for a typical single-file
pair. NOT a replacement for `check-coverage` — the full-tree
run remains the load-bearing pre-commit gate. The fast-feedback
role is to surface coverage gaps proactively during authoring,
BEFORE the Green amend triggers a multi-minute aggregate retry
on a missed defensive branch.

CLI-flag exemption note: the dev-tooling/checks/ CLAUDE.md
guidance reads "no CLI flags; the script reads the repo at
cwd." This script accepts an OPTIONAL `--paths` flag to scope the
per-file gate; the precedent is `red_green_replay.py` which
takes `argv[1]` as the COMMIT_EDITMSG path. The exemption is
documented at the v039 D3 canonical-target-list row.

No-`--paths` derive (epic li-cvaudit, cvnoarg): when invoked with
NO `--paths`, the check derives the changed-file list from
`git diff --name-only origin/master...HEAD`, filtered to `.py` files
under the consumer's configured `source_tree_prefixes`, and runs the
per-file gate against those. This replaces the prior no-arg
short-circuit (a justfile `if [[ -z "{{args}}" ]]` block that made the
aggregate invocation a silent no-op). An empty derived set (no changed
impl `.py`) still exits 0 — there is simply nothing to gate.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import
time. Subprocess stdout/stderr (pytest's progress; coverage's
report) flows through to the developer's terminal unmodified
by NOT capturing it.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import MirrorPairing, load_config  # noqa: E402

__all__: list[str] = []
# Isolated coverage data file. The script spawns its own pytest as
# a subprocess; if we let pytest-cov default to `.coverage` the
# inner data file would clash with any outer pytest-cov session
# that ALSO writes to `.coverage` (e.g., the test that exercises
# this script's own happy path runs INSIDE pytest, which is
# already writing to `.coverage` for the outer session). The
# unique `_DATA_FILE` name keeps the inner data isolated; the
# `coverage report` step reads the same file via `--data-file`.
_DATA_FILE: str = ".coverage.check-coverage-incremental"
# pytest-cov's `.pth` startup hook activates inside ANY subprocess
# whose env has `COV_CORE_*` set — including the inner pytest the
# script spawns when invoked under an outer pytest-cov session
# (this script's own happy-path test). Activating the hook in the
# inner subprocess would attach the inner coverage measurement to
# the OUTER session's data file, defeating the `_DATA_FILE`
# isolation above. Strip those vars from the env handed to the
# inner pytest invocation so it starts a fresh measurement against
# `_DATA_FILE` only.
_COV_CORE_ENV_PREFIX: str = "COV_CORE_"


def _resolve_mirror_test_path(
    *, impl_path: Path, mirror_pairings: tuple[MirrorPairing, ...]
) -> Path:
    """Map an impl path to its v033 D1 mirror-paired test path.

    Walks the consumer's `mirror_pairings` (from the
    `[tool.livespec_dev_tooling]` config, defaulting to the livespec-core
    historical mirrors); on the first match, transforms
    `<rel_parent>/<name>.py` to `<tests_tree>/<rel_parent>/test_<name>.py`.
    Leading underscores in `<name>.py` are stripped before the `test_`
    prefix is added (matches `tests_mirror_pairing.py`'s
    `_expected_paired_test_path`). Raises `ValueError` if `impl_path` is
    not under any configured mirror-paired source tree.
    """
    for pairing in mirror_pairings:
        try:
            rel = impl_path.relative_to(pairing.source_tree)
        except ValueError:
            continue
        parent = rel.parent
        name = rel.name
        test_name = f"test_{name[1:]}" if name.startswith("_") else f"test_{name}"
        return pairing.test_tree / parent / test_name
    known = ", ".join(str(p.source_tree) for p in mirror_pairings)
    msg = f"impl path {impl_path} is not under any mirror-paired source tree ({known})"
    raise ValueError(msg)


def _resolve_test_paths(
    *,
    impl_paths: list[Path],
    mirror_pairings: tuple[MirrorPairing, ...],
    log: structlog.stdlib.BoundLogger,
) -> list[Path] | None:
    """Resolve impl paths to mirror-paired test paths, or None on resolution failure.

    For each impl_path: call `_resolve_mirror_test_path` and
    confirm the resulting test file exists on disk. On either
    failure (ValueError raised, or test file not present), log
    a structured diagnostic and return None. Otherwise return
    the list of resolved test paths in the same order as
    impl_paths. An empty input returns the empty list — a
    no-op behavior the loop-not-taken branch unit-test
    exercises directly (argparse's `nargs="+"` ensures `main`
    never invokes this with an empty list, so the unreachable
    branch is otherwise unmeasured).
    """
    test_paths: list[Path] = []
    for impl in impl_paths:
        try:
            test_path = _resolve_mirror_test_path(impl_path=impl, mirror_pairings=mirror_pairings)
        except ValueError as exc:
            log.exception(
                "could not resolve mirror-paired test for impl path",
                impl_path=str(impl),
                reason=str(exc),
            )
            return None
        if not test_path.is_file():
            log.error(
                "mirror-paired test does not exist",
                impl_path=str(impl),
                expected_test=str(test_path),
            )
            return None
        test_paths.append(test_path)
    return test_paths


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-coverage-incremental",
        description=(
            "Path-scoped per-file 100% line+branch coverage gate (v039 D3). "
            "Resolves each --paths impl to its mirror-paired test, runs "
            "pytest with full --cov, then applies the per-file gate via "
            "coverage report --include=<impl> --fail-under=100."
        ),
    )
    _ = parser.add_argument(
        "--paths",
        nargs="*",
        default=[],
        type=Path,
        metavar="IMPL_PATH",
        help=(
            "impl path(s), repo-root-relative, to scope the per-file coverage "
            "gate to; when omitted, the changed impl `.py` set is derived from "
            "`git diff --name-only origin/master...HEAD`"
        ),
    )
    return parser


def _changed_py_impl_paths(
    *, diff_output: str, source_tree_prefixes: tuple[str, ...]
) -> list[Path]:
    """Filter a `git diff --name-only` blob to `.py` files under a source prefix.

    Keeps each non-blank line that ends in `.py` AND starts with one of
    `source_tree_prefixes` (the consumer's configured impl-tree prefixes),
    preserving order. Test files, docs, and config are dropped — only impl
    `.py` paths the per-file gate can resolve to a mirror-paired test
    survive.
    """
    out: list[Path] = []
    for line in diff_output.splitlines():
        path = line.strip()
        if not path or not path.endswith(".py"):
            continue
        if path.startswith(source_tree_prefixes):
            out.append(Path(path))
    return out


def _derive_paths_from_git(*, source_tree_prefixes: tuple[str, ...], cwd: Path) -> list[Path]:
    """Derive the changed impl-`.py` set from `git diff origin/master...HEAD`.

    Runs the diff in `cwd` (the repo root) and filters the result via
    `_changed_py_impl_paths`. Returns the empty list when there are no
    changed impl `.py` files (the no-op-after-derive case).

    The git subprocess is handed an env with every `GIT_*` var stripped:
    a parent process (notably a git commit hook) can inject `GIT_DIR` /
    `GIT_INDEX_FILE` / `GIT_WORK_TREE`, which would override `cwd` and make
    the diff target the WRONG repository. Clearing those keeps the diff
    scoped to the repository at `cwd`.
    """
    git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    # S603/S607: argv is a fixed list of literal git args; no shell input.
    diff = subprocess.run(
        ["git", "diff", "--name-only", "origin/master...HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd),
        env=git_env,
    ).stdout
    return _changed_py_impl_paths(diff_output=diff, source_tree_prefixes=source_tree_prefixes)


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("check_coverage_incremental")


def main() -> int:
    log = _configure_logger()
    args = _build_parser().parse_args()
    cwd = Path.cwd()
    config = load_config(repo_root=cwd)
    impl_paths: list[Path] = list(args.paths)
    derived = not impl_paths
    if derived:
        impl_paths = _derive_paths_from_git(
            source_tree_prefixes=config.source_tree_prefixes, cwd=cwd
        )
        if not impl_paths:
            log.info(
                "no changed impl .py paths derived from git diff; nothing to gate",
                base="origin/master...HEAD",
                source_tree_prefixes=list(config.source_tree_prefixes),
            )
            return 0
    test_paths = _resolve_test_paths(
        impl_paths=impl_paths, mirror_pairings=config.mirror_pairings, log=log
    )
    if test_paths is None:
        return 1

    inner_env = {k: v for k, v in os.environ.items() if not k.startswith(_COV_CORE_ENV_PREFIX)}
    inner_env["COVERAGE_FILE"] = _DATA_FILE

    # Coverage-threshold policy by invocation mode (epic li-cvaudit, cvnoarg):
    #   - Explicit `--paths` (interactive fast-feedback): enforce the per-file
    #     100% line+branch gate (`--fail-under=100`) — the developer asked for
    #     this exact scope.
    #   - Derived (no-`--paths`, the canonical-aggregate path): the inner
    #     pytest STRIPS `COV_CORE_*` for data-file isolation, so any mirror
    #     test that itself spawns a check binary as a grandchild subprocess
    #     loses coverage on those grandchild lines. The derived per-file
    #     percentage is therefore advisory — reported but not fatal
    #     (`--fail-under=0`). The load-bearing 100% gate in `just check`
    #     remains the FULL-tree `check-per-file-coverage`. Resolution errors
    #     (missing mirror, unknown tree) and pytest FAILURES still hard-fail
    #     in both modes — only the coverage-percentage threshold relaxes.
    fail_under = "0" if derived else "100"

    # S603/S607: argv is a fixed list (literal binary names + repo-controlled
    # paths from --paths); no untrusted shell input.
    pytest_rc = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            "--cov",
            "--cov-branch",
            "--cov-config=pyproject.toml",
            "--cov-report=",
            "--cov-fail-under=0",
            *(str(p) for p in test_paths),
        ],
        env=inner_env,
        check=False,
    ).returncode
    include = ",".join(str(p) for p in impl_paths)
    coverage_rc = subprocess.run(
        [
            "uv",
            "run",
            "coverage",
            "report",
            f"--data-file={_DATA_FILE}",
            f"--include={include}",
            f"--fail-under={fail_under}",
        ],
        check=False,
    ).returncode
    return max(pytest_rc, coverage_rc)


if __name__ == "__main__":
    raise SystemExit(main())
