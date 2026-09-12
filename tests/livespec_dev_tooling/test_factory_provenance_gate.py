"""Outside-in test for `livespec_dev_tooling/factory_provenance_gate.py`.

The decision half of the hermetic factory-provenance commit gate: the
canonical commit-refuse hook body reads the `livespec.factoryRunId` git
config marker and hands this module the commit-message file plus what it
read; the module classifies the staged tree against the SAME
`config.derive_source_prefixes` universe Red-Green-Replay uses, resolves
the HOST-WIDE mode file, writes the `Factory-Run-Id` provenance trailer,
and returns the verdict.

Four properties, each failing independently:

- **The marker writes the trailer and short-circuits.** A commit made
  under a factory run is in provenance by construction, so it neither
  needs the staged-tree classification nor an exception; the run id lands
  in the message as a `Factory-Run-Id:` trailer, replaced rather than
  accumulated across a Red→Green amend.
- **Warn is the default, and the mode file is host-wide.** Staged product
  `.py` with no marker emits the record and exits `0` unless the file at
  `${XDG_CONFIG_HOME:-$HOME/.config}/livespec/factory-provenance-mode`
  carries the exact token `fail`. Absent, unreadable, and unrecognized
  all resolve to warn — the direction that lets commits through.
- **A non-empty `Factory-Override:` is an AUDITED exception.** It is
  recorded at warning level with its reason; an empty one, and one
  commented out in the message template, are not exceptions at all.
- **Scope is product implementation `.py` only.** A docs-only staging, a
  vendored `.py`, and a path outside the declared prefixes each leave the
  gate silent.

Git and the fixture repositories are real (the module shells out to
`git diff --cached` and `git interpret-trailers`); the module itself is
exercised IN-PROCESS, per the `tests_no_subprocess_spawn` discipline —
no Python child is spawned.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_VENDOR_DIR = Path(__file__).resolve().parents[2] / "livespec_dev_tooling" / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from structlog.testing import capture_logs  # noqa: E402  — vendored structlog.

from livespec_dev_tooling.factory_provenance_gate import (  # noqa: E402
    REFUSE_EXIT_CODE,
    gate,
    main,
)

__all__: list[str] = []


_PYPROJECT = """\
[project]
name = "gate-fixture"
version = "0.0.0"

[tool.livespec_dev_tooling]
source_trees = ["pkg"]
"""

# git injects these into a hook's environment; when this suite runs under a
# lefthook pre-commit they leak in from the surrounding repo and would point
# every git invocation below at it instead of the fixture.
_GIT_ENV_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
)


def _run_git(*, args: list[str], cwd: Path) -> None:
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _fixture_repo(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Init a git repo carrying the `pkg/` source-prefix declaration; chdir into it."""
    for var in _GIT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(args=["init", "--quiet"], cwd=repo)
    _run_git(args=["config", "--local", "user.name", "Test User"], cwd=repo)
    _run_git(args=["config", "--local", "user.email", "test@example.com"], cwd=repo)
    _ = (repo / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    monkeypatch.chdir(repo)
    return repo


def _stage(*, repo: Path, rel: str, body: str = "x = 1\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")
    _run_git(args=["add", rel], cwd=repo)


def _message(*, repo: Path, text: str = "feat: subject line\n") -> Path:
    path = repo / "COMMIT_EDITMSG_fixture"
    _ = path.write_text(text, encoding="utf-8")
    return path


def _home_env(*, home: Path) -> dict[str, str]:
    return {"HOME": str(home)}


def _arm_fail_mode(*, home: Path) -> None:
    mode_file = home / ".config" / "livespec" / "factory-provenance-mode"
    mode_file.parent.mkdir(parents=True, exist_ok=True)
    _ = mode_file.write_text("fail\n", encoding="utf-8")


def _log() -> structlog.stdlib.BoundLogger:
    return structlog.get_logger("test_factory_provenance_gate")


def test_marker_present_writes_the_run_id_trailer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A commit made with the marker set carries a `Factory-Run-Id` trailer."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    msg = _message(repo=repo)

    with capture_logs() as records:
        rc = gate(
            cwd=repo,
            message_path=msg,
            factory_run_id="01M26981AYQW0HAVH8D5JS6G1H",
            env=_home_env(home=tmp_path / "home"),
            log=_log(),
        )

    assert rc == 0
    assert "Factory-Run-Id: 01M26981AYQW0HAVH8D5JS6G1H" in msg.read_text(encoding="utf-8")
    assert [r["event"] for r in records] == ["factory provenance recorded"]


def test_marker_replaces_an_earlier_run_id_trailer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Red→Green amend REPLACES the trailer rather than accumulating one per attempt."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    msg = _message(repo=repo, text="feat: subject\n\nFactory-Run-Id: OLDRUN\n")

    rc = gate(
        cwd=repo,
        message_path=msg,
        factory_run_id="NEWRUN",
        env=_home_env(home=tmp_path / "home"),
        log=_log(),
    )

    body = msg.read_text(encoding="utf-8")
    assert rc == 0
    assert body.count("Factory-Run-Id:") == 1
    assert "Factory-Run-Id: NEWRUN" in body


def test_marker_short_circuits_a_repo_with_nothing_staged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The marker is read FIRST: a factory commit staging no product `.py` still gets the trailer."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="docs/note.md", body="# note\n")
    msg = _message(repo=repo)

    rc = gate(
        cwd=repo,
        message_path=msg,
        factory_run_id="RUNID",
        env=_home_env(home=tmp_path / "home"),
        log=_log(),
    )

    assert rc == 0
    assert "Factory-Run-Id: RUNID" in msg.read_text(encoding="utf-8")


def test_missing_marker_warns_without_refusing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Warn is the DEFAULT: the record is emitted and the commit proceeds."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")

    with capture_logs() as records:
        rc = gate(
            cwd=repo,
            message_path=_message(repo=repo),
            factory_run_id="",
            env=_home_env(home=tmp_path / "home"),
            log=_log(),
        )

    assert rc == 0
    assert records[0]["event"] == "product .py committed without factory provenance"
    assert records[0]["mode"] == "warn"
    assert records[0]["staged_product_paths"] == ["pkg/impl.py"]


