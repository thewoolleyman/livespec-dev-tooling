"""Outside-in test for `livespec_dev_tooling/checks/plan_thread_epic_parity.py`.

The ledger-state PARITY half of plan-lifecycle enforcement: an ACTIVE plan thread
must not point at a done/closed ledger epic. ARMED-ONLY — self-skips unless both
`LIVESPEC_RUN_PLAN_EPIC_PARITY` and `BEADS_DOLT_PASSWORD` are set. The ledger read
is an injected seam, so the armed path is exercised without a live ledger. Driven
in-process per the repo's no-subprocess test convention; the default `bd` reader
is covered by monkeypatching `subprocess.run` (no real spawn).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "plan_thread_epic_parity.py"
_HELPER_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "_plan_thread_ledger.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path (the tree the RGR hook inspects)."""
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


def _arm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set both the RUN lever and the beads credential so the check is armed."""
    monkeypatch.setenv("LIVESPEC_RUN_PLAN_EPIC_PARITY", "1")
    monkeypatch.setenv("BEADS_DOLT_PASSWORD", "not-a-real-secret")


def _disarm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the arming env so the check self-skips."""
    monkeypatch.delenv("LIVESPEC_RUN_PLAN_EPIC_PARITY", raising=False)
    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)


def _fake_reader(statuses: dict[str, str]):
    """Build a StatusReader that resolves epic ids from a fixed mapping."""

    def _reader(*, epic_id: str, repo: Path) -> str | None:
        _ = repo
        return statuses.get(epic_id)

    return _reader


def _run(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    statuses: dict[str, str] | None = None,
) -> _CheckRun:
    """Invoke `main()` in-process under `cwd` with an injected status reader."""
    monkeypatch.chdir(cwd)
    rc = _MODULE.main(status_reader=_fake_reader(statuses or {}))
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write_handoff(*, root: Path, thread: str, body: str) -> Path:
    """Create `<root>/plan/<thread>/handoff.md` with `body`."""
    thread_dir = root / "plan" / thread
    thread_dir.mkdir(parents=True, exist_ok=True)
    handoff = thread_dir / "handoff.md"
    handoff.write_text(body, encoding="utf-8")
    return handoff


def _write_archived_handoff(*, root: Path, thread: str, body: str) -> Path:
    """Create `<root>/plan/archive/<thread>/handoff.md` with `body`."""
    thread_dir = root / "plan" / "archive" / thread
    thread_dir.mkdir(parents=True, exist_ok=True)
    handoff = thread_dir / "handoff.md"
    handoff.write_text(body, encoding="utf-8")
    return handoff


def _write_livespec_config(*, root: Path, prefix: str = "livespec-dev-tooling") -> None:
    """Create a minimal `.livespec.jsonc` carrying the store prefix."""
    (root / ".livespec.jsonc").write_text(
        (
            "{\n"
            '  "implementation": { "plugin": "livespec-orchestrator-beads-fabro" },\n'
            '  "livespec-orchestrator-beads-fabro": {\n'
            '    "connection": { "prefix": "' + prefix + '" }\n'
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )


def _write_exported_issues(*, root: Path, lines: list[str]) -> None:
    """Create a local beads JSONL export for descendant-edge fixtures."""
    beads_dir = root / ".beads"
    beads_dir.mkdir(parents=True, exist_ok=True)
    (beads_dir / "issues.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _anchor_body(epic_id: str) -> str:
    return f"# H\n\n**Ledger anchor:** epic `{epic_id}`\n"


def test_unarmed_lever_skips(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without the RUN lever the check self-skips (exit 0), even with drift present."""
    _disarm(monkeypatch)
    _write_handoff(root=tmp_path, thread="t", body=_anchor_body("livespec-dev-tooling-l2sm"))
    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        statuses={"livespec-dev-tooling-l2sm": "closed"},
    )
    assert result.returncode == 0, f"un-armed should skip; stderr={result.stderr!r}"
    assert "skipped" in (result.stdout + result.stderr)


def test_armed_lever_but_no_credential_skips(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The lever alone (no `BEADS_DOLT_PASSWORD`) still self-skips."""
    monkeypatch.setenv("LIVESPEC_RUN_PLAN_EPIC_PARITY", "1")
    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)
    _write_handoff(root=tmp_path, thread="t", body=_anchor_body("livespec-dev-tooling-l2sm"))
    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        statuses={"livespec-dev-tooling-l2sm": "closed"},
    )
    assert result.returncode == 0, f"lever-without-cred should skip; stderr={result.stderr!r}"


def test_armed_closed_epic_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: an active thread pointing at a closed epic fails and names the epic."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _write_handoff(root=tmp_path, thread="drift", body=_anchor_body("livespec-dev-tooling-l2sm"))
    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        statuses={"livespec-dev-tooling-l2sm": "done"},
    )
    assert result.returncode == 1, f"active→done epic should fail; stderr={result.stderr!r}"
    combined = result.stdout + result.stderr
    assert "plan/drift/handoff.md" in combined
    assert "livespec-dev-tooling-l2sm" in combined
    assert '"level": "error"' in combined


