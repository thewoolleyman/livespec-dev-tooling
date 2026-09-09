"""Tests for `livespec_dev_tooling/agent_hooks/pretooluse_background_guard.py`.

Per work-item livespec-dev-tooling-7us.2, the PreToolUse guard denies
(exit 2) any Bash tool call that combines `run_in_background` with a
gate command (`just check*`, `git commit`, `git push`, `gh pr`), and
fails open (exit 0) on every other input including unparseable stdin.

Covered behaviors:

- gate-pattern matching including wrapper prefixes
  (`mise exec -- git commit`, `git -C <path> push`) and non-matches
  (`git log`, plain `ls`, separated compound commands);
- the pure deny decision (`_should_deny`) over tool name /
  `run_in_background` / command-shape combinations;
- the end-to-end hook protocol via in-process `main()` calls,
  including the deny→allow pair that reads the bytes the hook
  actually emits;
- per work-item livespec-dev-tooling-k169, the COMMAND-TOKEN POSITION
  of the classification: a gate word standing in an argument path or
  inside an `echo` string is not an invocation of that gate, while the
  bare backgrounded gates stay denied wherever the shell would really
  run one (after a wrapper, a control word, or a `bash -c` script);
- per work-item livespec-dev-tooling-h7qp, the VENUE-AWARENESS of the
  deny hint: in a real fresh `git worktree add` of a consumer repo
  that arms the guard, every command the hint names must resolve in
  that worktree and every doc path it cites must exist there. Both
  worktree-pack conditions are exercised (absent → the one-line
  install command is named FIRST; installed → the runner is
  prescribed directly), and a CONTROL asserts the same actionability
  check FAILS against the previously-shipped unconditional hint text;
- per work-item livespec-dev-tooling-5ug6, the ADDRESS of the doc the
  hint cites: proved from a CONSUMER checkout, where the doc's
  repo-relative path resolves to nothing, the citation must name the
  repo that owns it and carry an address reachable from there. A
  second CONTROL asserts the actionability check FAILS on a bare
  relative citation, so the rule cannot pass vacuously.

Private names are imported via from-imports (the package-private
access model, mirroring `tests/livespec_dev_tooling/fleet/`);
monkeypatch seams use the string-target form.

**The guard script runs IN-PROCESS.** `test_script_denies_then_allows_
end_to_end` used to spawn `[sys.executable, pretooluse_background_
guard.py]` twice; both arms now call `main()` through `_run_script`.
The motive is the child, not the call: a `sys.executable` child
inherits `COVERAGE_PROCESS_START`, self-instruments under
`pytest --cov`, and drops a `.coverage.<host>.<pid>` file that races
the parallel dispatcher's combine step — while paying two fresh
interpreter starts for a guard that does no I/O beyond stdin and
stderr. The script reads its payload with one `sys.stdin.read()`, so
`monkeypatch.setattr(sys, "stdin", io.StringIO(payload))` supplies
EXACTLY the bytes the child got on its pipe, and `main()` returns the
int that `raise SystemExit(main())` would have handed the shell — no
`SystemExit` is raised and none is translated. The assertions are
untouched: the same exit codes (2 for the deny, 0 for the allow) and
the same `DENIED` / `gate-start` / `DIED_WITHOUT_VERDICT` substrings,
read off `capsys` stderr instead of `CompletedProcess.stderr`.

The `git` spawns in `_run_git` STAY: the venue-awareness tests below
prove the deny hint against a REAL `git worktree add` of a real
committed repository, which is the whole point of those arms — a
simulated worktree would prove nothing about what resolves inside one.
This slice FIXED their env, which previously passed no `env=` at all
and so leaked `COVERAGE_PROCESS_START` / `COV_CORE_*` into every child:
`_git_child_env` now filters both out of an `os.environ` copy. It is a
filtered copy rather than the hardcoded 3-key replacement used in the
sibling check suites because these fixtures run `git commit` and need
the ambient `PATH` and config. This file KEEPS its
`subprocess_spawn_allowlist` entry for those `git` children.

Branch parity with the retired spawn: the same two payloads drive the
same two arms — the backgrounded `mise exec -- git commit` deny with
its routing hint, and the backgrounded `tail -f` allow. The only lines
the child reached that an in-process call cannot are the module's
`if __name__ == "__main__": raise SystemExit(main())`, already excluded
repo-wide by the pre-existing `exclude_also` patterns in
`[tool.coverage.report]`, so no new exclusion is introduced.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest
from returns.io import IOFailure
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.agent_hooks._deny_hint import (
    _INSTALL_COMMAND,
    _gate_recipes_resolve,
    _imports_pack_fragment,
    _read_text,
    _repo_root,
    deny_hint,
)
from livespec_dev_tooling.agent_hooks.pretooluse_background_guard import (
    _load_hook_input,
    _matched_gate,
    _should_deny,
    main,
)
from livespec_dev_tooling.install_worktree_pack import (
    CANONICAL_GATE_RUN_BODY,
    CANONICAL_WORKTREE_JUST_BODY,
)

__all__: list[str] = []


_MODULE = "livespec_dev_tooling.agent_hooks.pretooluse_background_guard"
_REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# _matched_gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("just check", "just check"),
        ("just check-types", "just check"),
        ('just skip="check-coverage" check', "just check"),
        ("mise exec -- git commit -m 'feat: x'", "git commit"),
        ("git -C /data/projects/x/worktrees/wt push -u origin work", "git push"),
        ("gh pr create --base master --head work", "gh pr"),
        ("gh pr merge 7 --auto --rebase --delete-branch", "gh pr"),
    ],
)
def test_matched_gate_recognizes_gate_commands(command: str, expected: str) -> None:
    assert _matched_gate(command=command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "git log --oneline -5",
        "git status",
        "just --list",
        "gh run list --workflow CI",
        # Separator-bounded filler: `git` in the first segment must not
        # bridge to `push` in a later segment.
        "git log && echo push",
    ],
)
def test_matched_gate_ignores_non_gate_commands(command: str) -> None:
    assert _matched_gate(command=command) is None


def test_matched_gate_matches_gate_segment_inside_compound_command() -> None:
    assert _matched_gate(command="echo start && mise exec -- git push") == "git push"


# ---------------------------------------------------------------------------
# _should_deny (pure decision)
# ---------------------------------------------------------------------------


def test_should_deny_requires_bash_tool() -> None:
    tool_input: dict[str, object] = {"command": "git push", "run_in_background": True}
    assert _should_deny(tool_name="Read", tool_input=tool_input) is None


def test_should_deny_requires_run_in_background_true() -> None:
    assert _should_deny(tool_name="Bash", tool_input={"command": "git push"}) is None
    falsy: dict[str, object] = {"command": "git push", "run_in_background": False}
    assert _should_deny(tool_name="Bash", tool_input=falsy) is None
    truthy_string: dict[str, object] = {"command": "git push", "run_in_background": "yes"}
    assert _should_deny(tool_name="Bash", tool_input=truthy_string) is None


def test_should_deny_requires_string_command() -> None:
    tool_input: dict[str, object] = {"command": 42, "run_in_background": True}
    assert _should_deny(tool_name="Bash", tool_input=tool_input) is None


def test_should_deny_allows_backgrounded_non_gate_command() -> None:
    tool_input: dict[str, object] = {"command": "sleep 600", "run_in_background": True}
    assert _should_deny(tool_name="Bash", tool_input=tool_input) is None


def test_should_deny_denies_backgrounded_gate_command() -> None:
    tool_input: dict[str, object] = {"command": "just check", "run_in_background": True}
    assert _should_deny(tool_name="Bash", tool_input=tool_input) == "just check"


def test_should_deny_allows_the_sanctioned_detached_gate_runner() -> None:
    """Backgrounding `scripts/gate-run.sh` is the SUPPORTED way to run a long gate.

    The commit aggregate can outlast the harness's 20-minute tool-call
    ceiling, and a bare foreground re-issue then dies with no verdict.
    The detached runner keeps the gate in its own session and records a
    durable verdict, so its waiter is safe to background: killing the
    waiter loses nothing and it can simply be re-issued. Denying the
    runner would leave NO way to run a gate that outlasts the ceiling.
    """
    start: dict[str, object] = {
        "command": "scripts/gate-run.sh start -- mise exec -- git commit --amend --no-edit",
        "run_in_background": True,
    }
    assert _should_deny(tool_name="Bash", tool_input=start) is None

    waiter: dict[str, object] = {
        "command": "mise exec -- just gate-wait 20260805T051456Z-4055481",
        "run_in_background": True,
    }
    assert _should_deny(tool_name="Bash", tool_input=waiter) is None


def test_should_deny_does_not_let_naming_the_runner_launder_a_bare_gate() -> None:
    """The command must BE a runner invocation, not merely mention one.

    A bare backgrounded gate keeps its original hazard — the tool output
    is the only record, so a killed task leaves no verdict behind. That
    deny must not be escapable by putting the runner's name in a commit
    message or a comment.
    """
    in_message: dict[str, object] = {
        "command": "mise exec -- git commit -m 'feat(gate): add scripts/gate-run.sh'",
        "run_in_background": True,
    }
    assert _should_deny(tool_name="Bash", tool_input=in_message) == "git commit"

    in_comment: dict[str, object] = {
        "command": "just check  # supersedes gate-run.sh",
        "run_in_background": True,
    }
    assert _should_deny(tool_name="Bash", tool_input=in_comment) == "just check"


# ---------------------------------------------------------------------------
# main() — in-process hook-protocol behavior
# ---------------------------------------------------------------------------


def _run_main(*, monkeypatch: pytest.MonkeyPatch, stdin_text: str) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    return main()


def test_main_fails_open_on_unparseable_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_main(monkeypatch=monkeypatch, stdin_text="{nope") == 0


def test_main_fails_open_on_non_dict_hook_input(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_main(monkeypatch=monkeypatch, stdin_text="[1, 2]") == 0


def test_main_fails_open_on_non_dict_tool_input(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"tool_name": "Bash", "tool_input": "not a dict"})
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 0


def test_main_fails_open_on_missing_tool_name(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {"tool_input": {"command": "git push", "run_in_background": True}},
    )
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 0


def test_main_allows_foreground_gate_command(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "mise exec -- git push"}},
    )
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 0


def test_main_denies_backgrounded_gate_command(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "just check", "run_in_background": True},
        },
    )
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 2


def test_main_fails_open_on_internal_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    def exploding_load(*, raw: str) -> dict[str, object] | None:
        _ = raw
        raise RuntimeError("boom")

    monkeypatch.setattr(f"{_MODULE}._load_hook_input", exploding_load)
    assert _run_main(monkeypatch=monkeypatch, stdin_text="{}") == 0


# ---------------------------------------------------------------------------
# end-to-end — the hook protocol exactly as Claude Code drives it
# ---------------------------------------------------------------------------


class _HookRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


def _run_script(
    *, payload: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _HookRun:
    """Drive the hook end to end: JSON payload on stdin, exit code + streams out.

    The retired spawn handed `payload` to the child on its stdin pipe; the
    script reads it with a single `sys.stdin.read()`, so a monkeypatched
    `io.StringIO` delivers byte-for-byte what the child received. `main()`
    returns the int the `raise SystemExit(main())` line would have carried to
    the shell, so no `SystemExit` translation is involved on either path.
    """
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    returncode = main()
    captured = capsys.readouterr()
    return _HookRun(returncode=returncode, stdout=captured.out, stderr=captured.err)


def test_script_denies_then_allows_end_to_end(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deny_payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "mise exec -- git commit -m 'feat: x'",
                "run_in_background": True,
            },
        },
    )
    denied = _run_script(payload=deny_payload, monkeypatch=monkeypatch, capsys=capsys)
    assert denied.returncode == 2
    assert "DENIED" in denied.stderr
    # The deny must ROUTE the caller, not just refuse. It names the
    # detached runner rather than telling them to re-issue foreground —
    # that advice is what walks into the silent kill under load.
    assert "gate-start" in denied.stderr
    assert "DIED_WITHOUT_VERDICT" in denied.stderr

    allow_payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "tail -f build.log", "run_in_background": True},
        },
    )
    allowed = _run_script(payload=allow_payload, monkeypatch=monkeypatch, capsys=capsys)
    assert allowed.returncode == 0


def test_load_hook_input_rejects_bad_json_and_non_dict() -> None:
    assert _load_hook_input(raw="{nope") is None
    assert _load_hook_input(raw="[1, 2]") is None
    assert _load_hook_input(raw='{"a": 1}') == {"a": 1}


# ---------------------------------------------------------------------------
# Venue-aware deny hint (livespec-dev-tooling-h7qp)
# ---------------------------------------------------------------------------


# The hint text as it shipped BEFORE this work-item: it prescribed the gate
# recipes and cited the rationale doc unconditionally. It is the CONTROL —
# the actionability assertion below must FAIL against it in a fresh worktree,
# which is what proves the assertion has teeth rather than passing vacuously.
_LEGACY_HINT = (
    "Gate commands (just check*, git commit, git push, gh pr ...) must not be "
    "backgrounded BARE: the tool output is then the only record of the verdict, "
    "so a killed task or a turn-end leaves nothing behind. Do NOT answer this by "
    "re-issuing it foreground and waiting — the commit aggregate exceeds "
    "BASH_MAX_TIMEOUT_MS under load, and that kill produces NO verdict at all. "
    "Dispatch through the sanctioned detached runner instead, which IS allowed "
    "here: run_id=$(mise exec -- just gate-start -- <your gate command>) then "
    'background `mise exec -- just gate-wait "$run_id"`. The gate then runs in '
    "its own session that outlives the tool call, killing the waiter loses "
    "nothing, and the verdict is one of PASSED / FAILED / RUNNING / "
    "DIED_WITHOUT_VERDICT — so a gate that did not finish can never read as a "
    "pass. See .ai/gate-runtime-vs-harness-patience.md."
)

# The shape of an arming consumer repo's root justfile: a `check` aggregate
# plus the OPTIONAL pack import (`import?`) that silently no-ops while the
# gitignored-and-installed fragment is absent.
_CONSUMER_JUSTFILE = "import? 'dev-tooling/worktree.just'\n\ncheck:\n    @echo check\n"

_RATIONALE_DOC_RELPATH = ".ai/gate-runtime-vs-harness-patience.md"
# The address the citation must carry, spelled out here rather than imported
# from the module under test: an import would compare the string to itself.
_OWNING_REPO = "livespec-dev-tooling"
_RATIONALE_DOC_URL = (
    "https://github.com/thewoolleyman/livespec-dev-tooling/blob/master/"
    ".ai/gate-runtime-vs-harness-patience.md"
)

# `just` recipe headers (`gate-start *args:`), excluding `:=` assignments and
# indented recipe bodies; and the `import`/`import?` lines a root justfile
# pulls fragments in with.
_RECIPE_HEADER = re.compile(r"(?m)^([a-z][\w-]*)[^\n:]*:(?!=)")
_IMPORT_LINE = re.compile(r"(?m)^import\??\s+'([^']+)'")
# A `just <recipe>` the hint names, and any doc path it cites.
_NAMED_RECIPE = re.compile(r"\bjust\s+([a-z][\w-]*)")
_CITED_DOC = re.compile(r"(?<![\w/])([\w.][\w./-]*\.md)")
# An absolute URL is an ADDRESS rather than a repo-relative path: it denotes
# the same file from every venue, so it is lifted out of the text before the
# relative-path scan and then used to absolve the paths it spells.
_URL = re.compile(r"https?://\S+")


def _git_child_env() -> dict[str, str]:
    """A copy of `os.environ` with the coverage self-instrumentation keys removed.

    A FILTERED copy rather than the hardcoded 3-key env used elsewhere in this
    suite: these fixtures run `git commit`, which needs the real `PATH` and the
    ambient config the `--local` identity is layered onto, so replacing the
    environment wholesale would break the fixture rather than harden it.
    Removing `COVERAGE_PROCESS_START` and every `COV_CORE_*` key is what an
    allowlisted spawn owes — without it the `git` children inherit the parent's
    `pytest --cov` instrumentation and drop `.coverage.<host>.<pid>` files that
    race the parallel dispatcher's combine step. Mirrors `_child_env` in
    `tests/livespec_dev_tooling/worktree_pack/test_gate_run.py`.
    """
    env = dict(os.environ)
    _ = env.pop("COVERAGE_PROCESS_START", None)
    for name in [key for key in env if key.startswith("COV_CORE_")]:
        _ = env.pop(name, None)
    return env


def _run_git(*, args: list[str], cwd: Path) -> None:
    """Run a real `git` subcommand in `cwd` under the scrubbed child env."""
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        env=_git_child_env(),
    )


def _make_consumer_repo(*, repo: Path) -> None:
    """Create a committed one-file repo shaped like an arming consumer."""
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(args=["init", "--quiet"], cwd=repo)
    _run_git(args=["config", "--local", "user.name", "Test User"], cwd=repo)
    _run_git(args=["config", "--local", "user.email", "test@example.com"], cwd=repo)
    _ = (repo / "justfile").write_text(_CONSUMER_JUSTFILE, encoding="utf-8")
    _run_git(args=["add", "-A"], cwd=repo)
    _run_git(args=["commit", "--quiet", "-m", "chore: fixture"], cwd=repo)


def _add_fresh_worktree(*, repo: Path, path: Path) -> Path:
    """`git worktree add` a fresh worktree — no `just bootstrap`, no pack."""
    _run_git(args=["worktree", "add", "--quiet", "-b", "feat/x", str(path)], cwd=repo)
    return path


def _install_pack(*, root: Path) -> None:
    """Materialize the two pack members the gate recipes need."""
    pack_dir = root / "dev-tooling"
    pack_dir.mkdir(parents=True, exist_ok=True)
    _ = (pack_dir / "worktree.just").write_text(CANONICAL_WORKTREE_JUST_BODY, encoding="utf-8")
    _ = (pack_dir / "gate-run.sh").write_text(CANONICAL_GATE_RUN_BODY, encoding="utf-8")


def _body(*, path: Path) -> str:
    """The text of a path the caller has ALREADY confirmed is a readable file.

    `_read_text` answers on the `IOResult` railway
    (livespec-dev-tooling-qndn.10); every call site here has just passed
    `is_file()`, so the success track is the only one reachable and this
    helper keeps the unwrap out of the comprehensions below.
    """
    return unsafe_perform_io(_read_text(path=path).unwrap())


def _resolves(*, root: Path | None) -> bool:
    """`_gate_recipes_resolve`'s answer, asserting it ANSWERED at all."""
    resolved = _gate_recipes_resolve(root=root)
    assert not isinstance(resolved, IOFailure), f"venue probe did not answer: {resolved}"
    return unsafe_perform_io(resolved.unwrap())


