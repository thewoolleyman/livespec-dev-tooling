"""Consumer-tier: the gate Job renderer travels inside the release that drives it.

WHY THIS TIER, AND WHY THIS FILE EXISTS (stop-the-line R283, 2026-10-20). The
claim spans three artifacts that cannot see each other: the Python gate client
that decides which arguments a render carries, the bash renderer that accepts or
refuses them, and the `pyproject.toml` declaration that decides whether the two
reach a consuming host together. A unit test on any one of them passes against a
drifted neighbour, which is exactly how the defect this file closes survived.

Measured: livespec-dev-tooling-44fglo made the client pass `--gate-ref`, and that
client shipped to every consuming repository through releases 1.118.5 / 1.118.6.
A consuming repository carries no renderer of its own, so the client fell back to
a copy on the pushing HOST that only a hand-run `ansible/gates-kubeconfig.yml`
ever updates. Nothing re-converges that playbook, so the host copy stayed at
2026-10-18 and every delegated push from every other fleet repository was refused
with `render-gate-job did not complete ... FATAL: unknown argument --gate-ref`
until an operator noticed and ran the apply by hand.

THE SHAPE OF THE FIX THESE TESTS HOLD. The writer of the arguments and the reader
of them now move as ONE artifact: the wheel force-includes the committed renderer
and the template beside it into the package the client itself lives in, so the
only renderer a consuming repository can reach is the one from its own installed
release. There is no third "converged host copy" case left to go stale — that is
the whole point, and `resolve_renderer`'s fallback naming it is gone.

NOTHING HERE REACHES A CLUSTER, A MIRROR OR A HOST. The consumer is a fixture
tree under `tmp_path`, the client's only door to the world is its
`GateCommandRunner` seam, and the canned runner below answers every git step
itself. The ONE command it really runs is the renderer — a bash script that
contacts nothing by construction — because "the renderer that ships with this
client accepts every argument this client passes" is a claim about what that
script does with that argv, and a stubbed renderer would assert the stub.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from returns.result import Success

import livespec_dev_tooling
from livespec_dev_tooling.gate_remote_delegate import gate_remote_request, resolve_renderer
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The committed renderer tree, and the destination inside the package that the
# wheel copies it to. Both are spelled as the POSIX-relative strings the
# declaration itself uses, so the assertions below compare the declaration to
# itself rather than to a re-spelling of it.
_GATES = "ci-runner/k3s/phase2/gates"
_PACKAGED = "livespec_dev_tooling/gates"
_RENDERER = "render-gate-job.sh"
_TEMPLATE = "gate-job-template.yaml"

# The table whose entries carry a file into the built wheel from outside the
# package directory. Read as TEXT rather than parsed: stdlib `tomllib` lands in
# 3.11 and this repository's floor is 3.10.16, which is why every other
# declaration test here reads `pyproject.toml` the same way.
_FORCE_INCLUDE = "[tool.hatch.build.targets.wheel.force-include]"
_ENTRY = re.compile(r'^"(?P<source>[^"]+)" = "(?P<destination>[^"]+)"$', re.MULTILINE)

# The empty tree's hash — a real git object name, and what the canned
# `rev-parse HEAD^{tree}` below answers with — plus the origin the client
# derives the mirror and the Job's `--repo` from.
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_ORIGIN = "git@github.com:acme/widget.git"


def _wheel_force_include() -> dict[str, str]:
    """The `source -> destination` map the wheel build declares, or an empty map.

    An ABSENT table answers `{}` rather than raising, because the absence is
    precisely the state the first assertion of each test is about: a release
    that ships no renderer beside its client is the regression, and it must
    read as a failed assertion naming the declaration, not as a `KeyError`
    from the harness.
    """
    text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = text.partition(_FORCE_INCLUDE)[2].partition("\n[")[0]
    return {found["source"]: found["destination"] for found in _ENTRY.finditer(block)}


def _an_installed_package(*, root: Path) -> Path:
    """The package tree a consuming repository's venv holds, per the wheel's own map.

    Built by APPLYING the declaration rather than by arranging files by hand, so
    what the renderer test below runs is the file the wheel actually carries.
    Verified against a real `uv build` on 2026-10-20: the wheel holds
    `livespec_dev_tooling/gates/render-gate-job.sh` at mode 0755, byte-identical
    to the committed source, with the template beside it — which is what lets
    the renderer resolve its own template, since it looks for it next to itself.
    """
    for source, destination in _wheel_force_include().items():
        carried = _REPO_ROOT / source
        installed = root / destination
        installed.parent.mkdir(parents=True, exist_ok=True)
        _ = installed.write_bytes(carried.read_bytes())
        installed.chmod(carried.stat().st_mode & 0o777)
    return root


def _a_consumer_repository(*, root: Path) -> Path:
    """A fixture consuming repository — one that carries no renderer of its own.

    That absence is the Given, not an omission: only livespec-dev-tooling holds
    `ci-runner/k3s/phase2/gates/`, so every OTHER repository in the fleet reaches
    the renderer through the fallback this file is about.

    The `.github/workflows/ci.yml` is the one file the renderer reads out of the
    gated tree — its requirement 1, that the gate runs the gated repository's own
    container image rather than a baked-in one — and the `delegated_gate` switch
    is what makes this a repository that delegates at all.
    """
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text(
        "jobs:\n"
        "  one:\n"
        "    runs-on: self-hosted\n"
        "    container:\n"
        "      image: ghcr.io/example/sandbox:python-v1.11.1\n",
        encoding="utf-8",
    )
    _ = (root / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_gate = true\n", encoding="utf-8"
    )
    return root


class _CannedWorldRealRenderer:
    """Every git step canned; the RENDERER really runs.

    The renderer is the subject, so stubbing it would assert the stub. It is a
    bash script that reads a fixture directory and writes YAML to stdout — it
    opens no socket and touches nothing outside its own output.
    """

    def __init__(self, *, renderer: Path) -> None:
        self.renderer = renderer

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (stdin, stream)
        if argv[0] == str(self.renderer):
            ran = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, check=False)
            return Success(
                GateCommandResult(returncode=ran.returncode, stdout=ran.stdout, stderr=ran.stderr)
            )
        answered = f"{_TREE}\n" if "rev-parse" in argv else f"{_ORIGIN}\n"
        return Success(GateCommandResult(returncode=0, stdout=answered, stderr=""))


def test_a_consuming_repository_resolves_the_renderer_inside_its_own_release(
    *, tmp_path: Path
) -> None:
    """The fallback is the package's own copy — never a path only an operator converges.

    Joined by a VALUE and not by a shared expectation: the destination the wheel
    declaration names is the path the client is asserted to resolve, so moving
    one without the other fails here instead of stranding a consumer at a push.
    """
    declared = _wheel_force_include()

    assert declared.get(f"{_GATES}/{_RENDERER}") == f"{_PACKAGED}/{_RENDERER}", declared
    assert declared.get(f"{_GATES}/{_TEMPLATE}") == f"{_PACKAGED}/{_TEMPLATE}", declared

    consumer = _a_consumer_repository(root=tmp_path / "widget")
    installed = Path(livespec_dev_tooling.__file__).resolve().parent.parent

    assert resolve_renderer(repo_root=consumer) == installed / declared[f"{_GATES}/{_RENDERER}"]


def test_the_renderer_the_release_ships_accepts_every_argument_the_client_passes(
    *, tmp_path: Path
) -> None:
    """A delegated push from another repository renders its Job, rather than being refused.

    The regression this replaces produced `render-gate-job did not complete ...
    FATAL: unknown argument --gate-ref` for every consuming repository at once,
    because the renderer reached was older than the client reaching it. Here the
    two are one artifact, so the render completes and the manifest carries the
    per-run ref the client minted — the argument the stale copy rejected.
    """
    packaged = _an_installed_package(root=tmp_path / "site-packages") / _PACKAGED / _RENDERER

    assert packaged.is_file(), "the wheel ships no renderer beside the client that drives it"

    consumer = _a_consumer_repository(root=tmp_path / "widget")
    built = gate_remote_request(
        repo_root=consumer,
        renderer=packaged,
        runner=_CannedWorldRealRenderer(renderer=packaged),
    )

    assert isinstance(built, Success), built
    request = built.unwrap()
    assert request.gate_ref in request.manifest
