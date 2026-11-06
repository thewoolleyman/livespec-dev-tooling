"""Scenario "bootstrap names a bare python3 that does not satisfy requires-python".

`SPECIFICATION/non-functional-requirements.md`, "## Developer host platforms": a
developer host's first `python3` on `PATH` must satisfy `pyproject.toml`'s
`requires-python`, and `just bootstrap` names one that does not instead of
installing a replacement. These run the real host check the `bootstrap` recipe
runs first (`scripts/just/check-host-python3.sh`) under bash, against a stub
`python3` of a chosen version and stub `uv` and `mise` that log any call, and
assert:

- an older `python3` is refused naming `python3` and the required version, and
  no interpreter is installed;
- a `python3` at or above the floor passes;
- the `bootstrap` recipe runs the check before anything that could install an
  interpreter.

The required version is read from the committed `pyproject.toml`, so no test
restates it.
"""

from __future__ import annotations

import re
import stat
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK = _REPO_ROOT / "scripts" / "just" / "check-host-python3.sh"


def _floor() -> str:
    pyproject = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    [floor] = re.findall(r'^requires-python = ">=([0-9.]+)"$', pyproject, flags=re.MULTILINE)
    return floor


def _exe(*, path: Path, body: str) -> None:
    _ = path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _host(*, tmp_path: Path, python3_version: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    _ = log.write_text("", encoding="utf-8")
    _exe(path=bin_dir / "python3", body=f'#!/bin/sh\necho "Python {python3_version}"\n')
    for tool in ("uv", "mise"):
        _exe(path=bin_dir / tool, body=f'#!/bin/sh\nprintf "{tool} %s\\n" "$*" >> "{log}"\n')
    return bin_dir


def _check(*, bin_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_CHECK), str(_REPO_ROOT)],
        capture_output=True,
        text=True,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
        check=False,
        timeout=60,
    )


def _older_than(floor: str) -> str:
    major, minor, *_ = (int(part) for part in floor.split("."))
    return f"{major}.{minor - 1}.0" if minor > 0 else f"{major - 1}.99.0"


def test_bootstrap_names_a_bare_python3_that_does_not_satisfy_requires_python(
    *, tmp_path: Path
) -> None:
    floor = _floor()
    bin_dir = _host(tmp_path=tmp_path, python3_version=_older_than(floor))
    result = _check(bin_dir=bin_dir)
    assert result.returncode != 0
    assert "python3" in result.stderr
    assert floor in result.stderr
    assert (tmp_path / "calls.log").read_text(encoding="utf-8") == ""


def test_a_python3_at_the_floor_passes(*, tmp_path: Path) -> None:
    result = _check(bin_dir=_host(tmp_path=tmp_path, python3_version=_floor()))
    assert result.returncode == 0, result.stderr


def test_bootstrap_checks_python3_before_anything_that_could_install_an_interpreter() -> None:
    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    recipe = justfile.split("\nbootstrap:\n", 1)[1].split("\n\n", 1)[0]
    lines = [line.strip() for line in recipe.splitlines() if line.strip()]
    assert lines[0] == "scripts/just/check-host-python3.sh ."
    assert all("check-host-python3" not in line for line in lines[1:])