def _resolvable_recipes(*, root: Path) -> set[str]:
    """Every recipe name `just` would resolve at `root`, imports followed.

    Mirrors `just`'s own resolution for the shapes in play: the root
    justfile's recipes plus those of each `import`/`import?` target that
    EXISTS on disk — the optional form contributing nothing while absent,
    which is the silent no-op this work-item is about.
    """
    bodies = [
        _body(path=root / name)
        for name in ("justfile", "Justfile", ".justfile")
        if (root / name).is_file()
    ]
    for body in list(bodies):
        bodies.extend(
            _body(path=root / target)
            for target in _IMPORT_LINE.findall(body)
            if (root / target).is_file()
        )
    return {name for body in bodies for name in _RECIPE_HEADER.findall(body)}


def _assert_hint_is_actionable(*, hint: str, root: Path) -> None:
    """Every command the hint names resolves at `root`; every path is reachable.

    A recipe that does NOT resolve is tolerated only when the hint has
    ALREADY named the exact one-line command that installs it — the
    work-item's minimum bar, position included.

    A cited path is reachable when it EXISTS at `root` or when the hint
    also carries the absolute URL that spells it (livespec-dev-tooling
    -5ug6). The second arm is what a CONSUMER venue rests on: a
    producer-relative path resolves nowhere there, so the only honest
    citation is one that names where the file actually lives.
    """
    resolvable = _resolvable_recipes(root=root)
    install_at = hint.find(_INSTALL_COMMAND)
    for match in _NAMED_RECIPE.finditer(hint):
        recipe = match.group(1)
        assert recipe in resolvable or -1 < install_at < match.start(), (
            f"hint names `just {recipe}`, which does not resolve in {root}, "
            "without first naming the command that installs it"
        )
    urls = _URL.findall(hint)
    for cited in _CITED_DOC.findall(_URL.sub(" ", hint)):
        addressed = any(url.rstrip(").").endswith(cited) for url in urls)
        assert (root / cited).is_file() or addressed, (
            f"hint cites {cited}, which does not exist in {root} and which no "
            "URL in the hint addresses"
        )


