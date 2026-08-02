"""Tests for `required_role_keys_declared`."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from livespec_dev_tooling.config import REQUIRED_ROLE_KEYS, UNION_ROLE_KEYS

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "required_role_keys_declared.py"


def _load_check() -> ModuleType:
    assert _CHECK.is_file(), "required_role_keys_declared check module must exist"
    spec = importlib.util.spec_from_file_location(
        "required_role_keys_declared_under_test",
        str(_CHECK),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_check(
    *, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[dict[str, object]]]:
    module = _load_check()
    monkeypatch.chdir(root)
    rc = module.main()
    captured = capsys.readouterr()
    records = [
        json.loads(line)
        for line in (captured.out + captured.err).splitlines()
        if line.strip().startswith("{")
    ]
    return rc, records


def _write_justfile(*, root: Path, targets: tuple[str, ...]) -> None:
    lines = "\n".join(f"        {target}" for target in targets)
    _ = (root / "justfile").write_text(
        "check:\n" "    #!/usr/bin/env bash\n" "    targets=(\n" f"{lines}\n" "    )\n",
        encoding="utf-8",
    )


# The two role keys whose TOML spelling is a scalar rather than an array. Named
# explicitly rather than inferred from `Config.__dataclass_fields__` defaults:
# the union (livespec-dev-tooling-8o8e.1) made every default a declared-absent
# variant, so a `default is None` test silently emitted `[]` for the scalars and
# produced a block that no longer parses.
_SCALAR_SPELLED_ROLE_KEYS = frozenset({"dataclasses_tree", "neutral_hook_body_path"})


def _all_required_empty_block() -> str:
    """Every required key declared the way a CONFORMANT consumer declares it.

    The two halves are spelled differently because Phase 4 of
    `livespec-dev-tooling-8o8e.1` made them different: a bare `[]` / `""` on a
    UNION key is now a hard load error, while for every CLEAN key it remains
    legitimate — emptiness there removes exemptions rather than files
    (`SPECIFICATION` v033 section "Clean role keys retain `[]`"). Spelling both halves
    alike would make this fixture unloadable AND teach the wrong rule.
    """
    lines = ["[tool.livespec_dev_tooling]"]
    for key in sorted(REQUIRED_ROLE_KEYS):
        if key in UNION_ROLE_KEYS:
            lines.append(f'{key} = {{ not_applicable = "fixture consumer has no {key}" }}')
            continue
        value = '""' if key in _SCALAR_SPELLED_ROLE_KEYS else "[]"
        lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


def test_layout_dependent_wiring_missing_one_role_key_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_justfile(root=tmp_path, targets=("check-no-inheritance",))
    missing_key = sorted(REQUIRED_ROLE_KEYS)[0]
    pyproject = _all_required_empty_block().replace(f"{missing_key} = []\n", "")
    _ = (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")

    rc, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1
    assert any(record.get("missing_keys") == [missing_key] for record in records)
    assert any("declare the real value" in str(record.get("event")) for record in records)


def test_declared_empty_required_role_keys_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_justfile(root=tmp_path, targets=("check-no-inheritance",))
    _ = (tmp_path / "pyproject.toml").write_text(_all_required_empty_block(), encoding="utf-8")

    rc, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0
    assert not [record for record in records if record.get("level") == "error"]


def test_layout_independent_wiring_is_named_exclusion(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_justfile(
        root=tmp_path,
        targets=(
            "check-plugin-resolution",
            "check-primary-checkout-commit-refuse-hook-installed",
        ),
    )

    rc, records = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0
    assert any(
        record.get("status") == "excluded"
        and "no layout-dependent checks wired" in str(record.get("reason"))
        for record in records
    )


def test_missing_keys_event_names_every_legal_spelling_for_both_key_groups() -> None:
    """The remediation is read at the moment someone decides what to write.

    That is why this outranks the config-comment instances of the same
    staleness: `MISSING_KEYS_EVENT` is the text emitted when the check fires,
    and after `livespec-dev-tooling-8o8e.1` Phase 4 a reader who follows
    "declare it explicitly empty" on a UNION key lands in a hard
    `ConfigParseError`. A diagnostic that routes its reader into the next
    failure is worse than no diagnostic.

    The precision that must survive: `[]` is retired for the five UNION keys
    ONLY. For the five CLEAN keys it stays LEGITIMATE, because those are
    exemption/severity predicates whose consuming checks derive the universe
    from `resolve_check_universe()` — emptiness there removes exemptions, not
    files. `REQUIRED_ROLE_KEYS` spans BOTH groups, so a blanket rewrite in
    either direction would be a new defect, and this test pins both halves.
    """
    module = _load_check()
    event: str = module.MISSING_KEYS_EVENT

    # The retired instruction must be gone.
    assert "declare it explicitly empty" not in event

    # Every blessed declared-absent spelling is named INLINE, to the standard
    # `config._spellings_hint` already sets: a rejection that does not say what
    # IS legal only relocates the confusion.
    for variant in ("not_applicable", "superseded_by", "unarmed_until", "convention_not_adopted"):
        assert variant in event, variant

    # The union keys are named, so a reader can tell which half they are in
    # without consulting the spec.
    for key in UNION_ROLE_KEYS:
        assert key in event, key

    # The CLEAN-key carve-out survives: a bare `[]` is still correct there.
    assert "remains legitimate" in event
