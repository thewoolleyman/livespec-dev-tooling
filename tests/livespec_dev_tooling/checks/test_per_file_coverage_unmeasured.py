"""Tests for `per_file_coverage`'s report of first-party files no test imports.

Coverage.py lists only the modules a test run imported, and the verifier walks
only the files coverage measured. A first-party module that nothing imports is
therefore never judged, although the ratified rule is 100% line and branch
coverage across the whole first-party surface. The verifier enumerates the
repository's git-tracked `.py` files under its declared `source_tree_prefixes`
and names every one the coverage data does not hold.

Each fixture builds a real git repository at `tmp_path` (the enumeration reads
the git index), declares `source_tree_prefixes` in its `pyproject.toml`, and
writes a hand-authored `.coverage` through `CoverageData`. The check is driven
in-process, like its sibling test file.
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest
from coverage import CoverageData

__all__: list[str] = []


class _CheckRun(NamedTuple):
    returncode: int
    stderr: str


def _git(*, cwd: Path, args: list[str]) -> None:
    # S603/S607: argv is a fixed list (literal git binary + fixture-controlled
    # args); no untrusted shell input. The env drops every GIT_* variable a
    # surrounding hook injected, so the fixture never reaches the outer repo.
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _build_repo(*, root: Path, extra_pyproject: str = "") -> None:
    """A git repo with one measured file, one unmeasured file and one outside the prefix."""
    (root / "src").mkdir()
    (root / "other").mkdir()
    _ = (root / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_tree_prefixes = ["src/"]\n' + extra_pyproject,
        encoding="utf-8",
    )
    body = "from __future__ import annotations\n__all__: list[str] = []\n"
    for rel in ("src/measured.py", "src/orphan.py", "other/outside.py"):
        _ = (root / rel).write_text(body, encoding="utf-8")
    _git(cwd=root, args=["init", "-q"])
    _git(cwd=root, args=["add", "-A"])
    data = CoverageData(basename=str(root / ".coverage"), suffix=False)
    data.add_lines({str(root / "src" / "measured.py"): [1, 2]})
    data.write()


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("COVERAGE_FILE", raising=False)
    module = importlib.import_module("livespec_dev_tooling.checks.per_file_coverage")
    rc = module.main()
    return _CheckRun(returncode=rc, stderr=capsys.readouterr().err)


def test_unmeasured_first_party_file_is_reported_as_a_warning_by_default(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A tracked file under a source prefix the data lacks is named; the exit status holds."""
    _build_repo(root=tmp_path)

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert "src/orphan.py" in result.stderr
    assert "unmeasured" in result.stderr
    assert "src/measured.py" not in result.stderr


def test_unmeasured_first_party_file_fails_the_check_when_the_repo_opts_in(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`fail_on_unmeasured_first_party = true` turns the finding into a non-zero exit."""
    _build_repo(root=tmp_path, extra_pyproject="fail_on_unmeasured_first_party = true\n")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0
    assert "src/orphan.py" in result.stderr
    assert '"level": "error"' in result.stderr


def test_opt_out_spelling_keeps_the_finding_a_warning(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An explicit `false` is the same as the absent key: the exit status is unchanged."""
    _build_repo(root=tmp_path, extra_pyproject="fail_on_unmeasured_first_party = false\n")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert "src/orphan.py" in result.stderr


def test_opt_in_with_nothing_unmeasured_still_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The opt-in fails only on a finding: with every tracked file measured it exits 0."""
    _build_repo(root=tmp_path, extra_pyproject="fail_on_unmeasured_first_party = true\n")
    data = CoverageData(basename=str(tmp_path / ".coverage"), suffix=False)
    data.add_lines({str(tmp_path / "src" / name): [1, 2] for name in ("measured.py", "orphan.py")})
    data.write()

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert "unmeasured" not in result.stderr


def _load_opt_in(*, repo_root: Path) -> bool | None:
    loader = getattr(
        importlib.import_module("livespec_dev_tooling.config"),
        "load_fail_on_unmeasured_first_party",
        None,
    )
    assert loader is not None, "config must expose load_fail_on_unmeasured_first_party"
    return loader(repo_root=repo_root)


def test_opt_in_loader_is_none_without_a_pyproject_or_block_or_key(*, tmp_path: Path) -> None:
    """Absent file, absent block and absent key all read as `None`: not opted in."""
    assert _load_opt_in(repo_root=tmp_path / "missing") is None
    _ = (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    assert _load_opt_in(repo_root=tmp_path) is None
    _ = (tmp_path / "pyproject.toml").write_text("[tool.livespec_dev_tooling]\n", encoding="utf-8")
    assert _load_opt_in(repo_root=tmp_path) is None


def test_opt_in_loader_reads_the_boolean_and_rejects_anything_else(*, tmp_path: Path) -> None:
    """The key is a boolean; a string is a schema violation like every sibling key."""
    config_module = importlib.import_module("livespec_dev_tooling.config")
    pyproject = tmp_path / "pyproject.toml"
    _ = pyproject.write_text(
        "[tool.livespec_dev_tooling]\nfail_on_unmeasured_first_party = true\n", encoding="utf-8"
    )
    assert _load_opt_in(repo_root=tmp_path) is True
    _ = pyproject.write_text(
        '[tool.livespec_dev_tooling]\nfail_on_unmeasured_first_party = "yes"\n', encoding="utf-8"
    )
    with pytest.raises(config_module.ConfigParseError):
        _ = _load_opt_in(repo_root=tmp_path)
