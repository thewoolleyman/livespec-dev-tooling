"""Outside-in test for `livespec_dev_tooling/checks/handoff_dispatch_routing.py`.

The lint scans ACTIVE plan-thread handoffs (`plan/*/handoff.md`, excluding
`plan/archive/`) and fails when a handoff carries the colon-qualified
in-session-implement invocation token `:implement` without a valid per-file
opt-out marker. The rationale (a 2026-07-15 in-session implementation caused by
defective handoff wording) lives in the module docstring.

The check is driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under the
parallel dispatcher, and materially faster. `main()` reads `Path.cwd()`, so the
monkeypatched cwd is the synthetic fixture root.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "handoff_dispatch_routing.py"

_TOKEN = "/livespec-orchestrator-beads-fabro:implement"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the test
    exercises the on-disk module the Red→Green hook inspects, and so `main()`
    can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "handoff_dispatch_routing_under_test", str(_CHECK_PATH)
    )
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


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd`."""
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write_handoff(*, root: Path, thread: str, body: str) -> Path:
    """Create `<root>/plan/<thread>/handoff.md` with `body`."""
    thread_dir = root / "plan" / thread
    thread_dir.mkdir(parents=True, exist_ok=True)
    handoff = thread_dir / "handoff.md"
    handoff.write_text(body, encoding="utf-8")
    return handoff


def _write_epic(*, root: Path, thread: str, body: str) -> Path:
    """Create `<root>/plan/<thread>/epic.md` with `body`."""
    thread_dir = root / "plan" / thread
    thread_dir.mkdir(parents=True, exist_ok=True)
    epic = thread_dir / "epic.md"
    epic.write_text(body, encoding="utf-8")
    return epic


def test_offending_active_handoff_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An active handoff carrying the `:implement` token fails and names the file + route."""
    _write_handoff(
        root=tmp_path,
        thread="force-factory",
        body=f"## Next action\n\nRun `{_TOKEN} bd-ib-abc` to close the child.\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, (
        f"token-bearing active handoff should exit 1; got returncode={result.returncode} "
        f"stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "plan/force-factory/handoff.md" in combined
    ), f"diagnostic must name the offending handoff; stderr={result.stderr!r}"
    assert (
        "impl:" in combined and "Dispatcher" in combined
    ), f"diagnostic must name the factory dispatch route; stderr={result.stderr!r}"
    assert (
        '"level": "error"' in combined
    ), f"offending handoff should emit an error-level finding; stderr={result.stderr!r}"


def test_offending_migrated_epic_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A migrated `epic.md` carrying the `:implement` token fails and names the file."""
    _write_epic(
        root=tmp_path,
        thread="force-factory",
        body=f"# Ledger epic anchor\n\nlivespec-dev-tooling-abc\n\nRun `{_TOKEN} bd-ib-abc`.\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, (
        f"token-bearing migrated epic should exit 1; got returncode={result.returncode} "
        f"stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "plan/force-factory/epic.md" in combined
    assert "impl:" in combined and "Dispatcher" in combined


def test_clean_active_handoff_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An active handoff with no colon-qualified token passes (exit 0)."""
    _write_handoff(
        root=tmp_path,
        thread="work-item-state-machine",
        body="## Next action\n\nDispatch the ready child through the factory drain.\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"clean active handoff should exit 0; got returncode={result.returncode} "
        f"stderr={result.stderr!r}"
    )


def test_prose_implementation_not_flagged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Prose words `implement` / `implementation` (no colon) do not trip the lint."""
    _write_handoff(
        root=tmp_path,
        thread="shell-logic-hardening",
        body=(
            "## Next action\n\n"
            "The factory path is dispatch, not in-session implement. The "
            "implementation of the ready child proceeds via the Dispatcher.\n"
        ),
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"prose 'implementation' must not be flagged; got returncode={result.returncode} "
        f"stderr={result.stderr!r}"
    )


def test_archived_handoff_ignored(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Planning documents under `plan/archive/` are ignored."""
    # Nested archived thread: `plan/archive/<topic>/<doc>.md` is at depth 2, so
    # the single-level active globs never return it.
    nested = tmp_path / "plan" / "archive" / "old-thread"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "handoff.md").write_text(f"Run `{_TOKEN} bd-old`\n", encoding="utf-8")
    (nested / "epic.md").write_text(f"Run `{_TOKEN} bd-old`\n", encoding="utf-8")
    # Degenerate case: a document directly under `plan/archive/` IS matched by
    # the glob, but its parent dir name is `archive`, so the exclusion drops it.
    archive_root = tmp_path / "plan" / "archive"
    (archive_root / "handoff.md").write_text(f"Run `{_TOKEN} bd-root`\n", encoding="utf-8")
    (archive_root / "epic.md").write_text(f"Run `{_TOKEN} bd-root`\n", encoding="utf-8")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"archived plan docs must be ignored; got returncode={result.returncode} "
        f"stderr={result.stderr!r}"
    )


def test_opt_out_with_reason_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The opt-out marker with a non-empty reason suppresses the failure."""
    _write_handoff(
        root=tmp_path,
        thread="factory-outage",
        body=(
            "<!-- handoff-lint: allow-in-session-implement — factory down, "
            "maintainer-approved in-session run 2026-07-15 -->\n\n"
            f"## Next action\n\nRun `{_TOKEN} bd-ib-xyz`.\n"
        ),
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"opt-out marker with a reason should suppress the failure; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_opt_out_without_reason_still_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An opt-out marker with an empty reason does NOT suppress the failure."""
    _write_handoff(
        root=tmp_path,
        thread="sloppy-optout",
        body=(
            "<!-- handoff-lint: allow-in-session-implement —  -->\n\n"
            f"## Next action\n\nRun `{_TOKEN} bd-ib-xyz`.\n"
        ),
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, (
        f"empty-reason opt-out must not suppress the failure; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_no_plan_dir_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo with no `plan/` directory passes trivially (exit 0)."""
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (
        result.returncode == 0
    ), f"missing plan/ dir should exit 0; got returncode={result.returncode}"


def test_plan_dir_without_handoffs_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `plan/` directory with a thread but no `handoff.md` passes trivially."""
    (tmp_path / "plan" / "reasoning-only").mkdir(parents=True, exist_ok=True)
    (tmp_path / "plan" / "reasoning-only" / "notes.md").write_text("thinking\n", encoding="utf-8")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (
        result.returncode == 0
    ), f"plan/ with no active handoff should exit 0; got returncode={result.returncode}"


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