def _deny_hint(
    *, monkeypatch: pytest.MonkeyPatch, cwd: Path, capsys: pytest.CaptureFixture[str]
) -> str:
    """Trip the guard from `cwd` and return the hint it emitted."""
    monkeypatch.chdir(cwd)
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "mise exec -- just check", "run_in_background": True},
        },
    )
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 2
    event = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    return str(event["hint"])


def test_fresh_worktree_deny_names_only_resolvable_commands_and_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The venue this item was filed from: a fresh worktree, no pack."""
    repo = tmp_path / "consumer"
    _make_consumer_repo(repo=repo)
    worktree = _add_fresh_worktree(repo=repo, path=tmp_path / "wt")

    hint = _deny_hint(monkeypatch=monkeypatch, cwd=worktree, capsys=capsys)

    _assert_hint_is_actionable(hint=hint, root=worktree)
    # The remedy is named, and named as the module invocation that resolves
    # wherever the hook itself does.
    assert _INSTALL_COMMAND in hint
    # And the checkout-local rationale doc, which resolves nowhere here, is
    # addressed rather than left dangling — asserted in full below.
    assert _RATIONALE_DOC_URL in hint


def test_legacy_unconditional_hint_fails_the_actionability_assertion(tmp_path: Path) -> None:
    """Control: the same assertion must FAIL on the as-shipped text.

    Without this, a hint that merely stopped naming anything would pass
    `_assert_hint_is_actionable` vacuously and the regression test would
    prove nothing.
    """
    repo = tmp_path / "consumer"
    _make_consumer_repo(repo=repo)
    worktree = _add_fresh_worktree(repo=repo, path=tmp_path / "wt")

    with pytest.raises(AssertionError, match="does not resolve"):
        _assert_hint_is_actionable(hint=_LEGACY_HINT, root=worktree)


def test_consumer_checkout_deny_cites_the_rationale_by_its_owning_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The venue the defect was measured in: a consumer, not the owning repo.

    Verifying this from livespec-dev-tooling cannot fail — the relative
    path resolves there by construction — so the proof is run where it does
    NOT resolve, which is every repo that CONSUMES this package. The denial
    fires at the moment an agent is blocked and reaching for help; a
    citation that costs a tool call and returns nothing invites the reading
    that the guard is stale, exactly when it is right.
    """
    repo = tmp_path / "consumer"
    _make_consumer_repo(repo=repo)
    worktree = _add_fresh_worktree(repo=repo, path=tmp_path / "wt")
    # The precondition that makes this a consumer venue rather than the
    # producing repo: nothing in this checkout answers the relative path.
    assert not (worktree / _RATIONALE_DOC_RELPATH).exists()

    hint = _deny_hint(monkeypatch=monkeypatch, cwd=worktree, capsys=capsys)

    # The guidance is still cited — the defect is the citation's ADDRESS,
    # not its existence — and cited by an address that works from here.
    _assert_hint_is_actionable(hint=hint, root=worktree)
    assert _OWNING_REPO in hint
    assert _RATIONALE_DOC_URL in hint
    # And the reader is told the remedy stands without following it, so a
    # venue with no network is not a venue with no remedy.
    assert _INSTALL_COMMAND in hint
    assert "complete without it" in hint


