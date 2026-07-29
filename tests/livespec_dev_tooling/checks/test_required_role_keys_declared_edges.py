"""Edge coverage for `required_role_keys_declared`."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import required_role_keys_declared as check

__all__: list[str] = []


def _records(*, captured: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in captured.splitlines() if line.strip().startswith("{")]


def test_layout_dependent_slugs_are_injected_rather_than_walked() -> None:
    """The classifier takes its layout-dependent set as DATA, so it reaches no filesystem.

    Ratified livespec v179 member 1 disqualifies a public function that reaches an I/O
    boundary — including TRANSITIVELY, through a first-party callee. This function read
    as total by hand (no raise, no try, no I/O in its own body) and was disqualified by
    the mechanical fixpoint, because `layout_dependent_check_slugs()` walks the
    filesystem (`module_path.is_file()`). Hand judgement got that wrong and the fixpoint
    caught it; clause (d) is in the ratified text because of this function.

    The remedy INJECTS the set rather than wrapping a pure classification in `IOResult`:
    the rule wants I/O at the boundary, and both callers already ARE that boundary. That
    makes the function honestly total instead of merely honestly typed — strictly better
    than a `Result` whose failure track would be uninhabited.

    The old test faked the I/O by monkeypatching the module-level function. Needing to
    patch a module attribute to keep a classifier off the disk is exactly the smell the
    injection removes, which is why that monkeypatch is gone rather than retargeted.
    """
    parameters = inspect.signature(check.classify_role_key_declarations).parameters
    assert "layout_dependent" in parameters, (
        "classify_role_key_declarations must take its layout-dependent slug set as an "
        f"injected parameter; got parameters {sorted(parameters)}"
    )

    # The injected set is authoritative: `check-alpha` is not layout-dependent on disk,
    # so honoring it proves the value came from the caller rather than a directory walk.
    status = check.classify_role_key_declarations(
        justfile_text="check:\n    targets=(\n        check-alpha\n    )\n",
        declared_keys=frozenset(),
        layout_dependent=frozenset({"check-alpha"}),
    )

    assert status.wired_layout_dependent_checks == ("check-alpha",)


def test_parser_edges_are_layout_independent_exclusions() -> None:
    no_check = check.classify_role_key_declarations(
        justfile_text="build:\n    echo ok\n",
        declared_keys=frozenset(),
        layout_dependent=frozenset({"check-alpha"}),
    )
    next_recipe_no_targets = check.classify_role_key_declarations(
        justfile_text="check:\n    echo ok\nnext:\n    echo later\n",
        declared_keys=frozenset(),
        layout_dependent=frozenset({"check-alpha"}),
    )
    unclosed_targets = check.classify_role_key_declarations(
        justfile_text="check:\n    targets=(\n        check-alpha\n",
        declared_keys=frozenset(),
        layout_dependent=frozenset({"check-alpha"}),
    )
    non_check_target = check.classify_role_key_declarations(
        justfile_text="check:\n    targets=(\n        run-tests\n    )\n",
        declared_keys=frozenset(),
        layout_dependent=frozenset({"check-alpha"}),
    )

    assert no_check.is_excluded()
    assert next_recipe_no_targets.is_excluded()
    assert unclosed_targets.is_excluded()
    assert non_check_target.is_excluded()


def test_missing_justfile_is_named_exclusion(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = check.main()

    assert rc == 0
    assert any(
        record.get("status") == "excluded" and "justfile not found" in str(record.get("reason"))
        for record in _records(captured=capsys.readouterr().err)
    )


def test_malformed_config_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = (tmp_path / "justfile").write_text(
        "check:\n    targets=(\n        check-no-inheritance\n    )\n",
        encoding="utf-8",
    )
    _ = (tmp_path / "pyproject.toml").write_text("not [toml", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    rc = check.main()

    assert rc == 1
    assert any(
        record.get("event") == "consumer config parse failed"
        for record in _records(captured=capsys.readouterr().err)
    )
