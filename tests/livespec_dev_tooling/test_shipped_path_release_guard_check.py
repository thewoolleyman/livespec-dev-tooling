"""Integration-tier tests for `livespec_dev_tooling/shipped_path_release_guard_check.py`.

Slice B of the R6 guard (work-item `livespec-dev-tooling-l42g`). The module under
test is the RUNNABLE half: it resolves the guard's inputs from a real repository
and delegates the rule to slice A's pure core. These tests therefore build real
temporary git repositories — a real `git init`, a real staged index, a real
release-please config and real plugin manifests — and invoke `main()` IN-PROCESS
against each one, so what is pinned is the RESOLUTION, which is the only thing
this slice adds.

The four cases the work-item names:

- a `docs:` commit touching a shipped path FAILS;
- a `docs:` commit touching a non-shipped path PASSES;
- a releasing type (`fix:`) touching a shipped path PASSES;
- the override trailer PASSES a change that would otherwise fail.

Plus the per-repo resolution pinned in BOTH DIRECTIONS, which is the regression
that matters most: a repository declaring `changelog-sections` that include
`refactor` with `hidden: false` treats `refactor` as releasing, and a repository
declaring none does NOT. A fleet constant could only ever be right for one of
those two, so asserting only one direction would let the refuted premise back in.

`main()` is called in-process rather than spawned, per the
`tests_no_subprocess_spawn` discipline — only `git` itself is a subprocess here.
That makes the GIT_* hook variables load-bearing: when this suite runs under a
lefthook gate they are set, and the check's own `git diff --cached` would resolve
against the SURROUNDING repository instead of the fixture. They are scrubbed for
every test.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.shipped_path_release_guard_check import main

__all__: list[str] = []


# Vars git sets when invoking hooks (lefthook pre-commit / commit-msg /
# pre-push). Unscrubbed, they redirect the in-process check's `git diff --cached`
# to the surrounding repo instead of the fixture. Mirrors the discipline in
# `tests/livespec_dev_tooling/checks/test_commit_pairs_source_and_test.py`.
_GIT_HOOK_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)

# livespec's own declared shape: `refactor` is visible, `docs` is hidden.
_LIVESPEC_STYLE_CONFIG = {
    "release-type": "python",
    "changelog-sections": [
        {"type": "feat", "section": "Features"},
        {"type": "fix", "section": "Bug Fixes"},
        {"type": "refactor", "section": "Refactoring", "hidden": False},
        {"type": "docs", "section": "Documentation", "hidden": True},
        # Malformed entries release-please would ignore; the resolver skips them
        # rather than crashing on a config the CONSUMER maintains for a tool that
        # is not us.
        {"section": "a section with no type"},
        "not an object at all",
    ],
}


def _git(*, cwd: Path, args: list[str]) -> None:
    # S603/S607: argv is a fixed list (literal git binary + repo-controlled
    # args); bare `git` is the canonical invocation per system PATH; no
    # untrusted shell input.
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _make_repo(
    *,
    root: Path,
    release_please_config: object | None = None,
    config_name: str = "release-please-config.json",
    manifest_dir: str | None = ".claude-plugin",
    manifest_name: str = "marketplace.json",
) -> None:
    """Build a fixture repo: one baseline commit, an optional config, an optional manifest."""
    _git(cwd=root, args=["init", "-q"])
    _git(cwd=root, args=["config", "user.email", "test@example.com"])
    _git(cwd=root, args=["config", "user.name", "Test"])
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    if release_please_config is not None:
        (root / config_name).write_text(json.dumps(release_please_config), encoding="utf-8")
    if manifest_dir is not None:
        plugin_dir = root / manifest_dir
        plugin_dir.mkdir(parents=True)
        (plugin_dir / manifest_name).write_text('{"name": "fixture"}\n', encoding="utf-8")
    _git(cwd=root, args=["add", "-A"])
    _git(cwd=root, args=["commit", "-m", "chore: baseline"])


def _stage(*, root: Path, rel_path: str, content: str = "changed\n") -> None:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(cwd=root, args=["add", rel_path])


def _run(
    *,
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    message: str,
    write_default_message: bool = False,
) -> int:
    """Invoke the check in-process against `root`, returning its exit code.

    By default the message is written to a file passed as the positional
    argument, exactly as git's `commit-msg` hook supplies it. With
    `write_default_message` the message goes to `<git-dir>/COMMIT_EDITMSG` and
    NO argument is passed, pinning the fallback.
    """
    for name in _GIT_HOOK_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(root)
    if write_default_message:
        (root / ".git" / "COMMIT_EDITMSG").write_text(message, encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["shipped-path-release-guard"])
        return main()
    message_path = root / "commit-message.txt"
    message_path.write_text(message, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["shipped-path-release-guard", "commit-message.txt"])
    return main()


def test_docs_touching_a_shipped_path_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The defect the guard exists for: shipped bytes under a type that cuts no release."""
    _make_repo(root=tmp_path, release_please_config=_LIVESPEC_STYLE_CONFIG)
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")
    # A non-shipped path staged alongside, so the refusal must name only the
    # offending one.
    _stage(root=tmp_path, rel_path="docs/runbook.md")

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message="docs(skills): fix a typo\n") == 1

    finding = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert finding["failure_mode"] == "shipped_path_edited_without_a_release"
    assert finding["offending_paths"] == [".claude-plugin/skills/next/SKILL.md"]
    assert finding["commit_type"] == "docs(skills)"
    assert finding["releasing_types"] == ["feat", "fix", "refactor"]
    assert "release-please-config.json" in finding["releasing_types_source"]
    assert ".claude-plugin/" in finding["shipped_prefixes_source"]
    assert finding["override_trailer"].startswith("Shipped-Path-Release-Waived:")
    assert "docs/shipped-path-release-guard.md" in finding["documentation"]


