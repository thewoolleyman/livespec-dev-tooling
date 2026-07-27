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

THE CEILING IS UNCONDITIONAL (`livespec-dev-tooling-426a`). Every file
in the git-derived universe is gated identically: there is no per-repo
opt-in, no legacy-tree severity classifier, and no `newly_covered` /
`phase="0-warn"` bucket. Fixtures below still write a
`file_lloc_hard_gate` line in places, and that is deliberate — it pins
that the retired key is INERT rather than an error, because eight fleet
repos still carry it from the rollout.

Several fixtures still place files under `.claude-plugin/scripts/livespec`.
That path is no longer privileged; it survives only because these arms
predate the retirement and their subject is the ceiling, not the path.

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

    `file_lloc` itself no longer reads any key off this file — the hard gate is
    unconditional. Fixtures still write one to prove the RETIRED
    `file_lloc_hard_gate` key is inert, and because other config-reading paths
    resolve the `[tool.livespec_dev_tooling]` block from the git-toplevel root.
    It is never part of the `*.py` universe `git ls-files` walks.
    """
    _ = (tmp_path / "pyproject.toml").write_text(body, encoding="utf-8")


def _init_repo_with_files(*, tmp_path: Path) -> None:
    """`git init` the fixture and stage every file already written under it."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])


