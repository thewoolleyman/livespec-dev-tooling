"""Outside-in test for `livespec_dev_tooling/checks/agents_ai_references_resolve.py`.

Every concrete `.ai/<topic>.md` reference an `AGENTS.md` declares must
resolve to an existing file relative to that `AGENTS.md`'s directory.

Driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. `main()` reads
`Path.cwd()`, so the monkeypatched cwd is the fixture root — and the
isolation keeps the check from ever scanning the real repo.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "agents_ai_references_resolve.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path so `main()` can run in-process under a monkeypatched
    cwd and so the test exercises the on-disk module.
    """
    spec = importlib.util.spec_from_file_location(
        "agents_ai_references_resolve_under_test", str(_CHECK_PATH)
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
    """Invoke the check's `main()` in-process under `cwd` and capture output."""
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write(*, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _vacuous_events(*, result: _CheckRun) -> list[dict[str, Any]]:
    """The `vacuous` verdict events among the run's structlog JSON lines.

    The check emits nothing to stdout and one JSON object per line to
    stderr, so every captured line decodes — a decode failure here is a
    real regression in the check's output discipline and should surface
    as an error rather than be swallowed.
    """
    events: list[dict[str, Any]] = [
        json.loads(line) for line in (result.stdout + result.stderr).splitlines()
    ]
    return [event for event in events if event.get("verdict") == "vacuous"]


def test_resolving_reference_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AGENTS.md referencing `.ai/foo.md` with a real `.ai/foo.md` → exit 0, no `vacuous`."""
    _write(path=tmp_path / "AGENTS.md", text="See `.ai/foo.md` for detail.\n")
    _write(path=tmp_path / ".ai" / "foo.md", text="# detail\n")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"expected exit 0 for a resolving reference; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert _vacuous_events(result=result) == [], (
        f"a tree with a resolving reference is a genuine PASS, not `vacuous`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_dangling_reference_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AGENTS.md referencing `.ai/missing.md` with no such file → exit 1 + diagnostic."""
    _write(path=tmp_path / "AGENTS.md", text="See `.ai/missing.md` for detail.\n")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"expected non-zero exit for a dangling reference; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert ".ai/missing.md" in combined, (
        f"diagnostic does not surface the dangling reference; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "AGENTS.md" in combined


def test_nested_reference_resolves_relative_to_its_directory(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`sub/AGENTS.md` referencing `.ai/x.md` resolves against `sub/` → exit 0."""
    _write(path=tmp_path / "sub" / "AGENTS.md", text="See `.ai/x.md`.\n")
    _write(path=tmp_path / "sub" / ".ai" / "x.md", text="# nested detail\n")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"expected exit 0 for a directory-relative nested reference; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_archive_agents_md_is_excluded(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dangling reference inside `archive/AGENTS.md` is skipped → exit 0."""
    _write(path=tmp_path / "archive" / "AGENTS.md", text="Old `.ai/gone.md` ref.\n")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"expected exit 0 — archive/ AGENTS.md is excluded from the scan; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_ai_references_is_a_vacuous_warning_not_a_bare_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Zero referenced `.ai/` paths → exit 0, but a `vacuous` WARNING carrying the count.

    A repo may legitimately have no `.ai/` tree, so this is not a
    failure — but the run inspected nothing, so it must not read as a
    proof of reference integrity either (livespec-dev-tooling-xaxj5w).
    """
    _write(path=tmp_path / "AGENTS.md", text="# Agent instructions\n\nNo overflow files.\n")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"expected exit 0 for an AGENTS.md with no .ai/ references; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    vacuous = _vacuous_events(result=result)
    assert len(vacuous) == 1, (
        f"expected exactly one `vacuous` verdict when zero .ai/ paths are referenced; "
        f"got {vacuous!r} from stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert (
        vacuous[0].get("level") == "warning"
    ), f"the `vacuous` verdict must be emitted at WARNING level; got {vacuous[0]!r}"
    assert (
        vacuous[0].get("referenced_paths") == 0
    ), f"the `vacuous` verdict must carry the referenced-path count; got {vacuous[0]!r}"


def test_angle_bracket_placeholder_is_not_a_reference(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `.ai/<topic>.md` placeholder is not treated as a concrete reference → exit 0."""
    _write(
        path=tmp_path / "AGENTS.md",
        text="A member MAY disclose detail into `.ai/<topic>.md` files.\n",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"expected exit 0 — the angle-bracket placeholder is not a concrete reference; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
