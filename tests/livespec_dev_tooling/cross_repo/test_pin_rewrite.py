"""Behavioral tests for `pin_rewrite` — shared cross-repo pin rewrites.

The `bump-pin-rewrite` composite Action receives records emitted by
`pin_autodiscovery` and rewrites the matching pin in place. These tests cover
the legacy regex rewrites that used to live as inline Python heredocs in the
Action's bash case block.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_ACTION_PATH = _REPO_ROOT / ".github" / "actions" / "bump-pin-rewrite" / "action.yml"
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "cross_repo" / "pin_rewrite.py"
_MODULE_NAME = "livespec_dev_tooling.cross_repo.pin_rewrite"


def _module() -> ModuleType:
    """Import the module only after asserting the extracted file exists."""
    assert _MODULE_PATH.is_file(), f"missing extracted pin rewrite module: {_MODULE_PATH}"
    return importlib.import_module(_MODULE_NAME)


def test_legacy_regex_pin_cases_dispatch_shared_pin_rewrite_module() -> None:
    """The four legacy regex pin cases dispatch the tested `pin_rewrite` module."""
    text = _ACTION_PATH.read_text(encoding="utf-8")
    for fmt in (
        "livespec_jsonc_compat_pinned",
        "pyproject_toml_uv_sources",
        "vendor_jsonc",
        "github_workflow_uses_ref",
        "claude_settings_extra_known_marketplace_source_ref",
    ):
        assert f"{fmt})" in text, f"composite Action missing the {fmt} case arm"
    assert f"python -m {_MODULE_NAME}" in text, (
        "legacy regex pin cases MUST dispatch the tested pin_rewrite module "
        "instead of embedding Python heredocs in action.yml"
    )
    assert "python - <<PYEOF" not in text, (
        "the composite Action MUST NOT carry inline Python heredocs for pin rewrites; "
        "substantive transformation logic belongs in tested modules"
    )


def test_rewrite_livespec_jsonc_compat_pinned() -> None:
    """The `.livespec.jsonc` compat.pinned value is rewritten for the named key only."""
    text = (
        "{\n"
        '  "myapp": {"compat": {"livespec": ">=0.1.0,<1.0.0", "pinned": "v0.5.0"}},\n'
        '  "other": {"compat": {"livespec": ">=0.1.0,<1.0.0", "pinned": "v0.1.0"}}\n'
        "}\n"
    )
    new_text, count = _module().rewrite_pin_in_text(
        text=text,
        pin_format="livespec_jsonc_compat_pinned",
        pin_key="myapp",
        current_value="v0.5.0",
        new_value="v0.6.0",
    )
    assert count == 1
    assert '"pinned": "v0.6.0"' in new_text
    assert '"pinned": "v0.1.0"' in new_text


def test_rewrite_pyproject_toml_uv_sources() -> None:
    """The `[tool.uv.sources]` inline table tag is rewritten for the named package."""
    text = (
        "[tool.uv.sources]\n"
        'livespec-runtime = { git = "https://github.com/o/livespec-runtime.git", tag = "v0.3.0" }\n'
        'other = { git = "https://github.com/o/other.git", tag = "v1.0.0" }\n'
    )
    new_text, count = _module().rewrite_pin_in_text(
        text=text,
        pin_format="pyproject_toml_uv_sources",
        pin_key="livespec-runtime",
        current_value="v0.3.0",
        new_value="v0.4.0",
    )
    assert count == 1
    assert (
        'livespec-runtime = { git = "https://github.com/o/livespec-runtime.git", tag = "v0.4.0" }'
        in new_text
    )
    assert 'other = { git = "https://github.com/o/other.git", tag = "v1.0.0" }' in new_text


def test_rewrite_vendor_jsonc_upstream_ref() -> None:
    """The `.vendor.jsonc` upstream_ref is rewritten for the named library."""
    text = (
        "{\n"
        '  "libraries": [\n'
        '    {"name": "livespec_runtime", "upstream_ref": "v0.2.0"},\n'
        '    {"name": "other", "upstream_ref": "v1.0.0"}\n'
        "  ]\n"
        "}\n"
    )
    new_text, count = _module().rewrite_pin_in_text(
        text=text,
        pin_format="vendor_jsonc",
        pin_key="livespec_runtime",
        current_value="v0.2.0",
        new_value="v0.3.0",
    )
    assert count == 1
    assert '"name": "livespec_runtime", "upstream_ref": "v0.3.0"' in new_text
    assert '"name": "other", "upstream_ref": "v1.0.0"' in new_text


def test_rewrite_github_workflow_uses_ref() -> None:
    """The reusable workflow `uses:` ref is rewritten for the named workflow key."""
    key = "thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-bump.yml"
    text = (
        "jobs:\n"
        "  bump:\n"
        f"    uses: {key}@master\n"
        "  other:\n"
        "    uses: owner/other/.github/workflows/reusable.yml@v1\n"
    )
    new_text, count = _module().rewrite_pin_in_text(
        text=text,
        pin_format="github_workflow_uses_ref",
        pin_key=key,
        current_value="master",
        new_value="v0.46.0",
    )
    assert count == 1
    assert f"    uses: {key}@v0.46.0\n" in new_text
    assert "    uses: owner/other/.github/workflows/reusable.yml@v1\n" in new_text


def test_rewrite_claude_settings_extra_known_marketplace_source_ref() -> None:
    """The Claude marketplace source ref is rewritten for the named marketplace only."""
    text = (
        "{\n"
        '  "extraKnownMarketplaces": {\n'
        '    "livespec": {\n'
        '      "source": {\n'
        '        "source": "github",\n'
        '        "repo": "thewoolleyman/livespec",\n'
        '        "ref": "v0.7.3"\n'
        "      }\n"
        "    },\n"
        '    "livespec-driver-claude": {\n'
        '      "source": {\n'
        '        "source": "github",\n'
        '        "repo": "thewoolleyman/livespec-driver-claude",\n'
        '        "ref": "v0.2.1"\n'
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
    new_text, count = _module().rewrite_pin_in_text(
        text=text,
        pin_format="claude_settings_extra_known_marketplace_source_ref",
        pin_key="livespec",
        current_value="v0.7.3",
        new_value="v0.36.0",
    )
    assert count == 1
    assert '"ref": "v0.36.0"' in new_text
    assert '"ref": "v0.2.1"' in new_text


def test_rewrite_reports_zero_when_pin_absent() -> None:
    """A missing record target returns count zero and preserves text unchanged."""
    text = "[tool.uv.sources]\n"
    new_text, count = _module().rewrite_pin_in_text(
        text=text,
        pin_format="pyproject_toml_uv_sources",
        pin_key="missing",
        current_value="v1",
        new_value="v2",
    )
    assert count == 0
    assert new_text == text


def test_main_rewrites_file_in_place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`main()` reads the pin coordinates from env and rewrites the file in place."""
    pin_file = tmp_path / "pyproject.toml"
    _ = pin_file.write_text(
        "[tool.uv.sources]\n"
        'livespec-runtime = { git = "https://github.com/o/livespec-runtime.git", tag = "v0.3.0" }\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("PIN_FORMAT", "pyproject_toml_uv_sources")
    monkeypatch.setenv("PIN_FILE", str(pin_file))
    monkeypatch.setenv("PIN_KEY", "livespec-runtime")
    monkeypatch.setenv("PIN_CURRENT", "v0.3.0")
    monkeypatch.setenv("PIN_TAG", "v0.4.0")
    assert _module().main() == 0
    assert 'tag = "v0.4.0"' in pin_file.read_text(encoding="utf-8")


def test_main_returns_nonzero_when_pin_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` reports non-zero and leaves the file untouched when the pin is absent."""
    pin_file = tmp_path / ".vendor.jsonc"
    _ = pin_file.write_text('{"libraries": []}\n', encoding="utf-8")
    monkeypatch.setenv("PIN_FORMAT", "vendor_jsonc")
    monkeypatch.setenv("PIN_FILE", str(pin_file))
    monkeypatch.setenv("PIN_KEY", "missing")
    monkeypatch.setenv("PIN_CURRENT", "v1")
    monkeypatch.setenv("PIN_TAG", "v2")
    assert _module().main() == 1
    assert pin_file.read_text(encoding="utf-8") == '{"libraries": []}\n'
