"""Outside-in test for `livespec_dev_tooling/checks/no_shadow_ledger_body_identical.py`.

The check verifies that a consumer's configured `neutral_hook_body_path`
(a `[tool.livespec_dev_tooling]` role key) is BYTE-IDENTICAL to the single
packaged carrier constant
`livespec_dev_tooling.install_no_shadow_ledger.CANONICAL_NO_SHADOW_LEDGER_BODY`.
The role key must be declared before the check is used. Declared-empty is a
sanctioned no-op; declared non-empty requires the configured path to exist
and match byte-for-byte, else exit 4 with a `missing` or `body_mismatch`
failure mode (`SPECIFICATION/contracts.md`
§"`no_shadow_ledger_body_identical` check", steps 2 and 3).

The last two cases are the ones `livespec-dev-tooling-okz` was filed for, and
they are the reason "byte-identical" has to be MEASURED rather than asserted
in a docstring: a CRLF-lined copy and a copy that is not valid UTF-8 are both
plainly byte-different from canonical, and the decoding comparison this check
used to run reported the first as a PASS and blew up on the second. Their
sibling precedent is `_primary_checkout_hook_files._inspect_hook`, whose
identical defect was measured and fixed first (Conformance-Pattern concern #1).

Exercised in-process via `main()` with `monkeypatch.chdir` (this check is
not on the `subprocess_spawn_allowlist`), mirroring
`test_primary_checkout_commit_refuse_hook_installed.py`'s in-process
convention but without the subprocess-spawn detour that check's precedent
needed for its shell-hook-execution arm (this check has no shell-execution
side to exercise).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from returns.io import IOSuccess

from livespec_dev_tooling import config as config_module
from livespec_dev_tooling.checks import no_shadow_ledger_body_identical as _check
from livespec_dev_tooling.checks.no_shadow_ledger_body_identical import main
from livespec_dev_tooling.install_no_shadow_ledger import CANONICAL_NO_SHADOW_LEDGER_BODY
from tests.livespec_dev_tooling.checks.config_parse_rendering import (
    assert_main_renders_the_parse_failure,
)

__all__: list[str] = []


def _write_pyproject(*, repo_root: Path, body: str) -> None:
    _ = (repo_root / "pyproject.toml").write_text(body, encoding="utf-8")


def test_no_ops_when_role_key_declared_empty(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(a) exit 0 when `neutral_hook_body_path` is declared empty."""
    monkeypatch.chdir(tmp_path)

    assert main() == 0


