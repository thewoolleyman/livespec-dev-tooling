"""Outside-in test for `livespec_dev_tooling/tests_host_path_free.py`.

A test that reads, stats or writes an absolute path under `/etc`, `/var`, `/usr`,
`/opt` or `/run` — or converges an Ansible task whose destination is one — grades
the machine pytest happens to run on rather than the committed tree
(livespec-dev-tooling-vxkmab, from the 2026-10-18 F-az incident). The check fails
such a module naming the file, the line and the path; it passes a module that
derives every path from `tmp_path`, and it passes a module that merely NAMES a
host path without reaching it. The one exemption is a FIXTURE NAME held in the
check's own configuration, and a comment in a test module never is one. The
committed tree must pass it.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "tests_host_path_free.py"

# The two surfaces `scripts/just/check.sh` mirrors entry for entry, and the slug
# that has to appear in both for the check to be a member of `just check`.
_SLUG = "check-tests-host-path-free"
_RECIPE_BODY = "uv run python -m livespec_dev_tooling.tests_host_path_free"

# The check's OWN configuration: the allow-list of fixture names. Named here
# because every arm below drives the check through it, which is exactly what an
# operator adding a fixture to the allow-list does.
_ALLOW_LIST = "ALLOW_LISTED_FIXTURES"

# Three synthetic test modules, written into a throwaway `tests/` tree. Line
# numbers are load-bearing: the check must name the line its finding is about,
# so each arm below asserts the line as well as the path.

_OFFENDERS = """\
import os
from pathlib import Path

_MARKER = "/run/livespec/marker"
_ROOT = "/etc/livespec"
_REGISTRY: Path = Path(_ROOT) / "fabro-factories.json"
_TIMEOUT = 5
_UNSET: str


def test_reads_a_host_file() -> None:
    assert Path("/etc/livespec/sandbox-capabilities").read_text(encoding="utf-8")


def test_stats_a_host_file() -> None:
    assert Path("/var/lib/docker-sandbox-slice/restart-pending").is_file()


def test_writes_through_open() -> None:
    handle = open(_MARKER, "w", encoding="utf-8")
    handle.close()


def test_reads_the_module_constant() -> None:
    assert _REGISTRY.exists()


def test_stats_through_os() -> None:
    assert os.stat(path="/opt/livespec/codex-acp")
"""

_DESTINATIONS = """\
_DEST_VAR = "fabro_factory_registry_dest"
_DEFAULT = "/etc/livespec/fabro-factories.json"
_BASE = {"gather_facts": False}


def test_converges_the_real_destination() -> None:
    task = {
        "ansible.builtin.copy": {
            "content": "{}",
            "dest": "/etc/livespec/fabro-factories.json",
        }
    }
    extra = {**_BASE, _DEST_VAR: _DEFAULT, "timeout": 5}
    assert task and extra
"""

_CLEAN = """\
from pathlib import Path

_DOCUMENTED_DEFAULT = "/etc/livespec/fabro-factories.json"


def test_derives_every_path_from_tmp_path(*, tmp_path: Path) -> None:
    dest = tmp_path / "etc" / "livespec" / "fabro-factories.json"
    dest.parent.mkdir(parents=True)
    _ = dest.write_text("{}", encoding="utf-8")
    assert dest.read_text(encoding="utf-8") == "{}"


def test_names_the_documented_default_without_reaching_it() -> None:
    assert _DOCUMENTED_DEFAULT.startswith("/etc/")
"""

# Two reaches of the same kind: one in a test that DECLARES the fixture an
# operator may put on the allow-list, one in a test that instead argues its case
# in a comment. Only the first is ever exemptible.
_FIXTURE_AND_COMMENT = """\
from pathlib import Path


def test_reads_the_real_registry(*, host_captured_registry: Path) -> None:
    # The check's allow-list is what exempts this, never this comment.
    assert host_captured_registry
    assert Path("/etc/livespec/fabro-factories.json").read_text(encoding="utf-8")


