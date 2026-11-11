"""Unit coverage for the flake-retry closure decision module."""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling import flake_retry_decisions as decisions
from livespec_dev_tooling.flake_retry_decisions import retry_marker_for

_UNDETERMINABLE_CLOSURE: tuple[set[Path], set[str], bool] = (set(), set(), True)


def test_an_unrelated_change_keeps_the_bounded_retry_marker(*, tmp_path: Path) -> None:
    """The extracted decision preserves the untouched-test retry policy."""
    test_path = tmp_path / "test_example.py"
    _ = test_path.write_text("VALUE = 1\n", encoding="utf-8")

    marker = retry_marker_for(
        repo_root=tmp_path,
        test_path=test_path,
        change_paths={Path("README.md")},
    )

    assert marker == {"reruns": 3, "reruns_delay": 60}


def test_an_unsafe_change_withholds_the_retry_marker(*, tmp_path: Path) -> None:
    """Build configuration changes still disable every retry."""
    test_path = tmp_path / "test_example.py"
    _ = test_path.write_text("VALUE = 1\n", encoding="utf-8")

    marker = retry_marker_for(
        repo_root=tmp_path,
        test_path=test_path,
        change_paths={Path("pyproject.toml")},
    )

    assert marker is None


def test_a_change_to_the_decision_module_withholds_the_retry_marker(*, tmp_path: Path) -> None:
    """The plugin self-guard covers the module that now holds the retry decision."""
    test_path = tmp_path / "test_example.py"
    _ = test_path.write_text("VALUE = 1\n", encoding="utf-8")

    marker = retry_marker_for(
        repo_root=tmp_path,
        test_path=test_path,
        change_paths={Path("livespec_dev_tooling/flake_retry_decisions.py")},
    )

    assert marker is None


def test_a_version_only_release_change_does_not_withhold_the_session(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The release exception is evaluated before the unsafe-name session guard."""
    test_path = tmp_path / "test_example.py"
    _ = test_path.write_text("VALUE = 1\n", encoding="utf-8")

    def version_only(**_: object) -> bool:
        return True

    monkeypatch.setattr(decisions, "version_only_release_change", version_only)

    assert (
        decisions.session_withheld_reason(
            repo_root=tmp_path,
            test_paths=(test_path,),
            change_paths={Path("pyproject.toml"), Path("uv.lock")},
            memo={},
        )
        is None
    )


def test_a_justfile_change_withholds_the_whole_session(*, tmp_path: Path) -> None:
    """Build recipe changes are announced as a session-wide retry hold."""
    assert (
        decisions.session_withheld_reason(
            repo_root=tmp_path,
            test_paths=(),
            change_paths={Path("justfile")},
            memo={},
        )
        == "a justfile change"
    )


@pytest.mark.parametrize(
    ("closure", "reason"),
    [
        (None, "an unparseable closure module"),
        (_UNDETERMINABLE_CLOSURE, "an indeterminable path in a closure module"),
    ],
)
def test_an_unreadable_or_indeterminable_closure_withholds_every_retry(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    closure: tuple[set[Path], set[str], bool] | None,
    reason: str,
) -> None:
    """Closure uncertainty moves from one test marker to the whole session."""
    test_path = tmp_path / "test_example.py"
    _ = test_path.write_text("VALUE = 1\n", encoding="utf-8")

    def closure_result(**_: object) -> tuple[set[Path], set[str], bool] | None:
        return closure

    monkeypatch.setattr(decisions, "_closure", closure_result)

    assert (
        decisions.session_withheld_reason(
            repo_root=tmp_path,
            test_paths=(test_path,),
            change_paths={Path("README.md")},
            memo={},
        )
        == reason
    )


def test_the_closure_loop_returns_the_first_session_withholding_reason(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Collection stops when the first test proves the session is unsafe."""
    first = tmp_path / "test_first.py"
    second = tmp_path / "test_second.py"
    _ = first.write_text("VALUE = 1\n", encoding="utf-8")
    _ = second.write_text("VALUE = 2\n", encoding="utf-8")
    calls: list[Path] = []

    def withheld(*, test_path: Path, **_: object) -> str | None:
        calls.append(test_path)
        return "an unparseable closure module" if test_path == first else None

    monkeypatch.setattr(decisions, "_closure_withheld_reason", withheld)

    assert (
        decisions.session_withheld_reason(
            repo_root=tmp_path,
            test_paths=(first, second),
            change_paths={Path("README.md")},
            memo={},
        )
        == "an unparseable closure module"
    )
    assert calls == [first]
