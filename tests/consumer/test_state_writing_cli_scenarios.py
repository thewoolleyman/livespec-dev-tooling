"""Consumer-tier: the two `SPECIFICATION/scenarios.md` scenarios of a state-writing CLI's state path.

Governing specification: `SPECIFICATION/non-functional-requirements.md` section
"Testing approach", bullet "Host-state isolation of CLIs". The two scenarios are
two ends of one guarantee. A command-line entry point whose run writes host state
at a location named by a flag takes that location only from the flag, so a caller
that omits it is refused and nothing on the host is touched; and every committed
caller of such an entry point passes the flags explicitly, so the refusal never
fires on a host timer or guard operation that ran before the change.

Both arms drive what a caller and the test suite observe: the exit status and
the usage error of the entry point's own command line, and the finding the
invoker scan reports over a committed systemd unit.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FILER = "livespec_dev_tooling.flake_retry_filer"
_GUARD_CLI = "livespec_dev_tooling.fleet._docker_engine_guard_cli"
_PREFLIGHT_CLI = "livespec_dev_tooling.fleet._docker_engine_guard_preflight_cli"
_INVOKERS = "livespec_dev_tooling.state_cli_invokers"


def _filer_without_state_dir(*, tmp_path: Path) -> None:
    """The flake-retry filer, given its repository but no state directory."""
    filer = importlib.import_module(_FILER)
    _ = filer.main(argv=["--repo-root", str(tmp_path)])


def _guard_without_state_root(*, tmp_path: Path) -> None:
    """The Docker engine install guard, given its runtime root but no state root."""
    cli = importlib.import_module(_GUARD_CLI)
    _ = cli.parse_request(argv=["reserve", "run-a", "--runtime-root", str(tmp_path / "run")])


def _guard_without_runtime_root(*, tmp_path: Path) -> None:
    """The Docker engine install guard, given its state root but no runtime root."""
    cli = importlib.import_module(_GUARD_CLI)
    _ = cli.parse_request(argv=["reserve", "run-a", "--state-root", str(tmp_path / "var")])


def _preflight_without_state_root(*, tmp_path: Path) -> None:
    """The guard's preflight recorder, given its run but no state root."""
    del tmp_path
    cli = importlib.import_module(_PREFLIGHT_CLI)
    _ = cli.main(argv=["record", "--run", "run-a"])


@pytest.mark.parametrize(
    ("invocation", "flag"),
    [
        (_filer_without_state_dir, "--state-dir"),
        (_guard_without_state_root, "--state-root"),
        (_guard_without_runtime_root, "--runtime-root"),
        (_preflight_without_state_root, "--state-root"),
    ],
)
def test_a_state_writing_cli_invoked_without_its_state_path_flag_refuses_and_touches_no_host_state(
    *,
    invocation: Any,
    flag: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Omitting the flag exits non-zero naming it, with no directory or file written."""
    writes = Mock()
    for method in ("mkdir", "touch", "write_text", "write_bytes", "open"):
        monkeypatch.setattr(Path, method, getattr(writes, method))
    host = Mock()
    monkeypatch.setattr(importlib.import_module(_PREFLIGHT_CLI), "build_real_host", host)

    with pytest.raises(SystemExit) as refusal:
        invocation(tmp_path=tmp_path)

    assert refusal.value.code != 0
    assert flag in capsys.readouterr().err
    assert writes.mock_calls == []
    assert host.mock_calls == []
    assert list(tmp_path.iterdir()) == []


def test_a_committed_invoker_that_omits_a_state_writing_clis_state_path_flag_fails_the_test_suite(
    *, tmp_path: Path
) -> None:
    """A unit that runs the filer without `--state-dir` is named by file and flag."""
    invokers = importlib.import_module(_INVOKERS)
    unit = tmp_path / "ansible" / "roles" / "filer" / "templates" / "filer.service.j2"
    unit.parent.mkdir(parents=True)
    _ = unit.write_text(
        "[Service]\n" f"ExecStart=/usr/bin/python -m {_FILER} --repo-root /srv/checkout\n",
        encoding="utf-8",
    )

    (finding,) = invokers.find_unflagged_invokers(root=tmp_path)

    assert finding.path == "ansible/roles/filer/templates/filer.service.j2"
    assert finding.flag == "--state-dir"
    assert finding.path in finding.render()
    assert finding.flag in finding.render()


def test_the_committed_invokers_of_this_repository_pass_every_state_location_flag() -> None:
    """The control arm: the repository's own units, tasks, templates and scripts are clean."""
    invokers = importlib.import_module(_INVOKERS)

    found = invokers.find_unflagged_invokers(root=_REPO_ROOT)

    assert [finding.render() for finding in found] == []
