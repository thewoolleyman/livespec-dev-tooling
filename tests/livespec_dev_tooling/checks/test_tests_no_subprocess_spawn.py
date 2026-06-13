"""Outside-in test for `livespec_dev_tooling/checks/tests_no_subprocess_spawn.py`.

The `check-tests-no-subprocess-spawn` check is a defense-in-depth +
perf guard (epic 7us, work-item livespec-dev-tooling-4i5). It flags
test files under the consumer's `tests/` tree that spawn a Python
subprocess — `subprocess.run`/`Popen`/`call`/`check_output`/
`check_call` whose argv contains `sys.executable` (or a literal
`python`/`python3`). Such a child, run under `pytest --cov`, self-
instruments via the pth-installed `COVERAGE_PROCESS_START` hook and
writes `.coverage.*` that races concurrent coverage runs under the
parallel check dispatcher — the 7us.6 flaky "No data to report" bug.
The in-process `main()` invocation pattern spawns no instrumented
child AND is materially faster (no process spawn / venv resolution /
coverage subprocess startup).

The check steers authors to the in-process default:
`monkeypatch.chdir(tmp_path)` + `capsys` + `rc = main()`. A
`subprocess_spawn_allowlist` array under `[tool.livespec_dev_tooling]`
in the consumer's `pyproject.toml` exempts test files that genuinely
need a real subprocess (git / commit-refuse-hook / CLI-binary
behavior); those allowlisted tests MUST scrub `COVERAGE_PROCESS_START`
+ `COV_CORE_*` from the child env so the child does not self-instrument.

This test drives `main()` IN-PROCESS (monkeypatch.chdir + capsys),
both to dogfood the recommended default and so the new check does not
flag its own test file.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "tests_no_subprocess_spawn.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and
    so `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "tests_no_subprocess_spawn_under_test",
        str(_CHECK_PATH),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_pyproject(*, root: Path, allowlist: tuple[str, ...]) -> None:
    """Write a minimal `pyproject.toml` declaring the dev-tooling block.

    Declares `tests_tree_prefix = "tests/"` so the check walks the
    fixture's `tests/` dir, plus the `subprocess_spawn_allowlist` array
    seeded with `allowlist` so the allowlist code path is exercised.
    """
    lines = [
        "[tool.livespec_dev_tooling]",
        'tests_tree_prefix = "tests/"',
        "subprocess_spawn_allowlist = [",
    ]
    for entry in allowlist:
        lines.append(f'    "{entry}",')
    lines.append("]")
    _ = (root / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_test_file(*, root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")


_SPAWNING_TEST_BODY = (
    "from __future__ import annotations\n"
    "\n"
    "import subprocess\n"
    "import sys\n"
    "\n"
    "\n"
    "def test_spawns_a_python_child() -> None:\n"
    "    result = subprocess.run(\n"
    '        [sys.executable, "-c", "print(1)"],\n'
    "        capture_output=True,\n"
    "        text=True,\n"
    "        check=False,\n"
    "    )\n"
    "    assert result.returncode == 0\n"
)

_INPROCESS_TEST_BODY = (
    "from __future__ import annotations\n"
    "\n"
    "\n"
    "def test_calls_main_in_process(*, monkeypatch, tmp_path, capsys) -> None:\n"
    "    # In-process invocation: no subprocess, no instrumented child.\n"
    "    monkeypatch.chdir(tmp_path)\n"
    "    assert tmp_path.is_dir()\n"
)


def test_flags_test_file_that_spawns_python_subprocess(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `tests/` file doing `subprocess.run([sys.executable, ...])` fails the check.

    Fixture: `tests/test_spawner.py` spawns a `sys.executable` child.
    The check, invoked in-process with cwd monkeypatched to the
    fixture root and an EMPTY allowlist, must walk `tests/`, detect the
    spawn, exit non-zero, and surface the offending file in its
    diagnostic — naming the in-process `main()` alternative.
    """
    module = _load_check_module()
    _write_pyproject(root=tmp_path, allowlist=())
    _write_test_file(root=tmp_path, rel="tests/test_spawner.py", body=_SPAWNING_TEST_BODY)

    monkeypatch.chdir(tmp_path)
    rc = module.main()

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert rc != 0, (
        f"check should reject a `tests/` file spawning a sys.executable child; "
        f"got rc={rc} stdout={captured.out!r} stderr={captured.err!r}"
    )
    assert "tests/test_spawner.py" in combined, (
        f"diagnostic must surface the offending file; "
        f"stdout={captured.out!r} stderr={captured.err!r}"
    )
    assert "main()" in combined, (
        f"diagnostic must name the in-process `main()` alternative; "
        f"stdout={captured.out!r} stderr={captured.err!r}"
    )


