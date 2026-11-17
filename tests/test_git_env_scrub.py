"""The session scrub removes every repo-locating git variable and nothing else (fleet root fix).

A pytest run inside a commit hook in a linked worktree inherits the hook's GIT_DIR
and GIT_INDEX_FILE, so git-shelling fixtures wrote into the surrounding repository.
This tests the scrub directly and in-process: no git and no child process runs, so
it asserts the environment, not the outer repository's remote URLs or config keys.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType

_CONFTEST = Path(__file__).resolve().parent / "conftest.py"
_EXPECTED = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
)


def _load_conftest() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_scrub_conftest_under_test", _CONFTEST)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_scrub_names_all_seven_repo_locating_variables() -> None:
    assert set(_load_conftest().GIT_REPO_LOCATING_VARS) == set(_EXPECTED)


def test_the_scrub_removes_every_repo_locating_variable_and_keeps_the_rest() -> None:
    environ = {var: f"/outer/{var}" for var in _EXPECTED}
    environ.update({"PATH": "/usr/bin", "HOME": "/home/x", "GIT_AUTHOR_NAME": "kept"})
    _load_conftest().scrub_inherited_git_repo_locating_env(environ)
    assert environ == {"PATH": "/usr/bin", "HOME": "/home/x", "GIT_AUTHOR_NAME": "kept"}


def test_the_session_fixture_has_already_scrubbed_this_process() -> None:
    assert not [var for var in _EXPECTED if var in os.environ]
