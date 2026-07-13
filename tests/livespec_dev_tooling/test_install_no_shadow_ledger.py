"""Outside-in test for `livespec_dev_tooling/install_no_shadow_ledger.py`.

The installer writes the canonical neutral no-shadow-ledger Stop-hook body
to a consumer's configured `neutral_hook_body_path` role key (a
`[tool.livespec_dev_tooling]` key in the consuming repo's `pyproject.toml`).
Mirrors `test_install_commit_refuse_hooks.py`'s embedding-integrity and
round-trip coverage, adapted for the single-path (not three-hooks) shape
and the opt-in (role-key-absent no-ops) semantics.

The embedding-integrity assertions guarantee the SEED-body → constant
transcription (done via a throwaway generator script, per the authoring
brief) was not corrupted: the constant compiles as valid Python, starts
with the shebang, ends with the importable `main()` tail, and does NOT
contain the retired run-on-import tail.

Exercised entirely via `main()` (in-process, `monkeypatch.chdir`) — this
covers `install_neutral_hook_body`'s both branches (role key set / absent)
without hand-constructing a structlog logger, mirroring how
`test_install_commit_refuse_hooks.py` exercises `install_hooks` only
through `main()`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.install_no_shadow_ledger import (
    CANONICAL_NO_SHADOW_LEDGER_BODY,
    main,
)

__all__: list[str] = []


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
    """The role key present → the installer writes the exact canonical bytes."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nneutral_hook_body_path = "hooks/no_shadow_ledger.py"\n',
    )
    monkeypatch.chdir(tmp_path)

    rc = main()

    assert rc == 0
    written = tmp_path / "hooks" / "no_shadow_ledger.py"
    assert written.is_file()
    assert written.read_text(encoding="utf-8") == CANONICAL_NO_SHADOW_LEDGER_BODY


def test_main_no_ops_when_role_key_absent(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The role key absent → the installer writes nothing and returns 0."""
    monkeypatch.chdir(tmp_path)

    rc = main()

    assert rc == 0
    assert list(tmp_path.iterdir()) == []


def test_main_is_idempotent(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-running the installer overwrites with the identical canonical body."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nneutral_hook_body_path = "hooks/no_shadow_ledger.py"\n',
    )
    monkeypatch.chdir(tmp_path)

    assert main() == 0
    first = (tmp_path / "hooks" / "no_shadow_ledger.py").read_text(encoding="utf-8")
    assert main() == 0
    second = (tmp_path / "hooks" / "no_shadow_ledger.py").read_text(encoding="utf-8")

    assert first == second == CANONICAL_NO_SHADOW_LEDGER_BODY
