"""Consumer-tier: the CI severity-lever parity rule binds only the repository that carries the source.

`SPECIFICATION/contracts.md`, in its gate-surface severity lever rules, states that THIS
repository carries exactly one committed source naming the `LIVESPEC_FAIL_IF_*`
levers its CI workflow arms, and that a check fails when the workflow and that
source disagree. A consuming repository carries no such source: the source is
sourced only by this repository's own `check` recipe and is not shipped by the
pack. Yet consumers run the same shared `ci_matrix_completeness` check, and
their CI workflows arm levers of their own.

Measured 2026-11-10: livespec-overseer master ebbd6c90 (pin v1.190.1) went red
on check-metadata-batch, because the check read the absent source as empty and
reported every lever the consumer's `ci.yml` arms as
`ci-severity-lever-missing-from-source`, which CI's
`LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST` turns into a failure.

Each case runs the shipped check the way a consumer's CI does, as
`python -m livespec_dev_tooling.checks.ci_matrix_completeness` against a
synthetic project with the matrix lever armed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE = "livespec_dev_tooling.checks.ci_matrix_completeness"
_MATRIX_LEVER = "LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST"
_ARMED = (_MATRIX_LEVER, "LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST")
_SOURCE = Path("scripts") / "just" / "gate-surface-severity-levers.sh"


def _write_project(*, root: Path, source_levers: tuple[str, ...] | None) -> None:
    """Lay out a project whose CI arms two levers, with or without a committed source."""
    _ = (root / "canonical.json").write_text(json.dumps({"slugs": []}), encoding="utf-8")
    _ = (root / "justfile").write_text(
        "check:\n" "    #!/usr/bin/env bash\n" "    targets=(\n" "    )\n",
        encoding="utf-8",
    )
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    env = "".join(f"      {lever}: true\n" for lever in _ARMED)
    _ = (workflows / "ci.yml").write_text(
        "name: CI\n"
        "on: [push]\n"
        "jobs:\n"
        "  metadata:\n"
        "    runs-on: ubuntu-latest\n"
        "    env:\n"
        f"{env}"
        "    steps:\n"
        "      - run: true\n"
        "  ci-green:\n"
        "    needs: []\n"
        "    if: always()\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: gate\n"
        "        if: ${{ contains(needs.*.result, 'failure') }}\n"
        "        run: exit 1\n",
        encoding="utf-8",
    )
    if source_levers is not None:
        source = root / _SOURCE
        source.parent.mkdir(parents=True)
        _ = source.write_text(
            "".join(f"export {lever}=true\n" for lever in source_levers), encoding="utf-8"
        )


def _run_check(*, root: Path) -> subprocess.CompletedProcess[str]:
    """Run the shipped check with the matrix lever armed, as consumer CI does."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COVERAGE_", "COV_CORE_", "LIVESPEC_FAIL_IF_"))
    }
    environment["PYTHONPATH"] = str(_REPO_ROOT)
    environment[_MATRIX_LEVER] = "true"
    return subprocess.run(
        [sys.executable, "-m", _MODULE, "--canonical-from", "canonical.json"],
        cwd=str(root),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _lever_findings(*, stderr: str) -> list[dict[str, object]]:
    records = [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]
    return [record for record in records if "lever" in record]


def test_a_consumer_without_the_lever_source_gets_no_lever_parity_finding(
    *, tmp_path: Path
) -> None:
    _write_project(root=tmp_path, source_levers=None)

    result = _run_check(root=tmp_path)

    facts = (result.returncode, _lever_findings(stderr=result.stderr))
    assert facts == (0, []), result.stderr


def test_a_repository_whose_source_misses_an_armed_lever_still_fails_naming_it(
    *, tmp_path: Path
) -> None:
    _write_project(root=tmp_path, source_levers=(_MATRIX_LEVER,))

    result = _run_check(root=tmp_path)

    named = [finding.get("lever") for finding in _lever_findings(stderr=result.stderr)]
    assert (result.returncode, named) == (4, ["LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST"])
