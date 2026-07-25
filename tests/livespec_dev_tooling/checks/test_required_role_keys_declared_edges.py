"""Edge coverage for `required_role_keys_declared`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import required_role_keys_declared as check

__all__: list[str] = []


def _records(*, captured: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in captured.splitlines() if line.strip().startswith("{")]


def test_parser_edges_are_layout_independent_exclusions(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "layout_dependent_check_slugs", lambda: ("check-alpha",))

    no_check = check.classify_role_key_declarations(
        justfile_text="build:\n    echo ok\n", declared_keys=frozenset()
    )
    next_recipe_no_targets = check.classify_role_key_declarations(
        justfile_text="check:\n    echo ok\nnext:\n    echo later\n",
        declared_keys=frozenset(),
    )
    unclosed_targets = check.classify_role_key_declarations(
        justfile_text="check:\n    targets=(\n        check-alpha\n",
        declared_keys=frozenset(),
    )
    non_check_target = check.classify_role_key_declarations(
        justfile_text="check:\n    targets=(\n        run-tests\n    )\n",
        declared_keys=frozenset(),
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