def test_reads_it_without_declaring_the_fixture() -> None:
    # Exempt: this test has to read the real file. (It does not: a comment
    # never exempts anything, because the check reads no comments at all.)
    assert Path("/etc/livespec/sandbox-capabilities").is_file()
"""


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path (the tree the RGR hook inspects)."""
    assert _CHECK_PATH.is_file(), "tests_host_path_free check module should exist"
    spec = importlib.util.spec_from_file_location("tests_host_path_free_under_test", _CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CheckRun(NamedTuple):
    returncode: int
    findings: list[dict[str, object]]


def _run_check(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    allow_listed: tuple[str, ...] = (),
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd` and parse its findings.

    `allow_listed` stands in for the check's own configuration for the duration
    of the run, which is what an operator who adds a fixture name to it does.
    Asserted to be a frozenset first: the allow-list has to live in the CHECK,
    because that is what makes it reviewable rather than self-declared.
    """
    monkeypatch.chdir(cwd)
    module = _load_check_module()
    configured = getattr(module, _ALLOW_LIST, None)
    assert isinstance(
        configured, frozenset
    ), f"the check must hold its allow-list of fixture names in `{_ALLOW_LIST}`"
    monkeypatch.setattr(module, _ALLOW_LIST, frozenset(allow_listed))
    rc = module.main()
    captured = capsys.readouterr()
    findings = [json.loads(line) for line in captured.err.splitlines() if line.strip()]
    return _CheckRun(returncode=rc, findings=findings)


def _write(*, root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def _reported(*, run: _CheckRun) -> list[tuple[object, object, object, object]]:
    """Each finding as the four facts the work-item requires it to name, plus its kind."""
    return [(item["path"], item["line"], item["target"], item["kind"]) for item in run.findings]


def test_the_committed_tests_tree_reaches_no_real_host_path(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No test under `tests/` reads, stats, writes or converges a real host path."""
    run = _run_check(cwd=_REPO_ROOT, monkeypatch=monkeypatch, capsys=capsys)
    assert run.findings == []
    assert run.returncode == 0


def test_a_read_a_stat_and_a_write_of_a_host_path_each_fail(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every finding names the file, the line number and the path."""
    _write(root=tmp_path, relative="tests/test_offenders.py", text=_OFFENDERS)
    run = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _reported(run=run) == [
        (
            "tests/test_offenders.py",
            12,
            "/etc/livespec/sandbox-capabilities",
            "method:read_text",
        ),
        (
            "tests/test_offenders.py",
            16,
            "/var/lib/docker-sandbox-slice/restart-pending",
            "method:is_file",
        ),
        ("tests/test_offenders.py", 20, "/run/livespec/marker", "call:open"),
        ("tests/test_offenders.py", 25, "/etc/livespec", "method:exists"),
        ("tests/test_offenders.py", 29, "/opt/livespec/codex-acp", "call:os.stat"),
    ]


def test_an_ansible_task_destination_naming_a_host_path_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `dest` the module hard-codes, and an extra-var key held in a constant, both fail."""
    _write(root=tmp_path, relative="tests/ansible/test_destinations.py", text=_DESTINATIONS)
    run = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _reported(run=run) == [
        (
            "tests/ansible/test_destinations.py",
            10,
            "/etc/livespec/fabro-factories.json",
            "destination:dest",
        ),
        (
            "tests/ansible/test_destinations.py",
            13,
            "/etc/livespec/fabro-factories.json",
            "destination:fabro_factory_registry_dest",
        ),
    ]


def test_a_tmp_path_derived_tree_and_a_mere_mention_both_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Naming a role's documented default is not reaching it, and `tmp_path` never matches."""
    _write(root=tmp_path, relative="tests/test_clean.py", text=_CLEAN)
    run = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert run.findings == []
    assert run.returncode == 0


def test_every_finding_carries_the_remediation_that_names_tmp_path(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal is actionable: it says what to derive the path from instead."""
    _write(root=tmp_path, relative="tests/test_offenders.py", text=_OFFENDERS)
    run = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert run.findings
    for item in run.findings:
        assert "tmp_path" in str(item["remediation"])
        assert item["level"] == "error"


def test_a_fixture_on_the_configured_allow_list_exempts_the_test_that_declares_it(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Adding the fixture name to the check's configuration passes the test that declares it."""
    _write(root=tmp_path, relative="tests/test_allowed.py", text=_FIXTURE_AND_COMMENT)
    run = _run_check(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        allow_listed=("host_captured_registry",),
    )
    assert _reported(run=run) == [
        ("tests/test_allowed.py", 13, "/etc/livespec/sandbox-capabilities", "method:is_file")
    ]
    assert run.returncode == 1


def test_a_comment_never_exempts_a_host_path(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With nothing allow-listed, BOTH reaches fail — including the one a comment argues for."""
    _write(root=tmp_path, relative="tests/test_allowed.py", text=_FIXTURE_AND_COMMENT)
    run = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert _reported(run=run) == [
        (
            "tests/test_allowed.py",
            7,
            "/etc/livespec/fabro-factories.json",
            "method:read_text",
        ),
        ("tests/test_allowed.py", 13, "/etc/livespec/sandbox-capabilities", "method:is_file"),
    ]
    assert run.returncode == 1


def test_the_shipped_allow_list_names_no_fixture() -> None:
    """It ships EMPTY: no test in this repository needs to reach a real host path."""
    configured = getattr(_load_check_module(), _ALLOW_LIST, None)
    assert configured == frozenset()


def _justfile() -> str:
    return (_REPO_ROOT / "justfile").read_text(encoding="utf-8")


def _aggregate_targets() -> list[str]:
    """The `check:` recipe's `targets=(...)` array, in order."""
    array = re.search(r"\n    targets=\(\n(?P<body>(?:.*\n)*?)    \)\n", _justfile())
    assert array is not None, "the justfile must carry the `check:` recipe's targets=(...) array"
    return [
        stripped
        for line in array["body"].splitlines()
        if (stripped := line.strip()).startswith("check-")
    ]


def _inventory_targets() -> list[str]:
    """`check-targets.txt`, comments and blanks removed — what `scripts/just/check.sh` mirrors."""
    text = (_REPO_ROOT / "check-targets.txt").read_text(encoding="utf-8")
    return [
        stripped
        for line in text.splitlines()
        if (stripped := line.split("#")[0].strip()).startswith("check-")
    ]


def test_the_check_is_a_member_of_this_repositorys_own_check_aggregate() -> None:
    """Wired into `just check` on BOTH surfaces, and the recipe invokes the check module."""
    wired = _aggregate_targets()
    assert wired == _inventory_targets(), (
        "the justfile targets array and check-targets.txt must mirror each other entry for "
        "entry, or scripts/just/check.sh refuses the aggregate as drifted"
    )
    assert _SLUG in wired, f"{_SLUG} must be a member of this repository's `just check` aggregate"
    assert (
        f"\n{_SLUG}:\n    {_RECIPE_BODY}\n" in _justfile()
    ), f"the justfile must declare `{_SLUG}:` invoking the check module"


def test_the_check_is_repo_private_rather_than_a_canonical_slug() -> None:
    """The placement decision: a canonical slug obliges EVERY consumer to wire it."""
    canonical = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "tests_host_path_free.py"
    assert not canonical.exists(), (
        "the check must stay OUT of livespec_dev_tooling/checks/: that directory IS the "
        "canonical slug set, and a canonical slug obliges every consumer repository to wire "
        "it into its own `just check` and CI matrix, while the host-path tests this one "
        "polices are this repository's own Ansible role tests"
    )
