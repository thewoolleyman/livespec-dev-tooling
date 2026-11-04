"""Installed hooks select incident routing before any lefthook prechecks."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from livespec_dev_tooling.install_commit_refuse_hooks import CANONICAL_HOOK_BODY

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn


def test_installed_incident_hook_stops_before_lefthook_and_preserves_real_failure(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    for args in (["init", "-q"], ["config", "livespec.sandboxExempt", "true"]):
        subprocess.run(["git", *args], cwd=repo, env=environment, check=True)
    hook = repo / ".git/hooks/pre-commit"
    hook.write_text(CANONICAL_HOOK_BODY)
    hook.chmod(0o755)
    binary = tmp_path / "bin"
    binary.mkdir()
    (binary / "mise").write_text(
        "#!/bin/sh\n"
        'case "$*" in *livespec_dev_tooling.incident_hook_entry*) exit 23;; esac\n'
        'touch "$NORMAL_PATH"\nexit 0\n'
    )
    (binary / "mise").chmod(0o755)
    normal = tmp_path / "normal-entered"
    completed = subprocess.run(
        [str(hook)],
        cwd=repo,
        env=environment
        | {
            "PATH": str(binary) + os.pathsep + environment["PATH"],
            "EXPEDITED_INCIDENT_RESPONSE": "1",
            "NORMAL_PATH": str(normal),
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 23
    assert not normal.exists()
