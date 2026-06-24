"""Outside-in test for `checks/skill_invocation_paths.py` — fenced SKILL.md wrapper-invocation form.

Per the shared `skill_invocation_paths` check (work-item
legacy skill-invocation-paths work item): every `bin/<name>.py` wrapper
invocation that appears INSIDE a fenced code block of a
`.claude-plugin/skills/*/SKILL.md` file MUST use the canonical
form `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/<name>.py"`:

- MUST contain the `${CLAUDE_PLUGIN_ROOT}/` token.
- MUST NOT use `uv run` (the installed cache omits
  pyproject.toml / uv.lock so `uv run` cannot synthesize a venv).
- MUST NOT hard-code the `.claude-plugin/scripts` literal (the
  installer flattens `.claude-plugin/scripts/` to `scripts/`).
- The `${CLAUDE_PLUGIN_ROOT}/<relpath>.py` token MUST resolve to
  a real file under `.claude-plugin/<relpath>` in the repo.

The core semantic guarded here is the fenced-vs-prose
distinction: an invocation is a fenced exec line, NOT an inline
backtick reference in prose. A prose-only `bin/foo.py` reference
outside any fence is IGNORED. A repo with no
`.claude-plugin/skills/` directory passes vacuously (dev-tooling
itself has no skills).

The check reads `Path.cwd()`, so every test `monkeypatch.chdir`s
into its `tmp_path` fixture tree before invoking `main()` — a
prior cycle leaked a repo artifact by skipping this isolation.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_MODULE = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "skill_invocation_paths.py"


def _load_main() -> object:
    """Import the check module by file path and return its `main` callable.

    Loaded fresh per call so the module-under-test reads the
    current `Path.cwd()` (the tests `monkeypatch.chdir` into a
    fixture tree before invoking).
    """
    spec = importlib.util.spec_from_file_location(
        "skill_invocation_paths_under_test",
        str(_CHECK_MODULE),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def _write_skill(*, tmp_path: Path, skill_name: str, body: str) -> None:
    """Create `.claude-plugin/skills/<skill_name>/SKILL.md` with `body`."""
    skill_dir = tmp_path / ".claude-plugin" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    _ = (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


def _write_wrapper(*, tmp_path: Path, relpath: str) -> None:
    """Create a real wrapper file under `.claude-plugin/<relpath>`."""
    target = tmp_path / ".claude-plugin" / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text("#!/usr/bin/env python3\n", encoding="utf-8")


def test_accepts_canonical_fenced_invocation_resolving_to_real_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fenced canonical invocation pointing at a real wrapper passes (exit 0)."""
    _write_wrapper(tmp_path=tmp_path, relpath="scripts/bin/foo.py")
    _write_skill(
        tmp_path=tmp_path,
        skill_name="foo",
        body=(
            "## Invocation\n"
            "\n"
            "```bash\n"
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/foo.py" "$@"\n'
            "```\n"
        ),
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 0  # type: ignore[operator]


def test_rejects_uv_run_invocation(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A fenced `uv run` invocation is rejected (exit 1)."""
    _write_wrapper(tmp_path=tmp_path, relpath="scripts/bin/foo.py")
    _write_skill(
        tmp_path=tmp_path,
        skill_name="foo",
        body=(
            "## Invocation\n"
            "\n"
            "```bash\n"
            "uv run python3 .claude-plugin/scripts/bin/foo.py\n"
            "```\n"
        ),
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 1  # type: ignore[operator]


def test_rejects_claude_plugin_scripts_literal(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fenced invocation hard-coding the `.claude-plugin/scripts` literal is rejected."""
    _write_wrapper(tmp_path=tmp_path, relpath="scripts/bin/foo.py")
    _write_skill(
        tmp_path=tmp_path,
        skill_name="foo",
        body=(
            "## Invocation\n"
            "\n"
            "```bash\n"
            'python3 ".claude-plugin/scripts/bin/foo.py"\n'
            "```\n"
        ),
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 1  # type: ignore[operator]


def test_rejects_bare_invocation_without_plugin_root_token(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fenced bare `bin/foo.py` invocation (no `${CLAUDE_PLUGIN_ROOT}`) is rejected."""
    _write_wrapper(tmp_path=tmp_path, relpath="scripts/bin/foo.py")
    _write_skill(
        tmp_path=tmp_path,
        skill_name="foo",
        body=("## Invocation\n" "\n" "```bash\n" "python3 bin/foo.py\n" "```\n"),
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 1  # type: ignore[operator]


def test_rejects_invocation_not_resolving_to_real_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A canonical-form invocation whose target file does not exist is rejected."""
    # Note: no wrapper file is created — the token must fail to resolve.
    _write_skill(
        tmp_path=tmp_path,
        skill_name="foo",
        body=(
            "## Invocation\n"
            "\n"
            "```bash\n"
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/missing.py"\n'
            "```\n"
        ),
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 1  # type: ignore[operator]


def test_ignores_prose_only_reference_outside_fence(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backtick `bin/foo.py` reference in PROSE (outside any fence) is ignored (exit 0)."""
    _write_skill(
        tmp_path=tmp_path,
        skill_name="foo",
        body=(
            "## Overview\n"
            "\n"
            "Never invoke the `bin/foo.py` wrapper directly via `uv run`; "
            "this prose mention of `.claude-plugin/scripts/bin/foo.py` is "
            "explanatory only and is not an invocation.\n"
        ),
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 0  # type: ignore[operator]


def test_vacuous_skip_when_no_skills_dir(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repo with no `.claude-plugin/skills/` directory passes vacuously (exit 0)."""
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 0  # type: ignore[operator]


def test_check_module_importable_without_running_main() -> None:
    """The check module imports cleanly and exposes a callable `main`."""
    main = _load_main()
    assert callable(main)