def test_fail_mode_file_refuses(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The host-wide mode file carrying `fail` arms the refusal."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    home = tmp_path / "home"
    _arm_fail_mode(home=home)

    with capture_logs() as records:
        rc = gate(
            cwd=repo,
            message_path=_message(repo=repo),
            factory_run_id="",
            env=_home_env(home=home),
            log=_log(),
        )

    assert rc == REFUSE_EXIT_CODE
    assert records[0]["mode"] == "fail"


def test_mode_file_resolves_under_xdg_config_home(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`XDG_CONFIG_HOME` wins over `$HOME/.config` when set."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    xdg = tmp_path / "xdg"
    mode_file = xdg / "livespec" / "factory-provenance-mode"
    mode_file.parent.mkdir(parents=True, exist_ok=True)
    _ = mode_file.write_text("FAIL\n", encoding="utf-8")

    rc = gate(
        cwd=repo,
        message_path=_message(repo=repo),
        factory_run_id="",
        env={"HOME": str(tmp_path / "home"), "XDG_CONFIG_HOME": str(xdg)},
        log=_log(),
    )

    assert rc == REFUSE_EXIT_CODE


def test_unreadable_mode_file_resolves_to_warn(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mode file that cannot be read lets the commit through, never blocks it."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    home = tmp_path / "home"
    # A DIRECTORY where the file belongs: readable path, unreadable content.
    (home / ".config" / "livespec" / "factory-provenance-mode").mkdir(parents=True)

    rc = gate(
        cwd=repo,
        message_path=_message(repo=repo),
        factory_run_id="",
        env=_home_env(home=home),
        log=_log(),
    )

    assert rc == 0


def test_unrecognized_mode_token_resolves_to_warn(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the exact token `fail` arms the gate; a typo must not."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    home = tmp_path / "home"
    mode_file = home / ".config" / "livespec" / "factory-provenance-mode"
    mode_file.parent.mkdir(parents=True, exist_ok=True)
    _ = mode_file.write_text("failing\n", encoding="utf-8")

    rc = gate(
        cwd=repo,
        message_path=_message(repo=repo),
        factory_run_id="",
        env=_home_env(home=home),
        log=_log(),
    )

    assert rc == 0


def test_override_trailer_is_an_audited_exception(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-empty `Factory-Override:` exempts the commit and is RECORDED with its reason."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    home = tmp_path / "home"
    _arm_fail_mode(home=home)
    msg = _message(repo=repo, text="fix: subject\n\nFactory-Override: factory down, hand-fix\n")

    with capture_logs() as records:
        rc = gate(
            cwd=repo,
            message_path=msg,
            factory_run_id="",
            env=_home_env(home=home),
            log=_log(),
        )

    assert rc == 0
    assert records[0]["event"] == (
        "factory provenance AUDITED EXCEPTION: Factory-Override declared"
    )
    assert records[0]["reason"] == "factory down, hand-fix"


def test_last_override_reason_wins(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An amended message carrying two reasons is claimed under the LAST one."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    msg = _message(
        repo=repo,
        text="fix: subject\n\nFactory-Override: first reason\nFactory-Override: second reason\n",
    )

    with capture_logs() as records:
        rc = gate(
            cwd=repo,
            message_path=msg,
            factory_run_id="",
            env=_home_env(home=tmp_path / "home"),
            log=_log(),
        )

    assert rc == 0
    assert records[0]["reason"] == "second reason"


@pytest.mark.parametrize(
    "message",
    [
        pytest.param("fix: subject\n\nFactory-Override:\n", id="empty-reason"),
        pytest.param("fix: subject\n\nFactory-Override:   \n", id="whitespace-reason"),
        pytest.param("fix: subject\n\n# Factory-Override: template\n", id="commented-out"),
    ],
)
def test_non_declaring_override_is_not_an_exception(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    """An empty or commented-out override declares nothing, so it exempts nothing."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    home = tmp_path / "home"
    _arm_fail_mode(home=home)

    rc = gate(
        cwd=repo,
        message_path=_message(repo=repo, text=message),
        factory_run_id="",
        env=_home_env(home=home),
        log=_log(),
    )

    assert rc == REFUSE_EXIT_CODE


def test_unreadable_message_is_not_an_exception(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A message file that cannot be decoded declares no exception (it convicts, not exempts)."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    home = tmp_path / "home"
    _arm_fail_mode(home=home)
    msg = repo / "COMMIT_EDITMSG_fixture"
    _ = msg.write_bytes(b"fix: subject\n\nFactory-Override: \xff\xfe reason\n")

    rc = gate(
        cwd=repo,
        message_path=msg,
        factory_run_id="",
        env=_home_env(home=home),
        log=_log(),
    )

    assert rc == REFUSE_EXIT_CODE


@pytest.mark.parametrize(
    "staged",
    [
        pytest.param("docs/note.md", id="not-python"),
        pytest.param("outside/impl.py", id="outside-the-declared-prefixes"),
        pytest.param("pkg/_vendor/upstream.py", id="vendored"),
    ],
)
def test_out_of_scope_staging_is_silent(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, staged: str
) -> None:
    """Only PRODUCT implementation `.py` is in scope — the same universe RGR classifies."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel=staged)
    home = tmp_path / "home"
    _arm_fail_mode(home=home)

    with capture_logs() as records:
        rc = gate(
            cwd=repo,
            message_path=_message(repo=repo),
            factory_run_id="",
            env=_home_env(home=home),
            log=_log(),
        )

    assert rc == 0
    assert records == []


def test_malformed_consumer_config_leaves_nothing_in_scope(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A config defect is the repo's own gate's problem, not an unexplained commit failure."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    _ = (repo / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = "not-a-list"\n', encoding="utf-8"
    )
    home = tmp_path / "home"
    _arm_fail_mode(home=home)

    rc = gate(
        cwd=repo,
        message_path=_message(repo=repo),
        factory_run_id="",
        env=_home_env(home=home),
        log=_log(),
    )

    assert rc == 0


def test_main_passes_argv_through_to_the_verdict(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()` reads the message file and the run id from argv and returns the verdict."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    msg = _message(repo=repo)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["factory_provenance_gate", str(msg), "01M29GFWMRMEB3PYZVYKEG7EE6"]
    )

    rc = main()

    assert rc == 0
    assert "Factory-Run-Id: 01M29GFWMRMEB3PYZVYKEG7EE6" in msg.read_text(encoding="utf-8")
    assert "factory provenance recorded" in capsys.readouterr().err


def test_main_defaults_the_run_id_to_empty(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The run-id argv slot is optional: absent means "no marker", which is the gated case."""
    repo = _fixture_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(repo=repo, rel="pkg/impl.py")
    home = tmp_path / "home"
    _arm_fail_mode(home=home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(sys, "argv", ["factory_provenance_gate", str(_message(repo=repo))])

    rc = main()

    assert rc == REFUSE_EXIT_CODE
    assert "without factory provenance" in capsys.readouterr().err
