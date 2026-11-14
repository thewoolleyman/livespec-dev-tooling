"""Tests for locked-pyright first-run provisioning."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from livespec_dev_tooling import _pyright_warmup as module

__all__: list[str] = []


def test_warmup_runs_the_locked_pyright_install_in_its_given_environment(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The provisioning subprocess receives the caller's directory and environment."""
    _ = (tmp_path / "uv.lock").write_text(
        "[[package]]\n"
        'name = "consumer"\n'
        'source = { editable = "." }\n\n'
        "[package.dev-dependencies]\n"
        'dev = [{ name = "pyright" }]\n',
        encoding="utf-8",
    )
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        module.subprocess,
        "call",
        lambda args, **kwargs: calls.append((args, kwargs)) or 0,
    )
    environment = {"PYRIGHT_CACHE": "isolated"}

    assert "env" in inspect.signature(module.warm_locked_pyright).parameters
    assert module.warm_locked_pyright(cwd=tmp_path, env=environment, already_warmed=False) == 0
    assert calls == [
        (
            ["uv", "run", "--frozen", "pyright", "--version"],
            {"cwd": tmp_path, "env": environment},
        )
    ]
