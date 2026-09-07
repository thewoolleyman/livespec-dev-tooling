"""Tests for the CI-path predicate that `check-shell-quality` has a SUBJECT.

Two halves, and BOTH are load-bearing for work-item
livespec-dev-tooling-y6e2.

The first half pins the predicate itself against the workflow shapes that
were actually measured across the fleet on 2026-08-05 — the vacuous one, the
condition-too-narrow one, and the landed fix — so a future edit that re-gates
this repo's pack install away from the shell-quality gate is a red test rather
than a silently vacuous green job.

The second half is the CONTROL the work-item names as the load-bearing one: a
passing gate is not evidence while the gate can be green because its input is
ABSENT. It runs the REAL gate over the CI path's own two inputs — the pack
absent, then a violating pack installed — and asserts the two states are
DISTINGUISHABLE. Absent scores zero findings; violating scores findings. That
contrast is the observation the defect consisted of not having.
"""

from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.ci_shell_quality_subject import (
    PACK_INSTALL_ABSENT,
    PACK_INSTALL_AFTER_GATE,
    PACK_INSTALL_CONDITIONALLY_SKIPPED,
    shell_quality_subject_gaps,
)

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
# The exact command this repo's CI runs to materialize the gate's subject.
# Neutering it is how the positive assertion below proves itself fail-capable.
_CI_INSTALL_COMMAND = "python3 -m livespec_dev_tooling.install_worktree_pack"

# The vacuous shape: a job that runs the gate and never materializes its
# subject. This is what livespec master run 30939328152 reported green.
_VACUOUS_CI = """on:
  push:
jobs:
  check-metadata-batch:
    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Run the batched metadata checks
        run: |
          just check-heading-coverage
          just check-shell-quality
"""

# Install present but AFTER the gate — the pack exists by the time the job
# ends and the gate still read a justfile without it.
_AFTER_GATE_CI = """jobs:
  check-metadata-batch:
    steps:
      - name: Run the batched metadata checks
        run: |
          just check-shell-quality

      - name: Install canonical worktree pack (satisfy invariant)
        run: python3 -m livespec_dev_tooling.install_worktree_pack
"""

# The CONDITION-TOO-NARROW shape measured in five fleet repos: the install
# step exists, runs before the gate, and its `if:` names only the OTHER target
# that needs the pack — so on the shell-quality leg it reports `skipped`.
_CONDITIONED_AWAY_CI = """jobs:
  check-metadata:
    strategy:
      matrix:
        target:
          - check-primary-checkout-commit-refuse-hook-installed
          - check-shell-quality
    steps:
      - name: Install canonical worktree pack (satisfy invariant)
        if: matrix.target == 'check-primary-checkout-commit-refuse-hook-installed'
        run: python3 -m livespec_dev_tooling.install_worktree_pack

      - name: just ${{ matrix.target }}
        run: just ${{ matrix.target }}
"""

# The landed one-line fix (livespec PR 2042 and its six siblings): the same
# step with the second disjunct added, written as the folded scalar the repos
# actually use.
_CONDITIONED_TO_INCLUDE_CI = """jobs:
  check-metadata:
    strategy:
      matrix:
        target:
          - check-primary-checkout-commit-refuse-hook-installed
          - check-shell-quality
    steps:
      - name: Install canonical worktree pack (satisfy invariant)
        if: >-
          matrix.target == 'check-primary-checkout-commit-refuse-hook-installed'
          || matrix.target == 'check-shell-quality'
        run: python3 -m livespec_dev_tooling.install_worktree_pack

      - name: just ${{ matrix.target }}
        run: just ${{ matrix.target }}
"""

# A job that never runs the gate owes it no subject.
_NO_GATE_CI = """jobs:
  check-python:
    steps:
      - name: Run pytest
        run: just check-tests
"""

# Degenerate documents. `_STRAY_MAPPING_CI` carries a non-header mapping line
# at the job indent, which is not a job and must not be read as one.
_NO_JOBS_CI = """on:
  push:
"""
_EMPTY_JOBS_CI = """jobs:
"""
_STRAY_MAPPING_CI = """jobs:
  name: not-a-job
  ci-green:
    needs: [check-metadata-batch]
    runs-on: ubuntu-latest
"""

