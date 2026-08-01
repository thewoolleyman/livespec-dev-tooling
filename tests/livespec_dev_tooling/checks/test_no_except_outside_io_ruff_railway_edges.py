"""Green-leg branches the checksum-bound Red file cannot reach — `8o8e.5`.

A SEPARATE file because the Red test file's bytes are pinned by
`TDD-Red-Test-File-Checksum`: any branch that only exists once the conversion
lands needs its own home, and discovering that at the amend costs a rebuild.
This repo's handoff carries it as a standing rule — "budget a `*_edges.py`
sibling into every conversion".

Three groups live here:

1. **`_ruff_enables_ble001`'s `ruff-not-run` propagation.** Reaching it needs a
   `ruff` that ANSWERS `--show-files` and is GONE by `--show-settings`, so the
   shim DELETES ITSELF on its first call. A PATH that never had `ruff` cannot
   reach this branch — it fails at the enumeration one call earlier.
2. **`no_except_outside_io.main()`'s unprobed arm.** The supervisor must report
   "UNVERIFIED, not absent" and exit non-zero. That is the whole point of
   `8o8e.5`: an unprobed backstop used to exit 0.
3. **The Red file's own marker helpers**, whose non-matching branches run at
   the RED moment and never again. Pinning them is the positive control that
   an assertion failure there NAMES what came back instead of printing `False`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import _no_except_outside_io_ruff as subject
from livespec_dev_tooling.checks.no_except_outside_io import main

# The Red file's marker helpers are imported by PATH rather than by package:
# unlike `tests/.../testing/`, this package has no conftest that puts its own
# directory on `sys.path`, and adding one would change shared test infra for a
# two-line import.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_no_except_outside_io_ruff_railway import _gaps_of, _reason_of

_VENDOR_DIR = Path(subject.__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOSuccess  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = []

_SELECT = '[tool.ruff.lint]\nselect = ["BLE"]\n'


def _self_deleting_ruff(*, tmp_path: Path, listed: Path) -> str:
    """A `ruff` that answers `--show-files` once, then removes itself from PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    ruff = bin_dir / "ruff"
    _ = ruff.write_text(
        "#!/bin/sh\n"
        'if [ "$2" = "--show-files" ]; then\n'
        f'  echo "{listed}"\n'
        '  /bin/rm -f "$0"\n'
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    ruff.chmod(0o755)
    return str(bin_dir)


def test_a_ruff_that_vanishes_between_probes_is_named_not_run(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ruff` present for the enumeration and gone for the settings probe.

    Contrived on purpose: it is the only way to reach the second invocation's
    `ruff-not-run` arm, and the arm is real — a PATH change, an upgrade, or a
    container teardown mid-run all produce it.
    """
    root = tmp_path / "probe-root"
    root.mkdir()
    _ = (root / "pyproject.toml").write_text(_SELECT, encoding="utf-8")
    _ = (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setenv("PATH", _self_deleting_ruff(tmp_path=tmp_path, listed=root / "a.py"))

    assert (
        _reason_of(
            outcome=subject.find_ruff_backstop_gaps(
                repo_root=root, scan_roots=(Path(),), inspected_files=(Path("a.py"),)
            )
        )
        == "ruff-not-run"
    ), "a ruff that disappears before the settings probe must be named, not fused"


def test_main_reports_an_unprobed_backstop_and_exits_non_zero(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """⛔ THE POINT OF `8o8e.5`: an UNPROBED backstop used to exit 0.

    Driven in-process (`monkeypatch.chdir` + `main()` + `capsys`) rather than
    by spawning a Python child, which `check-tests-no-subprocess-spawn` bans.
    """
    _ = (tmp_path / "pyproject.toml").write_text(
        (tmp_path / "pyproject.toml").read_text(encoding="utf-8") + "\n" + _SELECT,
        encoding="utf-8",
    )
    # One first-party module under the conftest's declared source tree. Without
    # it the check reports "no first-party Python to check" and exits 0 — which
    # would make this test pass for the wrong reason on a broken probe.
    module = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "mod.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    _ = module.write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n", encoding="utf-8"
    )
    # `git` is resolved from the REAL PATH here, before the monkeypatch below
    # strips it: this repo's git is mise-managed and is not on /usr/bin:/bin.
    git = shutil.which("git")
    assert git is not None, "git must be on PATH to build the fixture repo"
    hermetic = {
        "HOME": str(tmp_path),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "PATH": os.environ.get("PATH", ""),
    }
    for args in (["init", "-q"], ["add", "-A"]):
        _ = subprocess.run(
            [git, *args], cwd=str(tmp_path), capture_output=True, check=True, env=hermetic
        )
    # A PATH carrying `git` but NOT `ruff`: the check derives its universe from
    # `git ls-files`, so stripping PATH wholesale would break the universe walk
    # instead of the ruff probe and the test would pass for the wrong reason.
    only_git = tmp_path / "only-git"
    only_git.mkdir()
    (only_git / "git").symlink_to(git)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(only_git))

    returncode = main()

    assert returncode == 1
    assert "could not be PROBED" in capsys.readouterr().err


def test_the_red_markers_name_what_came_back_instead(*, tmp_path: Path) -> None:
    """The Red file's helpers report the WRONG shape rather than a bare `False`.

    These branches run only at the Red moment, so without this they are dead
    lines at Green — and `check-per-file-coverage` counts TEST files.
    """
    del tmp_path
    assert _reason_of(outcome=IOSuccess([])).startswith("not-a-failure: ")
    assert _gaps_of(outcome=IOFailure("boom")).startswith("not-a-success: ")  # type: ignore[union-attr]