def test_a_bare_relative_citation_fails_the_actionability_assertion(tmp_path: Path) -> None:
    """Control: the citation rule must REJECT the shape this item filed.

    Without it, `_assert_hint_is_actionable` could pass the consumer-venue
    test by having stopped checking paths rather than by the hint having
    been fixed.
    """
    repo = tmp_path / "consumer"
    _make_consumer_repo(repo=repo)
    worktree = _add_fresh_worktree(repo=repo, path=tmp_path / "wt")

    with pytest.raises(AssertionError, match="does not exist"):
        _assert_hint_is_actionable(hint=f"See {_RATIONALE_DOC_RELPATH}.", root=worktree)


def test_installed_pack_worktree_prescribes_the_runner_directly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pack installed (and the doc present): prescribe, do not re-install."""
    repo = tmp_path / "consumer"
    _make_consumer_repo(repo=repo)
    worktree = _add_fresh_worktree(repo=repo, path=tmp_path / "wt")
    _install_pack(root=worktree)
    doc = worktree / _RATIONALE_DOC_RELPATH
    doc.parent.mkdir(parents=True, exist_ok=True)
    _ = doc.write_text("# rationale\n", encoding="utf-8")

    hint = _deny_hint(monkeypatch=monkeypatch, cwd=worktree, capsys=capsys)

    _assert_hint_is_actionable(hint=hint, root=worktree)
    assert "just gate-start" in hint
    assert _INSTALL_COMMAND not in hint
    assert _RATIONALE_DOC_RELPATH in hint


def test_gate_recipes_resolve_needs_fragment_import_and_runner(tmp_path: Path) -> None:
    """Each of the three conditions is load-bearing, and rootless is False."""
    assert _resolves(root=None) is False

    root = tmp_path / "repo"
    root.mkdir()
    _ = (root / "justfile").write_text(_CONSUMER_JUSTFILE, encoding="utf-8")
    # Fragment absent: the `import?` no-ops and nothing declares the recipes.
    # ABSENCE is an ANSWER — it rides the success track, not the failure one.
    assert _resolves(root=root) is False

    _install_pack(root=root)
    assert _resolves(root=root) is True

    # Runner body missing: `just gate-start` resolves but cannot run.
    (root / "dev-tooling" / "gate-run.sh").unlink()
    assert _resolves(root=root) is False

    # Fragment installed but never imported by the root justfile — the
    # 6-of-7-repos presentation this item absorbed.
    _install_pack(root=root)
    _ = (root / "justfile").write_text("check:\n    @echo check\n", encoding="utf-8")
    assert unsafe_perform_io(_imports_pack_fragment(root=root).unwrap()) is False
    assert _resolves(root=root) is False


def test_repo_root_finds_worktree_git_file_and_gives_up_outside_a_repo(tmp_path: Path) -> None:
    repo = tmp_path / "consumer"
    _make_consumer_repo(repo=repo)
    worktree = _add_fresh_worktree(repo=repo, path=tmp_path / "wt")
    # A linked worktree's `.git` is a FILE, not a directory.
    assert (worktree / ".git").is_file()
    assert _repo_root(start=worktree) == worktree

    outside = tmp_path / "outside"
    outside.mkdir()
    assert _repo_root(start=outside) is None
    assert unsafe_perform_io(deny_hint(cwd=outside).unwrap()).find(_INSTALL_COMMAND) > 0


def test_read_text_tells_an_absent_path_from_an_unreadable_one(tmp_path: Path) -> None:
    """A probe must never raise into the hook's fail-open boundary — and must not lie.

    Both non-answers are VALUES, because raising would reach `main`'s
    fail-open catch and ALLOW the bare backgrounded gate. They are no
    longer the same value: an absent path is the answer the probe is
    looking for and reads as the empty body, while a path that is there
    and unreadable establishes nothing and takes the failure track
    (livespec-dev-tooling-qndn.10).
    """
    assert unsafe_perform_io(_read_text(path=tmp_path / "absent").unwrap()) == ""

    unreadable = _read_text(path=tmp_path)
    assert isinstance(unreadable, IOFailure)
    assert unsafe_perform_io(unreadable.failure()).path == str(tmp_path)


def test_an_unreadable_venue_still_denies_and_names_the_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The hook's OTHER verdict is fail-open ALLOW, so the failure track stops here.

    A venue probe that cannot answer must not become an allow: the gate
    is still being bare-backgrounded, and this hook exists to deny that.
    The deny therefore stands, and the hint says what it could not read
    instead of asserting a prescription arm nothing established.
    """
    repo = tmp_path / "consumer"
    _make_consumer_repo(repo=repo)
    worktree = _add_fresh_worktree(repo=repo, path=tmp_path / "wt")
    _install_pack(root=worktree)
    # A pack fragment that is a DIRECTORY: present, and refusing to yield
    # text. The root justfile stays readable, so the recipes it really does
    # declare are still resolvable and the actionability assertion below is
    # judging the hint rather than an unreadable venue.
    fragment = worktree / "dev-tooling" / "worktree.just"
    fragment.unlink()
    fragment.mkdir()

    hint = _deny_hint(monkeypatch=monkeypatch, cwd=worktree, capsys=capsys)

    assert str(fragment) in hint
    assert "could NOT be established" in hint
    _assert_hint_is_actionable(hint=hint, root=worktree)
    assert _INSTALL_COMMAND in hint


