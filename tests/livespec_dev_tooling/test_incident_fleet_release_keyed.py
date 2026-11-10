"""A self-serving checkout's build is keyed to a release and judged per row surface.

These tests read real git repositories: tag ancestry, the files changed since a release
and each file's bytes come from git itself. Only the remote (`ls-remote`) and the
blobless workflow clone are answered by the test, because both would reach the network.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling._incident_fleet_capabilities import SURFACE_CAPABILITY
from livespec_dev_tooling._incident_fleet_command import render_report, run_fleet_audit
from livespec_dev_tooling._incident_fleet_gate_reader import read_gate_readers
from livespec_dev_tooling._incident_fleet_release_keyed import ServingReading, claim_reason
from livespec_dev_tooling._incident_fleet_surface_files import SURFACE_ROOTS, surface_files
from livespec_dev_tooling._incident_fleet_template_reader import read_templates
from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence
from livespec_dev_tooling.fleet._invocation_failure import BINARY_ABSENT, InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult
from livespec_dev_tooling.incident_fleet_audit import SURFACES
from livespec_dev_tooling.incident_fleet_host import HostProbe
from livespec_dev_tooling.incident_fleet_runner import scrubbed_runner

REPO_ROOT = Path(__file__).resolve().parents[2]
_ISOLATED = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}
CI = "jobs:\n  gate:\n    uses: ./.github/workflows/reusable-check-matrix.yml\n"
REPLAY = "livespec_dev_tooling/checks/red_green_replay.py"
HELPER = "livespec_dev_tooling/replay_helper.py"
COMMIT_MSG = "Commit-msg and TDD"
PRE_PUSH = "Pre-push"


class _Repo:
    """A real git repository standing in for a consumer's clone on this host.

    It holds every surface root, so every surface reads; the Commit-msg surface's root
    imports one helper module, which is therefore part of that surface only.
    """

    def __init__(self, *, path: Path) -> None:
        self.path = path
        path.mkdir(parents=True)
        _ = self.git("init", "-q", "-b", "master")
        for root in {root for roots in SURFACE_ROOTS.values() for root in roots}:
            self.write(root, "")
        self.write(".github/workflows/ci.yml", CI)
        self.write(REPLAY, "from livespec_dev_tooling import replay_helper\n")
        self.write(HELPER, "HELP = 1\n")
        self.write("config/incident-fleet-evidence.json", '{"schema": 1, "evidence": []}\n')
        _ = self.commit("first")

    def git(self, *args: str) -> str:
        environment = {"PATH": os.environ["PATH"], "HOME": str(self.path), **_ISOLATED}
        done = subprocess.run(
            ["git", "-C", str(self.path), *args],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        return done.stdout.strip()

    def write(self, name: str, text: str) -> None:
        target = self.path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(text, encoding="utf-8")

    def commit(self, message: str, files: dict[str, str] | None = None) -> str:
        for name, text in (files or {}).items():
            self.write(name, text)
        _ = self.git("add", "--", *(files or {"."}))
        _ = self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def tag(self, name: str) -> None:
        _ = self.git("tag", name)


@dataclass
class _Host:
    """The real local git for the clones; the remote and the workflow clone are answered."""

    root: Path
    remote: dict[str, str]
    fail: Callable[[list[str]], bool] = lambda _args: False

    def run(self, *, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        if self.fail(args):
            return IOFailure(
                InvocationNotPerformed(argv=tuple(args), kind=BINARY_ABSENT, detail="x")
            )
        if args[1] == "ls-remote":
            rows = "".join(f"{sha}\t{ref}\n" for ref, sha in self.remote.items() if ref in args[3:])
            return IOSuccess(CommandResult(returncode=0, stdout=rows, stderr=""))
        if args[1] == "-C" and Path(args[2]).is_relative_to(self.root):
            return scrubbed_runner(args=args, cwd=cwd)
        listing = ".github/workflows/ci.yml\0"
        return IOSuccess(
            CommandResult(returncode=0, stdout=listing if "ls-tree" in args else CI, stderr="")
        )

    def probe(self) -> HostProbe:
        return HostProbe(
            clones_root=self.root, proc_root=Path("/proc"), home=self.root, run=self.run
        )


def _own_install(repo: _Repo) -> None:
    dist = repo.path / ".venv/lib/python3.12/site-packages/livespec_dev_tooling-1.0.0.dist-info"
    dist.mkdir(parents=True)
    record = {"url": repo.path.as_uri(), "dir_info": {"editable": True}}
    _ = (dist / "direct_url.json").write_text(json.dumps(record), encoding="utf-8")


@pytest.fixture
def tooling(tmp_path: Path) -> _Repo:
    """This library's primary checkout: an editable install of its own source.

    `v1.0.0` and `v1.1.0` are releases. HEAD is a later commit touching a package module
    that no surface reaches, plus the committed claims. The `.venv` and a foreign state
    file are untracked, as they are in the real primary checkout.
    """
    repo = _Repo(path=tmp_path / "tooling")
    repo.tag("v1.0.0")
    _ = repo.commit("feature", {HELPER: "HELP = 2\n"})
    repo.tag("v1.1.0")
    _ = repo.commit(
        "claims",
        {"livespec_dev_tooling/unrelated.py": "X = 1\n", "config/claims.json": "{}\n"},
    )
    _own_install(repo)
    repo.write(".overseer-state", "foreign\n")
    return repo


def _host(repo: _Repo, **extra: str) -> _Host:
    tags = {
        f"refs/tags/{tag}": repo.git("rev-parse", f"{tag}^{{commit}}")
        for tag in repo.git("tag", "--list").split()
    }
    return _Host(root=repo.path.parent, remote={**tags, **extra})


def _gate(repo: _Repo, host: _Host | None = None) -> ServingReading:
    reading = read_gate_readers(probe=(host or _host(repo)).probe(), repository="example/tooling")
    assert isinstance(reading, ServingReading)
    return reading


# --- the audit over one consumer whose gate readers serve its own checkout ---
MANIFEST = '{"owner": "example", "fleet": [{"repo": "tooling", "class": "enforcement-suite"}]}'
DIGEST = hashlib.sha256(MANIFEST.encode()).hexdigest()
OTHER = "v9.0.0"


def _claims(*, gate_release: str) -> tuple[CapabilityEvidence, ...]:
    return tuple(
        CapabilityEvidence(
            repository="example/tooling",
            surface=surface,
            disposition="implemented",
            manifest_sha256=DIGEST,
            source_path=REPLAY,
            release_build=(
                gate_release if SURFACE_CAPABILITY[surface] == "gate-readers" else OTHER
            ),
            serving_build="",
            proof_ref="independent-host-proof:receipt-1",
            owner="controller-owner",
            incident_item="incident-1",
            cumulative_scope="b" * 64,
            normal_factory_proof="factory:scope",
        )
        for surface in SURFACES
    )


def _audit(repo: _Repo, *, gate_release: str, host: _Host | None = None) -> tuple[str, ...]:
    probe = (host or _host(repo)).probe()

    def read(*, repository: str, capability: str) -> str | ServingReading | None:
        if capability == "gate-readers":
            return read_gate_readers(probe=probe, repository=repository)
        return OTHER

    manifests = iter((MANIFEST, MANIFEST))
    report = run_fleet_audit(
        read_manifest=lambda: next(manifests, None),
        claims=_claims(gate_release=gate_release),
        read_serving=read,
    )
    return render_report(report=report)


def _finding(surface: str, reason: str) -> str:
    return f"finding\texample/tooling: {surface}: {reason}"


def test_a_claim_naming_the_newest_release_ancestor_classifies_and_prints_it_with_head(
    tooling: _Repo,
) -> None:
    head = tooling.git("rev-parse", "HEAD")
    reading = _gate(tooling)
    lines = _audit(tooling, gate_release="v1.1.0")
    matched = f"release v1.1.0 at HEAD {head}"
    assert (reading.build, reading.head, reading.detail) == ("v1.1.0", head, matched)
    assert f"serving\texample/tooling\tgate-readers\tv1.1.0\t{matched}" in lines
    assert f"row\texample/tooling\t{PRE_PUSH}\timplemented\tv1.1.0\t{matched}" in lines
    assert f"row\texample/tooling\t{COMMIT_MSG}\timplemented\tv1.1.0\t{matched}" in lines
    assert "ready\texample/tooling" in lines


def test_commits_touching_only_files_outside_a_surface_leave_its_row_classified(
    tooling: _Repo,
) -> None:
    _ = tooling.commit("outside", {"livespec_dev_tooling/elsewhere.py": "Y = 1\n"})
    reading = _gate(tooling)
    assert all(reading.build_for(surface=s) == "v1.1.0" for s, _ in reading.surfaces)
    assert "ready\texample/tooling" in _audit(tooling, gate_release="v1.1.0")


def test_a_changed_surface_file_unclassifies_only_its_own_row_naming_the_path(
    tooling: _Repo,
) -> None:
    _ = tooling.commit("helper", {HELPER: "HELP = 3\n"})
    lines = _audit(tooling, gate_release="v1.1.0")
    reason = f"surface files changed since release v1.1.0: {HELPER}"
    assert f"row\texample/tooling\t{COMMIT_MSG}\tunclassified\t-" in lines
    assert _finding(COMMIT_MSG, reason) in lines
    assert any(line.startswith(f"row\texample/tooling\t{PRE_PUSH}\timplemented") for line in lines)
    assert "ready\t-" in lines


def test_a_surface_root_absent_at_head_unclassifies_its_row(tooling: _Repo) -> None:
    _ = tooling.git("rm", "-q", REPLAY)
    _ = tooling.git("commit", "-q", "-m", "drop")
    reason = f"surface files absent at the serving commit: {REPLAY}"
    assert _finding(COMMIT_MSG, reason) in _audit(tooling, gate_release="v1.1.0")


def test_no_release_ancestor_leaves_the_rows_unclassified_naming_the_commit(
    tmp_path: Path,
) -> None:
    repo = _Repo(path=tmp_path / "tooling")
    _ = repo.git("checkout", "-q", "-b", "side")
    _ = repo.commit("side", {"livespec_dev_tooling/side.py": "SIDE = 1\n"})
    repo.tag("v2.0.0")
    _ = repo.git("checkout", "-q", "master")
    head = repo.commit("nightly", {"config/note.txt": "x\n"})
    repo.tag("nightly")
    _own_install(repo)
    reason = f"no release tag is an ancestor of {head}"
    assert _gate(repo) == ServingReading(build="", detail=reason, head=head, releases=frozenset())
    assert _finding(COMMIT_MSG, reason) in _audit(repo, gate_release="v2.0.0")


def test_a_claim_naming_a_release_that_is_not_the_newest_ancestor_does_not_classify(
    tooling: _Repo,
) -> None:
    head = tooling.git("rev-parse", "HEAD")
    _ = tooling.git("checkout", "-q", "-b", "side", "v1.0.0")
    _ = tooling.commit("side", {"livespec_dev_tooling/side.py": "SIDE = 1\n"})
    tooling.tag("v2.0.0")
    _ = tooling.git("checkout", "-q", "master")
    foreign = _audit(tooling, gate_release="v2.0.0")
    older = _audit(tooling, gate_release="v1.0.0")
    assert f"row\texample/tooling\t{PRE_PUSH}\tunclassified\tv1.1.0" in foreign
    assert _finding(PRE_PUSH, f"claimed release v2.0.0 is not an ancestor of HEAD {head}") in (
        foreign
    )
    older_reason = (
        f"claimed release v1.0.0 is not v1.1.0, the newest release ancestor of HEAD {head}"
    )
    assert _finding(PRE_PUSH, older_reason) in older


def test_untracked_files_do_not_dirty_the_checkout_but_a_tracked_modification_does(
    tooling: _Repo,
) -> None:
    assert (tooling.path / ".overseer-state").is_file()
    assert _gate(tooling).build == "v1.1.0"
    head = tooling.git("rev-parse", "HEAD")
    tooling.write(HELPER, "HELP = 4\n")
    reason = f"tracked modifications at HEAD {head}:  M {HELPER}"
    assert _gate(tooling) == ServingReading(build="", detail=reason, head=head)
    assert _finding(PRE_PUSH, reason) in _audit(tooling, gate_release="v1.1.0")


@pytest.mark.parametrize(
    ("fail", "remote", "detail"),
    [
        (
            lambda _args: False,
            {"refs/tags/v1.1.0": "0" * 40},
            "release v1.1.0 is not confirmed on the remote at the commit it names here",
        ),
        (
            lambda args: "ls-remote" in args,
            {},
            "release v1.1.0 is not confirmed on the remote at the commit it names here",
        ),
        (
            lambda args: "diff" in args,
            {},
            "the files changed between release v1.1.0 and {head} cannot be read",
        ),
    ],
)
def test_a_release_the_remote_or_the_clone_cannot_confirm_does_not_serve(
    tooling: _Repo,
    fail: Callable[[list[str]], bool],
    remote: dict[str, str],
    detail: str,
) -> None:
    host = _host(tooling, **remote)
    host.fail = fail
    head = tooling.git("rev-parse", "HEAD")
    reading = _gate(tooling, host)
    assert (reading.build, reading.detail) == ("", detail.format(head=head))


def test_a_reason_is_named_only_where_a_claim_cannot_classify_against_what_was_read() -> None:
    head = "c" * 40
    keyed = ServingReading(
        build="v1.1.0",
        head=head,
        releases=frozenset({"v1.1.0"}),
        surfaces=((PRE_PUSH, ""),),
    )
    commit_read = ServingReading(build="d" * 40)
    assert [
        claim_reason(reading=keyed, surface=PRE_PUSH, claimed="v1.1.0"),
        claim_reason(reading=keyed, surface="Elsewhere", claimed="v1.1.0"),
        claim_reason(reading=commit_read, surface=PRE_PUSH, claimed="e" * 40),
        keyed.build_for(surface="Elsewhere"),
        commit_read.build_for(surface=PRE_PUSH),
    ] == ["", "no surface file set is defined for this surface", "", "", "d" * 40]


# --- templates served from a consumer's own default branch ---
def _templates(repo: _Repo, *, head: str) -> ServingReading:
    reading = read_templates(
        probe=_host(repo, HEAD=head).probe(),
        repository="thewoolleyman/livespec-dev-tooling",
    )
    assert isinstance(reading, ServingReading)
    return reading


@pytest.fixture
def library(tmp_path: Path) -> _Repo:
    repo = _Repo(path=tmp_path / "livespec-dev-tooling")
    repo.tag("v1.1.0")
    return repo


def test_local_templates_are_keyed_to_the_newest_release_and_judged_per_template_surface(
    library: _Repo,
) -> None:
    head = library.commit("matrix", {".github/workflows/reusable-check-matrix.yml": "jobs: {}\n"})
    reading = _templates(library, head=head)
    matrix = "CI matrix/batch/direct action"
    assert (reading.build, reading.detail) == ("v1.1.0", f"release v1.1.0 at HEAD {head}")
    assert reading.build_for(surface="Release and distribution") == "v1.1.0"
    assert reading.build_for(surface=matrix) == ""
    assert dict(reading.surfaces)[matrix] == (
        "surface files changed since release v1.1.0: .github/workflows/reusable-check-matrix.yml"
    )


def test_a_default_branch_commit_the_clone_does_not_hold_does_not_serve(library: _Repo) -> None:
    absent = "1" * 40
    assert _templates(library, head=absent).detail == (
        f"the release tags that are ancestors of {absent} cannot be read in {library.path}"
    )


# --- the surface file sets themselves ---
PINNED_SURFACE_ROOTS = {
    "Pre-commit before mode selection": (
        "scripts/just/check-pre-commit.sh",
        "scripts/just/lint-autofix-staged.sh",
        "livespec_dev_tooling/workflow_checks/staged_precheck.py",
    ),
    "Commit-msg and TDD": (
        "livespec_dev_tooling/checks/red_green_replay.py",
        "livespec_dev_tooling/commit_replay_delegate.py",
        "livespec_dev_tooling/shipped_path_release_guard_check.py",
    ),
    "Pre-push": ("scripts/just/check-pre-push.sh", "livespec_dev_tooling/green_token.py"),
    "Explicit commands and parallel aggregation": (
        "scripts/just/check.sh",
        "scripts/just/check-changed.sh",
        "scripts/just/check-scoped.sh",
        "livespec_dev_tooling/parallel_check_dispatcher.py",
    ),
    "Fast-gate timing": (
        "livespec_dev_tooling/incident_gate_inventory.py",
        "livespec_dev_tooling/incident_local_gates.py",
    ),
    "Focused test selection": (
        "livespec_dev_tooling/incident_focused_admission.py",
        "livespec_dev_tooling/_incident_focused_scope.py",
    ),
    "Touched-file coverage": (
        "livespec_dev_tooling/checks/check_coverage_incremental.py",
        "livespec_dev_tooling/checks/per_file_coverage.py",
    ),
    "Full coverage producers/consumers": (
        "scripts/just/check-per-file-coverage.sh",
        "scripts/just/check-coverage.sh",
        "livespec_dev_tooling/checks/pbt_coverage_pure_modules.py",
    ),
    "Normal evidence caches": (
        "scripts/just/coverage-reuse-id.sh",
        "livespec_dev_tooling/green_token.py",
        "livespec_dev_tooling/_green_token_evidence.py",
    ),
    "Delegated pre-commit": (
        "livespec_dev_tooling/pre_commit_delegate.py",
        "livespec_dev_tooling/_gate_host_authority.py",
    ),
    "Delegated push/replay/explicit gates": (
        "livespec_dev_tooling/gate_remote_delegate.py",
        "livespec_dev_tooling/gate_runner_delegate.py",
        "livespec_dev_tooling/commit_replay_delegate.py",
    ),
    "Parity/completeness enforcement": (
        "livespec_dev_tooling/checks/ci_gate_parity.py",
        "livespec_dev_tooling/checks/aggregate_completeness.py",
        "livespec_dev_tooling/checks/ci_matrix_completeness.py",
        "livespec_dev_tooling/checks/canonical_recipe_fidelity.py",
    ),
    "Spec enforcement and debt": (
        "livespec_dev_tooling/checks/heading_coverage.py",
        "livespec_dev_tooling/checks/heading_coverage_debt_register.py",
        "livespec_dev_tooling/checks/no_todo_registry.py",
    ),
    "PR factory provenance": ("livespec_dev_tooling/factory_provenance_gate.py",),
    "Retrospective bypass audit": (
        "livespec_dev_tooling/_incident_provenance_protocol.py",
        "livespec_dev_tooling/checks/_red_green_replay_incident.py",
    ),
    "Branch/PR resolution": ("livespec_dev_tooling/incident_execution.py",),
    "Acceptance and completion": ("livespec_dev_tooling/incident_run_evidence.py",),
    "Normal master context": (
        "livespec_dev_tooling/incident_execution.py",
        "livespec_dev_tooling/incident_trusted_origin.py",
    ),
    "Closure/proof/archive": (
        "livespec_dev_tooling/incident_run_evidence.py",
        "livespec_dev_tooling/incident_hook_receipt.py",
    ),
    "Gate renderer and pod": (
        "ci-runner/k3s/phase2/gates/render-gate-job.sh",
        "ci-runner/k3s/phase2/gates/gate-job-template.yaml",
    ),
    "PR mode transport": (".github/workflows/incident-label-ci.yml",),
    "CI matrix/batch/direct action": (
        ".github/workflows/ci.yml",
        ".github/workflows/reusable-check-matrix.yml",
        ".github/actions/run-check/action.yml",
    ),
    "CI dependency/aggregate/merge context": (".github/workflows/ci.yml",),
    "Release and distribution": (
        ".github/workflows/release-please.yml",
        ".github/workflows/release-dispatch.yml",
        ".github/workflows/reusable-release-dispatch.yml",
    ),
    "Generated projects": (".github/workflows/fleet-conformance.yml",),
}


def test_every_release_keyed_surface_has_its_pinned_roots_and_each_exists_here() -> None:
    keyed = {s for s, c in SURFACE_CAPABILITY.items() if c in {"gate-readers", "templates"}}
    roots = {root for paths in SURFACE_ROOTS.values() for root in paths}
    assert dict(SURFACE_ROOTS) == PINNED_SURFACE_ROOTS
    assert set(SURFACE_ROOTS) == keyed
    assert [root for root in sorted(roots) if not (REPO_ROOT / root).is_file()] == []


def test_a_surface_reaches_imports_module_runs_and_local_workflows_but_no_more() -> None:
    files = {
        "livespec_dev_tooling/__init__.py": "",
        "livespec_dev_tooling/gate.py": (
            "import os\nimport livespec_dev_tooling.shared\n"
            "from livespec_dev_tooling.pkg import sub\nfrom . import ignored\n"
        ),
        "livespec_dev_tooling/shared.py": "",
        "livespec_dev_tooling/pkg/__init__.py": "",
        "livespec_dev_tooling/pkg/sub.py": "from returns.io import IOSuccess\n",
        "livespec_dev_tooling/unrelated.py": "",
        "scripts/gate.sh": "uv run python -m livespec_dev_tooling.gate --x\n",
        ".github/workflows/ci.yml": (
            "jobs:\n  a:\n    uses: ./.github/workflows/inner.yml\n"
            "  b:\n    steps:\n      - uses: './.github/actions/act'\n"
            "      - uses: ./.github/workflows/missing.yml\n"
        ),
        ".github/workflows/inner.yml": "run: python -m livespec_dev_tooling.shared\n",
        ".github/actions/act/action.yml": "runs: {}\n",
    }
    scripted, script_absent = surface_files(roots=("scripts/gate.sh",), read=files.get)
    workflow, workflow_absent = surface_files(
        roots=(".github/workflows/ci.yml", "nowhere.sh"), read=files.get
    )
    assert scripted == {
        "scripts/gate.sh",
        "livespec_dev_tooling/__init__.py",
        "livespec_dev_tooling/gate.py",
        "livespec_dev_tooling/shared.py",
        "livespec_dev_tooling/pkg/__init__.py",
        "livespec_dev_tooling/pkg/sub.py",
    }
    assert script_absent == ()
    assert workflow == {
        ".github/workflows/ci.yml",
        ".github/workflows/inner.yml",
        ".github/actions/act/action.yml",
        "livespec_dev_tooling/__init__.py",
        "livespec_dev_tooling/shared.py",
    }
    assert workflow_absent == (".github/workflows/missing.yml", "nowhere.sh")
