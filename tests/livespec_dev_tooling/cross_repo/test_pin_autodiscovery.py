"""Outside-in test for `cross_repo/pin_autodiscovery.py` — pin-format walk.

Per `SPECIFICATION/contracts.md` §"Pin autodiscovery rules", the walk
inspects four pin formats (`.livespec.jsonc` `compat.pinned`,
`pyproject.toml` `[tool.uv.sources]`, `.vendor.jsonc`,
`.copier-answers.yml` `_commit`) and yields normalized records. This
test file exercises each format individually, the source-repo filter,
the hyphen-to-underscore normalization for `.vendor.jsonc` matching,
the missing-file tolerance, the unrecognized-format tolerance, and
the multi-pin coexistence case.

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
# Direct-call tests against `discover()` for fast feedback + branch coverage.
# ---------------------------------------------------------------------------


def test_discover_empty_repo_yields_no_records(*, tmp_path: Path) -> None:
    """A consumer repo with none of the four pin files yields zero records."""
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_livespec_jsonc_emits_record(*, tmp_path: Path) -> None:
    """A `.livespec.jsonc` with a `compat.pinned` top-level key emits one record."""
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "template": "livespec",
                "myapp": {
                    "compat": {
                        "livespec": ">=0.1.0,<1.0.0",
                        "pinned": "v0.5.0",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 1
    record = result[0]
    assert record["pin_format"] == "livespec_jsonc_compat_pinned"
    assert record["file_path"] == ".livespec.jsonc"
    assert record["pin_key"] == "myapp"
    assert record["current_value"] == "v0.5.0"
    assert record["source_repo"] == "livespec"


def test_discover_livespec_jsonc_skips_top_keys_missing_compat(*, tmp_path: Path) -> None:
    """A `.livespec.jsonc` top-level scalar value (e.g., `template`) yields no record."""
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"template": "livespec", "spec_root": "SPECIFICATION"}),
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_livespec_jsonc_skips_compat_missing_required_fields(*, tmp_path: Path) -> None:
    """A `compat` block missing `pinned` or `livespec` is silently skipped."""
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "myapp": {"compat": {"pinned": "v0.5.0"}},  # missing `livespec`
                "otherapp": {"compat": {"livespec": ">=0.1.0,<1.0.0"}},  # missing `pinned`
                "noncompat": {"compat": "not-a-dict"},
            }
        ),
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_livespec_jsonc_unrecognized_when_malformed(*, tmp_path: Path) -> None:
    """A `.livespec.jsonc` that fails to parse yields an `unrecognized` record."""
    (tmp_path / ".livespec.jsonc").write_text("not-valid-json{", encoding="utf-8")
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["pin_format"] == "unrecognized"
    assert result[0]["file_path"] == ".livespec.jsonc"


def test_discover_livespec_jsonc_non_dict_top_level_yields_nothing(*, tmp_path: Path) -> None:
    """A `.livespec.jsonc` that parses but is not a dict yields no records."""
    (tmp_path / ".livespec.jsonc").write_text("[]", encoding="utf-8")
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_pyproject_uv_sources_emits_record(*, tmp_path: Path) -> None:
    """An entry under `[tool.uv.sources]` with `git` + `tag` emits one record."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\n\n'
        "[tool.uv.sources]\n"
        'livespec-runtime = { git = "https://github.com/thewoolleyman/livespec-runtime.git", tag = "v0.3.0" }\n'
        "\n[tool.ruff]\nline-length = 100\n",
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 1
    record = result[0]
    assert record["pin_format"] == "pyproject_toml_uv_sources"
    assert record["file_path"] == "pyproject.toml"
    assert record["pin_key"] == "livespec-runtime"
    assert record["current_value"] == "v0.3.0"
    assert record["source_repo"] == "livespec-runtime"


