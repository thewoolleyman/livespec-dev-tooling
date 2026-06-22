"""Fleet-test package conftest — make sibling test-helper modules importable.

Under `--import-mode=importlib` (set in pyproject.toml) with no
`__init__.py` in the test tree, a test module cannot import a sibling
non-`test_*` helper by bare name or relative path: the directory is not
on `sys.path` and there is no parent package. Inserting this directory
onto `sys.path` here (conftest is imported before test collection) lets
the fleet test modules `from _protection_fixtures import ...` the shared
branch-protection payload helper.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FLEET_TEST_DIR = Path(__file__).resolve().parent
if str(_FLEET_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_FLEET_TEST_DIR))
