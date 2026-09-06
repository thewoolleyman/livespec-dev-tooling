"""Outside-in test for `work_item_status_vocabulary`.

A work item that `bd create` left at BEADS status `open` is ranked by nothing:
the orchestrator runtime's `WorkItemStatus` vocabulary does not carry that value,
and `lane_of` passes an unrecognised status straight out as a lane name nothing
consumes. The check sweeps LIVE ledger records for a status outside that declared
vocabulary and names each one, so "not anywhere" becomes loud rather than silent.

The module is imported INSIDE each test via `importlib`, and the loader's first
assertion is that the module file exists — so the Red leg of this slice failed on
a genuine assertion rather than on a collection-time `ModuleNotFoundError`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "work_item_status_vocabulary.py"

_ITEM = "livespec-dev-tooling-e2wv"

# The seven live items measured across the fleet on 2026-08-21 — the population
# the filing enumerates, one of them a P1. Reproduced here as a fixture ledger so
# the naming behaviour is verifiable without the cross-tenant credential.
_MEASURED_FLEET_POPULATION: tuple[tuple[str, int, str], ...] = (
    ("livespec-s43svm.30", 1, "Wedged k3s runner pod (registration-not-found) deadlocks scale-up"),
    ("livespec-s43svm.37", 2, "check-no-workflow-edits accepts a forged canonical slug"),
    ("livespec-s43svm.33", 2, "Canonical-check reconcilers skip 3 of 8 consumers"),
    ("livespec-s43svm.38", 3, "console proof job requests a scale set that does not exist"),
    ("livespec-s43svm.29", 3, "Re-derive ARC maxRunners from measured matrix widths"),
    ("livespec-s43svm.28", 3, "Fate of the orphan local-ci-k3s scale set"),
    ("livespec-dev-tooling-e2wv", 2, "branch_protection_alignment treats a CONDITIONAL leniency"),
)


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path."""
    assert _CHECK_PATH.is_file(), f"check module should exist at {_CHECK_PATH}"
    spec = importlib.util.spec_from_file_location(
        "work_item_status_vocabulary_under_test", str(_CHECK_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CheckRun(NamedTuple):
    """The exit code plus everything the check emitted."""

    returncode: int
    output: str


def _arm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set both the RUN lever and the beads credential so the check is armed."""
    monkeypatch.setenv("LIVESPEC_RUN_WORK_ITEM_STATUS_VOCABULARY", "1")
    monkeypatch.setenv("BEADS_DOLT_PASSWORD", "not-a-real-secret")


def _run(
    *,
    module: ModuleType,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    items: list[dict[str, object]],
) -> _CheckRun:
    """Invoke `main()` in-process under `cwd` with an injected item reader."""

    def _items(*, repo: Path) -> list[dict[str, object]]:
        assert repo == cwd
        return items

    monkeypatch.chdir(cwd)
    rc = module.main(item_reader=_items)
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, output=captured.out + captured.err)


def _record(
    *, item_id: str = _ITEM, status: object = "open", **fields: object
) -> dict[str, object]:
    """Return a ledger record at the given status."""
    return {"id": item_id, "status": status, **fields}


def test_unarmed_lever_skips(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without the RUN lever the check self-skips even with an off-vocabulary item present."""
    module = _load_check_module()
    monkeypatch.delenv("LIVESPEC_RUN_WORK_ITEM_STATUS_VOCABULARY", raising=False)
    monkeypatch.setenv("BEADS_DOLT_PASSWORD", "not-a-real-secret")

    result = _run(
        module=module, cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys, items=[_record()]
    )

    assert result.returncode == 0
    assert "skipped" in result.output


def test_lever_without_credential_skips(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The lever alone does not arm the check; the tenant credential is also required."""
    module = _load_check_module()
    monkeypatch.setenv("LIVESPEC_RUN_WORK_ITEM_STATUS_VOCABULARY", "1")
    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)

    result = _run(
        module=module, cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys, items=[_record()]
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


def test_open_status_is_reported_naming_item_priority_and_title(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A live item at `open` produces a non-empty report that names it precisely."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[
            _record(
                priority=2,
                title="branch_protection_alignment treats a CONDITIONAL leniency",
            )
        ],
    )

    assert result.returncode == 1
    assert _ITEM in result.output
    assert '"status": "open"' in result.output
    assert '"priority": "2"' in result.output
    assert "CONDITIONAL leniency" in result.output
    assert '"verdict": "off-vocabulary-status"' in result.output


@pytest.mark.parametrize("status", ["pending-approval", "ready", "backlog", "blocked"])
def test_a_ledger_of_dor_verdicts_only_produces_an_empty_report(
    *,
    status: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every status the intake Definition-of-Ready gate produces passes."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_record(status=status)],
    )

    assert result.returncode == 0, result.output


@pytest.mark.parametrize("status", ["active", "acceptance"])
def test_in_flight_lanes_are_not_off_vocabulary(
    *,
    status: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`active` and `acceptance` are lanes the runtime moves items THROUGH, not dead ones.

    The four intake verdicts are not the vocabulary. Reporting everything outside
    them would flag every legitimately in-flight item, converting a precise finding
    into noise — the check tests the declared `WorkItemStatus` vocabulary instead.
    """
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_record(status=status)],
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
    """A closed item is never ranked by design, so its status cannot strand it."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_record(status=status)],
    )

    assert result.returncode == 0, result.output


@pytest.mark.parametrize("status", [None, 7])
def test_an_unreadable_status_is_itself_an_off_vocabulary_finding(
    *,
    status: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A record with no status, or a non-string one, is in no lane either."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[_record(status=status)],
    )

    assert result.returncode == 1
    assert '"status": "<unset>"' in result.output
    assert '"priority": ""' in result.output
    assert '"title": ""' in result.output


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
        items=[{"status": "open"}],
    )

    assert result.returncode == 0, result.output


def test_the_measured_fleet_population_is_named_item_by_item(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Against the 2026-08-21 fleet population every one of the seven is named, P1 included."""
    module = _load_check_module()
    _arm(monkeypatch)

    result = _run(
        module=module,
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        items=[
            _record(item_id=item_id, priority=priority, title=title)
            for item_id, priority, title in _MEASURED_FLEET_POPULATION
        ],
    )

    assert result.returncode == 1
    for item_id, _priority, _title in _MEASURED_FLEET_POPULATION:
        assert f'"work_item": "{item_id}"' in result.output, f"{item_id} must be named"
    assert '"priority": "1"' in result.output, "the P1 must be visible in the report"


def test_default_item_reader_is_used_when_none_is_injected(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()` with no injected reader falls back to the ledger-backed default."""
    module = _load_check_module()
    _arm(monkeypatch)

    def _items(*, repo: Path) -> list[dict[str, object]]:
        _ = repo
        return [_record()]

    monkeypatch.setattr(module, "bd_items_reader", _items)
    monkeypatch.chdir(tmp_path)

    rc = module.main()
    captured = capsys.readouterr()

    assert rc == 1
    assert '"verdict": "off-vocabulary-status"' in captured.out + captured.err


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()

    assert callable(module.main), "main should be importable without invocation"