def test_discover_pyproject_uv_sources_strips_dot_git_suffix(*, tmp_path: Path) -> None:
    """A `git` URL ending in `.git` has the suffix stripped when deriving source repo."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.uv.sources]\n"
        'libfoo = { git = "https://github.com/owner/libfoo.git", tag = "v1" }\n'
        'libbar = { git = "https://github.com/owner/libbar", tag = "v2" }\n',
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    sources = sorted(r["source_repo"] for r in result)
    assert sources == ["libbar", "libfoo"]


def test_discover_pyproject_uv_sources_skips_entries_without_tag(*, tmp_path: Path) -> None:
    """An entry under `[tool.uv.sources]` with only `git` (no `tag`) is skipped.

    The autodiscovery walk reads pins, and a missing `tag` means there's no
    pin value to surface. The well-shaped entry coexisting in the same block
    still emits, so the table isn't classified as `unrecognized`.
    """
    (tmp_path / "pyproject.toml").write_text(
        "[tool.uv.sources]\n"
        'foo = { git = "https://github.com/o/foo", branch = "main" }\n'
        'bar = { git = "https://github.com/o/bar", tag = "v1" }\n',
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["pin_key"] == "bar"


def test_discover_pyproject_uv_sources_block_at_end_of_file(*, tmp_path: Path) -> None:
    """A `[tool.uv.sources]` block at EOF (no following section) parses cleanly."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\n\n'
        "[tool.uv.sources]\n"
        'libfoo = { git = "https://github.com/owner/libfoo.git", tag = "v1" }\n',
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["pin_key"] == "libfoo"


def test_discover_pyproject_uv_sources_absent_section(*, tmp_path: Path) -> None:
    """A `pyproject.toml` with no `[tool.uv.sources]` section yields no records."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\n\n[tool.ruff]\nline-length = 100\n',
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_pyproject_uv_sources_empty_block_unrecognized(*, tmp_path: Path) -> None:
    """A `[tool.uv.sources]` section with zero entries yields an `unrecognized` record."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\n\n[tool.uv.sources]\n\n[tool.ruff]\nline-length = 100\n',
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["pin_format"] == "unrecognized"
    assert result[0]["file_path"] == "pyproject.toml"


