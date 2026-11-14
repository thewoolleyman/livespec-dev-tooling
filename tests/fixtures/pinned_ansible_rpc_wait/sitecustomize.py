"""Make ansible-core's in-process RPC server start wait for the hang guard, not five seconds.

Python imports a module named `sitecustomize` at interpreter start when its
directory is on `PYTHONPATH`, so a test that runs the pinned `ansible-core`
through `uvx` with `tests/pinned_ansible.RPC_WAIT_DIRECTORY` on `PYTHONPATH` gets
this file in the ansible controller, and in every child it spawns.

ansible-core 2.21's `LocalNotAProcess.start` (`ansible/_internal/_rpc_host.py`)
submits the RPC server to a worker thread and then runs
`if not _server_ready.wait(5): raise TimeoutError("Local RPC server did not start.")`.
The five seconds are fixed in ansible-core and no configuration changes them; a
CPU-starved host takes longer to schedule that thread (livespec-dev-tooling-biq757).
This file replaces the module's `_server_ready` with an event whose `wait` ignores
the caller's bound and waits for the number of seconds the test named, which is
the repository's hang guard. On expiry it writes the marker file the test reads
and raises an error that names the wait, so the run fails as a hang.

Nothing here imports ansible at interpreter start: a finder on `sys.meta_path`
acts only when ansible-core imports the one module, so a module run by a child
interpreter pays only for installing the finder.

Standalone on purpose: this runs inside the ansible interpreter, where neither
this repository nor its test helpers are importable.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import os
import sys
import tempfile
import threading
from collections.abc import Sequence
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

__all__: list[str] = ["install"]

_HOST_MODULE = "ansible._internal._rpc_host"
_WAIT_SECONDS_VARIABLE = "LIVESPEC_ANSIBLE_RPC_START_WAIT_SECONDS"
_MARKER_VARIABLE = "LIVESPEC_ANSIBLE_RPC_START_HANG_MARKER"
# ansible-core 2.21 opens its RPC host on an AF_UNIX socket at
# `<temporary directory>/pymp-<8 characters>/listener-<8 characters>`; the socket
# path limit is 107 bytes, so the directory part keeps well clear of 107 - 33.
_LONGEST_TEMPORARY_DIRECTORY = 60
_SHORT_TEMPORARY_DIRECTORY = "/tmp"


class PatientServerReady(threading.Event):
    """An event whose `wait` is bounded by the hang guard and reports expiry as a hang."""

    def __init__(self, *, wait_seconds: float, marker: str) -> None:
        super().__init__()
        self._wait_seconds = wait_seconds
        self._marker = marker

    def wait(self, timeout: float | None = None) -> bool:
        del timeout
        if super().wait(self._wait_seconds):
            return True
        _ = Path(self._marker).write_text(
            "the ansible RPC server never started\n", encoding="utf-8"
        )
        message = (
            "HANG: the test was waiting for ansible-core's in-process RPC server to start "
            "(`_server_ready.wait` in `ansible/_internal/_rpc_host.py`), and it had not "
            f"started after {self._wait_seconds:g} s, the repository's hang guard "
            "(tests/hang_guard.py). Local RPC server did not start."
        )
        raise TimeoutError(message)


class _PatchingLoader(importlib.abc.Loader):
    """Runs the real loader, then replaces the executed module's `_server_ready`."""

    def __init__(self, *, real: importlib.abc.Loader, wait_seconds: float, marker: str):
        self._real = real
        self._wait_seconds = wait_seconds
        self._marker = marker

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        return self._real.create_module(spec)

    def exec_module(self, module: ModuleType) -> None:
        self._real.exec_module(module)
        module._server_ready = PatientServerReady(  # type: ignore[attr-defined]  # noqa: SLF001
            wait_seconds=self._wait_seconds, marker=self._marker
        )
        if len(tempfile.gettempdir()) > _LONGEST_TEMPORARY_DIRECTORY:
            tempfile.tempdir = _SHORT_TEMPORARY_DIRECTORY


class _HostFinder(importlib.abc.MetaPathFinder):
    """Hands ansible-core's RPC host module to `_PatchingLoader`; ignores every other name."""

    def __init__(self, *, wait_seconds: float, marker: str) -> None:
        self._wait_seconds = wait_seconds
        self._marker = marker

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        if fullname != _HOST_MODULE:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.loader is None:
            return None
        spec.loader = _PatchingLoader(
            real=spec.loader, wait_seconds=self._wait_seconds, marker=self._marker
        )
        return spec


def install() -> None:
    """Install the finder when the test named a wait and a marker; do nothing otherwise."""
    seconds = os.environ.get(_WAIT_SECONDS_VARIABLE)
    marker = os.environ.get(_MARKER_VARIABLE)
    if not (seconds and marker):
        return
    sys.meta_path.insert(0, _HostFinder(wait_seconds=float(seconds), marker=marker))


install()
