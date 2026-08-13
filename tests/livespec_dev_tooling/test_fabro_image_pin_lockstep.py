"""Outside-in test for `livespec_dev_tooling/fabro_image_pin_lockstep.py`.

The Fabro sandbox image is a `base -> python -> {python-agent, python-rust
-> python-rust-agent}` layer tree (`docker/fabro-sandbox/<layer>/Dockerfile`);
the versions each layer bakes are declared as `ARG NAME=value` lines. The
check reads the ARG lines from the whole SET of layer Dockerfiles and fails
when any image-baked pin drifts from this repo's own pin sources:

- `ARG UV_VERSION` / `ARG JUST_VERSION` / `ARG LEFTHOOK_VERSION`
  must match `.mise.toml` `[tools]` `uv` / `just` / `lefthook`.
- `ARG PYTHON_VERSION` must match `.python-version`.
- `ARG GH_VERSION` must match the supported GitHub CLI pin.

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
# and safe local-development defaults for the three FROM-chain ARGs, plus
# deliberately un-obligated extras (`NODE_VERSION`, `RUST_VERSION`) with no
# repo-side pin source, so both parser arms are exercised.
_LOCKSTEP_BASE_DOCKERFILE = (
    "# base layer fixture\n"
    "FROM buildpack-deps:noble\n"
    "ARG MISE_VERSION=v2026.2.7\n"
    "ARG JUST_VERSION=1.36.0\n"
    "ARG LEFTHOOK_VERSION=1.13.6\n"
    "ARG SHELLCHECK_VERSION=0.11.0\n"
    "ARG NODE_VERSION=26.3.0\n"
    "ARG GH_VERSION=2.97.0\n"
    "RUN mkdir -p -m 755 /etc/apt/keyrings \\\n"
    "    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \\\n"
    "        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \\\n"
    "    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \\\n"
    '    && echo "deb [arch=$(dpkg --print-architecture) '
    "signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] "
    'https://cli.github.com/packages stable main" \\\n'
    "        > /etc/apt/sources.list.d/github-cli.list \\\n"
    "    && apt-get update \\\n"
    "    && apt-get install -y --no-install-recommends gh=${GH_VERSION}\n"
    "RUN mise use -g just@${JUST_VERSION} lefthook@${LEFTHOOK_VERSION} \\\n"
    "        shellcheck@${SHELLCHECK_VERSION} node@${NODE_VERSION}\n"
)
_LOCKSTEP_PYTHON_DOCKERFILE = (
    "# python layer fixture\n"
    "ARG BASE_IMAGE=livespec-fabro-sandbox:base-dev\n"
    "FROM ${BASE_IMAGE}\n"
    "ARG UV_VERSION=0.5.20\n"
    "ARG PYTHON_VERSION=3.10.16\n"
    "RUN mise use -g uv@${UV_VERSION} \\\n"
    "    && mise reshim\n"
    "RUN uv python install ${PYTHON_VERSION}\n"
)
_LOCKSTEP_PYTHON_RUST_DOCKERFILE = (
    "# python-rust layer fixture\n"
    "ARG PYTHON_IMAGE=livespec-fabro-sandbox:python-dev\n"
    "FROM ${PYTHON_IMAGE}\n"
    "ARG RUST_VERSION=1.92.0\n"
)
_LOCKSTEP_AGENT_DOCKERFILE = (
    "# agent layer fixture\n"
    "ARG PARENT_IMAGE=livespec-fabro-sandbox:python-dev\n"
    "FROM ${PARENT_IMAGE}\n"
)
_LOCKSTEP_LAYERS = {
    "agent": _LOCKSTEP_AGENT_DOCKERFILE,
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
    'shellcheck = "0.11.0"\n'
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


def test_rejects_drifted_from_chain_default(*, tmp_path: Path) -> None:
    """A FROM-chain ARG must retain its safe local-development default."""
    drifted_agent = _LOCKSTEP_AGENT_DOCKERFILE.replace(
        "ARG PARENT_IMAGE=livespec-fabro-sandbox:python-dev",
        "ARG PARENT_IMAGE=wrong:latest",
    )
    _write_fixture(
        root=tmp_path,
        layers={**_LOCKSTEP_LAYERS, "agent": drifted_agent},
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"FROM-chain default drift should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "PARENT_IMAGE" in combined and "wrong:latest" in combined, (
        f"diagnostic should name the drifted FROM-chain ARG and value; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_declared_tool_absent_from_the_image_args(*, tmp_path: Path) -> None:
    """A `.mise.toml` tool with no baked ARG pin is drift, not an exemption.

    The obligation is DERIVED from the `[tools]` table, so declaring a tool
    without baking it fails rather than silently creating no obligation.
    That silent-no-obligation gap is what let `shellcheck` reach every
    containerized CI job as a per-job network fetch from the releases CDN.
    """
    unbaked = _LOCKSTEP_BASE_DOCKERFILE.replace("ARG SHELLCHECK_VERSION=0.11.0\n", "")
    _write_fixture(
        root=tmp_path,
        layers={**_LOCKSTEP_LAYERS, "base": unbaked},
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"a declared-but-unbaked tool should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "SHELLCHECK_VERSION" in combined, (
        f"diagnostic should name the unbaked tool's obligated ARG; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_declared_tool_never_installed_by_mise(*, tmp_path: Path) -> None:
    """An ARG pin alone does not bake the tool — it must be `mise use -g`-installed.

    Without this direction a tool could carry a correct, in-lockstep ARG and
    still be absent from the image, which is exactly the un-cached state the
    ARG is meant to guarantee against.
    """
    declared_but_uninstalled = _LOCKSTEP_BASE_DOCKERFILE.replace(
        " shellcheck@${SHELLCHECK_VERSION}", ""
    )
    _write_fixture(
        root=tmp_path,
        layers={**_LOCKSTEP_LAYERS, "base": declared_but_uninstalled},
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"a declared tool never installed by mise should fail; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "shellcheck" in combined, (
        f"diagnostic should name the uninstalled tool; "
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


def test_rejects_unsupported_gh_version(*, tmp_path: Path) -> None:
    """An image-baked GitHub CLI version drifting from the supported pin fails."""
    base_with_old_gh = _LOCKSTEP_BASE_DOCKERFILE.replace(
        "ARG GH_VERSION=2.97.0",
        "ARG GH_VERSION=2.46.0",
    )
    _write_fixture(
        root=tmp_path,
        layers={**_LOCKSTEP_LAYERS, "base": base_with_old_gh},
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"unsupported gh pin should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "GH_VERSION" in combined and "2.46.0" in combined and "2.97.0" in combined, (
        f"diagnostic should carry the gh ARG name plus both versions; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_gh_without_signed_cli_apt_repository(*, tmp_path: Path) -> None:
    """The GitHub CLI must come from the official signed cli.github.com apt source."""
    base_without_signed_repo = _LOCKSTEP_BASE_DOCKERFILE.replace(
        "signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] "
        "https://cli.github.com/packages stable main",
        "https://example.invalid/packages stable main",
    )
    _write_fixture(
        root=tmp_path,
        layers={**_LOCKSTEP_LAYERS, "base": base_without_signed_repo},
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"unsigned gh apt source should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "cli.github.com" in combined and "signed-by" in combined, (
        f"diagnostic should name the signed GitHub CLI apt source; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_gh_apt_install_without_exact_package_pin(*, tmp_path: Path) -> None:
    """Installing bare `gh` from apt is drift-prone; the package pin is exact."""
    base_without_package_pin = _LOCKSTEP_BASE_DOCKERFILE.replace(
        "gh=${GH_VERSION}",
        "gh",
    )
    _write_fixture(
        root=tmp_path,
        layers={**_LOCKSTEP_LAYERS, "base": base_without_package_pin},
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"unpinned apt gh install should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "gh=${GH_VERSION}" in combined, (
        f"diagnostic should require the exact gh package pin; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_gh_installed_by_mise(*, tmp_path: Path) -> None:
    """The Fabro image must not route gh through mise's aqua backend."""
    base_with_mise_gh = _LOCKSTEP_BASE_DOCKERFILE.replace(
        "RUN mise use -g just@${JUST_VERSION}",
        "RUN mise use -g just@${JUST_VERSION} gh@${GH_VERSION}",
    )
    _write_fixture(
        root=tmp_path,
        layers={**_LOCKSTEP_LAYERS, "base": base_with_mise_gh},
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path)

    assert result.returncode != 0, (
        f"mise-managed gh should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "mise" in combined and "gh" in combined, (
        f"diagnostic should reject mise-managed gh; "
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