def test_no_shadow_ledger_body_identical_bug_guard_after_gate(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the gate is bypassed, a declared-empty hook path remains a bug."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_check, "role_absence_exit_code", lambda **_kwargs: None)
    # The patched seam is the shared supervisor helper the check now loads
    # through (`livespec-dev-tooling-efxa`), not the raw loader it imported
    # directly before. Same substitution, one name further along the chain.
    # The double now answers on that helper's `IOResult` railway
    # (`livespec-dev-tooling-qndn.17`), because a substitute that still
    # handed back a bare `Config` would exercise a shape `main()` no longer
    # consumes.
    monkeypatch.setattr(
        _check,
        "load_config_or_report",
        lambda **_kwargs: IOSuccess(
            replace(
                config_module.Config(),
                declared_keys=frozenset({"neutral_hook_body_path"}),
                neutral_hook_body_path=None,
            )
        ),
    )

    with pytest.raises(
        RuntimeError, match="neutral_hook_body_path unexpectedly empty after role-key gate"
    ):
        _check.main()


def test_passes_when_path_present_and_identical(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(b) exit 0 when the configured path exists and is byte-identical to canonical."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nneutral_hook_body_path = "hooks/no_shadow_ledger.py"\n',
    )
    hook_path = tmp_path / "hooks" / "no_shadow_ledger.py"
    hook_path.parent.mkdir(parents=True)
    _ = hook_path.write_text(CANONICAL_NO_SHADOW_LEDGER_BODY, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main() == 0


def test_fails_when_path_missing(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(c) exit 4 when the configured path does not exist."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nneutral_hook_body_path = "hooks/no_shadow_ledger.py"\n',
    )
    monkeypatch.chdir(tmp_path)

    assert main() == 4


def test_fails_when_body_mismatches(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(d) exit 4 when the configured path exists but its bytes differ from canonical."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nneutral_hook_body_path = "hooks/no_shadow_ledger.py"\n',
    )
    hook_path = tmp_path / "hooks" / "no_shadow_ledger.py"
    hook_path.parent.mkdir(parents=True)
    _ = hook_path.write_text(CANONICAL_NO_SHADOW_LEDGER_BODY + "# drift\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main() == 4


def test_fails_when_body_is_crlf_lined(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(d2) exit 4 for a CRLF-lined copy — byte-different, text-IDENTICAL after decode.

    The defect `livespec-dev-tooling-okz` names, measured rather than reasoned.
    `Path.read_text` performs universal-newline translation, so a copy whose
    every line ending is `\\r\\n` decoded back to exactly
    `CANONICAL_NO_SHADOW_LEDGER_BODY` and this check — the Verifier slot whose
    whole contract is BYTE-identity — returned 0 on a Driver copy it had not
    verified. The bytes differ on every line; only the comparison could not see
    it.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nneutral_hook_body_path = "hooks/no_shadow_ledger.py"\n',
    )
    hook_path = tmp_path / "hooks" / "no_shadow_ledger.py"
    hook_path.parent.mkdir(parents=True)
    crlf_body = CANONICAL_NO_SHADOW_LEDGER_BODY.replace("\n", "\r\n")
    _ = hook_path.write_bytes(crlf_body.encode("utf-8"))
    assert crlf_body.encode("utf-8") != CANONICAL_NO_SHADOW_LEDGER_BODY.encode("utf-8")
    monkeypatch.chdir(tmp_path)

    assert main() == 4


def test_fails_cleanly_when_body_is_not_valid_utf8(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(d3) exit 4 for a copy that is not valid UTF-8 — a FINDING, never a crash.

    The second half of `livespec-dev-tooling-okz`. Decoding was the only reason
    a copy whose bytes are not valid UTF-8 raised `UnicodeDecodeError` out of
    `main()` — an uncaught traceback reaching stderr through the interpreter
    rather than through structlog, which is the output discipline this package
    exists to enforce. The canonical body is UTF-8 by construction, so bytes
    that do not decode CANNOT equal it: `body_mismatch` was always the
    available answer, and comparing bytes reaches it without a `try`.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nneutral_hook_body_path = "hooks/no_shadow_ledger.py"\n',
    )
    hook_path = tmp_path / "hooks" / "no_shadow_ledger.py"
    hook_path.parent.mkdir(parents=True)
    _ = hook_path.write_bytes(CANONICAL_NO_SHADOW_LEDGER_BODY.encode("utf-8") + b"\xff\xfe")
    monkeypatch.chdir(tmp_path)

    assert main() == 4


def test_fails_when_path_is_a_directory(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(e) exit 4 when the configured path exists but is a directory, not a regular file."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nneutral_hook_body_path = "hooks/no_shadow_ledger.py"\n',
    )
    hook_path = tmp_path / "hooks" / "no_shadow_ledger.py"
    hook_path.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    assert main() == 4


def test_main_renders_the_consumer_config_parse_failure(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A malformed consumer config is a structured diagnostic, never a traceback.

    `SPECIFICATION/contracts.md` section "Configuration loader" puts the catch
    at this check's `main()` supervisor; before `livespec-dev-tooling-efxa`
    the `ConfigParseError` escaped from here as an uncaught traceback, which
    reaches stderr through the interpreter rather than through structlog and
    so broke the very output discipline this package exists to enforce.
    """
    assert_main_renders_the_parse_failure(
        module_slug="no_shadow_ledger_body_identical",
        check_id="no_shadow_ledger_body_identical",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
