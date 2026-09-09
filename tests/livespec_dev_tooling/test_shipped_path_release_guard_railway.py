"""The guard's four IO seams are on the railway, and the check CONSUMES the failure track.

Work-item `livespec-dev-tooling-qndn.2`, epic `8o8e`. The shipped-path release
guard reaches the outside world at exactly four public seams — two per-repo input
resolvers in `_shipped_path_release_guard_inputs` (a `read_text` and a
`json.loads`), and two range readers in `_shipped_path_release_guard_range` (a
`git` subprocess each). Every one of them used to fold a read that DID NOT HAPPEN
onto an ordinary answer, or raise out of `main()`.

**THE LOAD-BEARING ASSERTIONS IN THIS FILE ARE THE FAILURE ONES.** Typing a
function `IOResult` while still returning `IOSuccess` for a read that failed
MOVES the sentinel rather than removing it, so the type assertion alone would
pass against exactly the defect this conversion exists to remove. Each seam is
therefore pinned twice: the annotation the arming check reads, and the value the
seam produces when its read does not happen.

And the failure answers matter here MORE than in the average conversion, because
of the shape the guard's caller already documents: an empty commit list reads
exactly like a clean branch, and an empty shipped-prefix derivation is a
load-bearing ANSWER ("this repository ships no plugin bytes"). Both of the
guard's natural failure spellings are therefore indistinguishable from a PASS.
That is why every test below asserts the refusal — a conversion that merely
stopped raising would be a silent fail-open.

⛔ WHAT STAYS ON THE SUCCESS TRACK is asserted too, because over-conversion is
the symmetric error this thread has made before: an ABSENT release-please config
(release-please's own defaults apply), a repository deriving no shipped prefixes,
and a base ref that does not resolve are all ANSWERS. An invocation that
completes and answers is a success whatever it answers.

`main()` is called in-process rather than spawned, per the
`tests_no_subprocess_spawn` discipline — only `git` itself is a subprocess here.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from returns.io import IOFailure, IOResult, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling import _shipped_path_release_guard_range as guard_range
from livespec_dev_tooling import shipped_path_release_guard_check as check
from livespec_dev_tooling._shipped_path_release_guard_inputs import (
    InputUnreadable,
    Resolved,
    resolve_releasing_types,
    resolve_shipped_prefixes,
)
from livespec_dev_tooling._shipped_path_release_guard_range import (
    commits_in_range,
    range_base_resolvable,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

__all__: list[str] = []


_PACKAGE = Path(__file__).resolve().parents[2] / "livespec_dev_tooling"
_INPUTS_MODULE = "_shipped_path_release_guard_inputs.py"
_RANGE_MODULE = "_shipped_path_release_guard_range.py"

# Vars git sets when invoking hooks. Unscrubbed, they redirect the in-process
# check's git invocations to the surrounding repo instead of the fixture — the
# same scrubbing `test_shipped_path_release_guard_check.py` documents.
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


def _git(*, cwd: Path, args: list[str]) -> str:
    # S603/S607: argv is a fixed list (literal git binary + repo-controlled
    # args); bare `git` is the canonical invocation per system PATH; no
    # untrusted shell input.
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )
    return result.stdout.strip()


def _make_repo(*, root: Path, set_range_base: bool = True) -> None:
    """One baseline commit, and optionally an `origin/master` anchored at it."""
    _ = _git(cwd=root, args=["init", "-q"])
    _ = _git(cwd=root, args=["config", "user.email", "test@example.com"])
    _ = _git(cwd=root, args=["config", "user.name", "Test"])
    _ = (root / "README.md").write_text("baseline\n", encoding="utf-8")
    _ = _git(cwd=root, args=["add", "-A"])
    _ = _git(cwd=root, args=["commit", "-m", "chore: baseline"])
    if set_range_base:
        _ = _git(
            cwd=root,
            args=[
                "update-ref",
                "refs/remotes/origin/master",
                _git(cwd=root, args=["rev-parse", "HEAD"]),
            ],
        )


def _break_git_verb(*, monkeypatch: pytest.MonkeyPatch, verb: str) -> None:
    """Make exactly one git subcommand unrunnable, leaving every other one real.

    The seam being pinned is `subprocess.run` RAISING — git absent or
    unexecutable — which is the one failure no exit code can express. Patching a
    single verb rather than the whole binary is what lets a test reach the
    enumeration's LATER commands: `commits_in_range` only runs `git log` and
    `git show` once `git rev-list` has already answered.
    """
    real_run = subprocess.run

    def _selective(args: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if list(args)[1] == verb:
            message = f"fixture: `git {verb}` is unrunnable"
            raise OSError(message)
        return real_run(args, **kwargs)  # pyright: ignore[reportUnknownVariableType]

    monkeypatch.setattr(guard_range.subprocess, "run", _selective)


def _unlistable_root(*, repo_root: Path) -> IOResult[Resolved, InputUnreadable]:
    """A `resolve_shipped_prefixes` stand-in whose read never happened."""
    return IOFailure(InputUnreadable(source=str(repo_root), detail="fixture: root unlistable"))


def _run_range(*, monkeypatch: pytest.MonkeyPatch, root: Path) -> int:
    """Invoke the check with NO argv — the `just check` aggregate's range mode."""
    for name in _GIT_HOOK_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "argv", ["shipped-path-release-guard"])
    return check.main()


