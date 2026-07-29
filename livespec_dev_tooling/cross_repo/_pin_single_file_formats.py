"""_pin_single_file_formats — single-file pin-format walks.

Extracted verbatim from `pin_autodiscovery` (cohesive seam: the three pin
formats that read a single well-known file at the repo root rather than
scanning a directory). Per `SPECIFICATION/contracts.md` §"Pin
autodiscovery rules", these three formats are:

- `.livespec.jsonc` `compat.pinned` — every top-level key whose value
  carries a `compat` object with `pinned` and `livespec` fields. The
  pin's source repo is always `livespec`.
- `pyproject.toml` `[tool.uv.sources]` — every entry whose `git` URL
  identifies a GitHub repository; the `tag` field is the pin's current
  value. The source repo short-name derives from the trailing path
  segment of the URL (with any `.git` suffix stripped).
- `.vendor.jsonc` — every entry in the `libraries` array whose `name`
  matches the source repository's normalized Python package name
  (hyphen-to-underscore). The `upstream_ref` field is the pin's current
  value.

Each walk emits through the shared `record` normalizer, imported from
`_pin_directory_scan_formats` so the record shape is defined once.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.cross_repo._pin_directory_scan_formats import (  # noqa: E402
    read_pin_text,
    record,
)

__all__: list[str] = [
    "walk_livespec_jsonc",
    "walk_pyproject_toml",
    "walk_vendor_jsonc",
]


_LIVESPEC_JSONC = ".livespec.jsonc"
_PYPROJECT_TOML = "pyproject.toml"
_VENDOR_JSONC = ".vendor.jsonc"

_PIN_FORMAT_LIVESPEC = "livespec_jsonc_compat_pinned"
_PIN_FORMAT_UV_SOURCES = "pyproject_toml_uv_sources"
_PIN_FORMAT_VENDOR = "vendor_jsonc"
_PIN_FORMAT_UNRECOGNIZED = "unrecognized"


def _normalize_for_vendor_match(*, name: str) -> str:
    """Hyphen-to-underscore normalization for `.vendor.jsonc` `name` matching."""
    return name.replace("-", "_")


def walk_livespec_jsonc(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> list[dict[str, str]]:
    path = root / _LIVESPEC_JSONC
    if not path.is_file():
        return []
    rel_path = _LIVESPEC_JSONC
    text = read_pin_text(path=path)
    try:
        parsed = jsoncomment.loads(text)
    except (ValueError, json.JSONDecodeError):
        log.warning("unrecognized .livespec.jsonc — failed to parse", file_path=rel_path)
        return [
            record(
                pin_format=_PIN_FORMAT_UNRECOGNIZED,
                file_path=rel_path,
                pin_key="",
                current_value="",
                source_repo="",
            )
        ]
    if not isinstance(parsed, dict):
        return []
    # The `compat.pinned` field always pins the consumer to a livespec
    # release tag — the source repo is fixed at the literal "livespec".
    source_repo = "livespec"
    if source_repo_filter is not None and source_repo_filter != source_repo:
        return []
    out: list[dict[str, str]] = []
    # The `cast` is the single typed parse boundary: the parsed `.livespec.jsonc`
    # document is `Any`; casting to `dict[str, object]` (after the `isinstance`
    # guard above) types `.items()` so each `value`/`compat` narrows from
    # `object` via the per-key `isinstance(..., dict)` guards below — replacing
    # the prior `# pyright: ignore` markers with a real typed boundary.
    typed_parsed = cast("dict[str, object]", parsed)
    for top_key, value in typed_parsed.items():
        if not isinstance(value, dict):
            continue
        value_dict = cast("dict[str, object]", value)
        compat = value_dict.get("compat")
        if not isinstance(compat, dict):
            continue
        compat_dict = cast("dict[str, object]", compat)
        pinned = compat_dict.get("pinned")
        livespec_field = compat_dict.get("livespec")
        if not isinstance(pinned, str) or not isinstance(livespec_field, str):
            continue
        out.append(
            record(
                pin_format=_PIN_FORMAT_LIVESPEC,
                file_path=rel_path,
                pin_key=str(top_key),
                current_value=pinned,
                source_repo=source_repo,
            )
        )
    return out


_UV_SOURCES_HEADER_RE = re.compile(r"^\s*\[tool\.uv\.sources\]\s*$", re.MULTILINE)
_UV_SOURCES_ENTRY_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_\-]+)\s*=\s*\{(?P<body>[^}]*)\}\s*$",
    re.MULTILINE,
)
_UV_SOURCE_FIELD_RE = re.compile(r"(?P<key>git|tag|rev|branch)\s*=\s*\"(?P<value>[^\"]*)\"")
_NEXT_SECTION_RE = re.compile(r"^\s*\[(?!tool\.uv\.sources)", re.MULTILINE)


def _extract_uv_sources_block(*, text: str) -> str | None:
    """Return the body of the `[tool.uv.sources]` section, or None if absent."""
    header = _UV_SOURCES_HEADER_RE.search(text)
    if header is None:
        return None
    rest = text[header.end() :]
    next_section = _NEXT_SECTION_RE.search(rest)
    if next_section is None:
        return rest
    return rest[: next_section.start()]


def _source_repo_from_git_url(*, url: str) -> str:
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return tail[: -len(".git")] if tail.endswith(".git") else tail


def walk_pyproject_toml(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> list[dict[str, str]]:
    path = root / _PYPROJECT_TOML
    if not path.is_file():
        return []
    rel_path = _PYPROJECT_TOML
    text = read_pin_text(path=path)
    block = _extract_uv_sources_block(text=text)
    if block is None:
        return []
    out: list[dict[str, str]] = []
    saw_any_entry = False
    for match in _UV_SOURCES_ENTRY_RE.finditer(block):
        saw_any_entry = True
        name = match.group("name")
        body = match.group("body")
        fields = {f.group("key"): f.group("value") for f in _UV_SOURCE_FIELD_RE.finditer(body)}
        git_url = fields.get("git")
        tag = fields.get("tag")
        if git_url is None or tag is None:
            continue
        source_repo = _source_repo_from_git_url(url=git_url)
        if source_repo_filter is not None and source_repo_filter != source_repo:
            continue
        out.append(
            record(
                pin_format=_PIN_FORMAT_UV_SOURCES,
                file_path=rel_path,
                pin_key=name,
                current_value=tag,
                source_repo=source_repo,
            )
        )
    if not saw_any_entry:
        log.warning(
            "unrecognized [tool.uv.sources] block — no entries matched expected shape",
            file_path=rel_path,
        )
        return [
            record(
                pin_format=_PIN_FORMAT_UNRECOGNIZED,
                file_path=rel_path,
                pin_key="",
                current_value="",
                source_repo="",
            )
        ]
    return out


def walk_vendor_jsonc(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> list[dict[str, str]]:
    path = root / _VENDOR_JSONC
    if not path.is_file():
        return []
    rel_path = _VENDOR_JSONC
    text = read_pin_text(path=path)
    try:
        parsed = jsoncomment.loads(text)
    except (ValueError, json.JSONDecodeError):
        log.warning("unrecognized .vendor.jsonc — failed to parse", file_path=rel_path)
        return [
            record(
                pin_format=_PIN_FORMAT_UNRECOGNIZED,
                file_path=rel_path,
                pin_key="",
                current_value="",
                source_repo="",
            )
        ]
    # The `cast` is the single typed parse boundary: the parsed `.vendor.jsonc`
    # document is `Any`; casting to `dict[str, object]` (under the `isinstance`
    # guard) types `.get("libraries")` so the iteration below narrows from
    # `object` via the per-entry `isinstance` guards — replacing the prior
    # `# pyright: ignore` markers with a real typed boundary.
    config = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None
    libraries = config.get("libraries") if config is not None else None
    if not isinstance(libraries, list):
        return []
    filter_normalized = (
        _normalize_for_vendor_match(name=source_repo_filter)
        if source_repo_filter is not None
        else None
    )
    out: list[dict[str, str]] = []
    # The `cast` is the single typed parse boundary: the `isinstance` guard
    # above narrows `libraries` to `list[Unknown]`; the cast gives the entries
    # a typed `object` shape so the per-entry `isinstance(entry, dict)` guard
    # stays load-bearing, and the inner cast types each entry's `.get(...)` —
    # replacing the prior `# pyright: ignore` markers with a real boundary.
    typed_libraries: list[object] = cast("list[object]", libraries)
    for entry in typed_libraries:
        if not isinstance(entry, dict):
            continue
        entry_dict: dict[str, object] = cast("dict[str, object]", entry)
        name = entry_dict.get("name")
        upstream_ref = entry_dict.get("upstream_ref")
        if not isinstance(name, str) or not isinstance(upstream_ref, str):
            continue
        if filter_normalized is not None and filter_normalized != name:
            continue
        out.append(
            record(
                pin_format=_PIN_FORMAT_VENDOR,
                file_path=rel_path,
                pin_key=name,
                current_value=upstream_ref,
                source_repo=name,
            )
        )
    return out
