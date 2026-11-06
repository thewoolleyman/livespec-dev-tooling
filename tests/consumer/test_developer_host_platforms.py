"""Developer host platform scenarios of `SPECIFICATION/non-functional-requirements.md`.

"## Developer host platforms" governs what a developer host must hold for this
repository's daily commands, and what `just bootstrap` reports when it does not.
These run the real first-touch reconcile verb that `just bootstrap` runs
(`livespec_dev_tooling.fleet.local_reconcile`) against a real git checkout in a
temporary directory:

- bootstrap names a missing ledger pointer (`.beads/metadata.json`) instead of
  reporting success, and exits non-zero.

The scenario's Given, "a developer host that supplies every host toolchain
prerequisite", is modelled by standing in a passing row for every obligation
other than the two ledger-pointer rows under test, which run for real.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.fleet import local_reconcile
from livespec_dev_tooling.fleet._context import RowOutcome, RowPass
from livespec_dev_tooling.fleet._contract_local_rows import (
    LOCAL_OBLIGATION_ROWS,
    LocalObligationRow,
)
from livespec_dev_tooling.fleet._local_context import LocalContext

__all__: list[str] = []

pytestmark = pytest.mark.consumer

# The two ledger-pointer rows the scenario is about; every other row is the
# Given's satisfied prerequisite.
_LEDGER_POINTER_ROWS = frozenset({"beads-config-committed", "beads-metadata-present"})


def _satisfied(*, ctx: LocalContext) -> RowOutcome:
    del ctx
    return RowPass(note="prerequisite supplied by the host")


def _a_host_supplying_every_prerequisite(*, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = tuple(
        row
        if row.row_id in _LEDGER_POINTER_ROWS
        else LocalObligationRow(row_id=row.row_id, assert_local=None, reconcile_local=_satisfied)
        for row in LOCAL_OBLIGATION_ROWS
    )
    assert {row.row_id for row in rows} >= _LEDGER_POINTER_ROWS
    monkeypatch.setattr(local_reconcile, "LOCAL_OBLIGATION_ROWS", rows)


def _git(*args: str, cwd: Path) -> None:
    _ = subprocess.run(
        ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _a_checkout_with_config_but_no_metadata(*, tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    (checkout / ".beads").mkdir(parents=True)
    _ = (checkout / ".beads" / "config.yaml").write_text("dolt.host: 127.0.0.1\n", encoding="utf-8")
    _git("init", "-q", cwd=checkout)
    _git("add", ".beads/config.yaml", cwd=checkout)
    _git("commit", "-q", "-m", "fixture", cwd=checkout)
    return checkout


def test_bootstrap_names_a_missing_ledger_pointer_instead_of_reporting_success(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    checkout = _a_checkout_with_config_but_no_metadata(tmp_path=tmp_path)
    _a_host_supplying_every_prerequisite(monkeypatch=monkeypatch)
    monkeypatch.setattr(sys, "argv", ["local-reconcile", "--checkout", str(checkout)])

    code = local_reconcile.main()

    err = capsys.readouterr().err
    assert code != 0
    assert ".beads/metadata.json" in err
    assert "reconcile complete" not in err
