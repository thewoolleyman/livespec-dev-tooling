"""Tests for `livespec_dev_tooling/driver_checks/github_rate_limit_decision_body_identical.py`.

The Verifier half of the canonical GitHub rate-limit decision body. It holds
each Driver bundle's copy byte-identical to the single packaged carrier
constant, so a well-meant local edit in one Driver cannot silently un-measure
the guard in that runtime alone.

Exercised through `main()` (in-process, `monkeypatch.chdir`) so the same entry
point a Driver's justfile invokes is the one under test, mirroring
`test_install_no_shadow_ledger.py`. The installer-then-Verifier ordering in
the pass cases is also the corrective loop a Driver follows, so agreement at 0
proves the installer writes exactly what the Verifier demands.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from livespec_dev_tooling.driver_checks import (
    github_rate_limit_decision_body_identical as _check,
)
from livespec_dev_tooling.driver_checks.github_rate_limit_decision_body_identical import main
from livespec_dev_tooling.install_github_rate_limit_decision import (
    CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY,
    DECISION_BODY_FILENAME,
)
from livespec_dev_tooling.install_github_rate_limit_decision import main as install_main

__all__: list[str] = []


def _claude_bundle(*, root: Path) -> Path:
    """Make `root` read as a CLAUDE Driver bundle, and name the body's destination."""
    manifest = root / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    _ = manifest.write_text('{"name": "livespec"}\n', encoding="utf-8")
    return root / ".claude-plugin" / "hooks" / DECISION_BODY_FILENAME


def _codex_bundle(*, root: Path) -> Path:
    """Make `root` read as a CODEX Driver bundle, and name the body's destination."""
    manifest = root / ".agents" / "plugins" / "marketplace.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    _ = manifest.write_text('{"name": "livespec-driver-codex"}\n', encoding="utf-8")
    return root / "livespec" / "hooks" / DECISION_BODY_FILENAME


def test_no_ops_off_a_driver_tree(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A tree with no Driver manifest is a sanctioned skip, not a failure.

    Load-bearing: livespec core, the orchestrator plugins and this library
    itself carry no Driver manifest, and a Verifier that failed there would be
    demanding a file none of them has anywhere to put.
    """
    monkeypatch.chdir(tmp_path)

    assert main() == 0


def test_passes_when_the_claude_bundle_copy_is_identical(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Installer then Verifier: what the installer writes is what the Verifier demands."""
    _ = _claude_bundle(root=tmp_path)
    monkeypatch.chdir(tmp_path)

    assert install_main() == 0
    assert main() == 0


def test_passes_when_the_codex_bundle_copy_is_identical(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same agreement holds for the other Driver layout."""
    _ = _codex_bundle(root=tmp_path)
    monkeypatch.chdir(tmp_path)

    assert install_main() == 0
    assert main() == 0


def test_fails_when_the_bundle_carries_no_copy(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Driver bundle with no decision body fails rather than silently skipping."""
    _ = _claude_bundle(root=tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main() == 1


def test_fails_when_the_body_drifted(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One edited byte fails — the whole point of the identity bar.

    The drift here is a plausible local "improvement" rather than corruption:
    raising the bounded-literal-loop threshold. Every constant in the body is
    load-bearing to a number somebody measured, so a change that reads as
    harmless is exactly the one identity has to catch.
    """
    destination = _claude_bundle(root=tmp_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    drifted = CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY.replace(
        "MAX_LITERAL_ITERATIONS = 10", "MAX_LITERAL_ITERATIONS = 100"
    )
    assert drifted != CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY
    _ = destination.write_text(drifted, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main() == 1


def test_fails_when_the_path_is_a_directory(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory at the destination is a missing body, not a readable one."""
    destination = _claude_bundle(root=tmp_path)
    destination.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    assert main() == 1


def test_module_importable_without_running_main() -> None:
    """The module imports cleanly (covers the `__name__ != '__main__'` branch)."""
    spec = importlib.util.spec_from_file_location(
        "github_rate_limit_decision_body_identical_import_test", str(Path(_check.__file__))
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
