"""Every test that runs the pinned `ansible-core` waits for its RPC server under the hang guard.

Covers `SPECIFICATION/non-functional-requirements.md`, "Load-independent concurrency
waits", for ansible-core's in-process RPC host (livespec-dev-tooling-biq757). The
hook that does the waiting is `fixtures/pinned_ansible_rpc_wait/sitecustomize.py`;
the tests below load it against a stand-in `ansible._internal._rpc_host` that has
ansible-core's exact start shape, and against the real pinned ansible-core.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

from tests.hang_guard import HANG_GUARD_SECONDS
from tests.pinned_ansible import (
    RPC_START_HANG_MARKER_VARIABLE,
    RPC_START_WAIT_SECONDS_VARIABLE,
    RPC_WAIT_DIRECTORY,
    fail_if_rpc_start_hung,
    rpc_start_environment,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOOK = RPC_WAIT_DIRECTORY / "sitecustomize.py"
_HOST_MODULE = "ansible._internal._rpc_host"

# The start shape of ansible-core 2.21's `LocalNotAProcess.start`, with the wait
# shortened so a test can tell a patient wait from the fixed one in well under a second.
_STAND_IN_HOST = """\
import threading

_server_ready = threading.Event()
FIXED_WAIT_SECONDS = 0.05


def start(*, serve):
    threading.Thread(target=serve, daemon=True).start()
    if not _server_ready.wait(FIXED_WAIT_SECONDS):
        raise TimeoutError("Local RPC server did not start.")
