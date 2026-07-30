"""`main()`'s diagnostic path for an unreadable checks package — the Green-leg edge.

A sibling of `test_canonical_checks_railway.py` rather than an addition to it: that
file is the Red-recorded half of a Red→Green pair and is BYTE-IDENTITY-BOUND, so
extra Green-leg coverage lands here. This repo's existing `*_edges.py` idiom.

What it covers is the branch `livespec-dev-tooling-vzwa` created. Before the
conversion this module's docstring said no diagnostic surface existed because
"successful discovery is the only path" — true then, false now. Emitting a bare
non-zero exit with no reason would hand a consumer a failure it cannot act on, which
is the shape this epic exists to remove one size down.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

    import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL_CHECKS = _REPO_ROOT / "livespec_dev_tooling" / "canonical_checks.py"


def _import_canonical_checks() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "canonical_checks_railway_edges_under_test", str(_CANONICAL_CHECKS)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Required, not tidiness: the module's `@dataclass` resolves its annotations
    # through `sys.modules[cls.__module__]` under `from __future__ import
    # annotations`, and an unregistered module makes that lookup None.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_reports_an_unreadable_checks_package_and_exits_non_zero(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The thin transport FAILS with a named reason rather than emitting empty slugs.

    ⛔ THE STDOUT ASSERTION IS THE LOAD-BEARING ONE. Emitting `{"slugs": []}` and
    exiting 0 is the pre-conversion behavior, and every consumer reads an empty slug
    set as "this repo has no canonical checks" — which PASSES. So this pins that
    stdout carries NO payload on the failure path: a consumer parsing stdout must not
    receive a well-formed answer that happens to be empty.
    """
    module = _import_canonical_checks()
    missing = tmp_path / "definitely-not-a-package"
    monkeypatch.setattr(module, "_CHECKS_PACKAGE_DIR", missing)
    monkeypatch.setattr(sys, "argv", ["canonical-checks", "--json"])

    exit_code = module.main()
    captured = capsys.readouterr()

    assert exit_code == 1, f"an unreadable checks package must exit non-zero; got {exit_code}"
    assert captured.out == "", (
        f"stdout must carry NO payload on the failure path — an empty slug set is read "
        f"as 'no canonical checks' and passes; got {captured.out!r}"
    )
    diagnostic = json.loads(captured.err)
    assert (
        diagnostic["check_id"] == "canonical-checks-package-unreadable"
    ), f"the diagnostic must be identifiable; got {diagnostic!r}"
    assert diagnostic["package_path"] == str(
        missing
    ), f"the diagnostic must name the path walked; got {diagnostic!r}"
    assert (
        "broken install" in diagnostic["reason"]
    ), f"the reason must distinguish a broken install from an empty repo; got {diagnostic!r}"
