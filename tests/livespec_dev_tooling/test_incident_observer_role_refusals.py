"""The incident_observer renderer refuses an installation it cannot import.

livespec-dev-tooling-w7n3ad. `render_released_installation.py` runs with the
installation's own interpreter. A distribution can be recorded as installed
while its package does not import (a broken or partial install), and a manifest
rendered from anything else would describe a different tree than the one the
service authenticates at start, so the renderer refuses before printing one.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-w7n3ad
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = (
    _REPO_ROOT
    / "ansible"
    / "roles"
    / "incident_observer"
    / "files"
    / "render_released_installation.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_released_installation", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: a dataclass under `from __future__ import
    # annotations` resolves its field types through sys.modules.
    sys.modules[spec.name] = module
    # No bytecode beside the script: a `.pyc` inside the role tree is a binary
    # file `check-ansible-hostname-free` cannot decode as UTF-8.
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def test_main_refuses_when_the_installed_package_does_not_import(
    tmp_path, monkeypatch, capsys
) -> None:
    module = _load()
    monkeypatch.setattr(module.importlib.metadata, "version", lambda _: "1.2.3")
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda _: None)

    exit_code = module.main(
        [
            "--release",
            "v1.2.3",
            "--revision",
            "b" * 40,
            "--reader-release",
            "v0.290.0",
            "--reader-script",
            str(tmp_path / "incident_authority.py"),
            "--config",
            str(tmp_path / "controller.json"),
            "--required-job",
            "ci-green",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "refused: livespec_dev_tooling is not importable here" in captured.err
