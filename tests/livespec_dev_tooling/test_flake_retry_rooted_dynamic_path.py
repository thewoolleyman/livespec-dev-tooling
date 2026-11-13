"""A repository-rooted path with only computed segments is undeterminable.

livespec-dev-tooling-4ai5ao: `ROOT / name`, with `ROOT` the repository root and
`name` computed, names a repository path the plugin cannot read, and no literal
of the closure names it. SPECIFICATION non-functional-requirements.md
"Untouched-test retry": when the plugin cannot determine which paths a closure
names, the test MUST be treated as touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.flake_retry_decisions import retry_marker_for

_MARKER = {"reruns": 3, "reruns_delay": 60}
_UNRELATED_CHANGE = {Path("docs/x.md")}


def _marker(*, tmp_path: Path, conftest: str) -> dict[str, int] | None:
    tests = tmp_path / "tests"
    tests.mkdir()
    _ = (tests / "conftest.py").write_text(
        "from pathlib import Path\n\n" + conftest, encoding="utf-8"
    )
    test_path = tests / "test_x.py"
    _ = test_path.write_text("def test_plain():\n    assert True\n", encoding="utf-8")
    return retry_marker_for(repo_root=tmp_path, test_path=test_path, change_paths=_UNRELATED_CHANGE)


_ROOTED_COMPUTED = {
    "root-expression": "def spec(name):\n    return Path(__file__).parents[1] / name\n",
    "bound-root": (
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "def spec(name, leaf):\n    return ROOT / name / leaf\n"
    ),
}

_NOT_ROOTED_COMPUTED = {
    "parameter-base": "def spec(base, name):\n    return base / name\n",
    "arithmetic": "def half(total):\n    return total / 2\n",
}


@pytest.mark.parametrize("conftest", _ROOTED_COMPUTED.values(), ids=_ROOTED_COMPUTED.keys())
def test_a_rooted_path_with_only_computed_segments_touches_the_test(
    *, tmp_path: Path, conftest: str
) -> None:
    """Whatever the change set, a test whose closure computes a repository path fails at once."""
    assert _marker(tmp_path=tmp_path, conftest=conftest) is None


@pytest.mark.parametrize("conftest", _NOT_ROOTED_COMPUTED.values(), ids=_NOT_ROOTED_COMPUTED.keys())
def test_a_computed_path_off_the_repository_root_leaves_the_retry(
    *, tmp_path: Path, conftest: str
) -> None:
    """A computed path on a parameter, or plain arithmetic, names no repository path."""
    assert _marker(tmp_path=tmp_path, conftest=conftest) == _MARKER
