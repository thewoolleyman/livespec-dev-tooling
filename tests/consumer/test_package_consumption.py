"""Consumer-tier: the package is consumed via `python -m livespec_dev_tooling.checks.<slug>`.

Covers two `SPECIFICATION/scenarios.md` acceptance scenarios:

- "livespec consumes the package via uv git source"
- "every livespec-impl-* plugin consumes the package via `python -m`"

Both scenarios assert the SAME consumer-observable contract: a shared
check resolves to the package-provided module and runs against the
*consumer's own working tree* (cwd) — no consumer-local copy of the
check is required — completing with exit `0` on a clean tree. This test
exercises that contract directly: it builds a synthetic flat-layout
consumer fixture under `tmp_path` (a `pyproject.toml` declaring its
`[tool.livespec_dev_tooling]` layout plus a clean source module),
invokes a shared check as `python -m livespec_dev_tooling.checks.<slug>`
with `cwd=<fixture>`, and asserts exit `0`.

These are integration/consumer-tier tests, NOT unit tests: they run the
shipped module entrypoint end-to-end as a downstream consumer's
`just check` recipe (`uv run python -m
livespec_dev_tooling.checks.<slug>`) would.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]

# A clean flat-layout consumer fixture: a `pyproject.toml` declaring the
# `[tool.livespec_dev_tooling]` source-tree layout (the documented
# consumer configuration schema) plus one source module with no rule
# violation. The shared `no_inheritance` check reads `source_trees` from
# this block, walks `src/`, finds nothing forbidden, and exits 0 — the
# package-resolves-and-runs-clean contract both scenarios assert.
_CONSUMER_PYPROJECT = (
    "[tool.livespec_dev_tooling]\n"
    'source_trees = ["src"]\n'
    'target_dirs = ["src"]\n'
    'source_tree_prefixes = ["src/"]\n'
)
_CLEAN_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "def greet() -> str:\n"
    '    return "hello"\n'
)


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env.

    The rerouted checks derive their file universe from the git index
    (`config.resolve_check_universe`), so the consumer fixture must be a
    real git working tree. `git` is not a Python spawn, so it is allowed;
    the hardcoded env keeps `COVERAGE_PROCESS_START` out of this child.
    """
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _write_clean_consumer_fixture(*, root: Path) -> None:
    (root / "pyproject.toml").write_text(_CONSUMER_PYPROJECT, encoding="utf-8")
    src = root / "src"
    src.mkdir()
    (src / "mod.py").write_text(_CLEAN_SOURCE, encoding="utf-8")
    _git(cwd=root, args=["init", "-q"])
    _git(cwd=root, args=["add", "-A"])


def _run_check_as_consumer(*, slug: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke a shared check exactly as a consumer's `just check` recipe does.

    `python -m livespec_dev_tooling.checks.<slug>` resolves to the
    package-provided module on `sys.path`; `cwd` is the consumer's working
    tree, which the check reads. No consumer-local copy of the check exists.
    """
    return subprocess.run(
        [sys.executable, "-m", f"livespec_dev_tooling.checks.{slug}"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def test_livespec_consumes_check_via_python_m_on_clean_tree(*, tmp_path: Path) -> None:
    """Scenario: livespec consumes the package via uv git source.

    Every check resolves to the package-provided module and the run
    completes with exit `0` on a clean working tree.
    """
    _write_clean_consumer_fixture(root=tmp_path)

    result = _run_check_as_consumer(slug="no_inheritance", cwd=tmp_path)

    assert result.returncode == 0, (
        f"shared check should resolve to the package module and exit 0 on a "
        f"clean consumer tree; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_impl_plugin_consumes_check_without_local_copy(*, tmp_path: Path) -> None:
    """Scenario: every livespec-impl-* plugin consumes the package via `python -m`.

    The shared check runs against the plugin's working tree with NO
    plugin-local copy of the check present anywhere in the fixture — the
    only `livespec_dev_tooling` code in play is the installed package.
    """
    _write_clean_consumer_fixture(root=tmp_path)
    # Prove no plugin-local copy of any shared check exists in the fixture.
    assert not list(tmp_path.rglob("livespec_dev_tooling")), (
        "fixture must carry no plugin-local copy of the package; the check "
        "must resolve to the installed package only"
    )

    result = _run_check_as_consumer(slug="no_inheritance", cwd=tmp_path)

    assert result.returncode == 0, (
        f"shared check should run against the plugin tree from the installed "
        f"package alone; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_package_entrypoint_importable_via_documented_path() -> None:
    """The package is importable via its documented `python -m` entrypoint.

    A consumer's `pyproject.toml` pins `livespec-dev-tooling` and invokes
    checks as `python -m livespec_dev_tooling.checks.<slug>`; the module must
    therefore be importable as a runnable module. `python -c "import ..."`
    against the installed package is the minimal proof of resolvability.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import livespec_dev_tooling.checks.no_inheritance"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"package check module must be importable via the documented path; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