def test_armed_closed_epic_uses_repo_tenant_prefix(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: same-tenant anchors derive from the repo store prefix, not this package."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path, prefix="overseer")
    _write_handoff(root=tmp_path, thread="drift", body=_anchor_body("overseer-l2sm"))
    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        statuses={"overseer-l2sm": "done"},
    )
    assert result.returncode == 1, f"active→done tenant epic should fail; stderr={result.stderr!r}"
    assert "overseer-l2sm" in (result.stdout + result.stderr)


def test_armed_cross_tenant_anchor_ignored_under_derived_prefix(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: an anchor outside the repo-derived tenant prefix is still ignored."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path, prefix="overseer")
    _write_handoff(
        root=tmp_path,
        thread="xt",
        body=_anchor_body("livespec-dev-tooling-l2sm"),
    )
    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        statuses={"livespec-dev-tooling-l2sm": "closed"},
    )
    assert result.returncode == 0, f"cross-tenant anchor must be ignored; stderr={result.stderr!r}"


def test_armed_open_epic_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: an active thread pointing at an OPEN epic passes."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _write_handoff(root=tmp_path, thread="ok", body=_anchor_body("livespec-dev-tooling-scsj5e"))
    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        statuses={"livespec-dev-tooling-scsj5e": "backlog"},
    )
    assert result.returncode == 0, f"active→open epic should pass; stderr={result.stderr!r}"


def test_armed_archived_open_epic_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: an archived thread pointing at an OPEN epic fails."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _write_archived_handoff(
        root=tmp_path,
        thread="premature",
        body=_anchor_body("livespec-dev-tooling-q3emww"),
    )
    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        statuses={"livespec-dev-tooling-q3emww": "backlog"},
    )
    assert result.returncode == 1, f"archived→open epic should fail; stderr={result.stderr!r}"
    combined = result.stdout + result.stderr
    assert "plan/archive/premature/handoff.md" in combined
    assert "livespec-dev-tooling-q3emww" in combined
    assert '"level": "error"' in combined


def test_armed_archived_regroomed_anchor_with_open_replacement_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: archived procedural anchor closure is invalid while replacements stay open."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _write_archived_handoff(
        root=tmp_path,
        thread="regroomed",
        body=_anchor_body("livespec-dev-tooling-5asgvm"),
    )
    _write_exported_issues(
        root=tmp_path,
        lines=[
            (
                '{"id":"livespec-dev-tooling-5asgvm","status":"done",'
                '"resolution":"no-longer-applicable","depends_on":[]}'
            ),
            (
                '{"id":"livespec-dev-tooling-slice","status":"ready",'
                '"resolution":null,"depends_on":["livespec-dev-tooling-5asgvm"]}'
            ),
        ],
    )
    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        statuses={"livespec-dev-tooling-5asgvm": "done"},
    )
    assert result.returncode == 1, f"open replacement descendant should fail; {result.stderr!r}"
    combined = result.stdout + result.stderr
    assert "plan/archive/regroomed/handoff.md" in combined
    assert "livespec-dev-tooling-5asgvm" in combined
    assert "livespec-dev-tooling-slice" in combined