def test_discover_vendor_jsonc_emits_record(*, tmp_path: Path) -> None:
    """A `.vendor.jsonc` entry emits one record with the `name` as the source repo."""
    (tmp_path / ".vendor.jsonc").write_text(
        json.dumps(
            {
                "libraries": [
                    {
                        "name": "livespec_runtime",
                        "upstream_url": "https://github.com/thewoolleyman/livespec-runtime",
                        "upstream_ref": "v0.2.0",
                        "vendored_at": "2026-04-26T06:05:33Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 1
    record = result[0]
    assert record["pin_format"] == "vendor_jsonc"
    assert record["file_path"] == ".vendor.jsonc"
    assert record["pin_key"] == "livespec_runtime"
    assert record["current_value"] == "v0.2.0"
    assert record["source_repo"] == "livespec_runtime"


def test_discover_vendor_jsonc_skips_entries_with_missing_fields(*, tmp_path: Path) -> None:
    """A `.vendor.jsonc` entry missing `name` or `upstream_ref` is silently skipped."""
    (tmp_path / ".vendor.jsonc").write_text(
        json.dumps(
            {
                "libraries": [
                    {"upstream_ref": "v1"},  # missing name
                    {"name": "foo"},  # missing upstream_ref
                    "not-a-dict",  # not a dict entry
                ]
            }
        ),
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_vendor_jsonc_unrecognized_when_malformed(*, tmp_path: Path) -> None:
    """A `.vendor.jsonc` that fails to parse yields an `unrecognized` record."""
    (tmp_path / ".vendor.jsonc").write_text("not-valid-json", encoding="utf-8")
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["pin_format"] == "unrecognized"
    assert result[0]["file_path"] == ".vendor.jsonc"


def test_discover_vendor_jsonc_libraries_not_a_list_yields_nothing(*, tmp_path: Path) -> None:
    """A `.vendor.jsonc` whose `libraries` key is not a list yields no records."""
    (tmp_path / ".vendor.jsonc").write_text(
        json.dumps({"libraries": "not-a-list"}), encoding="utf-8"
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_copier_answers_emits_record(*, tmp_path: Path) -> None:
    """A `.copier-answers.yml` with `_commit` + `_src_path` emits one record."""
    (tmp_path / ".copier-answers.yml").write_text(
        "# Generated by copier - do not edit by hand\n"
        "_commit: v0.4.0\n"
        "_src_path: https://github.com/thewoolleyman/livespec-template\n"
        'project_name: "consumer-app"\n',
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 1
    record = result[0]
    assert record["pin_format"] == "copier_answers_commit"
    assert record["file_path"] == ".copier-answers.yml"
    assert record["pin_key"] == "_commit"
    assert record["current_value"] == "v0.4.0"
    assert record["source_repo"] == "livespec-template"


def test_discover_copier_answers_handles_quoted_value(*, tmp_path: Path) -> None:
    """A `.copier-answers.yml` whose `_commit` value is quoted is parsed correctly."""
    (tmp_path / ".copier-answers.yml").write_text(
        '_commit: "abcdef1234"\n' "_src_path: 'https://github.com/owner/template'\n",
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["current_value"] == "abcdef1234"
    assert result[0]["source_repo"] == "template"


def test_discover_copier_answers_unrecognized_when_required_keys_missing(*, tmp_path: Path) -> None:
    """A `.copier-answers.yml` missing `_commit` or `_src_path` yields `unrecognized`."""
    (tmp_path / ".copier-answers.yml").write_text("project_name: foo\n", encoding="utf-8")
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["pin_format"] == "unrecognized"


def test_discover_copier_answers_skips_blank_and_comment_lines(*, tmp_path: Path) -> None:
    """Blank lines and `#`-comment lines in `.copier-answers.yml` are skipped without false-positive entries."""
    (tmp_path / ".copier-answers.yml").write_text(
        "\n"
        "# a comment\n"
        "   \n"
        "non scalar value : with spaces but : multiple colons in one line that does not match\n"
        "_commit: deadbeef\n"
        "_src_path: https://github.com/o/t\n",
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["current_value"] == "deadbeef"


def test_discover_source_repo_filter_livespec(*, tmp_path: Path) -> None:
    """`--source-repo livespec` restricts output to `.livespec.jsonc` records."""
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"myapp": {"compat": {"livespec": ">=0.1.0,<1.0.0", "pinned": "v0.5.0"}}}),
        encoding="utf-8",
    )
    (tmp_path / ".vendor.jsonc").write_text(
        json.dumps(
            {
                "libraries": [
                    {
                        "name": "livespec_runtime",
                        "upstream_url": "https://x/y",
                        "upstream_ref": "v1",
                        "vendored_at": "2026-04-26T06:05:33Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo="livespec")
    assert len(result) == 1
    assert result[0]["source_repo"] == "livespec"


def test_discover_source_repo_filter_excludes_livespec_when_different(*, tmp_path: Path) -> None:
    """`--source-repo other` excludes the `.livespec.jsonc` record entirely."""
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"myapp": {"compat": {"livespec": ">=0.1.0,<1.0.0", "pinned": "v0.5.0"}}}),
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo="other")
    assert result == []


def test_discover_source_repo_filter_pyproject(*, tmp_path: Path) -> None:
    """The pyproject filter narrows to exactly the matching `[tool.uv.sources]` entry."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.uv.sources]\n"
        'foo = { git = "https://github.com/o/foo", tag = "v1" }\n'
        'bar = { git = "https://github.com/o/bar", tag = "v2" }\n',
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo="foo")
    assert len(result) == 1
    assert result[0]["source_repo"] == "foo"


def test_discover_source_repo_filter_vendor_hyphen_to_underscore(*, tmp_path: Path) -> None:
    """`--source-repo livespec-runtime` matches `.vendor.jsonc` `name: livespec_runtime`."""
    (tmp_path / ".vendor.jsonc").write_text(
        json.dumps(
            {
                "libraries": [
                    {
                        "name": "livespec_runtime",
                        "upstream_url": "https://x/y",
                        "upstream_ref": "v1",
                        "vendored_at": "2026-04-26T06:05:33Z",
                    },
                    {
                        "name": "other_lib",
                        "upstream_url": "https://x/y",
                        "upstream_ref": "v2",
                        "vendored_at": "2026-04-26T06:05:33Z",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo="livespec-runtime")
    assert len(result) == 1
    assert result[0]["pin_key"] == "livespec_runtime"


def test_discover_source_repo_filter_copier_matches(*, tmp_path: Path) -> None:
    """The copier filter matches when the trailing `_src_path` segment equals the filter."""
    (tmp_path / ".copier-answers.yml").write_text(
        "_commit: v1\n_src_path: https://github.com/owner/livespec-template\n",
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo="livespec-template")
    assert len(result) == 1
    assert result[0]["pin_key"] == "_commit"


def test_discover_source_repo_filter_copier_excludes_when_different(*, tmp_path: Path) -> None:
    """The copier filter excludes the record when the `_src_path` segment doesn't match."""
    (tmp_path / ".copier-answers.yml").write_text(
        "_commit: v1\n_src_path: https://github.com/owner/other-template\n",
        encoding="utf-8",
    )
    result = pin_autodiscovery.discover(root=tmp_path, source_repo="livespec-template")
    assert result == []


def test_discover_multiple_pin_formats_coexisting(*, tmp_path: Path) -> None:
    """All four formats coexisting in one repo yield one record per format."""
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
        "copier_answers_commit",
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
