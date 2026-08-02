"""Outside-in tests for `testing/_cli_e2e_driver.py` — the `claude -p` runner seam.

Per `livespec/SPECIFICATION/contracts.md` section "CLI end-to-end harness contract",
the Driver component (`RealCliRunner`, `CliRunner`, `CliResult`) shells out to
the real `claude` CLI binary; it is the one injectable, non-deterministic seam.
These tests exercise `RealCliRunner.run`'s argv shape (fresh session vs.
`--resume`) and its `HOME` env injection against a fake `claude` shim on PATH —
no API key, no network: the shim is a tiny script that echoes its argv or
`$HOME`.

Coverage target: 100% line + branch of `_cli_e2e_driver.py`.
"""

from __future__ import annotations

import stat
from pathlib import Path

from livespec_dev_tooling.testing._cli_e2e_driver import RealCliRunner

__all__: list[str] = []


def _install_fake_claude(*, bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "fake-claude"
    _ = shim.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stdout.write(' '.join(sys.argv[1:]))\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return shim


def test_real_cli_runner_fresh_session_argv(*, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    shim = _install_fake_claude(bin_dir=bin_dir)
    runner = RealCliRunner(claude_binary=str(shim))
    result = runner.run(
        prompt="/livespec:seed",
        home=tmp_path / "home",
        cwd=tmp_path,
        resume_session_id=None,
    )
    assert result.exit_code == 0
    assert result.stdout == "-p /livespec:seed"
    assert result.session_id is None


def test_real_cli_runner_resume_session_argv(*, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    shim = _install_fake_claude(bin_dir=bin_dir)
    runner = RealCliRunner(claude_binary=str(shim))
    result = runner.run(
        prompt="/livespec:doctor",
        home=tmp_path / "home",
        cwd=tmp_path,
        resume_session_id="sess-9",
    )
    assert result.stdout == "--resume sess-9 -p /livespec:doctor"


def test_real_cli_runner_sets_home_env(*, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    home = tmp_path / "myhome"
    shim = bin_dir / "echo-home"
    bin_dir.mkdir(parents=True)
    _ = shim.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "sys.stdout.write(os.environ['HOME'])\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    runner = RealCliRunner(claude_binary=str(shim))
    result = runner.run(prompt="x", home=home, cwd=tmp_path, resume_session_id=None)
    assert result.stdout == str(home)
