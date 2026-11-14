"""A path expression on a non-rooted base names no repository path.

livespec-dev-tooling-bob7iv: `(repo / "SPECIFICATION")` inside a conftest
helper taking `repo` as a parameter made every test beside that conftest count
as touched by a spec-only change. SPECIFICATION non-functional-requirements.md
"Untouched-test retry" rules that such a base MUST NOT name a repository path
and that its segments MUST NOT count as literals of the closure. Every base
that reads, or may read, the repository keeps the test touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.flake_retry_decisions import (
    retry_marker_for,
    retry_withheld_reason_for,
)

_MARKER = {"reruns": 3, "reruns_delay": 60}
_SPEC_CHANGE = {Path("SPECIFICATION/proposed_changes/x.md")}
_HEADER = (
    "import contextlib\nimport functools\nimport os\nimport tempfile\n"
    "from os import path as osp\nfrom pathlib import Path\n\nimport pytest\n\nimport pkgmod\n\n"
)


def _marker(*, tmp_path: Path, conftest: str) -> dict[str, int] | None:
    package = tmp_path / "pkgmod"
    package.mkdir()
    _ = (package / "__init__.py").write_text("", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    _ = (tests / "conftest.py").write_text(_HEADER + conftest, encoding="utf-8")
    test_path = tests / "test_x.py"
    _ = test_path.write_text("def test_plain():\n    assert True\n", encoding="utf-8")
    return retry_marker_for(repo_root=tmp_path, test_path=test_path, change_paths=_SPEC_CHANGE)


_NOT_ROOTED = {
    "function-parameter": "def _read(*, repo):\n    return (repo / 'SPECIFICATION').is_dir()\n",
    "tmp-path": "def spec(tmp_path):\n    return tmp_path / 'SPECIFICATION' / 'spec.md'\n",
    "derived-from-tmp-path": (
        "def spec(tmp_path):\n    repo = tmp_path / 'repo'\n    return repo / 'SPECIFICATION'\n"
    ),
    "home-and-arithmetic": "HOME = Path.home() / 'SPECIFICATION'\nHALF = 10 / 2\n",
    "tmp-path-overridden-through-mktemp": (
        "@pytest.fixture\ndef tmp_path(tmp_path_factory):\n"
        "    return tmp_path_factory.mktemp('repo')\n"
        "def spec(tmp_path):\n    return tmp_path / 'SPECIFICATION'\n"
    ),
    "keyword-defaults-that-are-not-rooted": (
        "@functools.cache\ndef make(*, base=None, other, depth: int = 1):\n"
        "    return base / 'SPECIFICATION'\n"
    ),
    "fixture-yielding-a-tmp-path": (
        "@pytest.fixture\ndef repo(tmp_path):\n    yield tmp_path / 'repo'\n"
        "def spec(repo):\n    return repo / 'SPECIFICATION'\n"
    ),
    "attribute-of-a-parameter": (
        "class Holder:\n    def __init__(self, base):\n        self.base = base\n"
        "    def spec(self):\n        return self.base / 'SPECIFICATION'\n"
    ),
    "temporary-directory": (
        "with contextlib.suppress(OSError):\n    pass\n"
        "with tempfile.TemporaryDirectory() as scratch:\n"
        "    SPEC = Path(scratch) / 'SPECIFICATION'\n"
    ),
    "lambda-parameter": "spec = lambda base: base / 'SPECIFICATION'\n",
}

_ROOTED = {
    "derived-from-file": (
        "ROOT = Path(__file__).resolve().parents[1]\nROOT = Path(__file__).resolve().parents[1]\n"
        "SPEC = ROOT / 'SPECIFICATION'\n"
    ),
    "bare-literal": "NAME = 'SPECIFICATION'\n",
    "module-dunder-file": "SPEC = Path(pkgmod.__file__).resolve().parents[1] / 'SPECIFICATION'\n",
    "yield-fixture": (
        "@pytest.fixture\ndef repo():\n    yield Path(__file__).parents[1]\n"
        "def test_y(repo):\n    assert (repo / 'SPECIFICATION').is_dir()\n"
    ),
    "fixture-name-unreadable": (
        "NAME = 'repo'\n@pytest.fixture(scope='session', name=NAME)\n"
        "def _repo():\n    return Path(__file__).parents[1]\n"
        "def spec(anything):\n    return anything / 'SPECIFICATION'\n"
    ),
    "renamed-fixture-at-the-working-directory": (
        "@pytest.fixture(name='repo')\ndef _repo():\n    return Path.cwd()\n"
        "def spec(repo):\n    return repo / 'SPECIFICATION'\n"
    ),
    "fixture-by-literal-lookup": (
        "@pytest.fixture\ndef repo():\n    return Path()\n"
        "def spec(request):\n    return request.getfixturevalue('repo') / 'SPECIFICATION'\n"
    ),
    "fixture-by-dynamic-lookup": (
        "def spec(request, name):\n    return request.getfixturevalue(name) / 'SPECIFICATION'\n"
    ),
    "pytest-rootpath": "def spec(pytestconfig):\n    return pytestconfig.rootpath / 'SPECIFICATION'\n",
    "subscript-store-from-a-function": (
        "PATHS = {}\ndef setup():\n    PATHS['root'] = Path(__file__).parent\n"
        "    UNBOUND['root'] = 1\nSPEC = PATHS['root'] / 'SPECIFICATION'\n"
    ),
    "attribute-subscript-store": (
        "class Box:\n    pass\nBox.paths['root'] = os.getcwd()\n"
        "def spec(box):\n    return box.paths['root'] / 'SPECIFICATION'\n"
    ),
    "unpacked-for-target": (
        "for ROOT, *_ in [(Path(__file__).parent, 1)]:\n    SPEC = ROOT / 'SPECIFICATION'\n"
    ),
    "comprehension-target": "SPECS = [r / 'SPECIFICATION' for r in [Path(__file__).parents[1]]]\n",
    "annotated-and-walrus": (
        "ROOT: Path = Path(__file__).parent\nUNSET: Path\n"
        "if (base := ROOT):\n    SPEC = base / 'SPECIFICATION'\n"
    ),
    "rooted-default": (
        "def spec(root=Path(__file__).parents[1]):\n    return root / 'SPECIFICATION'\n"
    ),
    "import-alias-dirname": "SPEC = Path(osp.dirname(__file__)) / 'SPECIFICATION'\n",
    "global-declaration": (
        "ROOT = None\ndef setup():\n    global ROOT\n    ROOT = Path(__file__).parent\n"
        "def spec():\n    global ROOT\n    return ROOT / 'SPECIFICATION'\n"
    ),
    "empty-iterable": "for r in []:\n    SPEC = r / 'SPECIFICATION'\n",
    "git-toplevel": (
        "import subprocess\n"
        "ROOT = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel']).strip())\n"
        "SPEC = ROOT / 'SPECIFICATION'\n"
    ),
    "environment-variable": "SPEC = Path(os.environ['REPO']) / 'SPECIFICATION'\n",
    "function-returning-a-root": (
        "def repo_root():\n    return Path(__file__).parents[1]\n"
        "SPEC = repo_root() / 'SPECIFICATION'\n"
    ),
    "unknown-builtin": ("def spec(tmp):\n    return sorted(tmp.iterdir())[0] / 'SPECIFICATION'\n"),
    "joined-literal": "SPEC = Path('a' + 'b') / 'SPECIFICATION'\n",
}


@pytest.mark.parametrize("conftest", _NOT_ROOTED.values(), ids=_NOT_ROOTED.keys())
def test_a_path_expression_on_a_non_rooted_base_leaves_the_retry(
    *, tmp_path: Path, conftest: str
) -> None:
    """A spec-only change does not touch a test whose closure names the spec only off-root."""
    assert _marker(tmp_path=tmp_path, conftest=conftest) == _MARKER


@pytest.mark.parametrize("conftest", _ROOTED.values(), ids=_ROOTED.keys())
def test_a_repository_rooted_path_or_bare_literal_still_touches_the_test(
    *, tmp_path: Path, conftest: str
) -> None:
    """A base that is, or may be, the repository keeps the test touched with no retry."""
    assert _marker(tmp_path=tmp_path, conftest=conftest) is None


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_CHANGE = {Path(".github/workflows/ci.yml")}
_WORKFLOW_UNDER_A_TEMPORARY_ROOT = (
    "def _workflow(*, root):\n    return root / '.github' / 'workflows' / 'ci.yml'\n"
    "def scratch_workflow(tmp_path):\n    root = tmp_path / 'repo'\n"
    "    return root / '.github' / 'workflows' / 'ci.yml'\n"
)
_WORKFLOW_UNDER_THE_REPOSITORY = (
    "def literal():\n    return Path('.github') / 'workflows' / 'ci.yml'\n",
    "def derived():\n    return Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'ci.yml'\n",
    "ROOT = Path(__file__).resolve().parents[1]\nWORKFLOW = ROOT / '.github' / 'workflows' / 'ci.yml'\n",
)
_COPIES_A_REPOSITORY_DIRECTORY = (
    "import shutil\nREPO_ROOT = Path(__file__).resolve().parents[1]\n"
    "def test_copy(tmp_path):\n"
    "    shutil.copytree(REPO_ROOT / 'ci-runner', tmp_path / 'ci-runner')\n"
)
_NAMES_A_FILE_ABOVE_THE_TESTS = (
    "SCRIPT = Path(__file__).resolve().parents[2] / 'homelab-worker' / 'prove-worker.sh'\n"
)


def _decide(*, tmp_path: Path, conftest: str, change: set[Path]) -> dict[str, int] | None:
    tests = tmp_path / "tests"
    tests.mkdir()
    _ = (tests / "conftest.py").write_text(
        "from pathlib import Path\n\n" + conftest, encoding="utf-8"
    )
    test_path = tests / "test_x.py"
    _ = test_path.write_text("def test_plain():\n    assert True\n", encoding="utf-8")
    return retry_marker_for(repo_root=tmp_path, test_path=test_path, change_paths=change)


@pytest.mark.integration
def test_a_changed_file_named_only_under_a_temporary_root_is_retried(*, tmp_path: Path) -> None:
    """A workflow path built on a parameter or on `tmp_path` leaves a ci.yml change untouched."""
    conftest = _WORKFLOW_UNDER_A_TEMPORARY_ROOT

    assert _decide(tmp_path=tmp_path, conftest=conftest, change=_WORKFLOW_CHANGE) == _MARKER


@pytest.mark.integration
@pytest.mark.parametrize("conftest", _WORKFLOW_UNDER_THE_REPOSITORY)
def test_a_changed_file_named_under_the_repository_root_is_touched(
    *, tmp_path: Path, conftest: str
) -> None:
    """A workflow path built on a literal, `__file__` or a rooted name keeps ci.yml touching."""
    assert _decide(tmp_path=tmp_path, conftest=conftest, change=_WORKFLOW_CHANGE) is None


@pytest.mark.integration
def test_a_test_copying_a_repository_directory_into_a_temporary_root_is_touched(
    *, tmp_path: Path
) -> None:
    """The copy names its source through a rooted expression, so the source still counts."""
    conftest = _COPIES_A_REPOSITORY_DIRECTORY
    change = {Path("ci-runner/k3s/x.sh")}

    assert _decide(tmp_path=tmp_path, conftest=conftest, change=change) is None


@pytest.mark.integration
def test_a_file_named_through_a_file_rooted_path_above_the_tests_is_touched(
    *, tmp_path: Path
) -> None:
    """A `__file__`-rooted path names its file on purpose, not through a suffixed segment."""
    conftest = _NAMES_A_FILE_ABOVE_THE_TESTS
    change = {Path("homelab-worker/prove-worker.sh")}

    assert _decide(tmp_path=tmp_path, conftest=conftest, change=change) is None


@pytest.mark.integration
def test_the_workflow_edit_commit_names_nothing_the_delegated_gate_scenarios_read() -> None:
    """Commit 63302bba's change set names no module or literal of the delegated-gate scenarios.

    This reads the real repository, so the scenarios' closure grows with it: a
    module joining it can make the test touched for its own reason, such as a
    path it builds that no analysis can determine. Only this change set's own
    attribution is asserted; the temporary-root case above pins the retry.
    """
    test_path = _REPO_ROOT / "tests/consumer/test_delegated_gate_declared_recipe_scenarios.py"
    change = {Path(".github/workflows/ci.yml"), Path(".livespec-workflow-edit-exemption")}

    reason = retry_withheld_reason_for(
        repo_root=_REPO_ROOT, test_path=test_path, memo={}, change_paths=change
    )

    assert not (reason or "").startswith(("changed closure module", "closure string literal"))
