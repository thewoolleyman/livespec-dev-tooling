"""An unresolved or class-held repository root keeps the test touched.

livespec-dev-tooling-bob7iv and livespec-dev-tooling-4ai5ao: SPECIFICATION
non-functional-requirements.md "Untouched-test retry" rules that a doubt keeps
a test touched. A root held in a class body and read through `self` or `cls`,
a method or property returning a root, a fixture the closure cannot resolve, a
fixture defined in a `pytest_plugins` module, and a name bound by a construct
the analysis records no value for all may name a repository path, so a change
to that path withholds the retry. A root that is imported, returned by an
imported function or supplied by a fixture, followed only by computed
segments, names a repository path no literal spells, so it withholds the retry
whatever the change set. A plain helper's parameter, plain arithmetic, a
pytest built-in fixture and a parametrized argument name no repository path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.flake_retry_decisions import retry_marker_for

_MARKER = {"reruns": 3, "reruns_delay": 60}
_CHANGE = {Path("data/x.json")}
_TEST_FILE = "tests/test_x.py"
_PLAIN_TEST = "def test_plain():\n    assert True\n"
_HEADER = "from pathlib import Path\n\nimport pytest\n\n"
_COMPUTED = "    name = str(len(__name__))\n"


def _marker(*, tmp_path: Path, files: dict[str, str]) -> dict[str, int] | None:
    for relative, source in {_TEST_FILE: _PLAIN_TEST, **files}.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(_HEADER + source, encoding="utf-8")
    return retry_marker_for(
        repo_root=tmp_path, test_path=tmp_path / _TEST_FILE, change_paths=_CHANGE
    )


_TOUCHED: dict[str, dict[str, str]] = {
    "class-attribute-through-self": {
        "tests/conftest.py": (
            "class Repo:\n    ROOT = Path(__file__).resolve().parents[1]\n\n"
            "    def read(self):\n        return (self.ROOT / 'data' / 'x.json').read_text()\n"
        ),
    },
    "class-attribute-through-cls": {
        "tests/conftest.py": (
            "class Repo:\n    ROOT = Path(__file__).resolve().parents[1]\n\n"
            "    @classmethod\n    def read(cls):\n"
            "        return (cls.ROOT / 'data' / 'x.json').read_text()\n"
        ),
    },
    "method-returning-the-root": {
        "tests/conftest.py": (
            "class Repo:\n    def root(self):\n"
            "        return Path(__file__).resolve().parents[1]\n\n"
            "    def read(self):\n        return (self.root() / 'data' / 'x.json').read_text()\n"
        ),
    },
    "property-returning-the-root": {
        "tests/conftest.py": (
            "class Repo:\n    @property\n    def root(self):\n"
            "        return Path(__file__).resolve().parents[1]\n\n"
            "    def read(self):\n        return (self.root / 'data' / 'x.json').read_text()\n"
        ),
    },
    "fixture-in-a-pytest-plugins-module": {
        "helpers/__init__.py": "",
        "helpers/fixtures.py": (
            "@pytest.fixture\ndef repo():\n    return Path(__file__).resolve().parents[1]\n"
        ),
        _TEST_FILE: (
            "pytest_plugins = ['helpers.fixtures']\n\n"
            "def test_read(repo):\n    assert (repo / 'data' / 'x.json').is_file()\n"
        ),
    },
    "fixture-from-an-unresolvable-plugin": {
        _TEST_FILE: (
            "pytest_plugins = ['elsewhere.fixtures']\n\n"
            "def test_read(repo):\n    assert (repo / 'data' / 'x.json').is_file()\n"
        ),
    },
    "fixture-nothing-defines": {
        _TEST_FILE: "def test_read(repo):\n    assert (repo / 'data' / 'x.json').is_file()\n",
    },
    "name-bound-without-a-recorded-value": {
        "tests/conftest.py": (
            "try:\n    raise LookupError(Path(__file__).resolve().parents[1])\n"
            "except LookupError as found:\n    SPEC = found.args[0] / 'data' / 'x.json'\n"
        ),
    },
    "imported-root-with-computed-segments": {
        "helpers.py": "REPO_ROOT = Path(__file__).resolve().parent\n",
        _TEST_FILE: (
            "from helpers import REPO_ROOT\n\ndef test_read():\n"
            + _COMPUTED
            + "    assert (REPO_ROOT / name).exists()\n"
        ),
    },
    "imported-root-function-with-computed-segments": {
        "helpers.py": "def repo_root():\n    return Path(__file__).resolve().parent\n",
        _TEST_FILE: (
            "from helpers import repo_root\n\ndef test_read():\n"
            + _COMPUTED
            + "    assert (repo_root() / name).exists()\n"
        ),
    },
    "fixture-root-with-computed-segments": {
        "tests/conftest.py": (
            "@pytest.fixture\ndef repo_root():\n    return Path(__file__).resolve().parents[1]\n"
        ),
        _TEST_FILE: (
            "def test_read(repo_root):\n" + _COMPUTED + "    assert (repo_root / name).exists()\n"
        ),
    },
}

_RETRIED: dict[str, dict[str, str]] = {
    "plain-helper-parameter": {
        "tests/conftest.py": "def _data(*, root):\n    return root / 'data' / 'x.json'\n",
    },
    "plain-arithmetic": {
        "tests/conftest.py": (
            "import time\n\nMINUTES = time.time() / 60\n\n"
            "def half(values):\n    return len(values) / 2\n"
        ),
    },
    "builtin-fixture": {
        _TEST_FILE: "def test_read(monkeypatch):\n    assert monkeypatch / 'data' / 'x.json'\n",
    },
    "parametrized-argument": {
        _TEST_FILE: (
            "@pytest.mark.parametrize('base', [1, 2])\n"
            "def test_read(base):\n    assert base / 'data' / 'x.json'\n"
        ),
    },
}


@pytest.mark.parametrize("files", _TOUCHED.values(), ids=_TOUCHED.keys())
def test_an_unresolved_or_class_held_root_keeps_the_test_touched(
    *, tmp_path: Path, files: dict[str, str]
) -> None:
    """A root the analysis cannot rule out, or that it resolves, withholds the retry."""
    assert _marker(tmp_path=tmp_path, files=files) is None


@pytest.mark.parametrize("files", _RETRIED.values(), ids=_RETRIED.keys())
def test_a_base_that_names_no_repository_path_leaves_the_retry(
    *, tmp_path: Path, files: dict[str, str]
) -> None:
    """A helper parameter, arithmetic, a built-in fixture or a parametrized value is no root."""
    assert _marker(tmp_path=tmp_path, files=files) == _MARKER
