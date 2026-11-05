"""The warm-cache populator skips a values file that opts out (bd-ib-dqxcsh)."""

from __future__ import annotations

import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "ci-runner" / "k3s" / "phase2" / "warm-cache" / "converge-warm-cache.sh"
_VALUES = _ROOT / "ci-runner" / "k3s" / "phase2" / "arc"


def _dry_run_repositories(*, values_dir: Path) -> list[str]:
    completed = subprocess.run(
        ["bash", str(_SCRIPT), "--dry-run"],
        env={"PATH": "/usr/bin:/bin", "WARM_CACHE_VALUES_DIR": str(values_dir)},
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.startswith("  https://github.com/")
    ]


def test_a_values_file_marked_warm_cache_exclude_is_not_a_populator_target(tmp_path: Path) -> None:
    (tmp_path / "values-kept.yaml").write_text(
        'githubConfigUrl: "https://github.com/thewoolleyman/kept"\n'
    )
    (tmp_path / "values-skipped.yaml").write_text(
        '# warm-cache: exclude\ngithubConfigUrl: "https://github.com/thewoolleyman/skipped"\n'
    )
    assert _dry_run_repositories(values_dir=tmp_path) == ["https://github.com/thewoolleyman/kept"]


def test_the_committed_fabro_values_file_is_excluded_from_the_populator() -> None:
    repositories = _dry_run_repositories(values_dir=_VALUES)
    assert "https://github.com/thewoolleyman/fabro" not in repositories
    assert "https://github.com/thewoolleyman/livespec-dev-tooling" in repositories
