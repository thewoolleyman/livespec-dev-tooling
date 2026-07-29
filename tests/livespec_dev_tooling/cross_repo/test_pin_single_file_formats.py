"""Outside-in tests for `cross_repo/_pin_single_file_formats.py`.

The single-file pin formats — `.livespec.jsonc` `compat.pinned`,
`pyproject.toml` `[tool.uv.sources]`, and `.vendor.jsonc` — each read one
well-known file at the repo root. This mirror file exercises each format
individually, the source-repo filter, the hyphen-to-underscore
normalization for `.vendor.jsonc` matching, the missing-file tolerance,
and the unrecognized-format tolerance. The walks are driven through the
public `_walk()` entry point (the same outside-in
surface these tests used before the decomposition).

Coverage target: 100% line + branch of `_pin_single_file_formats.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.cross_repo import pin_autodiscovery

__all__: list[str] = []


def _walk(*, root: Path, source_repo: str | None = None) -> list[dict[str, str]]:
    """The walk's records, failing loud if a pin file could not be READ.

    `discover` returns `IOResult` since livespec-dev-tooling-9sl0. Every
    test below drives readable fixtures, so `.unwrap()` is the right
    accessor: an unexpected read failure raises here instead of degrading
    to an empty record list, which is the shape that reads as "this repo
    carries no pins" and would make a broken walk look like a passing one.
    The `unreadable` sibling file pins the failure track itself.
    """
    return unsafe_perform_io(
        pin_autodiscovery.discover(root=root, source_repo=source_repo).unwrap()
    )


# ---------------------------------------------------------------------------
# .livespec.jsonc compat.pinned (first pin format)
# ---------------------------------------------------------------------------


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
    result = _walk(root=tmp_path, source_repo=None)
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
    result = _walk(root=tmp_path, source_repo=None)
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
    result = _walk(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_livespec_jsonc_unrecognized_when_malformed(*, tmp_path: Path) -> None:
    """A `.livespec.jsonc` that fails to parse yields an `unrecognized` record."""
    (tmp_path / ".livespec.jsonc").write_text("not-valid-json{", encoding="utf-8")
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["pin_format"] == "unrecognized"
    assert result[0]["file_path"] == ".livespec.jsonc"


def test_discover_livespec_jsonc_non_dict_top_level_yields_nothing(*, tmp_path: Path) -> None:
    """A `.livespec.jsonc` that parses but is not a dict yields no records."""
    (tmp_path / ".livespec.jsonc").write_text("[]", encoding="utf-8")
    result = _walk(root=tmp_path, source_repo=None)
    assert result == []


# ---------------------------------------------------------------------------
# pyproject.toml [tool.uv.sources] (second pin format)
# ---------------------------------------------------------------------------


def test_discover_pyproject_uv_sources_emits_record(*, tmp_path: Path) -> None:
    """An entry under `[tool.uv.sources]` with `git` + `tag` emits one record."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\n\n'
        "[tool.uv.sources]\n"
        'livespec-runtime = { git = "https://github.com/thewoolleyman/livespec-runtime.git", tag = "v0.3.0" }\n'
        "\n[tool.ruff]\nline-length = 100\n",
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
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
    result = _walk(root=tmp_path, source_repo=None)
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
    result = _walk(root=tmp_path, source_repo=None)
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
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["pin_key"] == "libfoo"


def test_discover_pyproject_uv_sources_absent_section(*, tmp_path: Path) -> None:
    """A `pyproject.toml` with no `[tool.uv.sources]` section yields no records."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\n\n[tool.ruff]\nline-length = 100\n',
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_pyproject_uv_sources_empty_block_unrecognized(*, tmp_path: Path) -> None:
    """A `[tool.uv.sources]` section with zero entries yields an `unrecognized` record."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\n\n[tool.uv.sources]\n\n[tool.ruff]\nline-length = 100\n',
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["pin_format"] == "unrecognized"
    assert result[0]["file_path"] == "pyproject.toml"


# ---------------------------------------------------------------------------
# .vendor.jsonc (third pin format)
# ---------------------------------------------------------------------------


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
    result = _walk(root=tmp_path, source_repo=None)
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
    result = _walk(root=tmp_path, source_repo=None)
    assert result == []


def test_discover_vendor_jsonc_unrecognized_when_malformed(*, tmp_path: Path) -> None:
    """A `.vendor.jsonc` that fails to parse yields an `unrecognized` record."""
    (tmp_path / ".vendor.jsonc").write_text("not-valid-json", encoding="utf-8")
    result = _walk(root=tmp_path, source_repo=None)
    assert len(result) == 1
    assert result[0]["pin_format"] == "unrecognized"
    assert result[0]["file_path"] == ".vendor.jsonc"


def test_discover_vendor_jsonc_libraries_not_a_list_yields_nothing(*, tmp_path: Path) -> None:
    """A `.vendor.jsonc` whose `libraries` key is not a list yields no records."""
    (tmp_path / ".vendor.jsonc").write_text(
        json.dumps({"libraries": "not-a-list"}), encoding="utf-8"
    )
    result = _walk(root=tmp_path, source_repo=None)
    assert result == []


# ---------------------------------------------------------------------------
# Source-repo filter over the single-file formats
# ---------------------------------------------------------------------------


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
    result = _walk(root=tmp_path, source_repo="livespec")
    assert len(result) == 1
    assert result[0]["source_repo"] == "livespec"


def test_discover_source_repo_filter_excludes_livespec_when_different(*, tmp_path: Path) -> None:
    """`--source-repo other` excludes the `.livespec.jsonc` record entirely."""
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"myapp": {"compat": {"livespec": ">=0.1.0,<1.0.0", "pinned": "v0.5.0"}}}),
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo="other")
    assert result == []


def test_discover_source_repo_filter_pyproject(*, tmp_path: Path) -> None:
    """The pyproject filter narrows to exactly the matching `[tool.uv.sources]` entry."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.uv.sources]\n"
        'foo = { git = "https://github.com/o/foo", tag = "v1" }\n'
        'bar = { git = "https://github.com/o/bar", tag = "v2" }\n',
        encoding="utf-8",
    )
    result = _walk(root=tmp_path, source_repo="foo")
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
    result = _walk(root=tmp_path, source_repo="livespec-runtime")
    assert len(result) == 1
    assert result[0]["pin_key"] == "livespec_runtime"
