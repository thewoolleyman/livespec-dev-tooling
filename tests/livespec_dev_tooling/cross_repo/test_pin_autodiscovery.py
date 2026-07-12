"""Outside-in test for `cross_repo/pin_autodiscovery.py` — the discover orchestrator + CLI.

Per `SPECIFICATION/contracts.md` §"Pin autodiscovery rules", the walk
inspects five pin formats and yields normalized records. The
per-format walks now live in two cohesive helper modules
(`_pin_single_file_formats`, `_pin_directory_scan_formats`) exercised by
their own mirror test files; this file exercises the parent
orchestration surface — the `discover()` entry point that fans out over
all five formats, the multi-pin coexistence cases, and the
module-as-script CLI invocation (per the semver-stable contract).

A `.copier-answers.yml` `_commit` marker is copier render-provenance,
NOT a version pin, so the walk deliberately emits no record for it.

Coverage target: 100% line + branch of `pin_autodiscovery.py`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from livespec_dev_tooling.cross_repo import pin_autodiscovery

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "cross_repo" / "pin_autodiscovery.py"


# ---------------------------------------------------------------------------
# discover() orchestration — the fan-out over every pin format.
# ---------------------------------------------------------------------------


def test_discover_empty_repo_yields_no_records(*, tmp_path: Path) -> None:
    """A consumer repo with none of the pin files yields zero records."""
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_all_four_pin_formats_coexisting(*, tmp_path: Path) -> None:
    """The four pin formats coexist and yield one record each.

    A `.copier-answers.yml` is created alongside them but is render-provenance,
    not a version pin, so the walk emits no `copier_answers_commit` record for
    it — the exact-equality set below excludes that format.
    """
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"myapp": {"compat": {"livespec": ">=0.1.0,<1.0.0", "pinned": "v0.5.0"}}}),
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.uv.sources]\n" 'foo = { git = "https://github.com/o/foo", tag = "v1" }\n',
        encoding="utf-8",
    )
    (tmp_path / ".vendor.jsonc").write_text(
        json.dumps(
            {
                "libraries": [
                    {
                        "name": "bar_lib",
                        "upstream_url": "https://x/y",
                        "upstream_ref": "v2",
                        "vendored_at": "2026-04-26T06:05:33Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".copier-answers.yml").write_text(
        "_commit: v0.4.0\n_src_path: https://github.com/o/baz-template\n",
        encoding="utf-8",
    )
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "bump.yml").write_text(
        "    uses: owner/sibling-repo/.github/workflows/reusable.yml@v0.1.0\n",
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    formats = sorted(r["pin_format"] for r in result)
    assert formats == [
        "github_workflow_uses_ref",
        "livespec_jsonc_compat_pinned",
        "pyproject_toml_uv_sources",
        "vendor_jsonc",
    ]


def test_discover_multiple_pin_formats_coexisting(*, tmp_path: Path) -> None:
    """Three real formats coexist and yield one record each.

    A `.copier-answers.yml` is present but yields no record (render-provenance,
    not a version pin), so the exact-equality set below lists only the three
    real formats.
    """
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"myapp": {"compat": {"livespec": ">=0.1.0,<1.0.0", "pinned": "v0.5.0"}}}),
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.uv.sources]\n" 'foo = { git = "https://github.com/o/foo", tag = "v1" }\n',
        encoding="utf-8",
    )
    (tmp_path / ".vendor.jsonc").write_text(
        json.dumps(
            {
                "libraries": [
                    {
                        "name": "bar_lib",
                        "upstream_url": "https://x/y",
                        "upstream_ref": "v2",
                        "vendored_at": "2026-04-26T06:05:33Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".copier-answers.yml").write_text(
        "_commit: v0.4.0\n_src_path: https://github.com/o/baz-template\n",
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    formats = sorted(r["pin_format"] for r in result)
    assert formats == [
        "livespec_jsonc_compat_pinned",
        "pyproject_toml_uv_sources",
        "vendor_jsonc",
    ]


def test_discover_multiple_pins_same_format(*, tmp_path: Path) -> None:
    """Multiple entries of the same format (`[tool.uv.sources]`) all emit records."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.uv.sources]\n"
        'foo = { git = "https://github.com/o/foo", tag = "v1" }\n'
        'bar = { git = "https://github.com/o/bar", tag = "v2" }\n'
        'baz = { git = "https://github.com/o/baz", tag = "v3" }\n',
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 3
    pin_keys = sorted(r["pin_key"] for r in result)
    assert pin_keys == ["bar", "baz", "foo"]


# ---------------------------------------------------------------------------
# CLI surface — exercises the module-as-script invocation per the
# semver-stable contract.
# ---------------------------------------------------------------------------


def test_cli_default_root_emits_json_array(*, tmp_path: Path) -> None:
    """`python -m ...pin_autodiscovery` with cwd=tmp_path emits a JSON array."""
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"myapp": {"compat": {"livespec": ">=0.1.0,<1.0.0", "pinned": "v0.5.0"}}}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(_MODULE_PATH)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"pin_autodiscovery should exit 0; stderr={result.stderr!r}"
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["pin_format"] == "livespec_jsonc_compat_pinned"


def test_cli_root_flag_overrides_cwd(*, tmp_path: Path) -> None:
    """`--root <path>` overrides cwd so the script walks the supplied root."""
    target = tmp_path / "consumer"
    target.mkdir()
    (target / ".livespec.jsonc").write_text(
        json.dumps({"myapp": {"compat": {"livespec": ">=0.1.0,<1.0.0", "pinned": "v0.5.0"}}}),
        encoding="utf-8",
    )
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    result = subprocess.run(
        [sys.executable, str(_MODULE_PATH), "--root", str(target)],
        cwd=str(other_cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert len(parsed) == 1


def test_cli_source_repo_filter_via_argv(*, tmp_path: Path) -> None:
    """`--source-repo livespec` filters output via argv parsing."""
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"myapp": {"compat": {"livespec": ">=0.1.0,<1.0.0", "pinned": "v0.5.0"}}}),
        encoding="utf-8",
    )
    (tmp_path / ".vendor.jsonc").write_text(
        json.dumps(
            {
                "libraries": [
                    {
                        "name": "other_lib",
                        "upstream_url": "https://x/y",
                        "upstream_ref": "v1",
                        "vendored_at": "2026-04-26T06:05:33Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(_MODULE_PATH), "--source-repo", "livespec"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert len(parsed) == 1
    assert parsed[0]["source_repo"] == "livespec"


def test_cli_help_flag_exits_zero(*, tmp_path: Path) -> None:
    """`--help` exits 0 with usage text on stdout, per the wrapper-shape contract."""
    result = subprocess.run(
        [sys.executable, str(_MODULE_PATH), "--help"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "pin-autodiscovery" in result.stdout


def test_cli_json_flag_default_is_true(*, tmp_path: Path) -> None:
    """Passing `--json` explicitly is accepted (forward-compat for future text mode)."""
    result = subprocess.run(
        [sys.executable, str(_MODULE_PATH), "--json"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed == []


def test_module_importable_without_running_main() -> None:
    """The module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "pin_autodiscovery_for_import_test", str(_MODULE_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
    assert callable(module.discover)
