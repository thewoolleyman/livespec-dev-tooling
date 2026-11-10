"""Consumer scenario for a delegated gate Job path that ignores the skip variable.

The delegated client keeps an authority member out of a gate Job by naming it
under the repository's own skip variable, and that holds only when the recipe
the Job actually runs reads the variable.  This drives the shipped check in a
fixture consumer process, the same boundary at which pinning repositories use
it, against the route shapes the fleet sweep of 2026-11-08 measured.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE = "livespec_dev_tooling.checks.delegated_job_authority_skip"
_LEVER = "LIVESPEC_FAIL_IF_DELEGATED_JOB_RUNS_AUTHORITY_MEMBERS"
_MEMBER = "check-ledger-thing"

_INVENTORY = f"check-alpha\n{_MEMBER}  # authority: ledger\n"

_CHECK_RECIPE_TAIL = """\
    targets=(
        check-alpha
        check-ledger-thing
    )
"""

# The aggregate recipe reads the skip list and hands it to the runner script,
# which is the shape the fleet's `check` recipes take.
_JUSTFILE_HEAD = f"""\
check:
    #!/usr/bin/env bash
    set -uo pipefail
{_CHECK_RECIPE_TAIL}    read -ra skip_targets <<< "${{SKIP_TARGETS:-}}"
    bash scripts/aggregate.sh "${{skip_targets[@]}}"

check-skipping *skip_targets:
    bash scripts/aggregate.sh "$@"

check-pre-commit-gated-tree:
    bash scripts/gated-tree.sh

check-pre-push:
    bash scripts/pre-push.sh

check-alpha:
    true

check-ledger-thing:
    true

check-fixed-a:
    true

check-fixed-b:
    true
"""

_RUNNER = 'for target in "$@"; do echo "skipping $target"; done\n'

_PRE_COMMIT_UNHONOURED = "just check-skipping check-red-green-replay\n"
_PRE_COMMIT_SCRIPT_READ = (
    'read -ra delegated_skip <<< "${SKIP_TARGETS:-}"\n'
    'just check-skipping check-red-green-replay "${delegated_skip[@]}"\n'
)
_PRE_COMMIT_UNION = (
    'SKIP_TARGETS="${SKIP_TARGETS:+$SKIP_TARGETS }check-red-green-replay" just check\n'
)
_PRE_COMMIT_FIXED_LIST = "just check-fixed-a\njust check-fixed-b\n"
_PRE_COMMIT_THROUGH_CHECK = "just hook_gate=1 check\n"
_PRE_PUSH_UNHONOURED = "just check-skipping\n"


def _run_check(*, root: Path, armed: bool) -> subprocess.CompletedProcess[str]:
    """Run the shipped consumer check without inheriting coverage instrumentation."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COVERAGE_", "COV_CORE_", "LIVESPEC_FAIL_IF_"))
    }
    environment["PYTHONPATH"] = str(_REPO_ROOT)
    if armed:
        environment[_LEVER] = "true"
    return subprocess.run(
        [sys.executable, "-m", _MODULE],
        cwd=str(root),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_repository(
    *,
    root: Path,
    flags: tuple[str, ...],
    gate_script: str,
    gate_script_name: str,
    gate_check_suite: tuple[str, ...] | None = None,
    inventory: str = _INVENTORY,
) -> None:
    """Lay out a consumer repository whose delegated Job runs `gate_script_name`."""
    suite = ""
    if gate_check_suite is not None:
        entries = ", ".join(f'"{entry}"' for entry in gate_check_suite)
        suite = f"gate_check_suite = [{entries}]\n"
    _ = (root / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n" + "".join(f"{flag} = true\n" for flag in flags) + suite,
        encoding="utf-8",
    )
    _ = (root / "check-targets.txt").write_text(inventory, encoding="utf-8")
    _ = (root / "justfile").write_text(_JUSTFILE_HEAD, encoding="utf-8")
    scripts = root / "scripts"
    scripts.mkdir()
    _ = (scripts / "aggregate.sh").write_text(_RUNNER, encoding="utf-8")
    _ = (scripts / gate_script_name).write_text(gate_script, encoding="utf-8")


@pytest.mark.parametrize(
    ("flag", "gate_script_name", "gate_script", "gate_check_suite", "path", "job_recipe"),
    [
        (
            "delegated_pre_commit",
            "gated-tree.sh",
            _PRE_COMMIT_UNHONOURED,
            None,
            "pre-commit",
            "check-pre-commit-gated-tree",
        ),
        (
            "delegated_gate",
            "pre-push.sh",
            _PRE_PUSH_UNHONOURED,
            ("bootstrap", "check-pre-push"),
            "pre-push",
            "check-pre-push",
        ),
    ],
)
def test_delegated_path_that_ignores_the_skip_variable_is_reported(
    *,
    tmp_path: Path,
    flag: str,
    gate_script_name: str,
    gate_script: str,
    gate_check_suite: tuple[str, ...] | None,
    path: str,
    job_recipe: str,
) -> None:
    """A Job route reaching the aggregate without the skip read names path, recipe, member."""
    _write_repository(
        root=tmp_path,
        flags=(flag,),
        gate_script=gate_script,
        gate_script_name=gate_script_name,
        gate_check_suite=gate_check_suite,
    )

    armed = _run_check(root=tmp_path, armed=True)
    warned = _run_check(root=tmp_path, armed=False)

    output = armed.stdout + armed.stderr
    assert armed.returncode == 1, output
    assert path in output
    assert job_recipe in output
    assert _MEMBER in output
    assert warned.returncode == 0, warned.stdout + warned.stderr
    assert _MEMBER in warned.stdout + warned.stderr


@pytest.mark.parametrize(
    ("gate_script", "gate_check_suite"),
    [
        (_PRE_COMMIT_THROUGH_CHECK, ("hook_gate=1 check",)),
        (_PRE_COMMIT_SCRIPT_READ, None),
        (_PRE_COMMIT_UNION, None),
        (_PRE_COMMIT_FIXED_LIST, None),
    ],
)
def test_delegated_path_that_honours_the_skip_variable_is_not_reported(
    *, tmp_path: Path, gate_script: str, gate_check_suite: tuple[str, ...] | None
) -> None:
    """A route reading, carrying, or never reaching the aggregate draws no finding."""
    _write_repository(
        root=tmp_path,
        flags=("delegated_pre_commit",),
        gate_script=gate_script,
        gate_script_name="gated-tree.sh",
        gate_check_suite=gate_check_suite,
    )

    completed = _run_check(root=tmp_path, armed=True)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert _MEMBER not in completed.stdout + completed.stderr


@pytest.mark.parametrize(
    ("flags", "inventory"),
    [
        ((), _INVENTORY),
        (("delegated_pre_commit", "delegated_gate"), "check-alpha\n"),
    ],
)
def test_repository_with_nothing_to_judge_passes_with_no_finding(
    *, tmp_path: Path, flags: tuple[str, ...], inventory: str
) -> None:
    """No delegated path, or no declared authority member, leaves nothing to report."""
    _write_repository(
        root=tmp_path,
        flags=flags,
        gate_script=_PRE_COMMIT_UNHONOURED,
        gate_script_name="gated-tree.sh",
        inventory=inventory,
    )

    completed = _run_check(root=tmp_path, armed=True)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout + completed.stderr == ""
