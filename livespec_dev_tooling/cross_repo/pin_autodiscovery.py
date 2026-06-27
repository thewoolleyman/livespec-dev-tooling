"""pin_autodiscovery — walk a consumer repo and emit pin records as JSON.

Per `SPECIFICATION/contracts.md` §"Pin autodiscovery rules", the walk
inspects the consumer repository for every supported pin format and
yields a normalized record per discovered pin. The walk covers four
formats:

- `.livespec.jsonc` `compat.pinned` — every top-level key whose value
  carries a `compat` object with `pinned` and `livespec` fields. The
  pin's source repo is always `livespec`; the top-level key name is
  the consumer-self-identifier.
- `pyproject.toml` `[tool.uv.sources]` — every entry whose `git` URL
  identifies a GitHub repository; the `tag` field is the pin's
  current value. The source repo short-name is derived from the
  trailing path segment of the URL (with any `.git` suffix stripped).
- `.vendor.jsonc` — every entry in the `libraries` array whose `name`
  matches the source repository's normalized Python package name
  (hyphen-to-underscore). The `upstream_ref` field is the pin's
  current value.
- `.github/workflows/*.yml` / `*.yaml` `uses:` ref — every line of the
  form `uses: <owner>/<repo>/<path>@<ref>` in any GitHub Actions
  workflow file. The pin's source repo is derived from the `<repo>`
  segment; `current_value` is `<ref>`; `pin_key` is
  `<owner>/<repo>/<path>` (the full `uses:` reference without `@ref`).

`.copier-answers.yml` `_commit` is deliberately NOT a pin format: it
is copier render-provenance, not a version pin, so rewriting it would
desync the render-provenance marker and poison future `copier update`s.

Source-repo-name normalization for `.vendor.jsonc` matching is
hyphen-to-underscore (e.g., `livespec-runtime` matches
`livespec_runtime`). Other pin formats use the source repo's short
name verbatim.

Invocation:

    python -m livespec_dev_tooling.cross_repo.pin_autodiscovery \\
        [--root <path>] [--source-repo <name>] [--json]

`--root` defaults to the current working directory. `--source-repo`
filters records to a single source; omit it to emit every discovered
pin. `--json` is the default (and currently only) output mode and is
accepted for forward-compat with any future text mode.

Tolerance:

- Missing pin files yield no records (no error).
- An unrecognized pin format on a file we DID find but cannot parse
  yields one record with `pin_format: "unrecognized"` and the file
  path for human inspection.

Output discipline mirrors the check modules: structured stderr via
structlog when diagnostics are emitted; the result JSON array is
written to stdout. No `print()`, no `sys.stderr.write` direct.
"""

from __future__ import annotations

import argparse
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

__all__: list[str] = []


_LIVESPEC_JSONC = ".livespec.jsonc"
_PYPROJECT_TOML = "pyproject.toml"
_VENDOR_JSONC = ".vendor.jsonc"

_PIN_FORMAT_LIVESPEC = "livespec_jsonc_compat_pinned"
_PIN_FORMAT_UV_SOURCES = "pyproject_toml_uv_sources"
_PIN_FORMAT_VENDOR = "vendor_jsonc"
_PIN_FORMAT_WORKFLOW_USES = "github_workflow_uses_ref"
_PIN_FORMAT_UNRECOGNIZED = "unrecognized"


def _normalize_for_vendor_match(*, name: str) -> str:
    """Hyphen-to-underscore normalization for `.vendor.jsonc` `name` matching."""
    return name.replace("-", "_")


def _record(
    *,
    pin_format: str,
    file_path: str,
    pin_key: str,
    current_value: str,
    source_repo: str,
) -> dict[str, str]:
    return {
        "pin_format": pin_format,
        "file_path": file_path,
        "pin_key": pin_key,
        "current_value": current_value,
        "source_repo": source_repo,
    }