# A worktree fragment carrying the two violation classes the canonical pack
# was fixed for in livespec-dev-tooling-9ywf: `{{...}}` interpolation into a
# recipe body, and a parameterized recipe with no `[positional-arguments]`.
_VIOLATING_WORKTREE_JUST = """# Violating worktree fragment fixture.

worktree-create branch:
    ./dev-tooling/worktree-lib.sh create {{branch}}
"""
_CLEAN_SHELL_SCRIPT = "#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n"


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a hermetic `git` subcommand — the check derives its corpus from the index."""
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={
            "HOME": str(cwd),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "PATH": os.environ["PATH"],
        },
    )


def _write(*, root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")


def _gate_findings(*, root: Path) -> int:
    """How many findings the REAL shell-quality gate scores against `root`."""
    _git(cwd=root, args=["add", "-A"])
    module = importlib.import_module("livespec_dev_tooling.checks.shell_quality")
    return len(module.findings_for_repo(repo_root=root))


def test_this_repos_ci_gives_the_shell_quality_gate_its_subject() -> None:
    """The positive — and it is asserted FAIL-CAPABLY, which is the whole point.

    "No gaps" against the live document has the same shape as the green job
    this work-item exists about: on its own it is equally consistent with
    "every gate-running job installs the pack" and with "the predicate never
    found the job at all". So the clean read is paired with a NEUTERED copy of
    the same document, whose install command is replaced by a no-op. That copy
    must report a gap and must name the real job — the observation that
    distinguishes the two readings.
    """
    assert _CI_YML.is_file(), "this repo's ci.yml should exist"
    source = _CI_YML.read_text(encoding="utf-8")

    assert shell_quality_subject_gaps(ci_yaml_text=source) == ()

    neutered = source.replace(_CI_INSTALL_COMMAND, "true")
    assert neutered != source, "this repo's ci.yml should run the canonical pack installer"
    gaps = shell_quality_subject_gaps(ci_yaml_text=neutered)
    assert [gap.failure_mode for gap in gaps] == [PACK_INSTALL_ABSENT]
    assert [gap.job for gap in gaps] == ["check-metadata-batch"]


def test_a_job_running_the_gate_without_installing_the_pack_is_a_gap() -> None:
    gaps = shell_quality_subject_gaps(ci_yaml_text=_VACUOUS_CI)

    assert [gap.failure_mode for gap in gaps] == [PACK_INSTALL_ABSENT]
    assert [gap.job for gap in gaps] == ["check-metadata-batch"]


def test_installing_the_pack_after_the_gate_is_a_gap() -> None:
    gaps = shell_quality_subject_gaps(ci_yaml_text=_AFTER_GATE_CI)

    assert [gap.failure_mode for gap in gaps] == [PACK_INSTALL_AFTER_GATE]


def test_an_install_condition_that_excludes_the_gate_leg_is_a_gap() -> None:
    gaps = shell_quality_subject_gaps(ci_yaml_text=_CONDITIONED_AWAY_CI)

    assert [gap.failure_mode for gap in gaps] == [PACK_INSTALL_CONDITIONALLY_SKIPPED]
    assert [gap.job for gap in gaps] == ["check-metadata"]


def test_an_install_condition_that_names_the_gate_leg_is_not_a_gap() -> None:
    assert shell_quality_subject_gaps(ci_yaml_text=_CONDITIONED_TO_INCLUDE_CI) == ()


def test_a_job_that_never_runs_the_gate_owes_it_no_subject() -> None:
    assert shell_quality_subject_gaps(ci_yaml_text=_NO_GATE_CI) == ()


@pytest.mark.parametrize("source", [_NO_JOBS_CI, _EMPTY_JOBS_CI, _STRAY_MAPPING_CI])
def test_a_document_with_no_gate_running_job_yields_no_gaps(*, source: str) -> None:
    """No `jobs:`, an empty one, and a stray mapping line are all answerable."""
    assert shell_quality_subject_gaps(ci_yaml_text=source) == ()


def test_the_gate_cannot_tell_an_absent_pack_from_a_clean_one_without_the_install(
    *, tmp_path: Path
) -> None:
    """THE CONTROL: absent-pack and violating-pack must be DISTINGUISHABLE states.

    Both halves run the real gate over the CI path's own inputs. With the pack
    ABSENT the optional `import?` resolves to nothing, the recipes the gate
    polices do not exist, and the gate scores ZERO findings — a green that
    depends on absence. Install a violating pack, exactly as the CI job's
    install step does, and the same gate scores findings.

    A CI job that runs the gate without the install step therefore reports the
    first number while believing it reported the second.
    """
    _write(root=tmp_path, rel="justfile", body="import? 'dev-tooling/worktree.just'\n")
    _write(root=tmp_path, rel="scripts/ok.sh", body=_CLEAN_SHELL_SCRIPT)
    _git(cwd=tmp_path, args=["init", "-q"])

    assert _gate_findings(root=tmp_path) == 0, "an absent pack must score a vacuous zero"

    _write(root=tmp_path, rel="dev-tooling/worktree.just", body=_VIOLATING_WORKTREE_JUST)
    _write(root=tmp_path, rel="dev-tooling/worktree-lib.sh", body=_CLEAN_SHELL_SCRIPT)

    assert _gate_findings(root=tmp_path) > 0, "an installed violating pack must score findings"
