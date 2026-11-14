"""Consumer scenario: a test loop over os.environ fails on every host.

SPECIFICATION/scenarios.md, "a test loop over os.environ fails the
ambient-environment check on every host, while a single-expression rewrite
passes" (livespec-dev-tooling-dpkz32). This drives the shipped
`no_ambient_environment_loops` check against a fixture consumer tree twice: once
with a `GIT_` variable in the process environment and once with none, and reads
the repository's own `just check` aggregate for the wiring that makes a failure
reach the required gate.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE = "livespec_dev_tooling.checks.no_ambient_environment_loops"
_LOOP = '    for name in [n for n in os.environ if n.startswith("GIT_")]:\n'
_LOOP_FILE = (
    "import os\n\n\ndef test_scrub(monkeypatch):\n"
    + _LOOP
    + "        monkeypatch.delenv(name)  # pragma: no cover\n"
)
_ALIAS_FILE = (
    "import os\n\n\ndef test_scrub(monkeypatch):\n"
    "    env = dict(os.environ)\n"
    '    for name in [n for n in env if n.startswith("GIT_")]:\n'
    "        monkeypatch.delenv(name)\n"
)
_REWRITE_FILE = (
    "import os\n\n\ndef test_scrub(monkeypatch):\n"
    '    _ = [monkeypatch.delenv(n) for n in os.environ if n.startswith("GIT_")]\n'
)


def _verdict(
    *, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[tuple[object, object, object]]]:
    tests = root / "tests"
    tests.mkdir(parents=True)
    _ = (root / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\ntests_tree_prefix = "tests/"\n', encoding="utf-8"
    )
    _ = (tests / "test_loop.py").write_text(_LOOP_FILE, encoding="utf-8")
    _ = (tests / "test_alias.py").write_text(_ALIAS_FILE, encoding="utf-8")
    _ = (tests / "test_rewrite.py").write_text(_REWRITE_FILE, encoding="utf-8")
    monkeypatch.chdir(root)
    code = importlib.import_module(_MODULE).main()
    records = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.strip()]
    failures = [(r["file"], r["line"], r["rewrite"]) for r in records if r["status"] == "fail"]
    return code, failures


def test_a_loop_over_os_environ_fails_on_every_host_while_the_rewrite_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = [monkeypatch.delenv(n) for n in list(os.environ) if n.startswith("GIT_")]
    without_git = _verdict(root=tmp_path / "bare", monkeypatch=monkeypatch, capsys=capsys)
    monkeypatch.setenv("GIT_AMBIENT_PROBE", "1")
    with_git = _verdict(root=tmp_path / "git", monkeypatch=monkeypatch, capsys=capsys)

    rewrite = "_ = [monkeypatch.delenv(name) for name in [n for n in {} if n.startswith('GIT_')]]"
    assert with_git == without_git
    assert without_git == (
        4,
        [
            ("tests/test_alias.py", 6, rewrite.format("env")),
            ("tests/test_loop.py", 5, rewrite.format("os.environ")),
        ],
    )


def test_the_check_is_a_member_of_the_just_check_aggregate() -> None:
    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    targets = (_REPO_ROOT / "check-targets.txt").read_text(encoding="utf-8")

    assert "\n        check-no-ambient-environment-loops\n" in justfile
    assert f"\ncheck-no-ambient-environment-loops:\n    uv run python -m {_MODULE}\n" in justfile
    assert "\ncheck-no-ambient-environment-loops  #" in targets
