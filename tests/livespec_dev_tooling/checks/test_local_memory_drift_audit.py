"""Outside-in tests for the consumer-side local-memory drift audit."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "local_memory_drift_audit.py"


class _CheckRun(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


def _load_check_module() -> ModuleType:
    assert _CHECK.is_file(), "local-memory drift audit check module must exist"
    spec = importlib.util.spec_from_file_location(
        "local_memory_drift_audit_under_test",
        str(_CHECK),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_check(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    env: dict[str, str],
) -> _CheckRun:
    module = _load_check_module()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "argv", ["local_memory_drift_audit"])
    for key in tuple(os.environ):
        if key.startswith("LIVESPEC_LOCAL_MEMORY_"):
            monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    rc = module.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _parse_findings(*, stderr: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in stderr.splitlines() if line.strip().startswith("{")]


def _claude_slug_for_repo(*, module: ModuleType, repo_root: Path) -> str:
    return str(module.claude_project_slug(repo_root=repo_root))


def _write_text(*, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _armed_env(*, home: Path, repo_root: Path, module: ModuleType) -> dict[str, str]:
    slug = _claude_slug_for_repo(module=module, repo_root=repo_root)
    return {
        "LIVESPEC_LOCAL_MEMORY_DRIFT_AUDIT": "1",
        "LIVESPEC_LOCAL_MEMORY_CLAUDE_PROJECTS_ROOT": str(home / ".claude" / "projects"),
        "LIVESPEC_LOCAL_MEMORY_CODEX_MEMORIES_ROOT": str(home / ".codex" / "memories"),
        "LIVESPEC_LOCAL_MEMORY_CODEX_BACKGROUND_AUDIT": str(
            home / ".codex" / "background-memory-audit.md"
        ),
        "LIVESPEC_LOCAL_MEMORY_REPO_SLUG": slug,
    }


def test_unarmed_audit_skips_and_scrubs_stale_local_memory_env(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Default invocation skips, and stale local-memory env does not leak between runs."""
    monkeypatch.setenv("LIVESPEC_LOCAL_MEMORY_STALE", "1")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys, env={})

    assert result.returncode == 0
    assert "skipped" in result.stderr
    assert result.stdout == ""


def test_slug_to_host_memory_mapping_points_at_current_repo_memory_dir(*, tmp_path: Path) -> None:
    """The Claude source is `~/.claude/projects/<slug>/memory/*.md` for this repo."""
    module = _load_check_module()
    repo_root = tmp_path / "adopters" / "livespec-driver-codex"
    projects_root = tmp_path / ".claude" / "projects"

    mapped = module.claude_memory_glob(projects_root=projects_root, repo_root=repo_root)

    assert mapped == projects_root / "-adopters-livespec-driver-codex" / "memory" / "*.md"


def test_reports_durable_local_memory_contamination_for_current_repo(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A committed fleet/adopter file containing a host-local memory paragraph fails."""
    module = _load_check_module()
    repo = tmp_path / "fleet" / "livespec-driver-claude"
    home = tmp_path / "home"
    slug = _claude_slug_for_repo(module=module, repo_root=repo)
    source_text = "Always preserve the adopter-only no-circular-dependency directive."
    _write_text(
        path=home / ".claude" / "projects" / slug / "memory" / "adopter.md",
        text=source_text + "\n",
    )
    _write_text(path=repo / "AGENTS.md", text=source_text + "\n")

    result = _run_check(
        cwd=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
        env=_armed_env(home=home, repo_root=repo, module=module),
    )

    assert result.returncode != 0
    findings = _parse_findings(stderr=result.stderr)
    assert any(finding.get("failure_mode") == "local_memory_contamination" for finding in findings)
    assert "AGENTS.md" in result.stderr
    assert "adopter.md" in result.stderr
    assert result.stdout == ""


def test_clean_repo_passes_with_valid_source_evidence(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A repo with source evidence but no committed copy of that evidence passes."""
    module = _load_check_module()
    repo = tmp_path / "livespec"
    home = tmp_path / "home"
    slug = _claude_slug_for_repo(module=module, repo_root=repo)
    _write_text(
        path=home / ".claude" / "projects" / slug / "memory" / "source.md",
        text="Remember the current repo slug for local harness cleanup only.\n\ntiny\n",
    )
    _write_text(path=repo / "README.md", text="public project documentation\n")

    result = _run_check(
        cwd=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
        env=_armed_env(home=home, repo_root=repo, module=module),
    )

    assert result.returncode == 0
    assert result.stdout == ""


def test_committed_claude_paths_do_not_count_as_source_evidence(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Committed `.claude/*` files are runtime/config files, not local-memory sources."""
    module = _load_check_module()
    repo = tmp_path / "livespec-dev-tooling"
    home = tmp_path / "home"
    _write_text(path=repo / ".claude" / "CLAUDE.md", text="durable local guidance\n")
    _write_text(path=repo / ".claude" / "settings.json", text="{ }\n")
    _write_text(path=repo / ".claude" / "hooks" / "stop.sh", text="durable local guidance\n")

    result = _run_check(
        cwd=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
        env=_armed_env(home=home, repo_root=repo, module=module),
    )

    assert result.returncode != 0
    assert "no_local_memory_source_evidence" in result.stderr
    assert "CLAUDE.md" not in result.stderr
    assert result.stdout == ""


def test_empty_no_source_evidence_fails_closed(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An armed factory worker with no valid source bundle fails closed."""
    module = _load_check_module()
    repo = tmp_path / "empty-consumer"
    home = tmp_path / "home"
    _write_text(path=repo / "README.md", text="clean\n")

    result = _run_check(
        cwd=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
        env=_armed_env(home=home, repo_root=repo, module=module),
    )

    assert result.returncode != 0
    assert "no_local_memory_source_evidence" in result.stderr
    assert "regroom" in result.stderr
    assert result.stdout == ""


def test_attached_source_bundle_inside_checkout_is_not_reported_as_contamination(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A regroom source bundle under the checkout is evidence, not a target finding."""
    module = _load_check_module()
    repo = tmp_path / "source-bundle-consumer"
    home = repo / "attached-source-bundle"
    slug = _claude_slug_for_repo(module=module, repo_root=repo)
    source_text = "Keep this attached source bundle out of committed target findings."
    _write_text(
        path=home / ".claude" / "projects" / slug / "memory" / "source.md",
        text=source_text + "\n",
    )
    _write_text(path=repo / "README.md", text="clean\n")

    result = _run_check(
        cwd=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
        env=_armed_env(home=home, repo_root=repo, module=module),
    )

    assert result.returncode == 0
    assert result.stdout == ""


def test_empty_codex_file_and_background_stores_do_not_mask_claude_evidence(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Empty Codex stores are ignored; non-empty Claude source evidence still passes."""
    module = _load_check_module()
    repo = tmp_path / "codex-consumer"
    home = tmp_path / "home"
    slug = _claude_slug_for_repo(module=module, repo_root=repo)
    _write_text(
        path=home / ".claude" / "projects" / slug / "memory" / "source.md",
        text="Use the local harness memory only as migration source evidence.\n",
    )
    _write_text(path=home / ".codex" / "memories" / "empty.md", text="")
    _write_text(path=home / ".codex" / "background-memory-audit.md", text="")
    _write_text(path=repo / "README.md", text="clean\n")

    result = _run_check(
        cwd=repo,
        monkeypatch=monkeypatch,
        capsys=capsys,
        env=_armed_env(home=home, repo_root=repo, module=module),
    )

    assert result.returncode == 0
    assert result.stdout == ""
