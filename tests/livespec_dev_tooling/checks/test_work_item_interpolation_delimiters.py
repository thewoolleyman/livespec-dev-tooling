"""Outside-in test for `work_item_interpolation_delimiters`.

A work item whose own text reproduces a literal doubled-brace
template-interpolation delimiter pair makes itself undispatchable. The check
sweeps NON-CLOSED ledger records for that pair, reports an editable field and an
append-only comment under DISTINCT verdicts, and names the offending work-item id
and field for every finding.

The hazardous token is never written literally in this file, for the same reason
the check never writes it: a goal that inlines this source would carry the pair
into the brief it is inlined into. Both delimiters are BUILT from single braces.

The module is imported INSIDE each test via `importlib`, and the loader's first
assertion is that the module file exists — so the Red leg of this slice failed on
a genuine assertion rather than on a collection-time `ModuleNotFoundError`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import NamedTuple, Protocol

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = (
    _REPO_ROOT / "livespec_dev_tooling" / "checks" / "work_item_interpolation_delimiters.py"
)

# Built, never written literally — see the module docstring.
_OPEN = "{" * 2
_CLOSE = "}" * 2
_SUBSTITUTE_OPEN = "⟦"
_SUBSTITUTE_CLOSE = "⟧"
_ITEM = "livespec-dev-tooling-9yb4"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path."""
    assert _CHECK_PATH.is_file(), f"check module should exist at {_CHECK_PATH}"
    spec = importlib.util.spec_from_file_location(
        "work_item_interpolation_delimiters_under_test", str(_CHECK_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CheckRun(NamedTuple):
    """The exit code plus everything the check emitted."""

    returncode: int
    output: str


class _SubprocessRun(Protocol):
    """Typed stand-in for `subprocess.run` monkeypatches."""

    def __call__(self, *args: object, **kwargs: object) -> SimpleNamespace:
        """Return the configured completed-process-like object."""
        ...


def _fake_subprocess_run(*, result: SimpleNamespace) -> _SubprocessRun:
    """Return a typed `subprocess.run` replacement that never spawns."""

    def _run(*args: object, **kwargs: object) -> SimpleNamespace:
        _ = args
        _ = kwargs
        return result

    return _run


def _arm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set both the RUN lever and the beads credential so the check is armed."""
    monkeypatch.setenv("LIVESPEC_RUN_WORK_ITEM_INTERPOLATION_DELIMITERS", "1")
    monkeypatch.setenv("BEADS_DOLT_PASSWORD", "not-a-real-secret")


def _run(
    *,
    module: ModuleType,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    items: list[dict[str, object]],
    comments: dict[str, list[dict[str, object]]] | None = None,
) -> _CheckRun:
    """Invoke `main()` in-process under `cwd` with injected ledger readers."""
    timeline = comments or {}

    def _items(*, repo: Path) -> list[dict[str, object]]:
        assert repo == cwd
        return items

    def _comments(*, repo: Path, item_id: str) -> list[dict[str, object]]:
        assert repo == cwd
        return timeline.get(item_id, [])

    monkeypatch.chdir(cwd)
    rc = module.main(item_reader=_items, comment_reader=_comments)
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, output=captured.out + captured.err)


def _record(*, status: str = "backlog", **fields: object) -> dict[str, object]:
    """Return a ledger record carrying `fields` at the given status."""
    return {"id": _ITEM, "status": status, **fields}


def test_unarmed_lever_skips(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without the RUN lever the check self-skips even with contamination present."""
    module = _load_check_module()
    monkeypatch.delenv("LIVESPEC_RUN_WORK_ITEM_INTERPOLATION_DELIMITERS", raising=False)
    monkeypatch.setenv("BEADS_DOLT_PASSWORD", "not-a-real-secret")

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_record(description=f"runs-on: {_OPEN} vars.X {_CLOSE}")],
    )

    assert result.returncode == 0
    assert "skipped" in result.output


