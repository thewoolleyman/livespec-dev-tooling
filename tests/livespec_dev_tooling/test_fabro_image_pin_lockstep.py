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

Tests invoke the check IN-PROCESS (`monkeypatch.chdir(tmp_path)` +
`capsys` + `rc = main()`) against synthetic fixture trees, mirroring the
sibling check-test style: no `COVERAGE_PROCESS_START`-instrumented child,
no `.coverage.*` race under the parallel dispatcher, and materially
faster. `main()` reads `Path.cwd()`, so the monkeypatched cwd anchors the
fixture, and the assertion targets are unchanged — the int exit code plus
the structlog stderr text, now read off `capsys` instead of
`CompletedProcess`.

Branch parity with the retired spawn: both ARG-parser arms (obligated and
un-obligated names), every missing-pin-source arm, and the drift and
lockstep exits are driven by the same fixtures as before. The two lines
the child process reached that an in-process call cannot are the module's
vendored-path guard (`sys.path.insert`) and its
`if __name__ == "__main__": raise SystemExit(main())` line; both are
already excluded repo-wide by the PRE-EXISTING `exclude_also` patterns in
`[tool.coverage.report]`, so neither was ever measured here and no new
exclusion is introduced.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

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
    "ARG GH_VERSION=2.102.0\n"
    "ARG GH_SHA256=bb766f710eef8ede859c18578c72c327597cd4c8a85b06001b1f3843c6019386\n"
    "RUN curl -fsSL -o /tmp/gh.tgz \\\n"
    '        "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh.tar.gz" \\\n'
    '    && echo "${GH_SHA256}  /tmp/gh.tgz" | sha256sum -c -\n'
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
_LOCKSTEP_PYTHON_RUST_FUZZ_DOCKERFILE = (
    "# python-rust-fuzz layer fixture (CI-only leaf; un-obligated extra pin)\n"
    "ARG PYTHON_RUST_IMAGE=livespec-fabro-sandbox:python-rust-dev\n"
    "FROM ${PYTHON_RUST_IMAGE}\n"
    "ARG CARGO_FUZZ_VERSION=0.13.2\n"
)
_LOCKSTEP_LAYERS = {
    "agent": _LOCKSTEP_AGENT_DOCKERFILE,
    "base": _LOCKSTEP_BASE_DOCKERFILE,
    "python": _LOCKSTEP_PYTHON_DOCKERFILE,
    "python-rust": _LOCKSTEP_PYTHON_RUST_DOCKERFILE,
    "python-rust-fuzz": _LOCKSTEP_PYTHON_RUST_FUZZ_DOCKERFILE,
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

# The factory reach check's SHIPPED copy of the fleet sandbox image pin, and the
# workflow pin it has to equal (work-item livespec-dev-tooling-jvnqwv). The
# shipped file exists because that check is a converge artifact: it runs from an
# installed tree on a pool node, where `.github/workflows/ci.yml` is not present,
# so the image it renders cannot be read out of the workflow. A second copy of a
# pin the release fan-out rewrites is a drift source by construction, and this
# check is the only thing standing between the two.
_FACTORY_REACH_PIN_PATH = Path("ci-runner") / "k3s" / "phase2" / "factory"
_FACTORY_REACH_PIN_NAME = "factory-reach-image.env"
_CI_WORKFLOW_PATH = Path(".github") / "workflows" / "ci.yml"
_LOCKSTEP_SANDBOX_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v1.42.0"
_LOCKSTEP_FACTORY_REACH_PIN = (
    "# fixture pin file\n" "\n" f"FACTORY_REACH_SANDBOX_IMAGE={_LOCKSTEP_SANDBOX_IMAGE}\n"
)
# TWO `container:` blocks naming the SAME image, because that is the real shape:
# GitHub Actions has no workflow-level `container:`, so this repository's ci.yml
# repeats the block in every containerized job. The reader must therefore
# de-duplicate rather than count lines.
_LOCKSTEP_CI_WORKFLOW = (
    "name: ci fixture\n"
    "jobs:\n"
    "  check-python:\n"
    "    runs-on: ubuntu-latest\n"
    "    container:\n"
    f"      image: {_LOCKSTEP_SANDBOX_IMAGE}\n"
    "    steps:\n"
    "      - uses: actions/checkout@v5\n"
    "  gate:\n"
    "    runs-on: ubuntu-latest\n"
    "    container:\n"
    f"      image: {_LOCKSTEP_SANDBOX_IMAGE}\n"
)


def _write_fixture(
    *,
    root: Path,
    layers: dict[str, str] | None,
    mise_toml: str | None,
    python_version: str | None,
    factory_reach_pin: str | None = _LOCKSTEP_FACTORY_REACH_PIN,
    ci_workflow: str | None = _LOCKSTEP_CI_WORKFLOW,
) -> None:
    """Write the layer Dockerfiles + pin sources; `None` omits that input.

    The two factory-reach inputs default to an IN-LOCKSTEP pair, so every case
    that is about the image's own ARG pins keeps exercising only what it names.
    """
    if layers is not None:
        for layer_name, content in layers.items():
            dockerfile_path = root / _LAYER_DIR / layer_name / "Dockerfile"
            dockerfile_path.parent.mkdir(parents=True, exist_ok=True)
            _ = dockerfile_path.write_text(content, encoding="utf-8")
    if mise_toml is not None:
        _ = (root / ".mise.toml").write_text(mise_toml, encoding="utf-8")
    if python_version is not None:
        _ = (root / ".python-version").write_text(python_version, encoding="utf-8")
    if factory_reach_pin is not None:
        pin_path = root / _FACTORY_REACH_PIN_PATH / _FACTORY_REACH_PIN_NAME
        pin_path.parent.mkdir(parents=True, exist_ok=True)
        _ = pin_path.write_text(factory_reach_pin, encoding="utf-8")
    if ci_workflow is not None:
        workflow_path = root / _CI_WORKFLOW_PATH
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        _ = workflow_path.write_text(ci_workflow, encoding="utf-8")


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling...`) so the test
    exercises the on-disk module the Red→Green hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "fabro_image_pin_lockstep_under_test", str(_CHECK)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_check_module()


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd` and capture output."""
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def test_accepts_image_pins_in_lockstep(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """All four obligated ARG pins (split across layers) matching passes (exit 0)."""
    _write_fixture(
        root=tmp_path,
        layers=_LOCKSTEP_LAYERS,
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"lockstep fixture should pass; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_drifted_from_chain_default(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"FROM-chain default drift should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "PARENT_IMAGE" in combined and "wrong:latest" in combined, (
        f"diagnostic should name the drifted FROM-chain ARG and value; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_declared_tool_absent_from_the_image_args(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"a declared-but-unbaked tool should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "SHELLCHECK_VERSION" in combined, (
        f"diagnostic should name the unbaked tool's obligated ARG; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_declared_tool_never_installed_by_mise(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

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


def test_rejects_missing_layer_dockerfiles(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"missing layer Dockerfiles should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "docker/fabro-sandbox" in combined, (
        f"diagnostic should name the layer dir; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_missing_mise_toml_and_python_version(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing repo-side pin sources fail; both absentees are named."""
    _write_fixture(
        root=tmp_path,
        layers=_LOCKSTEP_LAYERS,
        mise_toml=None,
        python_version=None,
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"missing pin sources should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert ".mise.toml" in combined and ".python-version" in combined, (
        f"diagnostic should name BOTH missing pin sources; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_mise_pin_mismatch(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"uv pin drift should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "UV_VERSION" in combined and "0.5.99" in combined and "0.5.20" in combined, (
        f"diagnostic should carry the ARG name plus both versions; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_python_version_mismatch(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An image-baked interpreter drifting from .python-version fails."""
    _write_fixture(
        root=tmp_path,
        layers=_LOCKSTEP_LAYERS,
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version="3.11.1\n",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"python pin drift should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "PYTHON_VERSION" in combined and "3.11.1" in combined, (
        f"diagnostic should carry the python ARG name and the repo pin; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_unsupported_gh_version(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An image-baked GitHub CLI version drifting from the supported pin fails."""
    base_with_old_gh = _LOCKSTEP_BASE_DOCKERFILE.replace(
        "ARG GH_VERSION=2.102.0",
        "ARG GH_VERSION=2.46.0",
    )
    _write_fixture(
        root=tmp_path,
        layers={**_LOCKSTEP_LAYERS, "base": base_with_old_gh},
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"unsupported gh pin should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "GH_VERSION" in combined and "2.46.0" in combined and "2.102.0" in combined, (
        f"diagnostic should carry the gh ARG name plus both versions; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_gh_not_downloaded_from_its_pinned_release(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """gh must come from its pinned GitHub release, not a rotting apt pin."""
    base_without_release = _LOCKSTEP_BASE_DOCKERFILE.replace(
        "https://github.com/cli/cli/releases/download/v${GH_VERSION}/",
        "https://example.invalid/",
    )
    _write_fixture(
        root=tmp_path,
        layers={**_LOCKSTEP_LAYERS, "base": base_without_release},
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"non-release gh source should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "github.com/cli/cli/releases" in combined, (
        f"diagnostic should name the pinned release source; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_gh_without_pinned_sha256_arg(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gh tarball checksum must be a pinned ARG, not an inline or absent value."""
    base_without_arg = _LOCKSTEP_BASE_DOCKERFILE.replace(
        "ARG GH_SHA256=bb766f710eef8ede859c18578c72c327597cd4c8a85b06001b1f3843c6019386\n",
        "",
    )
    _write_fixture(
        root=tmp_path,
        layers={**_LOCKSTEP_LAYERS, "base": base_without_arg},
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"missing GH_SHA256 pin should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "must pin GH_SHA256" in combined, (
        f"diagnostic should require the GH_SHA256 pin; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_gh_install_without_checksum_verification(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gh tarball must be verified against the pinned GH_SHA256."""
    base_without_verify = _LOCKSTEP_BASE_DOCKERFILE.replace("sha256sum -c -", "true")
    _write_fixture(
        root=tmp_path,
        layers={**_LOCKSTEP_LAYERS, "base": base_without_verify},
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"unverified gh install should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "sha256sum" in combined and "GH_SHA256" in combined, (
        f"diagnostic should require checksum verification; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_gh_installed_by_mise(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"mise-managed gh should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "mise" in combined and "gh" in combined, (
        f"diagnostic should reject mise-managed gh; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_layers_missing_obligated_args(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"missing obligated ARGs should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "LEFTHOOK_VERSION" in combined and "PYTHON_VERSION" in combined, (
        f"diagnostic should name BOTH missing ARGs; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_mise_toml_missing_tool_pin(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A .mise.toml [tools] table lacking the `just` pin fails."""
    mise_without_just = _LOCKSTEP_MISE_TOML.replace('just     = "1.36.0"\n', "")
    _write_fixture(
        root=tmp_path,
        layers=_LOCKSTEP_LAYERS,
        mise_toml=mise_without_just,
        python_version=_LOCKSTEP_PYTHON_VERSION,
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"missing .mise.toml pin should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "just" in combined, (
        f"diagnostic should name the missing tool pin; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_a_shipped_factory_reach_pin_drifted_from_the_workflow(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The shipped factory-reach pin must equal the workflow's sandbox image pin.

    The failure the obligation exists for: a release fan-out rewrites the
    `container:` pin in `.github/workflows/ci.yml` and leaves the copy that
    SHIPS to the pool node behind. Nothing on the node can notice — the check
    renders a Job, the Job pulls the superseded image, and it reports green for
    a toolchain no dispatch runs. So the drift has to redden here.
    """
    _write_fixture(
        root=tmp_path,
        layers=_LOCKSTEP_LAYERS,
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
        factory_reach_pin=_LOCKSTEP_FACTORY_REACH_PIN.replace(
            _LOCKSTEP_SANDBOX_IMAGE,
            "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v1.41.0",
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"a shipped factory-reach pin drifted from the workflow pin should fail; got "
        f"returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "python-v1.41.0" in combined and _LOCKSTEP_SANDBOX_IMAGE in combined, (
        f"diagnostic should name BOTH references, so the operator sees which way to bump; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_a_shipped_pin_file_naming_no_sandbox_image(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pin file with no `FACTORY_REACH_SANDBOX_IMAGE=` line is drift, not a pass.

    The file is the ONLY pin present on a pool node, so a copy that names
    nothing leaves the reach check unable to render a Job at all — and an
    obligation that treated "no value" as "no disagreement" would pass exactly
    the state nothing else catches.
    """
    _write_fixture(
        root=tmp_path,
        layers=_LOCKSTEP_LAYERS,
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
        factory_reach_pin="# a pin file that pins nothing\n",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"a shipped pin file naming no image should fail; got "
        f"returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert _FACTORY_REACH_PIN_NAME in combined, (
        f"diagnostic should name the pin file; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_a_workflow_declaring_two_distinct_container_images(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two distinct workflow container images is a refusal, never a pick.

    Which of them the shipped pin is supposed to equal is then a real question,
    and answering it by picking one would silently bless whichever happened to
    sort first.
    """
    _write_fixture(
        root=tmp_path,
        layers=_LOCKSTEP_LAYERS,
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
        ci_workflow=_LOCKSTEP_CI_WORKFLOW.replace(
            f"  gate:\n    runs-on: ubuntu-latest\n    container:\n"
            f"      image: {_LOCKSTEP_SANDBOX_IMAGE}\n",
            "  gate:\n    runs-on: ubuntu-latest\n    container:\n"
            "      image: ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-v1.42.0\n",
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"two distinct workflow container images should fail; got "
        f"returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "ci.yml" in combined, (
        f"diagnostic should name the workflow whose pins disagree; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rejects_missing_factory_reach_pin_and_ci_workflow(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both halves of the factory-reach obligation are REQUIRED inputs.

    Treating either absence as "nothing to compare" would make the obligation
    disappear the moment a file was renamed or deleted — the laxer-by-accident
    shape every lockstep arm here is written to avoid.
    """
    _write_fixture(
        root=tmp_path,
        layers=_LOCKSTEP_LAYERS,
        mise_toml=_LOCKSTEP_MISE_TOML,
        python_version=_LOCKSTEP_PYTHON_VERSION,
        factory_reach_pin=None,
        ci_workflow=None,
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"missing factory-reach inputs should fail; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert _FACTORY_REACH_PIN_NAME in combined and "ci.yml" in combined, (
        f"diagnostic should name BOTH missing inputs; "
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