def test_file_lloc_rejects_hard_offender(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `.py` file with > 250 LLOC fails (exit 1) — the hard ceiling."""
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
    """Invoked from a SUBDIRECTORY, file_lloc still hard-fails a > 250 file.

    file_lloc's PR1 walk anchored on `Path.cwd()`; invoked from a subdir it
    would shell `git ls-files` in that subdir and miss the oversized
    over-ceiling file (a silent exit 0). Re-anchoring on `resolve_repo_root`
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


def test_file_lloc_warns_soft_offender(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `.py` file with 201-250 LLOC passes (exit 0) but warns — the soft band."""
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


def test_file_lloc_accepts_file_below_soft_ceiling(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `.py` file with ≤ 200 LLOC passes silently (no warning, exit 0)."""
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


def test_file_lloc_accepts_file_at_hard_ceiling(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `.py` file at exactly 250 LLOC passes (soft band, exit 0).

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


def test_file_lloc_emits_soft_and_hard_in_one_run(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When both soft and hard offenders exist, hard wins (exit 1) + both diagnostics."""
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


def test_file_lloc_hard_fails_an_over_ceiling_file_with_no_opt_in_declared(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A > 250-LLOC file hard-fails (exit 1) with NO `file_lloc_hard_gate` declared.

    THE RETIREMENT OF THE OPT-IN (livespec-dev-tooling-426a). This file is outside
    the tree that used to be privileged, and the fixture repo declares no
    `[tool.livespec_dev_tooling]` block at all, which used to mean Phase-0 WARN and
    exit 0 -- the ceiling was repo-OPTIONAL, and a repo disarmed it fleet-wide by
    simply never opting in. It is now unconditional: over the hard ceiling is red
    everywhere, and the `newly_covered` / `phase="0-warn"` bucket no longer exists.
    """
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/big.py", n_statements=300)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, (
        f"an over-hard-ceiling file must fail without any opt-in; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "pkg/big.py" in combined
    assert (
        "250-line hard ceiling" in combined
    ), f"the hard-ceiling error must be emitted; combined={combined!r}"
    assert (
        "newly_covered" not in combined
    ), f"the Phase-0 newly_covered bucket is retired; combined={combined!r}"


def test_file_lloc_hard_fails_orchestrator_shaped_repo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo whose package dir is NOT named `livespec/` hard-fails too (exit 1).

    Two separate fail-open holes are pinned by this one arm. The old rglob over
    `.claude-plugin/scripts/livespec` walked ZERO files in a repo shaped like the
    orchestrator (package `livespec_orchestrator_beads_fabro/`, a 2,616-line
    `dispatcher.py`), so the check reported green having scanned nothing; the
    git-derived universe closed that. But the legacy-tree severity classifier
    then kept such a file at WARN no matter how large it was, because it matched
    no hardcoded tree -- so the ceiling was still unenforceable in exactly the
    repos the widening was meant to reach. Both are gone.
    """
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path="livespec_orchestrator_beads_fabro/dispatcher.py",
        n_statements=300,
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, (
        f"a package outside the old privileged tree must be hard-gated; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "livespec_orchestrator_beads_fabro/dispatcher.py" in combined
    assert "250-line hard ceiling" in combined
    assert "newly_covered" not in combined


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


# The RETIRED opt-in key, kept as a fixture to prove it is now inert.
_RETIRED_KEY_BLOCK = "[tool.livespec_dev_tooling]\nfile_lloc_hard_gate = true\n"


def test_file_lloc_retired_key_present_still_hard_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo still carrying `file_lloc_hard_gate = true` hard-fails a > 250 file.

    BACKWARD-COMPATIBILITY ARM. The key is retired and read by nothing; eight
    fleet repos still carry it. This pins that its presence changes nothing —
    the same result the no-key fixtures get. Historically: a repo whose package dir is not
    livespec-core's `.claude-plugin/scripts/livespec/` (here a bare `pkg/`) opts
    its whole git-derived universe into the hard gate via a committed pyproject
    declaration. Before the retirement this same file would only WARN (Phase-0
    newly-covered); with it, the > 250 file exits 1.
    """
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/big.py", n_statements=300)
    _write_pyproject(tmp_path=tmp_path, body=_RETIRED_KEY_BLOCK)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "pkg/big.py" in combined
    assert "hard ceiling" in combined
    # No newly-covered WARN marker: that bucket is retired.
    assert "newly_covered" not in combined


def test_file_lloc_retired_key_present_still_soft_warns(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A 201-250 file soft-warns and passes (exit 0), retired key present or not.

    The two-tier policy is now uniform everywhere — a
    soft band below the hard ceiling — to the whole universe, not just a hard
    cliff.
    """
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/medium.py", n_statements=220)
    _write_pyproject(tmp_path=tmp_path, body=_RETIRED_KEY_BLOCK)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/medium.py" in combined
    assert "soft ceiling" in combined
    assert "newly_covered" not in combined


def test_file_lloc_retired_key_present_all_under_ceiling_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo whose files are all ≤ 200 LLOC passes silently, retired key present."""
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/a.py", n_statements=50)
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/b.py", n_statements=120)
    _write_pyproject(tmp_path=tmp_path, body=_RETIRED_KEY_BLOCK)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "soft ceiling" not in combined
    assert "hard ceiling" not in combined


def test_file_lloc_retired_key_present_empty_universe_is_noop(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A codeless repo (0 first-party `.py`) walks nothing and passes, exit 0."""
    _write_pyproject(tmp_path=tmp_path, body=_RETIRED_KEY_BLOCK)
    _ = (tmp_path / "README.md").write_text("no code here\n", encoding="utf-8")
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "hard ceiling" not in combined


def test_file_lloc_hard_fails_when_a_config_block_exists_without_the_retired_key(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `[tool.livespec_dev_tooling]` block that never mentions the key hard-fails.

    This was the shape of the OMISSION that made enforcement repo-optional: a repo
    carrying a config block for `source_trees` and friends, simply never declaring
    `file_lloc_hard_gate`, kept its over-ceiling files at WARN — and the silence
    read as conformance rather than as an opt-out. The key is retired, so a block
    without it is no longer a way to disarm the ceiling.
    """
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/big.py", n_statements=300)
    _write_pyproject(
        tmp_path=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, (
        f"omitting the retired key must not disarm the ceiling; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "pkg/big.py" in combined
    assert "250-line hard ceiling" in combined
    assert "newly_covered" not in combined


def test_file_lloc_ignores_an_explicit_false_opt_out(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`file_lloc_hard_gate = false` is INERT — the file still hard-fails (exit 1).

    THE ARM THAT MATTERS MOST after the retirement, and the reason the key is not
    merely defaulted to true. A repo could previously write `= false` and switch
    the ceiling off for its whole package. That escape hatch is gone: the key is
    read by nothing, so an explicit opt-OUT no longer opts out of anything.

    It is also the backward-compatibility arm. Eight fleet repos still carry a
    `file_lloc_hard_gate` line from the rollout, and a stale value must not be an
    error — it must simply have no effect, so no repo needs a coordinated edit
    before this lands.
    """
    _write_py_with_lloc(tmp_path=tmp_path, rel_path="pkg/big.py", n_statements=300)
    _write_pyproject(
        tmp_path=tmp_path,
        body="[tool.livespec_dev_tooling]\nfile_lloc_hard_gate = false\n",
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, (
        f"an explicit `= false` must no longer disarm the ceiling; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "pkg/big.py" in combined
    assert "250-line hard ceiling" in combined
    assert "newly_covered" not in combined


def test_file_lloc_retired_key_present_hard_fails_core_tree_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file in the once-privileged core tree still hard-fails (exit 1).

    `.claude-plugin/scripts/livespec/` was one of the three trees the retired
    severity classifier hard-gated while everything else only warned. Removing
    the classifier must not have removed the gate from the trees it did cover —
    the retirement widened enforcement, it did not relocate it.
    """
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/big.py",
        n_statements=300,
    )
    _write_pyproject(tmp_path=tmp_path, body=_RETIRED_KEY_BLOCK)
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
