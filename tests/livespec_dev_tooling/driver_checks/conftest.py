"""driver_checks-test package conftest — make sibling test modules importable.

Under `--import-mode=importlib` (set in pyproject.toml) with no
`__init__.py` in the test tree, a test module cannot import a sibling
`test_*` module by bare name: the directory is not on `sys.path` and
there is no parent package. Inserting this directory onto `sys.path`
here (conftest is imported before test collection) lets the profile
mirror test modules `from test_plugin_structure import ...` the shared
synthetic-tree builders.
"""

from __future__ import annotations

import sys
from pathlib import Path

_DRIVER_CHECKS_TEST_DIR = Path(__file__).resolve().parent
if str(_DRIVER_CHECKS_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_DRIVER_CHECKS_TEST_DIR))
