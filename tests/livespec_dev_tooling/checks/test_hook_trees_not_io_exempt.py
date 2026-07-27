"""Outside-in test for `checks/hook_trees_not_io_exempt.py`.

Declaring an agent-runtime hook tree in `io_trees` makes it wholesale exempt
from the catch-position and domain-raise rules. livespec
`SPECIFICATION/non-functional-requirements.md` forecloses that: there is no
"thin repo" exemption, and a repo whose only Python is fail-open hooks still
composes those hooks' bodies on the railway beneath a single boundary. The
only exemption is a repo with ZERO first-party Python.

Three sessions of the `rop-sweep-fleet-policy` thread reached for that dodge
anyway, and the third MERGED it in six repositories before review caught it.
The prohibition is explicit in ratified prose and still was not reaching
anyone at the moment they edited `io_trees` — so it is mechanized here.

The rule is deliberately narrow: HOOK trees are not io trees. A genuine
layered `io/` tree must keep passing untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.checks import hook_trees_not_io_exempt

__all__: list[str] = []


_PYPROJECT_TEMPLATE = """[project]
name = "consumer"
version = "0.0.0"

[tool.livespec_dev_tooling]
source_trees = ["pkg"]
io_trees = [{io_trees}]
commands_trees = []
supervisor_entry_files = []
pure_trees = []
covered_trees = []
target_dirs = []
source_tree_prefixes = []
dataclasses_tree = ""
neutral_hook_body_path = ""
"""


def _run(
    *,
    tmp_path: Path,
    io_trees: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    """Write a consumer pyproject, run the check in-process, return (rc, output)."""
    _ = (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_TEMPLATE.format(io_trees=io_trees), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    code = hook_trees_not_io_exempt.main()
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_rejects_claude_hooks_declared_in_io_trees(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`.claude/hooks` in `io_trees` is a hard error naming the offending path."""
    code, output = _run(
        tmp_path=tmp_path, io_trees='".claude/hooks"', monkeypatch=monkeypatch, capsys=capsys
    )

    assert code == 1, f"must reject `.claude/hooks` in io_trees; got {code}, output={output!r}"
    assert ".claude/hooks" in output, f"must name the offending path; output={output!r}"


def test_rejects_claude_plugin_hooks_declared_in_io_trees(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`.claude-plugin/hooks` is the other agent-runtime hook tree, equally refused."""
    code, output = _run(
        tmp_path=tmp_path,
        io_trees='".claude-plugin/hooks"',
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert code == 1, f"must reject `.claude-plugin/hooks`; got {code}, output={output!r}"
    assert ".claude-plugin/hooks" in output, f"must name the offending path; output={output!r}"


def test_rejects_a_subdirectory_of_a_hook_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Naming a SUBTREE of a hook tree is the same dodge one level down."""
    code, output = _run(
        tmp_path=tmp_path,
        io_trees='".claude/hooks/guards"',
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert code == 1, f"must reject a hook SUBTREE in io_trees; got {code}, output={output!r}"


def test_diagnostic_carries_the_clause_the_reason_and_the_route(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bare rejection gets worked around; the message must teach the rule.

    The three parts, each load-bearing: the QUOTED clause (a reader who has not
    opened the spec learns the rule from the error itself), why the exemption is
    UNNECESSARY (the same clause grants the one fail-open boundary catch, so the
    posture is not at risk), and the CONFORMING ROUTE with a shipped reference
    to copy.
    """
    _, output = _run(
        tmp_path=tmp_path, io_trees='".claude/hooks"', monkeypatch=monkeypatch, capsys=capsys
    )

    assert "thin repo" in output, f"must QUOTE the foreclosing clause; output={output!r}"
    assert "supervisor_entry_files" in output, f"must name the route; output={output!r}"
    assert "livespec-driver-claude" in output, f"must point at the reference; output={output!r}"


def test_accepts_a_genuine_layered_io_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The rule is narrow: a real `io/` package tree is untouched."""
    code, output = _run(
        tmp_path=tmp_path, io_trees='"pkg/io"', monkeypatch=monkeypatch, capsys=capsys
    )

    assert code == 0, f"must accept a genuine layered io tree; got {code}, output={output!r}"


def test_accepts_declared_empty_io_trees(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Declared-empty is the sanctioned opt-out and must not be reinterpreted."""
    code, output = _run(tmp_path=tmp_path, io_trees="", monkeypatch=monkeypatch, capsys=capsys)

    assert code == 0, f"must accept an empty io_trees; got {code}, output={output!r}"


def test_accepts_a_hooks_directory_that_is_not_an_agent_runtime_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only `.claude`/`.claude-plugin` hook trees are refused, not any dir named `hooks`.

    A package that legitimately has `pkg/io/hooks` is not making the
    thin-repo claim this check exists to refuse.
    """
    code, output = _run(
        tmp_path=tmp_path, io_trees='"pkg/io/hooks"', monkeypatch=monkeypatch, capsys=capsys
    )

    assert code == 0, f"must not flag an unrelated `hooks` directory; got {code}, output={output!r}"


def test_reports_every_offending_tree_not_just_the_first(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both hook trees are named, so one fix-and-rerun cycle sees the whole set."""
    code, output = _run(
        tmp_path=tmp_path,
        io_trees='".claude/hooks", ".claude-plugin/hooks"',
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert code == 1, f"must reject; got {code}, output={output!r}"
    assert ".claude/hooks" in output, f"must name the first tree; output={output!r}"
    assert ".claude-plugin/hooks" in output, f"must name the second tree; output={output!r}"
