"""Suite-green leg helpers for `red_green_replay`.

The green-verified leg runs the staged tests for a test-only change, unless
shared test support changed; every other case runs the full pytest suite
inside the commit-msg hook. On a large suite a serial run takes tens of
minutes, so this helper module parallelizes it under pytest-xdist (worker count from the
`test_nprocs` env var when a justfile exports it, else the consumers'
lane-aware rule), bounds it with a
timeout whose expiry kills the whole process group (xdist workers
included), and checksums its output over a canonical form that does not
depend on parallel line ordering or run duration.

Split out of `_red_green_replay_modes.py` to keep that module under the
file-LLOC ceiling. The leading underscore marks a private sibling.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib.util
import os
import re
import signal
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import structlog.stdlib

# Make the script's own directory importable so the sibling `_*` modules
# resolve when this module is loaded standalone (the importlib test path).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _red_green_replay_protocol import RED_GREEN_REPLAY_PROTOCOL  # noqa: E402
from _red_green_replay_trailers import write_trailers  # noqa: E402

__all__: list[str] = [
    "DEFAULT_TIMEOUT_SECONDS",
    "SuiteRun",
    "_handle_suite_green_mode",
    "canonical_output_checksum",
    "has_shared_test_support",
    "run_suite",
    "stages_only_shared_test_support",
    "suite_pytest_argv",
    "suite_timeout_seconds",
    "xdist_importable",
]

DEFAULT_TIMEOUT_SECONDS: int = 2400
_TIMEOUT_ENV: str = "LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS"
_NPROCS_ENV: str = "test_nprocs"
_LANE_ENV: str = "LIVESPEC_CI_LANE"
_PARALLELISM_ENV: str = "LIVESPEC_TEST_PARALLELISM"
_KILL_GRACE_SECONDS: int = 30

# Lines that vary with xdist scheduling or terminal progress, not with the
# suite's verdict: worker chatter, `created: N/N workers`, `N workers [M items]`
# and `....F..  [ 42%]` progress rows.
_NOISE_LINE = re.compile(
    r"^(\[gw\d+\].*|created: \d+/\d+ workers?.*|\d+ workers? \[\d+ items?\].*"
    r"|[.FEsxX]*\s*\[\s*\d+%\])$"
)
_DURATION = re.compile(r"\bin \d+(?:\.\d+)?s(?: \(\d+:\d{2}:\d{2}\))?")


@dataclass(frozen=True, kw_only=True)
class SuiteRun:
    """Outcome of one bounded suite run; `returncode` is None on timeout."""

    returncode: int | None
    output: str
    timed_out: bool


def suite_timeout_seconds(*, environ: Mapping[str, str]) -> int:
    """Return the suite-green timeout; unset, non-numeric or <=0 means the default."""
    raw = environ.get(_TIMEOUT_ENV, "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return DEFAULT_TIMEOUT_SECONDS


def _lane_worker_count(*, environ: Mapping[str, str], visible_cpus: int) -> str:
    """The consumers' own lane-aware rule, for a repo that does not export `test_nprocs`.

    `auto` only on the hosted CI lane (small dedicated runners), then an explicit
    LIVESPEC_TEST_PARALLELISM, then a quarter of the visible CPUs (minimum 1), as
    `just-test-nprocs.sh` and the justfile `test_nprocs` expression compute it.
    Never a bare `auto` elsewhere: in a factory pod xdist's `auto` counts every
    HOST core (32-72) against the pod's 4-cpu quota.
    """
    if environ.get(_LANE_ENV, "local") == "hosted":
        return "auto"
    explicit = environ.get(_PARALLELISM_ENV, "").strip()
    if explicit:
        return explicit
    return str(max(1, visible_cpus // 4))


def suite_pytest_argv(
    *,
    environ: Mapping[str, str],
    test_paths: list[str] | None = None,
    xdist_available: bool,
    visible_cpus: int,
) -> list[str]:
    """Return pytest argv for the suite or the supplied staged test paths."""
    argv = [sys.executable, "-m", "pytest", "--tb=no", "-q"]
    if not xdist_available:
        return [*argv, *(test_paths or [])]
    nprocs = environ.get(_NPROCS_ENV, "").strip() or _lane_worker_count(
        environ=environ, visible_cpus=visible_cpus
    )
    return [*argv, "-n", nprocs, *(test_paths or [])]


def xdist_importable() -> bool:
    """Return True iff pytest-xdist is importable under this interpreter."""
    return importlib.util.find_spec("xdist") is not None


def has_shared_test_support(*, staged_paths: list[str]) -> bool:
    """Return whether staged test material can affect tests it does not name.

    Every file below ``tests/`` other than a ``test_*.py`` test module is
    conservatively shared support.  That includes ``conftest.py``, package
    initializers, fixture modules, and fixture data; any can alter collection
    or behavior outside the named test files.
    """
    return any(
        path.startswith("tests/")
        and not (Path(path).suffix == ".py" and Path(path).name.startswith("test_"))
        for path in staged_paths
    )


def stages_only_shared_test_support(*, staged_paths: list[str], tests_paths: list[str]) -> bool:
    """Return whether shared test support is staged with no test module beside it.

    Such a staging has no test of its own to fail or pass (pytest exits 5), so
    it is never a Red: it is green-verified by the full suite it can affect.
    """
    return has_shared_test_support(staged_paths=staged_paths) and not any(
        Path(path).name.startswith("test_") for path in tests_paths
    )


def canonical_output_checksum(*, output: str) -> str:
    """Checksum the sorted set of non-noise lines, durations normalized.

    Two runs of the same green suite differ in line order (xdist), in
    progress rows, and in elapsed time; none of that may move the digest.
    The pytest summary line (`N passed, M skipped`) is kept, so a changed
    outcome count does.
    """
    lines = {
        _DURATION.sub("in <t>s", line.strip())
        for line in output.splitlines()
        if line.strip() and not _NOISE_LINE.match(line.strip())
    }
    canonical = "\n".join(sorted(lines))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def run_suite(*, argv: list[str], timeout_seconds: int) -> SuiteRun:
    """Run `argv` in its own process group; on timeout kill the whole group."""
    with subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate(timeout=_KILL_GRACE_SECONDS)
            return SuiteRun(returncode=None, output=(stdout or "") + (stderr or ""), timed_out=True)
        return SuiteRun(returncode=proc.returncode, output=stdout + stderr, timed_out=False)


def _handle_suite_green_mode(
    *,
    msg_path: Path,
    log: structlog.stdlib.BoundLogger,
    staged_paths: list[str],
    tests_paths: list[str] | None = None,
) -> int:
    """Green-verify a product/test change that carries no new failing test.

    The green-verified leg (user design correction 2026-06-11): a
    behavior-preserving product change runs the full pytest suite.
    A passing test-only cleanup runs only its staged test modules,
    unless shared support was staged, because support can affect
    tests the commit does not name. Exit 0 is the ONLY green outcome
    (pytest exit 5, zero tests collected, proves nothing and rejects).
    On green, the `TDD-Suite-Green-*` trailer shape (scope, output
    checksum, captured-at — mirroring the Red-leg evidence fields)
    lands in the commit message so the commit-range validation
    recognizes the commit as verified.
    """
    run_touched_tests = bool(tests_paths) and not has_shared_test_support(staged_paths=staged_paths)
    selected_tests = tests_paths if run_touched_tests else None
    scope = "staged-tests" if run_touched_tests else "full-suite"
    log.info(
        "suite-green-candidate: product/test change without a Red leg; selecting replay scope",
        check_id="red-green-replay-suite-green-candidate",
        staged_paths=staged_paths,
        tests_paths=selected_tests,
    )
    xdist_available = xdist_importable()
    if not xdist_available:
        log.warning(
            "suite-green-serial-fallback: pytest-xdist not importable; running the suite serially",
            check_id="red-green-replay-suite-green-serial-fallback",
            hint="Add pytest-xdist to this repo's dev dependencies to parallelize this leg.",
        )
    timeout_seconds = suite_timeout_seconds(environ=os.environ)
    argv = suite_pytest_argv(
        environ=os.environ,
        test_paths=selected_tests,
        xdist_available=xdist_available,
        visible_cpus=len(os.sched_getaffinity(0)),
    )
    log.info(
        "suite-green-argv: pytest invocation",
        check_id="red-green-replay-suite-green-argv",
        argv=argv,
        scope=scope,
        timeout_seconds=timeout_seconds,
    )
    suite_result = run_suite(argv=argv, timeout_seconds=timeout_seconds)
    if suite_result.timed_out:
        timeout_message = (
            f"suite-green-timeout: the suite-green leg exceeded {timeout_seconds}s; the pytest "
            "process group was killed (raise LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS to allow longer)"
        )
        log.error(
            timeout_message,
            check_id="red-green-replay-suite-green-timeout",
            leg="suite-green",
            timeout_seconds=timeout_seconds,
            timeout_env_var="LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS",
            hint=(
                "The suite-green leg is bounded by LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS "
                f"(default 2400, now {timeout_seconds}). Parallelism comes from `test_nprocs`."
            ),
            protocol=RED_GREEN_REPLAY_PROTOCOL,
        )
        return 1
    suite_output = suite_result.output
    if suite_result.returncode != 0:
        log.error(
            "suite-red: selected pytest tests do not pass against the staged tree",
            check_id="red-green-replay-suite-red",
            pytest_returncode=suite_result.returncode,
            failure_summary=" ".join(suite_output.split())[:400],
            hint=(
                "The green-verified leg requires its selected tests to pass (exit 0; "
                "an empty selection, pytest exit 5, also rejects): a behavior-"
                "preserving change must keep every existing test green. If this "
                "change is SUPPOSED to alter behavior, author it via the ritual "
                "instead: Red commit (stage the failing test alone), then Green "
                "amend (stage the impl)."
            ),
            protocol=RED_GREEN_REPLAY_PROTOCOL,
        )
        return 1
    output_checksum = canonical_output_checksum(output=suite_output)
    captured_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_trailers(
        msg_path=msg_path,
        trailers=(
            ("TDD-Suite-Green-Scope", scope),
            ("TDD-Suite-Green-Output-Checksum", output_checksum),
            ("TDD-Suite-Green-Captured-At", captured_at),
        ),
    )
    return 0
