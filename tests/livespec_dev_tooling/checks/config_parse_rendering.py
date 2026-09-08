"""Shared fixture and assertion for the per-check `ConfigParseError` rendering.

`SPECIFICATION/contracts.md` section "Configuration loader" makes
`ConfigParseError` an IO-layer exception that each check's `main()` supervisor
catches and renders as a structured diagnostic. Slice 1
(`livespec-dev-tooling-i6zi`) built the single definition of that rendering in
`checks/_config_load.py`; slice 2 (`livespec-dev-tooling-efxa`) adopted it at
the remaining twenty-seven call sites. Each of those twenty-seven proves the
rendering in its OWN mirror test file, because `check_coverage_incremental`
gates every changed impl module at 100% against its PAIRED test alone — a
single consolidated sweep test would leave twenty-seven guard branches
uncovered at the pair level while looking fully covered in the whole-suite run.

This module is what keeps that per-file proof from being twenty-seven copies of
one body. It is a plain helper module rather than a `conftest.py` fixture
because the assertion and the fixture travel together: every call site wants
both, and splitting them would put the contract in two places.

WHAT THE ASSERTION PINS, and why it is the whole supervisor contract rather
than "nothing escaped": a NON-ZERO return AND one structured event carrying
`check_id`, `status="fail"` and a non-empty `error`. A test asserting only that
no exception escaped would pass against a silent `except: pass`, which is the
opposite of what the contract asks for.

WHY THE FIXTURE IS A GIT WORKING TREE WITH A TRACKED MODULE. The applies-to-all
checks resolve their file universe from the git index and return 0 on an empty
one. Without the tracked `.py` those cases would exit 0 before reaching any
config at all, and the non-zero assertion would fail for a reason that has
nothing to do with this rendering. The same git dependency is why the malformed
`pyproject.toml` must be reachable through `resolve_check_universe`: for those
checks the parse failure is raised inside it — `iter_first_party_py_files`
calls `load_config` itself for the `tests_tree_prefix` it filters on — an
earlier frame than the check's own load line.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = [
    "CONFIG_PARSE_FAILED_EVENT",
    "assert_main_renders_the_parse_failure",
]


_CHECKS_PACKAGE = "livespec_dev_tooling.checks"
# The one wording `required_role_keys_declared` has emitted since the rejecting
# loader landed, pinned here rather than read off the shared module: the
# migrated surfaces must agree with the PRECEDENT, and importing the constant
# would only make them agree with themselves.
CONFIG_PARSE_FAILED_EVENT = "consumer config parse failed"
# The same unparseable payload `test_config.py` and `test_config_load.py` use,
# so every call site exercises the REAL loader raising a REAL
# `ConfigParseError` with nothing monkeypatched onto it.
_MALFORMED_PYPROJECT = "not [toml"
_TRACKED_MODULE_BODY = "from __future__ import annotations\n\n__all__: list[str] = []\n"


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env.

    `git` is not a Python spawn, so `tests_no_subprocess_spawn` permits it; the
    hardcoded env keeps `COVERAGE_PROCESS_START` out of this child and keeps the
    developer's own git config from reaching the fixture.
    """
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _seed_malformed_consumer_repo(*, repo_root: Path) -> None:
    """Seed a git working tree with one tracked module and an unparseable config."""
    package = repo_root / "pkg"
    package.mkdir()
    _ = (package / "mod.py").write_text(_TRACKED_MODULE_BODY, encoding="utf-8")
    _ = (repo_root / "pyproject.toml").write_text(_MALFORMED_PYPROJECT, encoding="utf-8")
    _git(cwd=repo_root, args=["init", "-q"])
    _git(cwd=repo_root, args=["add", "-A"])


def _rendered_the_diagnostic(*, captured: str, check_id: str) -> bool:
    """True iff stderr carries one structured parse-failure event for `check_id`."""
    records = [json.loads(line) for line in captured.splitlines() if line.strip().startswith("{")]
    return any(
        record.get("event") == CONFIG_PARSE_FAILED_EVENT
        and record.get("check_id") == check_id
        and record.get("status") == "fail"
        and bool(record.get("error"))
        for record in records
    )


def assert_main_renders_the_parse_failure(
    *,
    module_slug: str,
    check_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Drive `<module_slug>.main()` against a malformed config and pin the diagnostic."""
    _seed_malformed_consumer_repo(repo_root=tmp_path)
    # A one-element argv is the no-arguments invocation these checks are wired
    # into `just check` with. `check_coverage_incremental` and
    # `red_green_replay` both read `sys.argv` before doing their work, and under
    # pytest it would otherwise carry the runner's own arguments.
    monkeypatch.setattr(sys, "argv", [module_slug])
    monkeypatch.chdir(tmp_path)
    module = importlib.import_module(f"{_CHECKS_PACKAGE}.{module_slug}")

    rc = module.main()

    assert rc != 0, "a malformed consumer config must still exit non-zero"
    assert _rendered_the_diagnostic(captured=capsys.readouterr().err, check_id=check_id), (
        f"{module_slug}.main() must render the structured parse-failure event "
        f"rather than let `ConfigParseError` escape as a traceback"
    )
