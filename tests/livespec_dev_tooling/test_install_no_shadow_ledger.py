"""Outside-in test for `livespec_dev_tooling/install_no_shadow_ledger.py`.

The installer writes the canonical neutral no-shadow-ledger Stop-hook body
to a consumer's configured `neutral_hook_body_path` role key (a
`[tool.livespec_dev_tooling]` key in the consuming repo's `pyproject.toml`).
Mirrors `test_install_commit_refuse_hooks.py`'s embedding-integrity and
round-trip coverage, adapted for the single-path (not three-hooks) shape
and the declared-ness gate the installer shares with its paired Verifier.

The embedding-integrity assertions guarantee the SEED-body → constant
transcription (done via a throwaway generator script, per the authoring
brief) was not corrupted: the constant compiles as valid Python, starts
with the shebang, ends with the importable `main()` tail, and does NOT
contain the retired run-on-import tail.

The agreement test is the load-bearing one for livespec-dev-tooling-eihv:
slice L moved `checks/no_shadow_ledger_body_identical.py` onto the shared
`role_absence_exit_code` gate and left this installer reading `role_path`
directly, so an UNDECLARED key drew a silent exit 0 from the installer and
a hard exit 1 from the Verifier — the surface that exists to FIX a
consumer's state stayed silent about exactly the condition the Verifier
fails on. The parametrized case walks all three declared-ness states
(undeclared / declared-absent / declared-present) through BOTH mains in
one checkout and asserts they return the same code, so the pair cannot
drift apart again without a red test.

Exercised entirely via `main()` (in-process, `monkeypatch.chdir`) — this
covers `install_neutral_hook_body`'s branches without hand-constructing a
structlog logger, mirroring how `test_install_commit_refuse_hooks.py`
exercises `install_hooks` only through `main()`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from livespec_dev_tooling import config as config_module
from livespec_dev_tooling import install_no_shadow_ledger as _installer
from livespec_dev_tooling.checks.no_shadow_ledger_body_identical import main as check_main
from livespec_dev_tooling.install_no_shadow_ledger import (
    CANONICAL_NO_SHADOW_LEDGER_BODY,
    main,
)

__all__: list[str] = []


_DECLARED_ABSENT_BLOCK = (
    "[tool.livespec_dev_tooling]\n"
    'neutral_hook_body_path = { not_applicable = "consumer is not a Driver repo" }\n'
)
_DECLARED_PRESENT_BLOCK = (
    '[tool.livespec_dev_tooling]\nneutral_hook_body_path = "hooks/no_shadow_ledger.py"\n'
)


def _write_pyproject(*, repo_root: Path, body: str) -> None:
    _ = (repo_root / "pyproject.toml").write_text(body, encoding="utf-8")


# --- embedding integrity -------------------------------------------------


def test_canonical_body_compiles_as_valid_python() -> None:
    """The embedded constant is syntactically valid Python (transcription proof)."""
    compile(CANONICAL_NO_SHADOW_LEDGER_BODY, "<body>", "exec")


def test_canonical_body_starts_and_ends_correctly() -> None:
    """The constant carries the shebang head and the importable-`main()` tail."""
    assert CANONICAL_NO_SHADOW_LEDGER_BODY.startswith("#!/usr/bin/env python3\n")
    assert CANONICAL_NO_SHADOW_LEDGER_BODY.endswith("raise SystemExit(main())\n")


def test_canonical_body_has_importable_main_and_no_run_on_import_tail() -> None:
    """The retired run-on-import tail is gone; the importable `main()` replaces it."""
    assert "def main() -> int:" in CANONICAL_NO_SHADOW_LEDGER_BODY
    assert "def _warning()" in CANONICAL_NO_SHADOW_LEDGER_BODY
    assert "\nsys.exit(0)\n" not in CANONICAL_NO_SHADOW_LEDGER_BODY


# --- install round trip (via main()) ---------------------------------------


def test_main_writes_canonical_body_when_role_key_set(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The role key declared present → the installer writes the exact canonical bytes."""
    _write_pyproject(repo_root=tmp_path, body=_DECLARED_PRESENT_BLOCK)
    monkeypatch.chdir(tmp_path)

    rc = main()

    assert rc == 0
    written = tmp_path / "hooks" / "no_shadow_ledger.py"
    assert written.is_file()
    assert written.read_text(encoding="utf-8") == CANONICAL_NO_SHADOW_LEDGER_BODY


def test_main_no_ops_when_role_key_declared_absent(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blessed declared-absent inline table → the installer writes nothing and returns 0."""
    _write_pyproject(repo_root=tmp_path, body=_DECLARED_ABSENT_BLOCK)
    monkeypatch.chdir(tmp_path)

    rc = main()

    assert rc == 0
    assert [entry.name for entry in tmp_path.iterdir()] == ["pyproject.toml"]


def test_main_hard_errors_when_role_key_undeclared(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The role key UNDECLARED → exit 1 naming the key, and nothing is written.

    `neutral_hook_body_path` is a REQUIRED role key: absence is not a
    spelling of "not applicable" (v0.54.12). The installer applies the same
    declared-ness gate as its paired Verifier rather than no-opping, so the
    consumer hears about the misconfiguration from the surface that exists
    to repair it.
    """
    monkeypatch.chdir(tmp_path)

    rc = main()

    assert rc == 1
    assert list(tmp_path.iterdir()) == []


def test_main_is_idempotent(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-running the installer overwrites with the identical canonical body."""
    _write_pyproject(repo_root=tmp_path, body=_DECLARED_PRESENT_BLOCK)
    monkeypatch.chdir(tmp_path)

    assert main() == 0
    first = (tmp_path / "hooks" / "no_shadow_ledger.py").read_text(encoding="utf-8")
    assert main() == 0
    second = (tmp_path / "hooks" / "no_shadow_ledger.py").read_text(encoding="utf-8")

    assert first == second == CANONICAL_NO_SHADOW_LEDGER_BODY


# --- installer/Verifier agreement (livespec-dev-tooling-eihv) --------------


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        pytest.param(None, 1, id="undeclared"),
        pytest.param(_DECLARED_ABSENT_BLOCK, 0, id="declared-absent"),
        pytest.param(_DECLARED_PRESENT_BLOCK, 0, id="declared-present"),
    ],
)
def test_installer_and_check_agree_on_every_declaredness_state(
    *,
    block: str | None,
    expected: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Installer and Verifier return the SAME code in all three declared-ness states.

    Run in that order, installer-then-Verifier is also the corrective loop a
    consumer follows, so declared-present agreeing at 0 proves the installer
    writes exactly what the Verifier demands.
    """
    if block is not None:
        _write_pyproject(repo_root=tmp_path, body=block)
    monkeypatch.chdir(tmp_path)

    installer_rc = main()
    check_rc = check_main()

    assert installer_rc == expected
    assert check_rc == expected


def test_install_neutral_hook_body_bug_guard_after_gate(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the gate is bypassed, a declared-absent hook path remains a bug.

    Mirrors the Verifier's identical guard: past the declared-ness gate the
    role is a `DeclaredPath` by construction, so a `None` there is a defect
    in the gate rather than a consumer misconfiguration.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_installer, "role_absence_exit_code", lambda **_kwargs: None)
    monkeypatch.setattr(
        _installer,
        "load_config",
        lambda **_kwargs: replace(
            config_module.Config(),
            declared_keys=frozenset({"neutral_hook_body_path"}),
        ),
    )

    with pytest.raises(
        RuntimeError, match="neutral_hook_body_path unexpectedly empty after role-key gate"
    ):
        _ = _installer.main()
