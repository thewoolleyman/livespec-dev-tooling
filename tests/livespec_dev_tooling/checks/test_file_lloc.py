"""Outside-in test for `livespec_dev_tooling/checks/file_lloc.py` — per-file LLOC policy.

Per `SPECIFICATION/constraints.md` §"File LLOC ceiling" (post-v005):
files at 201-250 LLOC pass with a structured warning (SOFT ceiling);
files above 250 LLOC fail (HARD ceiling). LLOC excludes blank lines,
comment-only lines, and module/class/function docstrings.

The check now resolves the files it inspects from the git-derived
first-party `.py` universe (`config.iter_first_party_py_files`) rather
than a hardcoded `_COVERED_TREES` tuple, so every test builds a real
temp git working tree and `git add`s its files before invoking
`main()` under a monkeypatched cwd — the same hermetic shape the
`iter_first_party_py_files` foundation tests use in
`tests/livespec_dev_tooling/test_config.py`. `git ls-files` reads the
index, so files must be `git add`ed (no commit is needed).

Phase-0 severity: the three legacy trees
(`.claude-plugin/scripts/livespec`, `.claude-plugin/scripts/bin`,
`dev-tooling`) are retained ONLY as a severity classifier. A file
UNDER a legacy tree keeps today's hard gate (soft-warn 201-250,
hard-fail >250, exit 1); a file NEWLY pulled into the git-derived
universe emits every LLOC diagnostic at WARN (even >250, no exit-1
contribution) with a `newly_covered` / `phase="0-warn"` marker, until
Phase 2 flips its repo to the hard gate.

The check is driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` +
`capsys` + `rc = main()`) rather than via a `sys.executable`
subprocess (work-item livespec-dev-tooling-py9). The in-process call
spawns no `COVERAGE_PROCESS_START`-instrumented child (no `.coverage.*`
race under the parallel dispatcher) and is materially faster. `main()`
reads `Path.cwd()`, so the monkeypatched cwd is the fixture root.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FILE_LLOC = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "file_lloc.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and
    so `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location("file_lloc_under_test", str(_FILE_LLOC))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_check_module()


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic env.

    `git` is not a Python spawn (`tests_no_subprocess_spawn` only forbids
    `sys.executable`/`python`/`python3` argv[0]), so this is allowed in
    `tests/`. The env is a hardcoded 3-key dict (never an `os.environ`
    passthrough), so `COVERAGE_PROCESS_START` / `COV_CORE_*` can never leak
    into the child — the same shape `test_config.py` uses for the
    `iter_first_party_py_files` foundation tests.
    """
    # S603/S607: argv is a fixed list (literal git binary + repo-controlled
    # args); no untrusted shell input.
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd` and capture output."""
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write_py_with_lloc(*, tmp_path: Path, rel_path: str, n_statements: int) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    body_lines = "\n".join(f"x_{i} = {i}" for i in range(n_statements))
    full.write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n\n" + body_lines + "\n",
        encoding="utf-8",
    )


def _write_pyproject(*, tmp_path: Path, body: str) -> None:
    """Write a `pyproject.toml` at the fixture root carrying `body`.

    `file_lloc`'s flip lever (`config.load_file_lloc_hard_gate`) reads the
    `[tool.livespec_dev_tooling]` block off this file directly from disk, so it
    need only exist at the git-toplevel root the check resolves — it is never
    part of the `*.py` universe `git ls-files` walks.
    """
    _ = (tmp_path / "pyproject.toml").write_text(body, encoding="utf-8")


def _init_repo_with_files(*, tmp_path: Path) -> None:
    """`git init` the fixture and stage every file already written under it."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])


def test_file_lloc_rejects_legacy_hard_offender(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A legacy-tree `.py` file with > 250 LLOC fails (exit 1) — the hard gate is preserved."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/big.py",
        n_statements=300,
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/livespec/big.py" in combined
    assert "hard ceiling" in combined


def test_file_lloc_anchors_on_repo_root_from_subdirectory(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invoked from a SUBDIRECTORY, file_lloc still hard-fails a legacy-tree > 250 file.

    file_lloc's PR1 walk anchored on `Path.cwd()`; invoked from a subdir it
    would shell `git ls-files` in that subdir and miss the oversized
    legacy-tree file (a silent exit 0). Re-anchoring on `resolve_repo_root`
    (PR2) makes the walk invocation-location-independent, so the hard gate
    fires regardless of cwd depth.
    """
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/big.py",
        n_statements=300,
    )
    subdir = tmp_path / "pkg" / "nested"
    subdir.mkdir(parents=True)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=subdir, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/livespec/big.py" in combined
    assert "hard ceiling" in combined


def test_file_lloc_warns_legacy_soft_offender(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A legacy-tree `.py` file with 201-250 LLOC passes (exit 0) but warns."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "soft ceiling" in combined
    assert ".claude-plugin/scripts/livespec/medium.py" in combined


def test_file_lloc_accepts_legacy_file_below_soft_ceiling(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A legacy-tree `.py` file with ≤ 200 LLOC passes silently (no warning, exit 0)."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/small.py",
        n_statements=50,
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "soft ceiling" not in combined
    assert "hard ceiling" not in combined


def test_file_lloc_accepts_legacy_file_at_hard_ceiling(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A legacy-tree `.py` file at exactly 250 LLOC passes (soft band, exit 0).

    250 is in the soft band (201-250); only > 250 is the hard fail.
    `_write_py_with_lloc` emits 2 setup statements (future-import,
    `__all__`) plus `n_statements` assignments, so 248 statements lands
    at exactly 250 LLOC.
    """
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/edge.py",
        n_statements=248,
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "hard ceiling" not in combined


def test_file_lloc_excludes_blank_lines_and_comments_and_docstrings(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Blank lines, comments, and docstrings do not count toward LLOC."""
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    package_dir.mkdir(parents=True)
    source = package_dir / "padded.py"
    blanks = "\n" * 250
    comments = "\n".join(f"# comment {i}" for i in range(250))
    docstring_lines = "\n".join(f"docstring line {i}" for i in range(250))
    source.write_text(
        f'"""\n{docstring_lines}\n"""\n'
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        f"{blanks}\n"
        f"{comments}\n"
        "\n"
        "x = 0\n"
        "y = 1\n"
        "z = 2\n",
        encoding="utf-8",
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_file_lloc_emits_legacy_soft_and_hard_in_one_run(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When both soft and hard legacy offenders exist, hard wins (exit 1) + both diagnostics."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/big.py",
        n_statements=300,
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "soft ceiling" in combined
    assert "hard ceiling" in combined


def test_file_lloc_warns_newly_covered_hard_offender(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A > 250-LLOC file OUTSIDE the legacy trees WARNS (newly-covered) and passes (exit 0).

    This is the fail-open hole the reroute closes: the old
    `_COVERED_TREES` rglob never saw a file at `pkg/big.py`, so a repo
    with an oversized non-legacy file reported green. The git-derived
    universe now sees it, but Phase-0 severity keeps it at WARN (with a
    `newly_covered` marker) rather than hard-failing.
    """
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/big.py", n_statements=300)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/big.py" in combined
    assert "newly_covered" in combined
    # WARN-not-error: the legacy hard-fail error message must NOT appear.
    assert "250-line hard ceiling" not in combined


def test_file_lloc_warns_orchestrator_shaped_repo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo whose package dir is NOT named `livespec/` (orchestrator shape) WARNS, exit 0.

    The orchestrator's package is `livespec_orchestrator_beads_fabro/`
    with a 2,616-line `dispatcher.py`; the old rglob over
    `.claude-plugin/scripts/livespec` etc. walked zero files there. The
    git-derived universe finds the package regardless of its name, and
    Phase-0 severity emits at WARN, not red.
    """
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path="livespec_orchestrator_beads_fabro/dispatcher.py",
        n_statements=300,
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "livespec_orchestrator_beads_fabro/dispatcher.py" in combined
    assert "newly_covered" in combined
    assert "250-line hard ceiling" not in combined


def test_file_lloc_accepts_codeless_repo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A genuinely codeless repo (0 first-party `.py`) walks nothing and passes (exit 0).

    The verified fleet case is `livespec-console-beads-fabro`; the
    git-derived universe is empty, which is a legitimate result, not an
    error.
    """
    _ = (tmp_path / "README.md").write_text("no code here\n", encoding="utf-8")
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


_HARD_GATE_BLOCK = "[tool.livespec_dev_tooling]\nfile_lloc_hard_gate = true\n"


def test_file_lloc_hard_gate_flip_fails_non_legacy_hard_offender(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With `file_lloc_hard_gate = true`, a NON-legacy > 250 file hard-fails (exit 1).

    This is the flip lever the mechanism adds: a repo whose package dir is not
    livespec-core's `.claude-plugin/scripts/livespec/` (here a bare `pkg/`) opts
    its whole git-derived universe into the hard gate via a committed pyproject
    declaration. Without the flip this same file would only WARN (Phase-0
    newly-covered); with it, the > 250 file exits 1.
    """
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/big.py", n_statements=300)
    _write_pyproject(tmp_path=tmp_path, body=_HARD_GATE_BLOCK)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "pkg/big.py" in combined
    assert "hard ceiling" in combined
    # The flip supersedes the Phase-0 classifier: no newly-covered WARN marker.
    assert "newly_covered" not in combined


def test_file_lloc_hard_gate_flip_warns_non_legacy_soft_offender(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With the flip on, a NON-legacy 201-250 file passes (exit 0) but soft-warns.

    The flip applies the SAME two-tier policy the legacy trees already had — a
    soft band below the hard ceiling — to the whole universe, not just a hard
    cliff.
    """
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/medium.py", n_statements=220)
    _write_pyproject(tmp_path=tmp_path, body=_HARD_GATE_BLOCK)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/medium.py" in combined
    assert "soft ceiling" in combined
    assert "newly_covered" not in combined


def test_file_lloc_hard_gate_flip_all_under_ceiling_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With the flip on, a repo whose files are all ≤ 200 LLOC passes silently."""
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/a.py", n_statements=50)
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/b.py", n_statements=120)
    _write_pyproject(tmp_path=tmp_path, body=_HARD_GATE_BLOCK)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "soft ceiling" not in combined
    assert "hard ceiling" not in combined


def test_file_lloc_hard_gate_flip_empty_universe_is_noop(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A codeless repo (0 first-party `.py`) with the flip on still walks nothing, exit 0."""
    _write_pyproject(tmp_path=tmp_path, body=_HARD_GATE_BLOCK)
    _ = (tmp_path / "README.md").write_text("no code here\n", encoding="utf-8")
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "hard ceiling" not in combined


def test_file_lloc_block_present_but_flip_key_absent_preserves_warn(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `[tool.livespec_dev_tooling]` block WITHOUT the flip key keeps Phase-0 WARN.

    The default-preserving arm for a non-core repo that already carries a config
    block (for `source_trees` etc.) but has not opted in: its > 250 non-legacy
    file WARNs (exit 0), exactly as today.
    """
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/big.py", n_statements=300)
    _write_pyproject(
        tmp_path=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/big.py" in combined
    assert "newly_covered" in combined
    assert "250-line hard ceiling" not in combined


def test_file_lloc_flip_key_false_preserves_warn(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An explicit `file_lloc_hard_gate = false` is identical to today's behavior.

    The explicit-off arm: a repo may write the key `= false` and still get the
    Phase-0 WARN for a non-legacy > 250 file, no exit-1 contribution.
    """
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/big.py", n_statements=300)
    _write_pyproject(
        tmp_path=tmp_path,
        body="[tool.livespec_dev_tooling]\nfile_lloc_hard_gate = false\n",
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/big.py" in combined
    assert "newly_covered" in combined
    assert "250-line hard ceiling" not in combined


def test_file_lloc_hard_gate_flip_still_hard_fails_legacy_tree_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With the flip on, a legacy-tree > 250 file still hard-fails (the gate is a superset).

    The flip widens the hard gate to the whole universe; a file that already
    hard-gated under the legacy classifier keeps hard-gating.
    """
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/big.py",
        n_statements=300,
    )
    _write_pyproject(tmp_path=tmp_path, body=_HARD_GATE_BLOCK)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/livespec/big.py" in combined
    assert "hard ceiling" in combined


def test_file_lloc_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main)