def test_docs_touching_a_non_shipped_path_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-releasing type outside the shipped set strands nothing."""
    _make_repo(root=tmp_path, release_please_config=_LIVESPEC_STYLE_CONFIG)
    _stage(root=tmp_path, rel_path="docs/runbook.md")

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message="docs: update the runbook\n") == 0


def test_a_releasing_type_touching_a_shipped_path_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shipped bytes under a releasing type reach seats at the next release."""
    _make_repo(root=tmp_path, release_please_config=_LIVESPEC_STYLE_CONFIG)
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message="fix(skills): fix a typo\n") == 0


def test_the_override_trailer_passes_a_change_that_would_otherwise_fail(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard forces an EXPLICIT decision rather than forbidding the edit."""
    _make_repo(root=tmp_path, release_please_config=_LIVESPEC_STYLE_CONFIG)
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")
    message = (
        "docs(skills): fix a typo\n"
        "\n"
        "A comment-only correction that changes no behaviour.\n"
        "\n"
        "Shipped-Path-Release-Waived: prose-only; no served behaviour changes\n"
    )

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message=message) == 0


def test_a_valueless_override_trailer_is_not_an_override(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare trailer records nothing, so it is a bypass flag rather than a decision."""
    _make_repo(root=tmp_path, release_please_config=_LIVESPEC_STYLE_CONFIG)
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")
    message = "docs(skills): fix a typo\n\nShipped-Path-Release-Waived:\n"

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message=message) == 1


def test_a_repo_declaring_refactor_visible_treats_refactor_as_releasing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direction one of the per-repo resolution: declared `hidden: false` releases."""
    _make_repo(root=tmp_path, release_please_config=_LIVESPEC_STYLE_CONFIG)
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message="refactor: rename it\n") == 0


def test_a_repo_declaring_no_changelog_sections_does_not_release_refactor(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Direction two: with no declaration release-please hides `refactor`, so it strands bytes.

    Read together with the test above, this is what makes a fleet constant
    impossible: the SAME commit type, the SAME shipped path, opposite verdicts,
    decided only by the repository's own config.
    """
    _make_repo(root=tmp_path, release_please_config={"release-type": "python"})
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message="refactor: rename it\n") == 1

    finding = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert finding["releasing_types"] == ["feat", "feature", "fix", "perf", "revert"]
    assert "built-in defaults" in finding["releasing_types_source"]


