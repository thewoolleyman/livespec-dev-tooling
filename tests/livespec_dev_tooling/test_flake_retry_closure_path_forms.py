"""Closure path forms that must withhold a failing test's flake retry.

SPECIFICATION non-functional-requirements.md "Untouched-test retry" requires
the conservative result whenever a changed repository path is reachable from a
failing test's static closure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.flake_retry_decisions import retry_marker_for

_MARKER = {"reruns": 3, "reruns_delay": 60}
_TEST = "tests/test_target.py"
_HEADER = "from pathlib import Path\nimport os\nimport pytest\n\n"


def _marker(*, tmp_path: Path, files: dict[str, str], change: str) -> dict[str, int] | None:
    """Write a minimal repository and ask the retry policy about its test."""
    for relative, source in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(_HEADER + source, encoding="utf-8")
    return retry_marker_for(
        repo_root=tmp_path,
        test_path=tmp_path / _TEST,
        change_paths={Path(change)},
    )


_TOUCHED: dict[str, tuple[dict[str, str], str]] = {
    "getattr-request-path": (
        {_TEST: "def test_target(request):\n    return getattr(request, 'path').parent / 'data'\n"},
        "tests/data/value.json",
    ),
    "request-alias": (
        {
            _TEST: "def test_target(request):\n    req = request\n    return req.path.parent / 'data'\n"
        },
        "tests/data/value.json",
    ),
    "fixture-imported-from-another-test-module": (
        {
            "tests/support.py": (
                "@pytest.fixture\ndef data(request):\n" "    return request.path.parent / 'data'\n"
            ),
            _TEST: "from tests.support import data\n\ndef test_target(data):\n    return data\n",
        },
        "tests/data/value.json",
    ),
    "non-slash-path-forms": (
        {
            _TEST: (
                "def test_target(request):\n"
                "    one = os.path.join(os.path.dirname(__file__), 'data')\n"
                "    two = Path(f'{Path(__file__).parent}/data')\n"
                "    three = Path(__file__).with_name('data')\n"
                "    four = Path(request.module.__file__).parent / 'data'\n"
                "    return one, two, three, four\n"
            )
        },
        "tests/data/value.json",
    ),
    "helper-parameter-called-with-request": (
        {
            _TEST: (
                "def data_dir(req):\n    return req.path.parent / 'data'\n\n"
                "def test_target(request):\n    return data_dir(request)\n"
            )
        },
        "tests/data/value.json",
    ),
    "request-node-parent-path": (
        {_TEST: ("def test_target(request):\n" "    return request.node.parent.path / 'data'\n")},
        "tests/data/value.json",
    ),
    "undeterminable-non-slash-path": (
        {_TEST: ("def test_target():\n" "    return os.path.join(Path(__file__).parent, name)\n")},
        "docs/unrelated.md",
    ),
}


@pytest.mark.parametrize(("files", "change"), _TOUCHED.values(), ids=_TOUCHED.keys())
def test_closure_path_forms_withhold_the_retry_when_their_location_changes(
    *, tmp_path: Path, files: dict[str, str], change: str
) -> None:
    """Each supported or unknown repository-path form fails the test at once."""
    assert _marker(tmp_path=tmp_path, files=files, change=change) is None


def test_a_literal_only_module_name_keeps_a_joined_path_determinate(*, tmp_path: Path) -> None:
    """A literal-only path binding still permits a retry for an unrelated change."""
    marker = _marker(
        tmp_path=tmp_path,
        files={
            _TEST: (
                "CLAIMS_RELATIVE_PATH = Path('config') / 'incident-fleet-evidence.json'\n"
                "ROOT = Path(__file__).resolve().parents[1]\n"
                "def test_target():\n    return ROOT / CLAIMS_RELATIVE_PATH\n"
            )
        },
        change="docs/unrelated.md",
    )

    assert marker == _MARKER
