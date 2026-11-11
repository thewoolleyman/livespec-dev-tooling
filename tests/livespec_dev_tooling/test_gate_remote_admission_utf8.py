"""A multi-byte character split across pipe reads must not end the terminal watch."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from livespec_dev_tooling.gate_remote_admission import _WATCH_TERMINAL_SCRIPT

__all__: list[str] = []


def test_a_utf8_character_split_across_reads_still_yields_the_terminal_event(
    tmp_path: Path,
) -> None:
    """The watch decodes incrementally, so a split character delays but never aborts the verdict."""
    kubectl = tmp_path / "kubectl"
    kubectl.write_text(
        "#!/bin/sh\n"
        'printf \'{"metadata": {"annotations": {"note": "caf\\303\'\n'
        "sleep 0.5\n"
        "printf '\\251\"}}}\\n'\n"
        'printf \'%s\\n\' \'{"status": {"conditions": [{"type": "Complete", "status": "True"}]}}\'\n',
        encoding="utf-8",
    )
    kubectl.chmod(0o755)
    environment = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}

    completed = subprocess.run(
        [
            "sh",
            "-ceu",
            _WATCH_TERMINAL_SCRIPT,
            "await-gate-terminal-watch",
            "gate-widget-7f2qd",
            "gates",
            "60s",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=5,
    )

    assert completed.returncode == 0
    assert '"type": "Complete"' in completed.stdout
