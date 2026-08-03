"""Tests for the canonical shell-quality policy check."""

from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

import pytest
from returns.primitives.exceptions import UnwrapFailedError

from livespec_dev_tooling.install_worktree_pack import CANONICAL_WORKTREE_JUST_BODY

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "shell_quality.py"

_LEGACY_INTERPOLATED_WORKTREE_JUST = """# Legacy bootstrapped worktree pack fixture.

worktree-create branch base_ref="":
    ./dev-tooling/worktree-lib.sh create {{branch}} {{base_ref}}

worktree-hydrate:
    ./dev-tooling/worktree-lib.sh hydrate

worktree-land base_ref="":
    ./dev-tooling/worktree-lib.sh land {{base_ref}}

worktree-reap *args:
    ./dev-tooling/worktree-lib.sh reap {{args}}
"""


def _git(*, cwd: Path, args: list[str]) -> None:
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


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    assert _CHECK_PATH.is_file(), "shell-quality check module should exist"
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    monkeypatch.chdir(cwd)
    module = importlib.import_module("livespec_dev_tooling.checks.shell_quality")
    rc = module.main()
    captured = capsys.readouterr()
    return rc, captured.err


def test_shellcheck_warning_or_higher_fails_without_baseline(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="scripts/warning.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nRUNNER_UID_HINT=1001\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"check_id": "shell-quality"' in stderr
    assert '"code": "SC2034"' in stderr
    assert '"severity": "warning"' in stderr


def test_documented_no_errexit_deviation_passes(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "# Deliberately omit errexit so every probe can run before summary.",
                "check-all:",
                "    #!/usr/bin/env bash",
                "    set -uo pipefail",
                "    failures=0",
                "    false || failures=$((failures + 1))",
                "    printf '%s\\n' \"${failures}\"",
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0, stderr


def test_multiline_errexit_recipe_fails(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "build:",
                "    #!/usr/bin/env bash",
                "    set -euo pipefail",
                "    python -m build",
                "    python -m twine check dist/*",
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"reason": "nonconforming-just-recipe"' in stderr
    assert '"recipe": "build"' in stderr


def test_accidental_masked_coverage_omission_fails(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "check-per-file-coverage:",
                "    #!/usr/bin/env bash",
                "    set -uo pipefail",
                "    pytest --cov",
                "    python -m coverage_gate",
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"reason": "missing-errexit-rationale"' in stderr
    assert '"recipe": "check-per-file-coverage"' in stderr


def test_just_interpolation_in_recipe_body_fails(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "run arg:",
                "    python tool.py {{arg}}",
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"reason": "just-interpolation"' in stderr
    assert '"recipe": "run"' in stderr


def test_parameterized_recipe_without_per_recipe_positional_arguments_fails(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "set positional-arguments",
                "",
                "run *args:",
                '    scripts/run.sh "$@"',
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/run.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$@\"\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"reason": "global-positional-arguments"' in stderr
    assert '"reason": "missing-per-recipe-positional-arguments"' in stderr
    assert '"recipe": "run"' in stderr


def test_thin_parameterized_recipe_with_per_recipe_positional_arguments_passes(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "[positional-arguments]",
                "run *args:",
                '    scripts/run.sh "$@"',
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/run.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$@\"\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0, stderr


def test_bootstrapped_legacy_worktree_pack_fragment_fails(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(root=tmp_path, rel="justfile", body="import? 'dev-tooling/worktree.just'\n")
    _write(
        root=tmp_path,
        rel="dev-tooling/worktree.just",
        body=_LEGACY_INTERPOLATED_WORKTREE_JUST,
    )
    _write(
        root=tmp_path,
        rel="dev-tooling/worktree-lib.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$@\"\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    for recipe in ("worktree-create", "worktree-land", "worktree-reap"):
        assert f'"recipe": "{recipe}"' in stderr
    assert stderr.count('"reason": "just-interpolation"') == 3
    assert stderr.count('"reason": "missing-per-recipe-positional-arguments"') == 3


def test_bootstrapped_canonical_worktree_pack_fragment_passes(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(root=tmp_path, rel="justfile", body="import? 'dev-tooling/worktree.just'\n")
    _write(root=tmp_path, rel="dev-tooling/worktree.just", body=CANONICAL_WORKTREE_JUST_BODY)
    _write(
        root=tmp_path,
        rel="dev-tooling/worktree-lib.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$@\"\n",
    )
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])

    module = importlib.import_module("livespec_dev_tooling.checks.shell_quality")
    assert hasattr(module, "findings_for_repo")
    assert module.findings_for_repo(repo_root=tmp_path) == []

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0, stderr


def test_empty_shell_corpus_fails_closed(*, tmp_path: Path) -> None:
    _write(root=tmp_path, rel="README.md", body="no tracked shell files\n")
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])

    module = importlib.import_module("livespec_dev_tooling.checks.shell_quality")

    with pytest.raises(UnwrapFailedError):
        module.findings_for_repo(repo_root=tmp_path)
