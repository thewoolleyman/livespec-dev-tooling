"""A `__file__`-relative directory is a named repository path.

livespec-dev-tooling-4ai5ao: SPECIFICATION non-functional-requirements.md
"Untouched-test retry" counts a `__file__`-derived base as repository-rooted.
When it resolves to a directory inside the repository, that directory is a
repository path the closure names: followed only by computed segments, it names
the directory itself, and followed by literal segments, it names them under
the directory as well as bare. A change inside the directory touches the test;
a change outside it does not. In a test module, `request.path`,
`request.fspath` and `request.node.path` are that module's own path; in a
`conftest.py` they are some test path under the conftest's own directory, so a
change anywhere under that directory touches the test; anywhere else they are
undeterminable. An upward step -- `.parent`, `dirname`, a `..` segment or
`parents[n]` -- widens such a span, and turns a directory reached through a
fixture into a span, so a change above the conftest's directory still touches
the test. `request.config.invocation_params.dir` is the repository root.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.flake_retry_decisions import retry_marker_for

_MARKER = {"reruns": 3, "reruns_delay": 60}
_TEST_FILE = "tests/test_x.py"
_HEADER = "import os\nfrom pathlib import Path\n\nimport pytest\n\n"
_COMPUTED = "    name = str(len(__name__))\n"
_FILE_RELATIVE = (
    "def test_read():\n"
    + _COMPUTED
    + "    assert (Path(__file__).resolve().parent / f'{name}.json')\n"
)
_REQUESTED_DATA = "@pytest.fixture\ndef data(request):\n    return request.path.parent / 'data'\n"
_SUB_TEST = "tests/sub/test_x.py"
_USE = "def test_read(data):\n    assert data\n"
_HERE = "@pytest.fixture\ndef here(request):\n    return request.path.parent\n"
_HERE_PARENT_DATA = "def test_read(here):\n    assert (here.parent / 'data')\n"


def _sub_data(*, base: str) -> str:
    return f"@pytest.fixture\ndef data(request):\n    return {base} / 'data'\n"


_DELEGATED_GATE_SHAPE = {
    "pkg/__init__.py": "",
    "pkg/authority.py": (
        "_CHECKS = Path(__file__).resolve().parent / 'checks'\n\n"
        "def check_path(module):\n    return _CHECKS / f'{module}.py'\n"
    ),
    _TEST_FILE: "from pkg.authority import check_path\n\ndef test_read():\n    assert check_path\n",
}


def _marker(*, tmp_path: Path, files: dict[str, str], change: str) -> dict[str, int] | None:
    for relative, source in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(_HEADER + source, encoding="utf-8")
    test_file = next(relative for relative in files if Path(relative).name.startswith("test_"))
    return retry_marker_for(
        repo_root=tmp_path, test_path=tmp_path / test_file, change_paths={Path(change)}
    )


_TOUCHED: dict[str, tuple[dict[str, str], str]] = {
    "file-relative-directory-with-computed-segments": (
        {_TEST_FILE: _FILE_RELATIVE},
        "tests/x.json",
    ),
    "fixture-returning-a-file-relative-directory": (
        {
            "tests/conftest.py": (
                "@pytest.fixture\ndef here():\n    return Path(__file__).resolve().parent\n"
            ),
            _TEST_FILE: "def test_read(here):\n" + _COMPUTED + "    assert (here / name)\n",
        },
        "tests/x.json",
    ),
    "dirname-of-file-with-computed-segments": (
        {
            _TEST_FILE: (
                "def test_read():\n"
                + _COMPUTED
                + "    assert (Path(os.path.dirname(__file__)) / name)\n"
            ),
        },
        "tests/x.json",
    ),
    "literal-under-a-file-relative-directory": (
        {
            _TEST_FILE: (
                "FIXTURES = Path(__file__).resolve().parent / 'fx'\n\n"
                "def test_read():\n    assert list(FIXTURES.glob('*.json'))\n"
            ),
        },
        "tests/fx/x.json",
    ),
    "request-path-parent": (
        {_TEST_FILE: "def test_read(request):\n    assert (request.path.parent / 'data')\n"},
        "tests/data/x.json",
    ),
    "request-node-path-parent": (
        {_TEST_FILE: "def test_read(request):\n    assert (request.node.path.parent / 'data')\n"},
        "tests/data/x.json",
    ),
    "request-fspath-dirname": (
        {
            _TEST_FILE: (
                "def test_read(request):\n"
                "    assert (Path(os.path.dirname(request.fspath)) / 'data')\n"
            ),
        },
        "tests/data/x.json",
    ),
    "invocation-directory": (
        {
            _TEST_FILE: (
                "def test_read(request):\n"
                "    assert (request.config.invocation_params.dir / 'data')\n"
            ),
        },
        "data/x.json",
    ),
    "invocation-directory-with-computed-segments": (
        {
            _TEST_FILE: (
                "def test_read(request):\n"
                + _COMPUTED
                + "    assert (request.config.invocation_params.dir / name)\n"
            ),
        },
        "docs/x.md",
    ),
    "conftest-request-path-and-a-test-in-a-subdirectory": (
        {
            "tests/conftest.py": _REQUESTED_DATA,
            "tests/sub/test_x.py": "def test_read(data):\n    assert data\n",
        },
        "tests/sub/data/x.json",
    ),
    "request-path-in-a-helper-module": (
        {
            "pkg/__init__.py": "",
            "pkg/helpers.py": ("def data_dir(request):\n    return request.path.parent / 'data'\n"),
            _TEST_FILE: (
                "from pkg.helpers import data_dir\n\n"
                "def test_read(request):\n    assert data_dir(request)\n"
            ),
        },
        "tests/data/x.json",
    ),
    "request-path-in-the-root-conftest": (
        {"conftest.py": _REQUESTED_DATA, _TEST_FILE: "def test_read(data):\n    assert data\n"},
        "tests/data/x.json",
    ),
    "conftest-request-path-derived-in-the-test": (
        {
            "tests/conftest.py": (
                "@pytest.fixture\ndef here(request):\n    return request.path.parent\n"
            ),
            "tests/sub/test_x.py": (
                "def test_read(here):\n" + _COMPUTED + "    assert (here.parent / name)\n"
            ),
        },
        "tests/sub/x.json",
    ),
    "span-widened-by-two-parent-steps": (
        {"tests/sub/conftest.py": _sub_data(base="request.path.parent.parent"), _SUB_TEST: _USE},
        "tests/data/x.json",
    ),
    "span-widened-by-parents-index": (
        {
            "tests/sub/conftest.py": _sub_data(base="Path(str(request.path)).parents[1]"),
            _SUB_TEST: _USE,
        },
        "tests/data/x.json",
    ),
    "span-widened-past-its-directory-by-parents-index": (
        {
            "tests/sub/conftest.py": _sub_data(base="request.path.parents[2]"),
            "tests/sub/deep/test_x.py": _USE,
        },
        "tests/data/x.json",
    ),
    "span-widened-by-a-dot-dot-segment": (
        {"tests/sub/conftest.py": _sub_data(base="request.path.parent / '..'"), _SUB_TEST: _USE},
        "tests/data/x.json",
    ),
    "span-widened-by-a-parent-step-in-the-test": (
        {"tests/sub/conftest.py": _HERE, _SUB_TEST: _HERE_PARENT_DATA},
        "tests/data/x.json",
    ),
    "span-widened-to-the-root-with-computed-segments": (
        {
            "tests/conftest.py": _HERE,
            _TEST_FILE: "def test_read(here):\n" + _COMPUTED + "    assert (here.parent / name)\n",
        },
        "zz.json",
    ),
    "fixture-directory-and-a-parent-step-in-the-test": (
        {
            "tests/sub/conftest.py": (
                "@pytest.fixture\ndef here():\n    return Path(__file__).resolve().parent\n"
            ),
            _SUB_TEST: _HERE_PARENT_DATA,
        },
        "tests/data/x.json",
    ),
    "span-widened-by-a-computed-parents-index": (
        {
            "tests/sub/conftest.py": (
                "@pytest.fixture\ndef data(request):\n"
                + _COMPUTED
                + "    return request.path.parents[len(name)] / 'data'\n"
            ),
            _SUB_TEST: _USE,
        },
        "docs/x.md",
    ),
}

_RETRIED: dict[str, tuple[dict[str, str], str]] = {
    "file-relative-directory-and-a-change-outside-it": (
        {_TEST_FILE: _FILE_RELATIVE},
        "docs/x.json",
    ),
    "request-path-and-a-change-outside-its-directory": (
        {_TEST_FILE: "def test_read(request):\n    assert (request.path.parent / 'data')\n"},
        "docs/data/x.json",
    ),
    "widened-span-and-a-change-outside-it": (
        {"tests/sub/conftest.py": _sub_data(base="request.path.parent.parent"), _SUB_TEST: _USE},
        "docs/data/x.json",
    ),
    "package-directory-and-a-workflow-change": (
        _DELEGATED_GATE_SHAPE,
        ".github/workflows/ci.yml",
    ),
}


@pytest.mark.parametrize(("files", "change"), _TOUCHED.values(), ids=_TOUCHED.keys())
def test_a_change_inside_a_file_relative_directory_touches_the_test(
    *, tmp_path: Path, files: dict[str, str], change: str
) -> None:
    """A change under a directory the closure reaches from `__file__` withholds the retry."""
    assert _marker(tmp_path=tmp_path, files=files, change=change) is None


@pytest.mark.parametrize(("files", "change"), _RETRIED.values(), ids=_RETRIED.keys())
def test_a_change_outside_a_file_relative_directory_leaves_the_retry(
    *, tmp_path: Path, files: dict[str, str], change: str
) -> None:
    """A change outside every directory the closure names leaves the test retried."""
    assert _marker(tmp_path=tmp_path, files=files, change=change) == _MARKER
