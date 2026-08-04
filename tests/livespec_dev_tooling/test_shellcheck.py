"""Tests for tracked shell discovery and ShellCheck JSON normalization."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from returns.pipeline import is_successful

from livespec_dev_tooling.shellcheck import (
    ShellCorpusEmpty,
    ShellFinding,
    discover_tracked_shell_files,
    run_shellcheck,
)

__all__: list[str] = []


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


def _init_repo(*, repo_root: Path) -> None:
    _git(cwd=repo_root, args=["init", "-q"])
    _git(cwd=repo_root, args=["config", "user.email", "test@test.test"])
    _git(cwd=repo_root, args=["config", "user.name", "Test User"])


def _track_all(*, repo_root: Path) -> None:
    _git(cwd=repo_root, args=["add", "-A"])


def test_discovery_includes_tracked_shell_files_in_ordinary_and_dot_directories(
    *,
    tmp_path: Path,
) -> None:
    _init_repo(repo_root=tmp_path)
    ordinary = tmp_path / "scripts" / "clean.sh"
    dotted = tmp_path / ".claude" / "hooks" / "guard.sh"
    untracked = tmp_path / "scripts" / "untracked.sh"
    ordinary.parent.mkdir(parents=True)
    dotted.parent.mkdir(parents=True)
    _ = ordinary.write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
    _ = dotted.write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
    _ = untracked.write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "scripts/clean.sh", ".claude/hooks/guard.sh"])

    result = discover_tracked_shell_files(repo_root=tmp_path)

    assert result.unwrap() == (
        Path(".claude/hooks/guard.sh"),
        Path("scripts/clean.sh"),
    )


def test_shellcheck_failing_control_reports_expected_code_and_normalized_record(
    *,
    tmp_path: Path,
) -> None:
    _init_repo(repo_root=tmp_path)
    script = tmp_path / "scripts" / "fail.sh"
    script.parent.mkdir()
    _ = script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "name='one two'",
                "printf '%s\\n' $name",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _track_all(repo_root=tmp_path)

    result = run_shellcheck(repo_root=tmp_path)

    assert result.unwrap() == (
        ShellFinding(
            path=Path("scripts/fail.sh"),
            code="SC2086",
            severity="info",
        ),
    )


def test_shellcheck_clean_control_reports_no_findings(*, tmp_path: Path) -> None:
    _init_repo(repo_root=tmp_path)
    script = tmp_path / "scripts" / "clean.sh"
    script.parent.mkdir()
    _ = script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "printf '%s\\n' \"${HOME}\"",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _track_all(repo_root=tmp_path)

    result = run_shellcheck(repo_root=tmp_path)

    assert result.unwrap() == ()


def test_empty_shell_corpus_fails_explicitly(*, tmp_path: Path) -> None:
    _init_repo(repo_root=tmp_path)
    readme = tmp_path / "README.md"
    _ = readme.write_text("no shell here\n", encoding="utf-8")
    _track_all(repo_root=tmp_path)

    result = run_shellcheck(repo_root=tmp_path)

    assert not is_successful(result)
    failure = result.failure()
    assert isinstance(failure, ShellCorpusEmpty)
    assert failure.repo_root == tmp_path


def test_missing_shellcheck_binary_fails_with_actionable_domain_error(
    *,
    tmp_path: Path,
) -> None:
    _init_repo(repo_root=tmp_path)
    script = tmp_path / "scripts" / "clean.sh"
    script.parent.mkdir()
    _ = script.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
        encoding="utf-8",
    )
    _track_all(repo_root=tmp_path)

    try:
        result = run_shellcheck(
            repo_root=tmp_path,
            shellcheck_bin="definitely-not-shellcheck",
        )
    except TypeError as exc:  # pragma: no cover
        pytest.fail(  # pragma: no cover
            f"expected an actionable shellcheck failure, got TypeError: {exc}"
        )

    shellcheck_module = pytest.importorskip("livespec_dev_tooling.shellcheck")
    shellcheck_unavailable = shellcheck_module.ShellCheckUnavailable
    assert not is_successful(result)
    failure = result.failure()
    assert isinstance(failure, shellcheck_unavailable)
    assert failure.binary_name == "definitely-not-shellcheck"
    assert failure.required_version == "0.11.0"
    assert failure.remedy == (
        "install ShellCheck 0.11.0 and expose it on PATH, for example with "
        "`mise install shellcheck@0.11.0` from the consumer repo"
    )
