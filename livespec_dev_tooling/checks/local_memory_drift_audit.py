"""Audit committed files against explicit host-local memory sources.

The check is consumer-side and local-vantage only: it reads the current
checkout plus explicitly mapped host-local Claude/Codex memory surfaces. It
does not clone, fetch, or parse downstream repos. Committed `.claude/*` files
are legitimate runtime/config files in the checkout; they are scan targets, but
they never satisfy the source-evidence requirement.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  - vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "claude_memory_glob",
    "claude_project_slug",
    "main",
]


_CHECK_ID = "local_memory_drift_audit"
_ARM_ENV = "LIVESPEC_LOCAL_MEMORY_DRIFT_AUDIT"
_CLAUDE_PROJECTS_ROOT_ENV = "LIVESPEC_LOCAL_MEMORY_CLAUDE_PROJECTS_ROOT"
_CODEX_MEMORIES_ROOT_ENV = "LIVESPEC_LOCAL_MEMORY_CODEX_MEMORIES_ROOT"
_CODEX_BACKGROUND_AUDIT_ENV = "LIVESPEC_LOCAL_MEMORY_CODEX_BACKGROUND_AUDIT"
_REPO_SLUG_ENV = "LIVESPEC_LOCAL_MEMORY_REPO_SLUG"
_FAIL_EXIT = 1
_SOURCE_FAIL_EXIT = 4
_MIN_SNIPPET_CHARS = 24
_SKIP_DIRS = frozenset({".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "_vendor"})
_TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".json",
        ".jsonc",
        ".just",
        ".md",
        ".py",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)


@dataclass(frozen=True, kw_only=True)
class MemorySource:
    path: Path
    source_kind: str
    text: str


@dataclass(frozen=True, kw_only=True)
class SourceSnippet:
    source: MemorySource
    text: str


@dataclass(frozen=True, kw_only=True)
class Contamination:
    source: Path
    source_kind: str
    target: Path
    snippet: str


def claude_project_slug(*, repo_root: Path) -> str:
    """Return Claude's host-local project slug for a checkout path."""
    absolute = repo_root.resolve()
    parts = absolute.parts
    for anchor in ("adopters", "fleet"):
        if anchor in parts:
            index = parts.index(anchor)
            return "-" + "-".join(parts[index:])
    return re.sub(r"[^A-Za-z0-9._-]", "-", absolute.as_posix())


def claude_memory_glob(*, projects_root: Path, repo_root: Path) -> Path:
    """Return the only Claude memory glob accepted as source evidence."""
    slug = os.environ.get(_REPO_SLUG_ENV, claude_project_slug(repo_root=repo_root))
    return projects_root / slug / "memory" / "*.md"


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(_CHECK_ID)


def _enabled() -> bool:
    return os.environ.get(_ARM_ENV, "").lower() in {"1", "true", "yes"}


def _read_text(*, path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="ignore")


def _nonempty_source(*, path: Path, source_kind: str) -> MemorySource | None:
    if not path.is_file():
        return None
    text = _read_text(path=path)
    if not text.strip():
        return None
    return MemorySource(path=path, source_kind=source_kind, text=text)


def _codex_memory_files(*, memories_root: Path) -> tuple[Path, ...]:
    if not memories_root.is_dir():
        return ()
    return tuple(
        path
        for path in sorted(memories_root.rglob("*"))
        if path.is_file() and _TEXT_SUFFIXES.intersection({path.suffix})
    )


def _memory_sources(*, repo_root: Path) -> tuple[MemorySource, ...]:
    home = Path.home()
    projects_root = Path(
        os.environ.get(_CLAUDE_PROJECTS_ROOT_ENV, str(home / ".claude" / "projects"))
    )
    codex_root = Path(os.environ.get(_CODEX_MEMORIES_ROOT_ENV, str(home / ".codex" / "memories")))
    background = Path(
        os.environ.get(
            _CODEX_BACKGROUND_AUDIT_ENV,
            str(home / ".codex" / "background-memory-audit.md"),
        )
    )
    claude_glob = claude_memory_glob(projects_root=projects_root, repo_root=repo_root)
    candidates = [
        *_source_candidates(paths=sorted(claude_glob.parent.glob(claude_glob.name)), kind="claude"),
        *_source_candidates(paths=_codex_memory_files(memories_root=codex_root), kind="codex-file"),
        *_source_candidates(paths=(background,), kind="codex-background"),
    ]
    return tuple(source for source in candidates if source is not None)


def _source_candidates(
    *, paths: tuple[Path, ...] | list[Path], kind: str
) -> tuple[MemorySource | None, ...]:
    return tuple(_nonempty_source(path=path, source_kind=kind) for path in paths)


def _snippets(*, sources: tuple[MemorySource, ...]) -> tuple[SourceSnippet, ...]:
    snippets: list[SourceSnippet] = []
    for source in sources:
        for paragraph in re.split(r"\n\s*\n", source.text):
            snippet = " ".join(paragraph.split())
            if len(snippet) >= _MIN_SNIPPET_CHARS:
                snippets.append(SourceSnippet(source=source, text=snippet))
    return tuple(snippets)


def _repo_text_files(*, root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and _SKIP_DIRS.isdisjoint(path.relative_to(root).parts)
        and path.suffix in _TEXT_SUFFIXES
    )


def _is_source_path(*, path: Path, sources: tuple[MemorySource, ...]) -> bool:
    resolved = path.resolve()
    return any(resolved == source.path.resolve() for source in sources)


def _contamination(
    *, repo_root: Path, snippets: tuple[SourceSnippet, ...], sources: tuple[MemorySource, ...]
) -> tuple[Contamination, ...]:
    findings: list[Contamination] = []
    for target in _repo_text_files(root=repo_root):
        if _is_source_path(path=target, sources=sources):
            continue
        text = " ".join(_read_text(path=target).split())
        for snippet in snippets:
            if snippet.text in text:
                findings.append(
                    Contamination(
                        source=snippet.source.path,
                        source_kind=snippet.source.source_kind,
                        target=target.relative_to(repo_root),
                        snippet=snippet.text[:120],
                    )
                )
    return tuple(findings)


def _log_no_evidence(*, log: structlog.stdlib.BoundLogger, repo_root: Path) -> None:
    log.error(
        "local-memory drift audit: no valid source evidence",
        check_id=_CHECK_ID,
        status="fail",
        failure_mode="no_local_memory_source_evidence",
        repo=str(repo_root),
        hint=(
            "fail closed: provide explicit Claude/Codex local-memory source evidence "
            "or route to regroom with an attached source bundle"
        ),
    )


def main() -> int:
    log = _configure_logger()
    if not _enabled():
        log.info(
            "local-memory drift audit: skipped",
            check_id=_CHECK_ID,
            reason=f"{_ARM_ENV} is unset",
        )
        return 0

    repo_root = Path.cwd()
    sources = _memory_sources(repo_root=repo_root)
    snippets = _snippets(sources=sources)
    if not snippets:
        _log_no_evidence(log=log, repo_root=repo_root)
        return _SOURCE_FAIL_EXIT

    findings = _contamination(repo_root=repo_root, snippets=snippets, sources=sources)
    for finding in findings:
        log.error(
            "local-memory drift audit: committed file contains host-local memory text",
            check_id=_CHECK_ID,
            status="fail",
            failure_mode="local_memory_contamination",
            source_kind=finding.source_kind,
            source=str(finding.source),
            path=str(finding.target),
            snippet=finding.snippet,
        )
    return _FAIL_EXIT if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