def test_lever_without_credential_skips(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The lever alone does not arm the check; the tenant credential is also required."""
    module = _load_check_module()
    monkeypatch.setenv("LIVESPEC_RUN_WORK_ITEM_INTERPOLATION_DELIMITERS", "1")
    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_record(description=f"runs-on: {_OPEN} vars.X {_CLOSE}")],
    )

    assert result.returncode == 0
    assert "skipped" in result.output


def test_armed_empty_ledger_read_is_a_failure_not_a_clean_sweep(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An armed check that inspected nothing reports that, rather than passing."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(module=module, cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys, items=[])

    assert result.returncode == 1
    assert "zero ledger records" in result.output


def test_contaminated_editable_field_fails_naming_item_and_field(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-closed record whose description carries the pair fails, named precisely."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_record(description=f"runs-on: {_OPEN} vars.CI_RUNNER_LABELS {_CLOSE}")],
    )

    assert result.returncode == 1
    assert _ITEM in result.output
    assert '"field": "description"' in result.output
    assert '"verdict": "editable-repair-in-place"' in result.output
    assert '"delimiter": "open"' in result.output
    assert '"delimiter": "close"' in result.output
    assert "docs/work-item-interpolation-delimiters.md" in result.output


def test_substituted_text_passes_on_the_same_item(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same item passes once rewritten with the documented substitution characters."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[
            _record(
                description=(
                    f"runs-on: {_SUBSTITUTE_OPEN} vars.CI_RUNNER_LABELS {_SUBSTITUTE_CLOSE}"
                ),
                notes=f"legend: {_SUBSTITUTE_OPEN} opener, {_SUBSTITUTE_CLOSE} closer",
            )
        ],
    )

    assert result.returncode == 0, result.output


@pytest.mark.parametrize("status", ["closed", "done"])
def test_closed_records_are_excluded_from_the_population(
    *,
    status: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Closed items are never dispatched, so their historical contamination is harmless."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_record(status=status, description=f"{_OPEN} vars.X {_CLOSE}")],
        comments={_ITEM: [{"id": "c1", "text": f"{_OPEN} vars.X {_CLOSE}"}]},
    )

    assert result.returncode == 0, result.output


def test_contaminated_comment_yields_a_distinct_verdict(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An append-only comment is unrepairable, so it never shares the editable verdict."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_record(description="clean prose")],
        comments={
            _ITEM: [
                {
                    "id": "comment-7",
                    "created_at": "2026-08-21T09:26:50Z",
                    "text": f"the opener is {_OPEN}",
                    "author": "thewoolleyman",
                }
            ]
        },
    )

    assert result.returncode == 1
    assert '"verdict": "append-only-successor-or-hold"' in result.output
    assert '"verdict": "editable-repair-in-place"' not in result.output
    assert '"field": "comments:comment-7"' in result.output
    assert '"comment_created_at": "2026-08-21T09:26:50Z"' in result.output
    assert "clean-text successor" in result.output


def test_one_comment_reports_each_delimiter_once(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two contaminated strings in one comment are one poisoned comment, not two."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_record()],
        comments={_ITEM: [{"id": "c1", "text": f"first {_OPEN}", "summary": f"second {_OPEN}"}]},
    )

    assert result.returncode == 1
    assert result.output.count('"delimiter": "open"') == 1


def test_metadata_is_scanned_structurally_without_json_serialization(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nested metadata strings are reached; nesting punctuation never invents a finding."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[
            _record(
                metadata={
                    "depth": 3,
                    "nested": {"inner": {"quotes": [f"leading {_OPEN}"]}},
                }
            )
        ],
    )

    assert result.returncode == 1
    assert '"field": "metadata.nested.inner.quotes[0]"' in result.output
    assert result.output.count('"delimiter": "open"') == 1


def test_title_carries_the_same_editable_verdict(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A title contaminated from birth is an editable finding like any other field."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_record(title=f"closer only {_CLOSE}")],
    )

    assert result.returncode == 1
    assert '"field": "title"' in result.output
    assert '"delimiter": "close"' in result.output
    assert '"delimiter": "open"' not in result.output


def test_record_without_a_string_id_is_skipped(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unidentifiable record cannot be named in a finding, so it leaves the population."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[{"status": "backlog", "description": f"{_OPEN} vars.X {_CLOSE}"}],
    )

    assert result.returncode == 0, result.output


def test_default_readers_are_used_when_none_are_injected(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()` with no injected readers falls back to the ledger-backed defaults."""
    module = _load_check_module()
    _arm(monkeypatch)

    def _items(*, repo: Path) -> list[dict[str, object]]:
        _ = repo
        return [_record(description="clean prose")]

    def _comments(*, repo: Path, item_id: str) -> list[dict[str, object]]:
        _ = repo
        _ = item_id
        return [{"id": "c1", "text": f"poisoned {_CLOSE}"}]

    monkeypatch.setattr(module, "bd_items_reader", _items)
    monkeypatch.setattr(module, "_bd_comment_reader", _comments)
    monkeypatch.chdir(tmp_path)

    rc = module.main()
    captured = capsys.readouterr()

    assert rc == 1
    assert '"verdict": "append-only-successor-or-hold"' in captured.out + captured.err


def test_bd_comment_reader_parses_a_zero_exit_show(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default comment reader parses `bd show --json` output (no real spawn)."""
    module = _load_check_module()
    payload = '{"data": [{"id": "x", "comments": [{"id": "c1", "text": "hi"}]}]}'
    fake = SimpleNamespace(returncode=0, stdout=payload, stderr="")
    monkeypatch.setattr(module.subprocess, "run", _fake_subprocess_run(result=fake))

    read = module._bd_comment_reader  # noqa: SLF001  — private helper under test

    assert read(repo=tmp_path, item_id=_ITEM) == [{"id": "c1", "text": "hi"}]


def test_bd_comment_reader_returns_empty_on_nonzero_exit(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed `bd show` yields no comments rather than raising."""
    module = _load_check_module()
    fake = SimpleNamespace(returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr(module.subprocess, "run", _fake_subprocess_run(result=fake))

    read = module._bd_comment_reader  # noqa: SLF001  — private helper under test

    assert read(repo=tmp_path, item_id=_ITEM) == []


def test_comments_of_tolerates_every_absent_shape() -> None:
    """The comment extractor answers for a missing record, a missing key, and junk entries."""
    module = _load_check_module()
    comments_of = module._comments_of  # noqa: SLF001  — private helper under test

    assert comments_of(records=[]) == []
    assert comments_of(records=[{"comments": "not-a-list"}]) == []
    assert comments_of(records=[{"comments": [{"id": "c1"}, 7]}]) == [{"id": "c1"}]


def test_comment_field_is_empty_when_absent_or_non_string() -> None:
    """A comment lacking an id or timestamp still produces a reportable finding."""
    module = _load_check_module()
    field = module._comment_field  # noqa: SLF001  — private helper under test

    assert field(key="id", comment={"id": "c1"}) == "c1"
    assert field(key="id", comment={"id": 7}) == ""
    assert field(key="created_at", comment={}) == ""


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()

    assert callable(module.main), "main should be importable without invocation"