def _diagnostics(*, capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    """Every structlog JSON line the check wrote to stderr."""
    captured = capsys.readouterr().err
    return [json.loads(line) for line in captured.splitlines() if line.strip()]


def _annotation_head(*, annotation: ast.expr) -> str:
    """A return annotation's TERMINAL name, as the arming check reads it.

    `public_api_result_typed._is_railway_compliant` compares that head name
    against `{"Result", "IOResult"}`, so this walks a `Subscript` down to its
    base exactly the way that check does — `IOResult[Resolved, InputUnreadable]`
    reduces to `IOResult`, and a bare `int` is already its own head.
    """
    while isinstance(annotation, ast.Subscript):
        annotation = annotation.value
    return ast.unparse(annotation)


def _annotation_heads(*, module: str) -> dict[str, str]:
    """Each annotated function in `module` mapped to its return annotation's head.

    Read from the SOURCE rather than from `__annotations__` because
    `from __future__ import annotations` leaves the runtime value a string, and a
    string comparison would pass against a typo the check would reject.
    """
    tree = ast.parse((_PACKAGE / module).read_text(encoding="utf-8"))
    return {
        node.name: _annotation_head(annotation=node.returns)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.returns is not None
    }


@pytest.mark.parametrize(
    ("module", "function"),
    [
        (_INPUTS_MODULE, "resolve_releasing_types"),
        (_INPUTS_MODULE, "resolve_shipped_prefixes"),
        (_RANGE_MODULE, "range_base_resolvable"),
        (_RANGE_MODULE, "commits_in_range"),
    ],
)
def test_the_four_public_seams_are_railway_typed(*, module: str, function: str) -> None:
    """The acceptance assertion: each of the four returns an `IOResult`.

    Necessary and NOT sufficient — every other test in this file exists because
    an `IOResult` that never fails is the same sentinel with a new type.
    """
    head = _annotation_heads(module=module).get(function)

    assert head == "IOResult", f"{module}::{function} returns `{head}`, not a railway type"


def test_an_absent_release_please_config_stays_an_ordinary_answer(*, tmp_path: Path) -> None:
    """Release-please's own defaults are an ANSWER, so they ride the success track."""
    resolved = resolve_releasing_types(repo_root=tmp_path)

    assert isinstance(resolved, IOSuccess)
    answer = unsafe_perform_io(resolved.unwrap())
    assert answer.values == frozenset({"feat", "feature", "fix", "perf", "revert"})
    assert "built-in defaults" in answer.source


def test_a_present_but_unparseable_release_please_config_fails(*, tmp_path: Path) -> None:
    """⛔ NOT the defaults. A malformed config is not the absent-config case.

    Falling back here would report a releasing-type set the repository never
    declared, sourced to a file that could not be parsed — the value-against-a-
    wrong-source failure `Resolved` exists to make impossible.
    """
    _ = (tmp_path / "release-please-config.json").write_text("{ not json at all", encoding="utf-8")

    resolved = resolve_releasing_types(repo_root=tmp_path)

    assert isinstance(resolved, IOFailure)
    failed = unsafe_perform_io(resolved.failure())
    assert isinstance(failed, InputUnreadable)
    assert failed.source == "release-please-config.json"
    assert failed.detail


def test_a_repository_deriving_no_shipped_prefixes_stays_an_ordinary_answer(
    *, tmp_path: Path
) -> None:
    """An empty derivation is the answer "this repository ships no plugin bytes"."""
    resolved = resolve_shipped_prefixes(repo_root=tmp_path)

    assert isinstance(resolved, IOSuccess)
    answer = unsafe_perform_io(resolved.unwrap())
    assert answer.values == frozenset()
    assert "ships no plugin bytes" in answer.source


def test_a_repository_root_that_cannot_be_listed_fails(*, tmp_path: Path) -> None:
    """The empty derivation above is why this MUST NOT be `IOSuccess(frozenset())`.

    An unreadable root derives nothing, so a fold onto the empty answer would
    have the guard report itself correctly inert on a repository it never
    managed to look at.
    """
    resolved = resolve_shipped_prefixes(repo_root=tmp_path / "no-such-checkout")

    assert isinstance(resolved, IOFailure)
    failed = unsafe_perform_io(resolved.failure())
    assert failed.source.endswith("no-such-checkout")


def test_an_unresolvable_base_is_a_success_carrying_false(*, tmp_path: Path) -> None:
    """The probe's non-zero EXIT is the answer it asks for, not a failure.

    The caller turns this `False` into a refusal — but it does so with a remedy
    ("fetch the base ref") that a git which never ran has no use for, which is
    the whole reason the two are different tracks.
    """
    _make_repo(root=tmp_path, set_range_base=False)

    probed = range_base_resolvable(repo_root=tmp_path)

    assert isinstance(probed, IOSuccess)
    assert unsafe_perform_io(probed.unwrap()) is False


def test_a_resolvable_base_is_a_success_carrying_true(*, tmp_path: Path) -> None:
    _make_repo(root=tmp_path)

    probed = range_base_resolvable(repo_root=tmp_path)

    assert isinstance(probed, IOSuccess)
    assert unsafe_perform_io(probed.unwrap()) is True


def test_the_base_probe_fails_when_git_cannot_run(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """git absent is NOT "the base does not resolve"; before the conversion it raised."""
    _make_repo(root=tmp_path)
    _break_git_verb(monkeypatch=monkeypatch, verb="rev-parse")

    probed = range_base_resolvable(repo_root=tmp_path)

    assert isinstance(probed, IOFailure)
    failed = unsafe_perform_io(probed.failure())
    assert failed.argv.startswith("git rev-parse")


def test_an_empty_range_enumerates_to_an_empty_success(*, tmp_path: Path) -> None:
    """The empty tuple stays reachable ONLY as a genuine answer."""
    _make_repo(root=tmp_path)

    enumerated = commits_in_range(repo_root=tmp_path)

    assert isinstance(enumerated, IOSuccess)
    assert unsafe_perform_io(enumerated.unwrap()) == ()


def test_the_enumeration_reports_the_commits_it_reads(*, tmp_path: Path) -> None:
    _make_repo(root=tmp_path)
    (tmp_path / ".claude-plugin").mkdir()
    _ = (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        '{"name": "x"}\n', encoding="utf-8"
    )
    _ = _git(cwd=tmp_path, args=["add", "-A"])
    _ = _git(cwd=tmp_path, args=["commit", "-m", "docs: add a manifest"])

    enumerated = commits_in_range(repo_root=tmp_path)

    assert isinstance(enumerated, IOSuccess)
    commits = unsafe_perform_io(enumerated.unwrap())
    assert len(commits) == 1
    assert commits[0].message.startswith("docs: add a manifest")
    assert commits[0].changed_paths == (".claude-plugin/plugin.json",)


def test_the_enumeration_fails_when_the_base_does_not_resolve(*, tmp_path: Path) -> None:
    """A non-zero `rev-list` contradicts the precondition the caller established.

    Before the conversion this raised `CalledProcessError` out of the aggregate:
    a check that DIED rather than a range that was judged.
    """
    _make_repo(root=tmp_path, set_range_base=False)

    enumerated = commits_in_range(repo_root=tmp_path)

    assert isinstance(enumerated, IOFailure)
    failed = unsafe_perform_io(enumerated.failure())
    assert failed.argv.startswith("git rev-list")
    assert "exit " in failed.detail


@pytest.mark.parametrize("verb", ["rev-list", "log", "show"])
def test_a_git_command_that_stops_answering_ends_the_enumeration(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verb: str
) -> None:
    """⛔ A PARTIAL list would be reported as the whole range.

    The three verbs are the three commands the enumeration issues, and the later
    two are only reachable once `rev-list` has answered — so each is broken on
    its own. Whichever one stops answering, the commits it would have described
    must NOT come back as a shorter list: the dropped commits would then read as
    judged and clean.
    """
    _make_repo(root=tmp_path)
    _ = (tmp_path / "shipped.txt").write_text("bytes\n", encoding="utf-8")
    _ = _git(cwd=tmp_path, args=["add", "-A"])
    _ = _git(cwd=tmp_path, args=["commit", "-m", "docs: a commit in the range"])
    _break_git_verb(monkeypatch=monkeypatch, verb=verb)

    enumerated = commits_in_range(repo_root=tmp_path)

    assert isinstance(enumerated, IOFailure)
    failed = unsafe_perform_io(enumerated.failure())
    assert failed.argv.startswith(f"git {verb}")


def test_main_refuses_a_repository_whose_release_please_config_cannot_be_parsed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The caller CONSUMES the input failure track: exit 1, named, with no verdict."""
    _make_repo(root=tmp_path)
    _ = (tmp_path / "release-please-config.json").write_text("{ not json", encoding="utf-8")

    assert _run_range(monkeypatch=monkeypatch, root=tmp_path) == 1

    modes = [line.get("failure_mode") for line in _diagnostics(capsys=capsys)]
    assert "input_unreadable" in modes


def test_main_refuses_when_the_shipped_prefix_derivation_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The SECOND resolver's failure track is consumed too, not just the first.

    Asserted through a seam rather than an unlistable cwd because `Path.cwd()`
    itself is what fails when the working directory is removed — which never
    reaches the resolver, so it would pin nothing about this branch.
    """
    _make_repo(root=tmp_path)
    monkeypatch.setattr(check, "resolve_shipped_prefixes", _unlistable_root)

    assert _run_range(monkeypatch=monkeypatch, root=tmp_path) == 1

    modes = [line.get("failure_mode") for line in _diagnostics(capsys=capsys)]
    assert "input_unreadable" in modes


@pytest.mark.parametrize("verb", ["rev-parse", "rev-list"])
def test_range_mode_refuses_when_a_git_command_does_not_answer(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    verb: str,
) -> None:
    """Both range seams refuse: the base probe and the enumeration.

    ⛔ Exit 1, never 0. An unanswered git command leaves the range UNKNOWN, and
    the module's own docstring records why unknown must not be spelled the same
    way as clean: an empty commit list reads exactly like a clean branch.
    """
    _make_repo(root=tmp_path)
    _break_git_verb(monkeypatch=monkeypatch, verb=verb)

    assert _run_range(monkeypatch=monkeypatch, root=tmp_path) == 1

    modes = [line.get("failure_mode") for line in _diagnostics(capsys=capsys)]
    assert "range_command_failed" in modes