def test_a_repo_with_no_release_please_config_at_all_falls_back_to_the_defaults(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Neither config spelling present: the defaults apply and say so."""
    _make_repo(root=tmp_path, release_please_config=None)
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message="chore: tidy up\n") == 1

    finding = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert "built-in defaults" in finding["releasing_types_source"]


def test_the_dotfile_release_please_config_spelling_is_honoured(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`.release-please-config.json` is the other spelling release-please accepts."""
    _make_repo(
        root=tmp_path,
        release_please_config=_LIVESPEC_STYLE_CONFIG,
        config_name=".release-please-config.json",
    )
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message="docs: fix a typo\n") == 1

    finding = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert finding["releasing_types"] == ["feat", "fix", "refactor"]
    assert finding["releasing_types_source"].startswith(".release-please-config.json")


def test_a_nested_plugin_manifest_is_derived_as_a_shipped_prefix(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The second fleet layout: the manifest sits one level below the repository root."""
    _make_repo(
        root=tmp_path,
        release_please_config=_LIVESPEC_STYLE_CONFIG,
        manifest_dir="carrier/.claude-plugin",
        manifest_name="plugin.json",
    )
    _stage(root=tmp_path, rel_path="carrier/.claude-plugin/skills/next/SKILL.md")

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message="docs: fix a typo\n") == 1

    finding = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert finding["shipped_prefixes"] == ["carrier/.claude-plugin/"]
    assert (
        "derived from the `.claude-plugin/` manifest directories"
        in (finding["shipped_prefixes_source"])
    )


def test_a_repo_with_no_plugin_manifest_ships_nothing_and_says_so(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty derivation is an ANSWER, logged with its own source rather than passing silently."""
    _make_repo(root=tmp_path, release_please_config=_LIVESPEC_STYLE_CONFIG, manifest_dir=None)
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message="docs: fix a typo\n") == 0

    resolution = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert resolution["shipped_prefixes"] == []
    assert "ships no plugin bytes" in resolution["shipped_prefixes_source"]


def test_the_message_defaults_to_the_git_dir_commit_editmsg(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no positional argument the check reads `<git-dir>/COMMIT_EDITMSG`."""
    _make_repo(root=tmp_path, release_please_config=_LIVESPEC_STYLE_CONFIG)
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")

    assert (
        _run(
            monkeypatch=monkeypatch,
            root=tmp_path,
            message="docs: fix a typo\n",
            write_default_message=True,
        )
        == 1
    )


def test_an_unreadable_message_file_fails_rather_than_passing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No message means no commit type and no override, which is undecidable, not clean."""
    _make_repo(root=tmp_path, release_please_config=_LIVESPEC_STYLE_CONFIG)
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")
    for name in _GIT_HOOK_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["shipped-path-release-guard", "no-such-message.txt"])

    assert main() == 1

    finding = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert finding["failure_mode"] == "message_file_unreadable"


def test_a_comment_only_message_yields_no_commit_type(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Git's `#` lines are not the message; a message that is only comments types nothing."""
    _make_repo(root=tmp_path, release_please_config=_LIVESPEC_STYLE_CONFIG)
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")
    message = "\n# Please enter the commit message for your changes.\n#\n"

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message=message) == 1

    finding = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert finding["commit_type"] == "<no conventional-commit type>"


def test_a_breaking_footer_releases_a_docs_typed_shipped_edit(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The BODY reaches the core, not just the subject — a breaking footer releases."""
    _make_repo(root=tmp_path, release_please_config=_LIVESPEC_STYLE_CONFIG)
    _stage(root=tmp_path, rel_path=".claude-plugin/skills/next/SKILL.md")
    message = "docs(skills): rewrite the contract\n\nBREAKING CHANGE: the contract changed\n"

    assert _run(monkeypatch=monkeypatch, root=tmp_path, message=message) == 0
