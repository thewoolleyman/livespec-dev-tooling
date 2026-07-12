"""testing-test package conftest — make sibling test modules importable.

Under `--import-mode=importlib` (set in pyproject.toml) with no
`__init__.py` in the test tree, a test module cannot import a sibling
`test_*` module by bare name: the directory is not on `sys.path` and
there is no parent package. Inserting this directory onto `sys.path`
here (conftest is imported before test collection) lets the cli_e2e
mirror test modules `from test_cli_e2e import ...` the shared
synthetic plugin/fixture builders.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTING_TEST_DIR = Path(__file__).resolve().parent
if str(_TESTING_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTING_TEST_DIR))
