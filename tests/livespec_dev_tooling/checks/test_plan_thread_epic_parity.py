"""Outside-in test for `plan_thread_epic_parity`.

Ratified Planning Lane v197 stores the plan anchor in ledger epic metadata and
keeps handoff entries in the ledger timeline. Parity therefore compares live and
archived plan directories with same-tenant ledger epics that name their
`plan_slug`; it no longer reads `plan/*/handoff.md` or `plan/*/epic.md`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import NamedTuple, Protocol

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "plan_thread_epic_parity.py"
_HELPER_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "_plan_thread_ledger.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path."""
    spec = importlib.util.spec_from_file_location(
        "plan_thread_epic_parity_under_test", str(_CHECK_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_helper_module() -> ModuleType:
    """Import the ledger helper fresh from its file path."""
    spec = importlib.util.spec_from_file_location(
        "plan_thread_ledger_under_test", str(_HELPER_PATH)
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


class _SubprocessRun(Protocol):
    """Typed stand-in for `subprocess.run` monkeypatches."""

    def __call__(self, *args: object, **kwargs: object) -> SimpleNamespace:
        """Return the configured completed-process-like object."""
        ...


def _fake_subprocess_run(*, result: SimpleNamespace) -> _SubprocessRun:
    """Return a typed subprocess.run replacement."""

    def _run(*args: object, **kwargs: object) -> SimpleNamespace:
        _ = args
        _ = kwargs
        return result

    return _run


def _arm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set both the RUN lever and the beads credential so the check is armed."""
    monkeypatch.setenv("LIVESPEC_RUN_PLAN_EPIC_PARITY", "1")
    monkeypatch.setenv("BEADS_DOLT_PASSWORD", "not-a-real-secret")


def _disarm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the arming env so the check self-skips."""
    monkeypatch.delenv("LIVESPEC_RUN_PLAN_EPIC_PARITY", raising=False)
    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)


def _run(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    items: list[dict[str, object]] | None = None,
) -> _CheckRun:
    """Invoke `main()` in-process under `cwd` with an injected item reader."""

    def _items(*, repo: Path) -> list[dict[str, object]]:
        assert repo == cwd
        return items or []

    monkeypatch.chdir(cwd)
    rc = _MODULE.main(item_reader=_items)
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _mkdir(*, root: Path, relative: str) -> None:
    """Create a plan fixture directory."""
    _ = (root / relative).mkdir(parents=True, exist_ok=True)


def _write_livespec_config(*, root: Path, prefix: str = "livespec-dev-tooling") -> None:
    """Create a minimal `.livespec.jsonc` carrying the store prefix."""
    body = "\n".join(
        (
            "{",
            '  "implementation": { "plugin": "livespec-orchestrator-beads-fabro" },',
            '  "livespec-orchestrator-beads-fabro": {',
            f'    "connection": {{ "prefix": "{prefix}" }}',
            "  }",
            "}",
            "",
        )
    )
    _ = (root / ".livespec.jsonc").write_text(
        body,
        encoding="utf-8",
    )


def _epic(
    *,
    item_id: str,
    status: str,
    slug: str,
    resolution: str | None = None,
) -> dict[str, object]:
    """Return a plan-epic record with all recognized slug carriers populated."""
    return {
        "id": item_id,
        "type": "epic",
        "status": status,
        "resolution": resolution,
        "metadata": {"plan_slug": slug},
        "notes": f"plan_slug={slug}",
        "spec_commitment_hint": f"plan:{slug}",
        "depends_on": [],
    }


def test_unarmed_lever_skips(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without the RUN lever the check self-skips even with drift present."""
    _disarm(monkeypatch)
    _mkdir(root=tmp_path, relative="plan/live")

    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_epic(item_id="livespec-dev-tooling-e1", status="closed", slug="live")],
    )

    assert result.returncode == 0
    assert "skipped" in (result.stdout + result.stderr)


def test_armed_active_closed_epic_fails_from_ledger_metadata(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: an active plan whose metadata anchor epic is closed fails."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _mkdir(root=tmp_path, relative="plan/drift")

    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_epic(item_id="livespec-dev-tooling-e1", status="done", slug="drift")],
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "plan/drift" in combined
    assert "livespec-dev-tooling-e1" in combined
    assert '"disposition": "re-scoped"' in combined


def test_armed_active_open_epic_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: an active plan whose metadata anchor epic is open passes."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _mkdir(root=tmp_path, relative="plan/live")

    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_epic(item_id="livespec-dev-tooling-e1", status="backlog", slug="live")],
    )

    assert result.returncode == 0, result.stderr


def test_armed_non_plan_metadata_without_slug_is_ignored(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: ordinary ledger metadata without `plan_slug` is not a crash."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _mkdir(root=tmp_path, relative="plan/live")
    ordinary_record: dict[str, object] = {
        "id": "livespec-dev-tooling-task",
        "type": "task",
        "status": "open",
        "metadata": {"priority": "normal"},
    }

    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[
            ordinary_record,
            _epic(item_id="livespec-dev-tooling-e1", status="backlog", slug="live"),
        ],
    )

    assert result.returncode == 0, result.stderr


def test_armed_archived_open_epic_fails_from_ledger_metadata(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: an archived plan whose metadata anchor epic is open fails."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _mkdir(root=tmp_path, relative="plan/archive/premature")

    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_epic(item_id="livespec-dev-tooling-e1", status="ready", slug="premature")],
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "plan/archive/premature" in combined
    assert "livespec-dev-tooling-e1" in combined


def test_armed_missing_active_anchor_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: an active plan with no same-tenant metadata anchor is unreadable drift."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _mkdir(root=tmp_path, relative="plan/missing")

    result = _run(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys, items=[])

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "plan/missing" in combined
    assert "missing ledger epic metadata anchor" in combined


def test_armed_cross_tenant_anchor_ignored(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: a plan epic outside the repo-derived tenant prefix is ignored."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path, prefix="overseer")
    _mkdir(root=tmp_path, relative="plan/live")

    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_epic(item_id="livespec-dev-tooling-e1", status="done", slug="live")],
    )

    assert result.returncode == 1
    assert "missing ledger epic metadata anchor" in (result.stdout + result.stderr)


def test_armed_archived_regroomed_anchor_with_open_replacement_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: archived procedural anchor closure is invalid while replacements stay open."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _mkdir(root=tmp_path, relative="plan/archive/regroomed")
    anchor = _epic(
        item_id="livespec-dev-tooling-5asgvm",
        status="done",
        slug="regroomed",
        resolution="no-longer-applicable",
    )
    replacement: dict[str, object] = {
        "id": "livespec-dev-tooling-slice",
        "status": "ready",
        "resolution": None,
        "depends_on": ["livespec-dev-tooling-5asgvm"],
    }

    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[anchor, replacement],
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "plan/archive/regroomed" in combined
    assert "livespec-dev-tooling-5asgvm" in combined
    assert "livespec-dev-tooling-slice" in combined


def test_parse_status_variants() -> None:
    """`_parse_status` remains as the legacy status parser alias."""
    parse = _MODULE._parse_status  # noqa: SLF001  — private helper under test
    assert parse(text='noise\n{"status": "done"}') == "done"
    assert parse(text='[{"status": "closed"}]') == "closed"
    assert parse(text="no json here") is None
    assert parse(text="[]") is None


def test_ledger_helper_parses_records_and_dependency_shapes() -> None:
    """The extracted helper reads issue records and both known dependency edge shapes."""
    assert _HELPER_PATH.is_file(), "ledger helper module should exist"
    helper = _load_helper_module()
    assert helper.parse_records(text='noise\n{"data": [{"id": "a"}]}') == [{"id": "a"}]
    assert helper.parse_records(text='{"id": "a"}') == [{"id": "a"}]
    assert helper.parse_records(text='[{"id": "a"}, 7]') == [{"id": "a"}]
    assert helper.parse_records(text="123") == []
    assert helper.depends_on(record={"depends_on": ["anchor"]}, epic_id="anchor")
    assert helper.depends_on(
        record={"dependencies": [{"depends_on_id": "anchor"}]},
        epic_id="anchor",
    )
    assert helper.depends_on(record={"dependencies": [{"id": "anchor"}]}, epic_id="anchor")
    assert not helper.depends_on(record={"dependencies": [7]}, epic_id="anchor")
    assert helper.record_id(record={"id": "desc"}) == "desc"
    assert helper.record_id(record={"id": 7}) is None
    assert helper.is_completion_closed(record={"status": "done", "resolution": "completed"})
    assert not helper.is_completion_closed(record={"status": "ready", "resolution": None})


def test_ledger_helper_item_reader_uses_export_then_bd(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The helper prefers local `.beads/issues.jsonl`, else parses `bd list --json`."""
    assert _HELPER_PATH.is_file(), "ledger helper module should exist"
    helper = _load_helper_module()
    beads_dir = tmp_path / ".beads"
    _ = beads_dir.mkdir()
    _ = (beads_dir / "issues.jsonl").write_text('{"id":"from-export"}\n', encoding="utf-8")
    assert helper.bd_items_reader(repo=tmp_path) == [{"id": "from-export"}]
    other_repo = tmp_path / "other"
    _ = other_repo.mkdir()
    fake = SimpleNamespace(returncode=0, stdout='{"data":[{"id":"from-bd"}]}', stderr="")
    monkeypatch.setattr(helper.subprocess, "run", _fake_subprocess_run(result=fake))
    assert helper.bd_items_reader(repo=other_repo) == [{"id": "from-bd"}]
    failed = SimpleNamespace(returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr(helper.subprocess, "run", _fake_subprocess_run(result=failed))
    assert helper.bd_items_reader(repo=other_repo) == []


def test_bd_status_reader_ok(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The default reader returns the parsed status when `bd` exits 0 (no real spawn)."""
    fake = SimpleNamespace(returncode=0, stdout='{"status": "done"}', stderr="")
    monkeypatch.setattr(_MODULE.subprocess, "run", _fake_subprocess_run(result=fake))
    read = _MODULE._bd_status_reader  # noqa: SLF001  — private helper under test
    assert read(epic_id="livespec-dev-tooling-l2sm", repo=tmp_path) == "done"


def test_bd_status_reader_nonzero_returns_none(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The default reader returns None when `bd` exits non-zero."""
    fake = SimpleNamespace(returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr(_MODULE.subprocess, "run", _fake_subprocess_run(result=fake))
    read = _MODULE._bd_status_reader  # noqa: SLF001  — private helper under test
    assert read(epic_id="livespec-dev-tooling-l2sm", repo=tmp_path) is None


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