def test_armed_cross_tenant_anchor_ignored(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: a cross-tenant (non `livespec-dev-tooling-*`) anchor is ignored."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _write_handoff(root=tmp_path, thread="xt", body=_anchor_body("livespec-35s3zo"))
    result = _run(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        statuses={"livespec-35s3zo": "closed"},
    )
    assert result.returncode == 0, f"cross-tenant anchor must be ignored; stderr={result.stderr!r}"


def test_armed_handoff_without_anchor_ignored(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed: an active handoff with no `**Ledger anchor:**` line is skipped, not failed."""
    _arm(monkeypatch)
    _write_livespec_config(root=tmp_path)
    _write_handoff(root=tmp_path, thread="anchorless", body="# H\n\nNo anchor here.\n")
    result = _run(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys, statuses={})
    assert result.returncode == 0, f"anchor-less handoff must be skipped; stderr={result.stderr!r}"


def test_armed_no_plan_dir_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Armed but no `plan/` directory → exit 0."""
    _arm(monkeypatch)
    result = _run(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"armed + no plan/ should exit 0; got {result.returncode}"


def test_parse_status_variants() -> None:
    """`_parse_status` extracts status from dict/list/preamble and tolerates bad shapes."""
    parse = _MODULE._parse_status  # noqa: SLF001  — private helper under test
    assert parse(text='noise\n{"status": "done"}') == "done"
    assert parse(text='[{"status": "closed"}]') == "closed"
    assert parse(text="no json here") is None
    assert parse(text="[]") is None
    assert parse(text="123") is None
    assert parse(text='{"other": 1}') is None
    assert parse(text='{"status": 7}') is None
    assert parse(text="[42]") is None


def test_ledger_helper_parses_records_and_dependency_shapes() -> None:
    """The extracted helper reads issue records and both known dependency edge shapes."""
    assert _HELPER_PATH.is_file(), "ledger helper module should exist"
    helper = _load_helper_module()
    assert helper.parse_records(text='noise\n{"data": [{"id": "a"}]}') == [{"id": "a"}]
    assert helper.parse_records(text='{"id": "a"}') == [{"id": "a"}]
    assert helper.parse_records(text='[{"id": "a"}, 7]') == [{"id": "a"}]
    assert helper.parse_records(text="123") == []
    assert helper.parse_records(text="[]") == []
    assert helper.parse_records(text="no json") == []
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
    _write_exported_issues(root=tmp_path, lines=['{"id":"from-export"}'])
    assert helper.bd_items_reader(repo=tmp_path) == [{"id": "from-export"}]
    other_repo = tmp_path / "other"
    other_repo.mkdir()
    fake = SimpleNamespace(returncode=0, stdout='{"data":[{"id":"from-bd"}]}', stderr="")
    monkeypatch.setattr(helper.subprocess, "run", lambda *_a, **_k: fake)
    assert helper.bd_items_reader(repo=other_repo) == [{"id": "from-bd"}]
    failed = SimpleNamespace(returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr(helper.subprocess, "run", lambda *_a, **_k: failed)
    assert helper.bd_items_reader(repo=other_repo) == []


def test_ledger_helper_status_reader_parses_bd_show(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The helper status reader parses `bd show --json` and returns None on failure."""
    assert _HELPER_PATH.is_file(), "ledger helper module should exist"
    helper = _load_helper_module()
    fake = SimpleNamespace(returncode=0, stdout='{"status":"done"}', stderr="")
    monkeypatch.setattr(helper.subprocess, "run", lambda *_a, **_k: fake)
    assert helper.bd_status_reader(epic_id="livespec-dev-tooling-anchor", repo=tmp_path) == "done"
    failed = SimpleNamespace(returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr(helper.subprocess, "run", lambda *_a, **_k: failed)
    assert helper.bd_status_reader(epic_id="livespec-dev-tooling-anchor", repo=tmp_path) is None


def test_ledger_helper_descendant_offenders_filters_completion_and_tenant(
    *, tmp_path: Path
) -> None:
    """The helper reports only same-tenant descendants that are not completion-closed."""
    assert _HELPER_PATH.is_file(), "ledger helper module should exist"
    helper = _load_helper_module()
    tenant_id_re = _MODULE._tenant_id_re(tenant_prefix="livespec-dev-tooling")  # noqa: SLF001

    def _items(*, repo: Path) -> list[dict[str, object]]:
        assert repo == tmp_path
        return [
            {
                "id": "livespec-dev-tooling-open",
                "status": "ready",
                "resolution": None,
                "depends_on": ["livespec-dev-tooling-anchor"],
            },
            {
                "id": "livespec-dev-tooling-done",
                "status": "done",
                "resolution": "completed",
                "depends_on": ["livespec-dev-tooling-anchor"],
            },
            {
                "id": "other-open",
                "status": "ready",
                "resolution": None,
                "depends_on": ["livespec-dev-tooling-anchor"],
            },
        ]

    offenders = helper.descendant_offenders(
        statuses=[(tmp_path / "handoff.md", "livespec-dev-tooling-anchor", "done")],
        item_reader=_items,
        tenant_id_re=tenant_id_re,
        repo=tmp_path,
    )
    assert offenders == [
        (tmp_path / "handoff.md", "livespec-dev-tooling-anchor", "livespec-dev-tooling-open")
    ]
    assert (
        helper.descendant_offenders(
            statuses=[(tmp_path / "handoff.md", "livespec-dev-tooling-anchor", "ready")],
            item_reader=_items,
            tenant_id_re=tenant_id_re,
            repo=tmp_path,
        )
        == []
    )


def test_bd_status_reader_ok(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The default reader returns the parsed status when `bd` exits 0 (no real spawn)."""
    fake = SimpleNamespace(returncode=0, stdout='{"status": "done"}', stderr="")
    monkeypatch.setattr(_MODULE.subprocess, "run", lambda *_a, **_k: fake)
    read = _MODULE._bd_status_reader  # noqa: SLF001  — private helper under test
    assert read(epic_id="livespec-dev-tooling-l2sm", repo=tmp_path) == "done"


def test_bd_status_reader_nonzero_returns_none(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The default reader returns None when `bd` exits non-zero."""
    fake = SimpleNamespace(returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr(_MODULE.subprocess, "run", lambda *_a, **_k: fake)
    read = _MODULE._bd_status_reader  # noqa: SLF001  — private helper under test
    assert read(epic_id="livespec-dev-tooling-l2sm", repo=tmp_path) is None


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