# ---------------------------------------------------------------------------
# Command-token position, not substring (livespec-dev-tooling-k169)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        # The filed occurrence: a sanctioned detached-gate WAITER whose run-id
        # scratch path carries the word `checks`. The recipe it names is
        # `gate-wait`; `checks` sits in an ARGUMENT. Both spellings are here
        # because the shape that actually tripped is the one the
        # start-anchored runner allowance does NOT reach (a `cd` ahead of it).
        'cd /repo && mise exec -- just gate-wait "$(cat tmp/scratchpad/run-checks.id)"',
        "cd /repo && mise exec -- just gate-status tmp/scratchpad/run-checks.id",
        # Ledger comment [1]: a poll loop whose only gate-shaped content is the
        # words `just check` inside an echo STRING. It runs no gate at all.
        "gh api repos/o/r/commits --jq . && echo 'waiting on just check'",
        'echo "next up: just check" && sleep 60',
        # The same words in a `git`/`gh` ARGUMENT rather than the subcommand.
        "git log --oneline --grep commit",
        "gh run list --workflow pr",
        # A leading separator yields an empty first segment, which has no
        # command word at all.
        "; sleep 60",
        # Text `shlex` cannot lex (an apostrophe in an unquoted word) falls
        # back to the coarse tokenizer, which still reads `echo` as the
        # command word rather than finding a gate inside its arguments.
        "echo don't wait for just check && sleep 60",
    ],
)
def test_matched_gate_ignores_gate_words_outside_command_position(command: str) -> None:
    """A gate word in an argument is not an invocation of that gate.

    The guard used to match `just check` as "the word `check` anywhere
    after the word `just`", so a scratch-file path carrying `checks` and
    an `echo` string quoting the recipe both read as bare backgrounded
    gates. The deny then prescribed the detached runner to a caller who
    was already using it — advice with no move left in it, which is what
    pushes an agent to engineer AROUND the guard.
    """
    assert _matched_gate(command=command) is None


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("mise exec -- just check", "just check"),
        ("nohup git commit --amend --no-edit", "git commit"),
        ("git push -u origin feat/x", "git push"),
        ("gh pr merge 7 --auto --rebase", "gh pr"),
        # Control words stand between the segment boundary and the command.
        ("until gh pr checks; do sleep 30; done", "gh pr"),
        # A shell runner's script argument IS command text, so it is
        # classified as such rather than treated as an opaque argument.
        ("bash -c 'mise exec -- just check'", "just check"),
    ],
)
def test_matched_gate_still_finds_gates_in_command_position(command: str, expected: str) -> None:
    """Positional matching must not cost the guard its teeth."""
    assert _matched_gate(command=command) == expected


def test_should_deny_allows_a_backgrounded_waiter_whose_path_carries_checks() -> None:
    """The acceptance case: the waiter is allowed, the bare gates are not."""
    waiter: dict[str, object] = {
        "command": 'cd /repo && mise exec -- just gate-wait "$(cat tmp/run-checks.id)"',
        "run_in_background": True,
    }
    assert _should_deny(tool_name="Bash", tool_input=waiter) is None

    echoed: dict[str, object] = {
        "command": "gh api repos/o/r/commits --jq . && echo 'waiting on just check'",
        "run_in_background": True,
    }
    assert _should_deny(tool_name="Bash", tool_input=echoed) is None


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("just check", "just check"),
        ("mise exec -- git commit -m 'fix: x'", "git commit"),
        ("git push", "git push"),
        ("gh pr create --fill", "gh pr"),
    ],
)
def test_should_deny_still_denies_every_bare_backgrounded_gate(command: str, expected: str) -> None:
    """A bare backgrounded gate keeps its original hazard, so it stays denied."""
    tool_input: dict[str, object] = {"command": command, "run_in_background": True}
    assert _should_deny(tool_name="Bash", tool_input=tool_input) == expected
