"""One isolated pytest-cov measurement under the repository's own configuration.

Shared by `check_coverage_incremental` and the expedited incident's focused
evidence, so the two cannot disagree about what a covered line is. Both run a
nested pytest whose coverage data must land in a private file rather than in the
normal `.coverage`, and both measure under `pyproject.toml` — its `omit` and
`exclude_also` and its pytest `addopts`. They differ from the full-tree gates in
one way: those run with `COVERAGE_FILE` unset (`check-per-file-coverage.sh`),
while these set it to the private data file.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

__all__: list[str] = ["COVERAGE_CONFIG", "isolated_environment", "pytest_coverage_arguments"]

# The configuration every normal coverage path measures under.
COVERAGE_CONFIG: str = "pyproject.toml"
# pytest-cov's `.pth` startup hook activates inside ANY subprocess whose env has
# `COV_CORE_*` set — including a nested pytest spawned under an outer pytest-cov
# session. Activating it there would attach the nested measurement to the OUTER
# session's data file, defeating the private data file. Strip those variables so
# the nested pytest starts a fresh measurement against the private file only.
_COV_CORE_ENV_PREFIX: str = "COV_CORE_"


def isolated_environment(*, environ: Mapping[str, str], data_file: str) -> dict[str, str]:
    """Return `environ` without outer pytest-cov wiring, writing to `data_file`."""
    env = {key: value for key, value in environ.items() if not key.startswith(_COV_CORE_ENV_PREFIX)}
    env["COVERAGE_FILE"] = data_file
    return env


def pytest_coverage_arguments(*, tests: Iterable[str], config: str = COVERAGE_CONFIG) -> list[str]:
    """Return the pytest arguments that measure `tests` with branch coverage, unreported.

    The threshold is left to the caller's own report step, so the nested pytest
    never fails on a percentage.
    """
    return [
        "--cov",
        "--cov-branch",
        f"--cov-config={config}",
        "--cov-report=",
        "--cov-fail-under=0",
        *tests,
    ]
