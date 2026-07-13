"""Outside-in test for `livespec_dev_tooling/fabro_image_pin_lockstep.py`.

The Fabro sandbox image is a `base -> python -> python-rust` layer chain
(`docker/fabro-sandbox/<layer>/Dockerfile`); the versions each layer bakes
are declared as `ARG NAME=value` lines. The check reads the ARG lines from
the whole SET of layer Dockerfiles and fails when any image-baked pin
drifts from this repo's own pin sources:

- `ARG UV_VERSION` / `ARG JUST_VERSION` / `ARG LEFTHOOK_VERSION`
  must match `.mise.toml` `[tools]` `uv` / `just` / `lefthook`.
- `ARG PYTHON_VERSION` must match `.python-version`.

Tests invoke the check as a subprocess with `cwd=tmp_path` against
synthetic fixture trees, mirroring the sibling check-test style.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "fabro_image_pin_lockstep.py"

_LAYER_DIR = Path("docker") / "fabro-sandbox"

# Layer fixture set — the obligated ARG pins are SPLIT across layers
# exactly as the real image splits them (JUST/LEFTHOOK in base, UV/PYTHON
# in python). Each layer body carries non-ARG lines (comment, FROM, RUN)
# and a value-less `ARG BASE_IMAGE`/`ARG PYTHON_IMAGE` (the FROM-chain
# arg — deliberately NOT matched by the `ARG NAME=value` parser), plus a
# deliberately un-obligated extra (`NODE_VERSION`, `RUST_VERSION`) with no
# repo-side pin source, so both parser arms are exercised.
_LOCKSTEP_BASE_DOCKERFILE = (
    "# base layer fixture\n"
    "FROM buildpack-deps:noble\n"
    "ARG MISE_VERSION=v2026.2.7\n"
    "ARG JUST_VERSION=1.36.0\n"
    "ARG LEFTHOOK_VERSION=1.13.6\n"
    "ARG NODE_VERSION=26.3.0\n"
    "RUN mise use -g just@${JUST_VERSION}\n"
)
_LOCKSTEP_PYTHON_DOCKERFILE = (
    "# python layer fixture\n"
    "ARG BASE_IMAGE\n"
    "FROM ${BASE_IMAGE}\n"
    "ARG UV_VERSION=0.5.20\n"
    "ARG PYTHON_VERSION=3.10.16\n"
    "RUN uv python install ${PYTHON_VERSION}\n"
)
_LOCKSTEP_PYTHON_RUST_DOCKERFILE = (
    "# python-rust layer fixture\n"
    "ARG PYTHON_IMAGE\n"
    "FROM ${PYTHON_IMAGE}\n"
    "ARG RUST_VERSION=1.92.0\n"
)
_LOCKSTEP_LAYERS = {
    "base": _LOCKSTEP_BASE_DOCKERFILE,
    "python": _LOCKSTEP_PYTHON_DOCKERFILE,
    "python-rust": _LOCKSTEP_PYTHON_RUST_DOCKERFILE,
}

# The `[tools]` table parser mirrors check_tools' fixture coverage:
# preamble comment, stray key outside any section, a non-tools section, an
# inline comment inside `[tools]`, and a malformed line (no quoted
# version) — each closes a distinct parser branch.
_LOCKSTEP_MISE_TOML = (
    "# preamble comment\n"
    "stray-key = 1\n"
    "[other]\n"
    'foo = "bar"\n'
    "[tools]\n"
    "# inline tools comment\n"
    'uv       = "0.5.20"\n'
    'just     = "1.36.0"\n'
    'lefthook = "1.13.6"\n'
    "malformed line without equals\n"
)

_LOCKSTEP_PYTHON_VERSION = "3.10.16\n"


def _write_fixture(
    *,
    root: Path,
    layers: dict[str, str] | None,
    mise_toml: str | None,
    python_version: str | None,
) -> None:
    """Write the layer Dockerfiles + pin sources; `None` omits that input."""
    if layers is not None:
        for layer_name, content in layers.items():
            dockerfile_path = root / _LAYER_DIR / layer_name / "Dockerfile"
            dockerfile_path.parent.mkdir(parents=True, exist_ok=True)
            _ = dockerfile_path.write_text(content, encoding="utf-8")
    if mise_toml is not None:
        _ = (root / ".mise.toml").write_text(mise_toml, encoding="utf-8")
    if python_version is not None:
        _ = (root / ".python-version").write_text(python_version, encoding="utf-8")


def _run_check(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_CHECK)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def test_accepts_image_pins_in_lockstep(*, tmp_path: Path) -> None:
    """All four obligated ARG pins (split across layers) matching passes (exit 0)."""
    _write_fixture(
        root=tmp_path,
        layers=_LOCKSTEP_LAYERS,
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"lockstep fixture should pass; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_missing_layer_dockerfiles(*, tmp_path: Path) -> None:
    """A repo without the layer Dockerfile tree fails and names the layer dir.

    This repo owns the image, so the layers' absence is itself drift (e.g. a
    deletion without retiring the check), not a no-op.
    """
    _write_fixture(
        root=tmp_path,
        layers=None,
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"missing layer Dockerfiles should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "docker/fabro-sandbox" in combined, (
        f"diagnostic should name the layer dir; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_missing_mise_toml_and_python_version(*, tmp_path: Path) -> None:
    """Missing repo-side pin sources fail; both absentees are named."""
    _write_fixture(
        root=tmp_path,
        layers=_LOCKSTEP_LAYERS,
        mise_toml=None,
        python_version=None,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"missing pin sources should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert ".mise.toml" in combined and ".python-version" in combined, (
        f"diagnostic should name BOTH missing pin sources; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_mise_pin_mismatch(*, tmp_path: Path) -> None:
    """An image-baked uv version drifting from .mise.toml fails, naming both values."""
    drifted_python = _LOCKSTEP_PYTHON_DOCKERFILE.replace(
        "ARG UV_VERSION=0.5.20",
        "ARG UV_VERSION=0.5.99",
    )
    _write_fixture(
        root=tmp_path,
        layers={**_LOCKSTEP_LAYERS, "python": drifted_python},
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"uv pin drift should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "UV_VERSION" in combined and "0.5.99" in combined and "0.5.20" in combined, (
        f"diagnostic should carry the ARG name plus both versions; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_python_version_mismatch(*, tmp_path: Path) -> None:
    """An image-baked interpreter drifting from .python-version fails."""
    _write_fixture(
        root=tmp_path,
        layers=_LOCKSTEP_LAYERS,
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version="3.11.1\n",
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"python pin drift should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "PYTHON_VERSION" in combined and "3.11.1" in combined, (
        f"diagnostic should carry the python ARG name and the repo pin; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_layers_missing_obligated_args(*, tmp_path: Path) -> None:
    """Layers lacking LEFTHOOK_VERSION (base) and PYTHON_VERSION (python) fail.

    Covers both missing-ARG arms (the mise-pinned trio loop and the python
    pin) across two different layer files in one fixture.
    """
    base_without_lefthook = "".join(
        line + "\n"
        for line in _LOCKSTEP_BASE_DOCKERFILE.splitlines()
        if not line.startswith("ARG LEFTHOOK_VERSION=")
    )
    python_without_pyver = "".join(
        line + "\n"
        for line in _LOCKSTEP_PYTHON_DOCKERFILE.splitlines()
        if not line.startswith("ARG PYTHON_VERSION=")
    )
    _write_fixture(
        root=tmp_path,
        layers={
            **_LOCKSTEP_LAYERS,
            "base": base_without_lefthook,
            "python": python_without_pyver,
        },
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"missing obligated ARGs should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "LEFTHOOK_VERSION" in combined and "PYTHON_VERSION" in combined, (
        f"diagnostic should name BOTH missing ARGs; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_mise_toml_missing_tool_pin(*, tmp_path: Path) -> None:
    """A .mise.toml [tools] table lacking the `just` pin fails."""
    mise_without_just = _LOCKSTEP_MISE_TOML.replace('just     = "1.36.0"\n', "")
    _write_fixture(
        root=tmp_path,
        layers=_LOCKSTEP_LAYERS,
        mise_toml=mise_without_just,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"missing .mise.toml pin should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "just" in combined, (
        f"diagnostic should name the missing tool pin; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "fabro_image_pin_lockstep_for_import_test",
        str(_CHECK),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"