"""


def _load_hook() -> ModuleType:
    """The hook as a module of its own, imported without the interpreter having run it."""
    spec = importlib.util.spec_from_file_location("pinned_ansible_rpc_wait_hook", _HOOK)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def stand_in_host(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Put a stand-in `ansible._internal._rpc_host` on `sys.path`, and take it off again."""
    package = tmp_path / "ansible" / "_internal"
    package.mkdir(parents=True)
    for directory in (package.parent, package):
        _ = (directory / "__init__.py").write_text("", encoding="utf-8")
    _ = (package / "_rpc_host.py").write_text(_STAND_IN_HOST, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    meta_path = list(sys.meta_path)
    yield tmp_path
    sys.meta_path[:] = meta_path
    for name in [n for n in sys.modules if n == "ansible" or n.startswith("ansible.")]:
        del sys.modules[name]


def _serve_after(*, host: ModuleType, seconds: float) -> Callable[[], None]:
    def serve() -> None:
        time.sleep(seconds)
        host._server_ready.set()  # noqa: SLF001 - the stand-in's own module event

    return serve


def test_the_hook_directory_carries_a_sitecustomize() -> None:
    assert _HOOK.is_file(), f"{_HOOK} must exist: it is what the ansible interpreter loads"


def test_a_slow_rpc_start_is_waited_for_rather_than_cut_at_the_fixed_wait(
    *, stand_in_host: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del stand_in_host
    monkeypatch.setenv(RPC_START_WAIT_SECONDS_VARIABLE, "30")
    monkeypatch.setenv(RPC_START_HANG_MARKER_VARIABLE, str(tmp_path / "marker"))
    _load_hook().install()
    host = importlib.import_module(_HOST_MODULE)
    # Started 0.5 s after the call, ten times the stand-in's fixed 0.05 s wait.
    host.start(serve=_serve_after(host=host, seconds=0.5))
    assert not (tmp_path / "marker").exists()


def test_an_rpc_server_that_never_starts_fails_as_a_hang_that_names_the_wait(
    *, stand_in_host: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del stand_in_host
    marker = tmp_path / "marker"
    monkeypatch.setenv(RPC_START_WAIT_SECONDS_VARIABLE, "0.3")
    monkeypatch.setenv(RPC_START_HANG_MARKER_VARIABLE, str(marker))
    _load_hook().install()
    host = importlib.import_module(_HOST_MODULE)
    with pytest.raises(TimeoutError, match=r"HANG: .*RPC server.*_server_ready\.wait"):
        host.start(serve=lambda: None)
    assert marker.is_file()
    with pytest.raises(pytest.fail.Exception, match=r"HANG: .*RPC server"):
        fail_if_rpc_start_hung(marker=marker)


def test_no_marker_means_no_hang(*, tmp_path: Path) -> None:
    fail_if_rpc_start_hung(marker=tmp_path / "never-written")


@pytest.mark.parametrize("unset", [RPC_START_WAIT_SECONDS_VARIABLE, RPC_START_HANG_MARKER_VARIABLE])
def test_the_hook_does_nothing_unless_the_wait_and_the_marker_are_named(
    *, stand_in_host: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unset: str
) -> None:
    del stand_in_host
    monkeypatch.setenv(RPC_START_WAIT_SECONDS_VARIABLE, "30")
    monkeypatch.setenv(RPC_START_HANG_MARKER_VARIABLE, str(tmp_path / "marker"))
    monkeypatch.delenv(unset)
    meta_path = list(sys.meta_path)
    _load_hook().install()
    assert sys.meta_path == meta_path


def test_a_missing_host_module_is_still_missing(
    *, stand_in_host: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The finder claims only a module it can find; any other import behaves as before."""
    (stand_in_host / "ansible" / "_internal" / "_rpc_host.py").unlink()
    monkeypatch.setenv(RPC_START_WAIT_SECONDS_VARIABLE, "30")
    monkeypatch.setenv(RPC_START_HANG_MARKER_VARIABLE, str(tmp_path / "marker"))
    _load_hook().install()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(_HOST_MODULE)


def test_a_long_temporary_directory_is_replaced_for_the_rpc_socket(
    *, stand_in_host: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ansible-core 2.21 puts its RPC socket under the temporary directory (AF_UNIX: 107 bytes)."""
    del stand_in_host
    monkeypatch.setenv(RPC_START_WAIT_SECONDS_VARIABLE, "30")
    monkeypatch.setenv(RPC_START_HANG_MARKER_VARIABLE, str(tmp_path / "marker"))
    long_directory = tmp_path / ("d" * 90)
    long_directory.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(long_directory))
    _load_hook().install()
    _ = importlib.import_module(_HOST_MODULE)
    assert tempfile.gettempdir() == "/tmp"


def test_a_short_temporary_directory_is_left_alone(
    *, stand_in_host: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del stand_in_host
    monkeypatch.setenv(RPC_START_WAIT_SECONDS_VARIABLE, "30")
    monkeypatch.setenv(RPC_START_HANG_MARKER_VARIABLE, str(tmp_path / "marker"))
    monkeypatch.setattr("tempfile.tempdir", "/var/tmp")
    _load_hook().install()
    _ = importlib.import_module(_HOST_MODULE)
    assert tempfile.gettempdir() == "/var/tmp"


def test_the_environment_a_test_runs_ansible_in_carries_the_hook(*, tmp_path: Path) -> None:
    environment = rpc_start_environment(
        base={"PYTHONPATH": "/already/there"}, marker=tmp_path / "marker"
    )
    assert environment["PYTHONPATH"] == f"{RPC_WAIT_DIRECTORY}{os.pathsep}/already/there"
    assert environment[RPC_START_WAIT_SECONDS_VARIABLE] == str(HANG_GUARD_SECONDS)
    assert environment[RPC_START_HANG_MARKER_VARIABLE] == str(tmp_path / "marker")
    assert rpc_start_environment(base={}, marker=tmp_path / "m")["PYTHONPATH"] == str(
        RPC_WAIT_DIRECTORY
    )


def test_every_test_inherits_the_hook_through_its_process_environment() -> None:
    assert os.environ["PYTHONPATH"].split(os.pathsep)[0] == str(RPC_WAIT_DIRECTORY)
    assert os.environ[RPC_START_WAIT_SECONDS_VARIABLE] == str(HANG_GUARD_SECONDS)
    assert RPC_START_HANG_MARKER_VARIABLE in os.environ


def test_the_pinned_ansible_core_loads_the_patient_wait() -> None:
    """The real pinned ansible-core, run the way a play test runs it, gets the replaced event."""
    pin = _pinned_core()
    probe = textwrap.dedent(
        """\
        import ansible._internal._rpc_host as host
        print(type(host._server_ready).__name__)
        """
    )
    done = subprocess.run(
        ["uvx", "--from", pin, "python", "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        timeout=HANG_GUARD_SECONDS,
        env=os.environ | {"ANSIBLE_NOCOWS": "1"},
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "PatientServerReady", done.stdout + done.stderr


def _pinned_core() -> str:
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        (_REPO_ROOT / "justfile").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None
    pin = re.search(r"ansible-core==[0-9][0-9A-Za-z.]*", recipe["body"])
    assert pin is not None
    return pin[0]