def _walk_livespec_jsonc(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> list[dict[str, str]]:
    path = root / _LIVESPEC_JSONC
    if not path.is_file():
        return []
    rel_path = _LIVESPEC_JSONC
    text = path.read_text(encoding="utf-8")
    try:
        parsed = jsoncomment.loads(text)
    except (ValueError, json.JSONDecodeError):
        log.warning("unrecognized .livespec.jsonc — failed to parse", file_path=rel_path)
        return [
            _record(
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
            _record(
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


def _walk_pyproject_toml(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> list[dict[str, str]]:
    path = root / _PYPROJECT_TOML
    if not path.is_file():
        return []
    rel_path = _PYPROJECT_TOML
    text = path.read_text(encoding="utf-8")
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
            _record(
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
            _record(
                pin_format=_PIN_FORMAT_UNRECOGNIZED,
                file_path=rel_path,
                pin_key="",
                current_value="",
                source_repo="",
            )
        ]
    return out


def _walk_vendor_jsonc(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> list[dict[str, str]]:
    path = root / _VENDOR_JSONC
    if not path.is_file():
        return []
    rel_path = _VENDOR_JSONC
    text = path.read_text(encoding="utf-8")
    try:
        parsed = jsoncomment.loads(text)
    except (ValueError, json.JSONDecodeError):
        log.warning("unrecognized .vendor.jsonc — failed to parse", file_path=rel_path)
        return [
            _record(
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
            _record(
                pin_format=_PIN_FORMAT_VENDOR,
                file_path=rel_path,
                pin_key=name,
                current_value=upstream_ref,
                source_repo=name,
            )
        )
    return out


_WORKFLOW_USES_RE = re.compile(
    r"""
    ^\s+uses:\s+
    (?P<owner>[A-Za-z0-9_.-]+)/
    (?P<repo>[A-Za-z0-9_.-]+)/
    (?P<path>[^@\s]+)@
    (?P<ref>[^\s#]+)
    """,
    re.VERBOSE,
)


def _walk_github_workflow_uses(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> list[dict[str, str]]:
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return []
    out: list[dict[str, str]] = []
    yml_paths = sorted(list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml")))
    for yml_path in yml_paths:
        rel_path = str(yml_path.relative_to(root))
        text = yml_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            match = _WORKFLOW_USES_RE.match(line)
            if match is None:
                continue
            owner = match.group("owner")
            repo = match.group("repo")
            path = match.group("path")
            ref = match.group("ref")
            if source_repo_filter is not None and source_repo_filter != repo:
                continue
            out.append(
                _record(
                    pin_format=_PIN_FORMAT_WORKFLOW_USES,
                    file_path=rel_path,
                    pin_key=f"{owner}/{repo}/{path}",
                    current_value=ref,
                    source_repo=repo,
                )
            )
    _ = log
    return out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pin-autodiscovery",
        description=(
            "Walk a consumer repo and emit a JSON array of pin records per "
            'SPECIFICATION/contracts.md §"Pin autodiscovery rules". Covers '
            ".livespec.jsonc, pyproject.toml [tool.uv.sources], .vendor.jsonc, "
            "and .github/workflows/*.yml uses: refs."
        ),
    )
    _ = parser.add_argument(
        "--root",
        type=Path,
        default=None,
        metavar="PATH",
        help="consumer repo root to walk (default: current working directory)",
    )
    _ = parser.add_argument(
        "--source-repo",
        type=str,
        default=None,
        metavar="NAME",
        help="restrict output to pins of this source repo (omit to emit all)",
    )
    _ = parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="emit JSON to stdout (default; accepted for forward-compat)",
    )
    return parser


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("pin_autodiscovery")


def discover(*, root: Path, source_repo: str | None) -> list[dict[str, str]]:
    """Pure entry point — walk `root` and return discovered pin records.

    Importable for embedded use (e.g., from a future Python-driven
    workflow); equivalent to invoking the CLI with `--root=<root>` and
    optionally `--source-repo=<source_repo>`.
    """
    log = _configure_logger()
    records: list[dict[str, str]] = []
    records.extend(_walk_livespec_jsonc(root=root, source_repo_filter=source_repo, log=log))
    records.extend(_walk_pyproject_toml(root=root, source_repo_filter=source_repo, log=log))
    records.extend(_walk_vendor_jsonc(root=root, source_repo_filter=source_repo, log=log))
    records.extend(_walk_github_workflow_uses(root=root, source_repo_filter=source_repo, log=log))
    return records


def main() -> int:
    args = _build_parser().parse_args()
    root: Path = args.root if args.root is not None else Path.cwd()
    source_repo: str | None = args.source_repo
    records = discover(root=root, source_repo=source_repo)
    _ = sys.stdout.write(json.dumps(records, indent=2, sort_keys=True))
    _ = sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
