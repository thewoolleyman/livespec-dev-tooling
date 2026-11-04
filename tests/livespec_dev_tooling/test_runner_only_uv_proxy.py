"""The pool-provided uv shim routes locked artifacts through the files proxy."""

from __future__ import annotations

import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[2]
_SHIM = _REPO / "ansible" / "roles" / "sccache_binary" / "files" / "uv"
_HELD_PATH = "/packages/held/held-1.0.whl"
_MISSING_PATH = "/packages/missing/missing-1.0.whl"


class _Proxy(BaseHTTPRequestHandler):
    """A files proxy that holds exactly one locked artifact."""

    def do_HEAD(self) -> None:  # noqa: N802
        status = 200 if self.path in {"/health", _HELD_PATH} else 404
        self.send_response(status)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        """Keep the test's proxy traffic out of pytest output."""


def _run_shim(*, tmp_path: Path, proxy: str) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    """Run the pool shim against a fake uv that records its lock input."""
    project = tmp_path / "project"
    project.mkdir()
    lock = project / "uv.lock"
    lock.write_text(
        "\n".join(
            (
                f'held = "https://files.pythonhosted.org{_HELD_PATH}"',
                f'missing = "https://files.pythonhosted.org{_MISSING_PATH}"',
                "",
            ),
        ),
        encoding="utf-8",
    )
    shim_bin = tmp_path / "pool-bin"
    shim_bin.mkdir()
    shim = shim_bin / "uv"
    shim.write_bytes(_SHIM.read_bytes())
    shim.chmod(0o755)
    real_bin = tmp_path / "real-bin"
    real_bin.mkdir()
    real_uv = real_bin / "uv"
    real_uv.write_text('#!/bin/sh\ncat uv.lock > "$UV_CAPTURE"\n', encoding="utf-8")
    real_uv.chmod(0o755)
    capture = tmp_path / "seen.lock"
    environment = dict(os.environ)
    environment.update(
        {
            "PATH": f"{shim_bin}{os.pathsep}{real_bin}{os.pathsep}{environment['PATH']}",
            "PYPI_FILES_PROXY": proxy,
            "UV_CAPTURE": str(capture),
        }
    )
    completed = subprocess.run(
        [str(shim), "sync", "--locked"],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, capture, lock


def test_the_pool_uv_shim_routes_only_proxy_held_locked_artifacts(tmp_path: Path) -> None:
    """A job's uv sync uses the host-served source for artifacts it holds."""
    assert _SHIM.is_file(), "the runner-visible uv shim must be installed by the pool role"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Proxy)
    worker = Thread(target=server.serve_forever)
    worker.start()
    try:
        proxy = f"http://127.0.0.1:{server.server_address[1]}"
        completed, capture, lock = _run_shim(tmp_path=tmp_path, proxy=proxy)
    finally:
        server.shutdown()
        worker.join()

    assert completed.returncode == 0, completed.stderr
    captured = capture.read_text(encoding="utf-8")
    assert f"{proxy}{_HELD_PATH}" in captured
    assert f"https://files.pythonhosted.org{_MISSING_PATH}" in captured
    assert f"https://files.pythonhosted.org{_HELD_PATH}" in lock.read_text(
        encoding="utf-8"
    ), "the shim must restore the repository lock after uv exits"