def test_accepts_allowlisted_spawning_file(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An allowlisted `tests/` file that spawns a subprocess passes (exit 0).

    Same spawning fixture, but the file's path prefix is listed in
    `subprocess_spawn_allowlist`, so the check exempts it.
    """
    module = _load_check_module()
    _write_pyproject(root=tmp_path, allowlist=("tests/test_spawner.py",))
    _write_test_file(root=tmp_path, rel="tests/test_spawner.py", body=_SPAWNING_TEST_BODY)

    monkeypatch.chdir(tmp_path)
    rc = module.main()

    captured = capsys.readouterr()
    assert rc == 0, (
        f"check should exempt an allowlisted spawning file; "
        f"got rc={rc} stdout={captured.out!r} stderr={captured.err!r}"
    )


def test_accepts_in_process_test_file(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `tests/` file using only the in-process pattern passes (exit 0)."""
    module = _load_check_module()
    _write_pyproject(root=tmp_path, allowlist=())
    _write_test_file(root=tmp_path, rel="tests/test_inprocess.py", body=_INPROCESS_TEST_BODY)

    monkeypatch.chdir(tmp_path)
    rc = module.main()

    captured = capsys.readouterr()
    assert rc == 0, (
        f"check should accept an in-process-only test file; "
        f"got rc={rc} stdout={captured.out!r} stderr={captured.err!r}"
    )


def test_accepts_tree_without_tests_directory(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo cwd with no `tests/` directory passes (exit 0)."""
    module = _load_check_module()
    _write_pyproject(root=tmp_path, allowlist=())

    monkeypatch.chdir(tmp_path)
    rc = module.main()

    captured = capsys.readouterr()
    assert rc == 0, (
        f"check should accept a tree with no tests/ dir; "
        f"got rc={rc} stdout={captured.out!r} stderr={captured.err!r}"
    )


# A single fixture exercising every detection branch of the check's AST
# walk, driven end-to-end through `main()` (no private-member access).
# The three python-argv spawns (sys.executable / python / python3) must
# be flagged; every other call shape must be ignored.
_ALL_SHAPES_TEST_BODY = (
    "from __future__ import annotations\n"
    "\n"
    "import os\n"
    "import subprocess\n"
    "import sys\n"
    "from subprocess import Popen\n"
    "\n"
    "\n"
    "def test_all_call_shapes() -> None:\n"
    "    subprocess.run([sys.executable, '-c', 'pass'])  # flagged (sys.executable)\n"
    "    Popen(['python', '-c', 'pass'])  # flagged (python literal, bare-name call)\n"
    "    subprocess.check_output(['python3'])  # flagged (python3 literal)\n"
    "    subprocess.run(['git', 'init'])  # non-python literal — ignored\n"
    "    subprocess.run([sys.platform])  # attribute != executable — ignored\n"
    "    subprocess.run([cfg.executable])  # executable attr, base != sys — ignored\n"
    "    subprocess.run([cmd])  # Name argv0 — ignored\n"
    "    subprocess.run(argv)  # Name first arg, not a list literal — ignored\n"
    "    subprocess.run()  # no positional args — ignored\n"
    "    helper()  # bare Name call, not a subprocess func — ignored\n"
    "    os.path.join(x)  # attribute call, not a subprocess func — ignored\n"
    "    factory()[0]()  # call whose func is a Subscript — ignored\n"
)


def test_detection_distinguishes_every_call_shape(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every AST detection branch is exercised end-to-end through `main()`.

    The fixture file mixes the three python-argv spawns with eight
    non-spawn call shapes (non-python literal, `sys.platform` attribute,
    a non-`sys` `.executable` attribute, Name argv0, Name first arg, no
    args, a bare-name non-subprocess call, an attribute non-subprocess
    call, and a Subscript-func call). With an empty allowlist the check
    must fail, surfacing exactly the three spawning lines (the
    `def`-offset places them at fixture lines 10, 11, 12).
    """
    module = _load_check_module()
    _write_pyproject(root=tmp_path, allowlist=())
    _write_test_file(root=tmp_path, rel="tests/test_shapes.py", body=_ALL_SHAPES_TEST_BODY)

    monkeypatch.chdir(tmp_path)
    rc = module.main()

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert rc != 0, (
        f"check should flag the python-argv spawns; "
        f"got rc={rc} stdout={captured.out!r} stderr={captured.err!r}"
    )
    for line in ('"line": 10', '"line": 11', '"line": 12'):
        assert (
            line in combined
        ), f"diagnostic must surface flagged line {line!r}; combined={combined!r}"
    # Exactly three findings (one JSON object per offending line) — no
    # non-python call shape leaked into the offender set.
    assert (
        combined.count('"failure_mode": "python_subprocess_spawn"') == 3
    ), f"expected exactly 3 spawn findings; combined={combined!r}"


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main().

    Closes the `_VENDOR_DIR` already-present branch and the
    `if __name__ == "__main__":` else-arm for per-file 100%.
    """
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
