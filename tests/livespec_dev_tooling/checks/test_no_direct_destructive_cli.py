"""Outside-in test for `checks/no_direct_destructive_cli.py` — destructive-default CLI wrapping.

Per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Destructive-default CLI wrapping" (li-1f5 item 5, preservation
split): destructive-default external CLIs MUST be invoked through
project-local scripted wrappers that pin safe flags; agent-facing
prose MUST refer to the wrapper, not the underlying CLI. The shared
check greps the three agent-facing trees — `dev-tooling/`,
`.claude-plugin/`, and `.claude/plugins/` — for direct invocations
of known-destructive-default CLIs:

- `bd init`
- `git push --force` (including `--force-with-lease` and the `-f`
  short spelling)
- `git reset --hard`
- `gh repo delete`

A line matching any banned invocation is a violation (exit 1) UNLESS
the file is exempted by the explicit
`[tool.livespec_dev_tooling].destructive_cli_allowlist` path-prefix
allowlist in the consumer's `pyproject.toml` (e.g., a research-notes
subtree that legitimately documents a destructive CLI's behavior).
A repo with none of the scanned trees passes vacuously. Binary files
(NUL byte present) and `_vendor`/`__pycache__` subtrees are skipped.

The check reads `Path.cwd()`, so every test `monkeypatch.chdir`s
into its `tmp_path` fixture tree before invoking `main()`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_MODULE = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_direct_destructive_cli.py"


def _load_main() -> object:
    """Import the check module by file path and return its `main` callable.

    Loaded fresh per call so the module-under-test reads the
    current `Path.cwd()` (the tests `monkeypatch.chdir` into a
    fixture tree before invoking).
    """
    spec = importlib.util.spec_from_file_location(
        "no_direct_destructive_cli_under_test",
        str(_CHECK_MODULE),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def _write_file(*, tmp_path: Path, relpath: str, body: str) -> None:
    """Create `<tmp_path>/<relpath>` (parents included) with `body`."""
    target = tmp_path / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(body, encoding="utf-8")


def _write_pyproject(*, tmp_path: Path, body: str) -> None:
    _ = (tmp_path / "pyproject.toml").write_text(body, encoding="utf-8")


def test_rejects_bd_init_in_dev_tooling_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A direct `bd init` invocation under `dev-tooling/` is rejected (exit 1)."""
    _write_file(
        tmp_path=tmp_path,
        relpath="dev-tooling/setup.sh",
        body="#!/usr/bin/env bash\nbd init --server --quiet\n",
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 1  # type: ignore[operator]


def test_rejects_git_push_force_in_claude_plugin_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `git push --force` invocation under `.claude-plugin/` is rejected (exit 1)."""
    _write_file(
        tmp_path=tmp_path,
        relpath=".claude-plugin/skills/release/SKILL.md",
        body="## Steps\n\n```bash\ngit push --force origin master\n```\n",
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 1  # type: ignore[operator]


def test_rejects_force_with_lease_and_short_f_spellings(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--force-with-lease` and the `-f` short flag are force-push spellings too."""
    _write_file(
        tmp_path=tmp_path,
        relpath="dev-tooling/lease.sh",
        body="git push --force-with-lease origin topic\n",
    )
    _write_file(
        tmp_path=tmp_path,
        relpath="dev-tooling/short.sh",
        body="git push origin topic -f\n",
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 1  # type: ignore[operator]


def test_rejects_git_reset_hard_in_claude_plugins_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `git reset --hard` invocation under `.claude/plugins/` is rejected (exit 1)."""
    _write_file(
        tmp_path=tmp_path,
        relpath=".claude/plugins/cleaner/hooks/reset.sh",
        body="git reset --hard origin/master\n",
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 1  # type: ignore[operator]


def test_rejects_gh_repo_delete(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A `gh repo delete` invocation in an agent-facing tree is rejected (exit 1)."""
    _write_file(
        tmp_path=tmp_path,
        relpath="dev-tooling/cleanup.md",
        body="Run `gh repo delete owner/scratch --yes` to drop the scratch repo.\n",
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 1  # type: ignore[operator]


def test_accepts_safe_invocations(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Safe-by-default spellings of the same CLIs pass (exit 0).

    The pyproject block is present WITHOUT the allowlist key, pinning
    the key-absent regime (the check applies its empty default).
    """
    _write_pyproject(
        tmp_path=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
    )
    _write_file(
        tmp_path=tmp_path,
        relpath="dev-tooling/notes.md",
        body=(
            "git push origin master\n"
            "git reset --soft HEAD~1\n"
            "bd list --json\n"
            "gh repo view owner/repo\n"
            "git push --follow-tags origin master\n"
        ),
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 0  # type: ignore[operator]


def test_allowlisted_path_prefix_is_exempt(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A violation inside an allowlisted path prefix is exempt (exit 0)."""
    _write_pyproject(
        tmp_path=tmp_path,
        body=(
            "[tool.livespec_dev_tooling]\n"
            'destructive_cli_allowlist = ["dev-tooling/research/"]\n'
        ),
    )
    _write_file(
        tmp_path=tmp_path,
        relpath="dev-tooling/research/bd-notes.md",
        body="`bd init` auto-commits to master during bootstrap.\n",
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 0  # type: ignore[operator]


def test_violation_outside_allowlisted_prefix_still_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The allowlist exempts ONLY its prefixes; a sibling violation still fails."""
    _write_pyproject(
        tmp_path=tmp_path,
        body=(
            "[tool.livespec_dev_tooling]\n"
            'destructive_cli_allowlist = ["dev-tooling/research/"]\n'
        ),
    )
    _write_file(
        tmp_path=tmp_path,
        relpath="dev-tooling/research/bd-notes.md",
        body="`bd init` auto-commits to master during bootstrap.\n",
    )
    _write_file(
        tmp_path=tmp_path,
        relpath="dev-tooling/hook.sh",
        body="git reset --hard origin/master\n",
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 1  # type: ignore[operator]


def test_vacuous_skip_when_no_scanned_trees(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repo with none of the scanned trees passes vacuously (exit 0)."""
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 0  # type: ignore[operator]


def test_skips_binary_files(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A binary file (NUL byte) carrying a banned byte sequence is skipped (exit 0)."""
    blob = tmp_path / "dev-tooling" / "blob.bin"
    blob.parent.mkdir(parents=True, exist_ok=True)
    _ = blob.write_bytes(b"\x00git reset --hard origin/master\xff")
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 0  # type: ignore[operator]


def test_skips_vendor_and_pycache_subtrees(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Violations under `_vendor/` or `__pycache__/` subtrees are skipped (exit 0)."""
    _write_file(
        tmp_path=tmp_path,
        relpath=".claude-plugin/_vendor/lib/setup.sh",
        body="bd init --server\n",
    )
    _write_file(
        tmp_path=tmp_path,
        relpath=".claude-plugin/__pycache__/cache.txt",
        body="git push --force origin master\n",
    )
    monkeypatch.chdir(tmp_path)
    main = _load_main()
    assert main() == 0  # type: ignore[operator]


def test_check_module_importable_without_running_main() -> None:
    """The check module imports cleanly and exposes a callable `main`."""
    main = _load_main()
    assert callable(main)
