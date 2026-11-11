"""The serving readers: one per capability, each reading what actually serves it."""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from returns.io import IOFailure, IOSuccess
from returns.result import Failure

from livespec_dev_tooling._incident_fleet_capabilities import CAPABILITIES
from livespec_dev_tooling._incident_fleet_clones import consumer_clone
from livespec_dev_tooling._incident_fleet_driver_reader import read_driver_hooks
from livespec_dev_tooling._incident_fleet_gate_reader import read_gate_readers
from livespec_dev_tooling._incident_fleet_recovery_reader import read_recovery_authorization
from livespec_dev_tooling._incident_fleet_release_keyed import ServingReading
from livespec_dev_tooling._incident_fleet_sources import load_claims
from livespec_dev_tooling._incident_fleet_template_reader import read_templates
from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.fleet._invocation_failure import BINARY_ABSENT, InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult
from livespec_dev_tooling.incident_fleet_controller_reader import read_controller_serving
from livespec_dev_tooling.incident_fleet_host import HostProbe
from livespec_dev_tooling.incident_fleet_serving import (
    PRODUCTION_READERS,
    Reader,
    host_serving_reader,
)
from tests.livespec_dev_tooling import test_incident_fleet_controller_reader as controller_tests

host = controller_tests.host


# --- consumer clones ---
def _clones_probe(*, clones_root: Path | None) -> HostProbe:
    return HostProbe(
        clones_root=clones_root,
        proc_root=Path("/proc"),
        home=Path("/"),
        run=_asking_probe(asked=[]).run,
    )


def test_a_present_clone_is_the_directory_named_for_the_repository(tmp_path: Path) -> None:
    (tmp_path / "tooling").mkdir()
    assert consumer_clone(
        probe=_clones_probe(clones_root=tmp_path), repository="example/tooling"
    ) == (tmp_path / "tooling")


def test_an_absent_clone_or_an_unknown_clones_root_is_unread(tmp_path: Path) -> None:
    assert (
        consumer_clone(probe=_clones_probe(clones_root=tmp_path), repository="example/notes")
        is None
    )
    assert (
        consumer_clone(probe=_clones_probe(clones_root=None), repository="example/tooling") is None
    )


def test_a_file_in_place_of_a_clone_is_unread(tmp_path: Path) -> None:
    _ = (tmp_path / "tooling").write_text("not a directory")
    assert (
        consumer_clone(probe=_clones_probe(clones_root=tmp_path), repository="example/tooling")
        is None
    )


@pytest.mark.parametrize("repository", ["example/..", "example/.", "example/", ""])
def test_a_name_that_could_leave_the_clones_root_is_unread(tmp_path: Path, repository: str) -> None:
    (tmp_path / "x").mkdir()
    assert (
        consumer_clone(probe=_clones_probe(clones_root=tmp_path / "x"), repository=repository)
        is None
    )


# --- gate readers ---
COMMIT = "a" * 40


class _Fleet:
    def __init__(self, *, root: Path) -> None:
        self.root = root
        self.git: dict[str, CommandOutcome] = {}
        self.asked: list[list[str]] = []

    def install(self, *, name: str, direct_url: object | None, dists: int = 1) -> Path:
        clone = self.root / name
        for index in range(dists):
            dist = (
                clone
                / ".venv"
                / "lib"
                / "python3.12"
                / "site-packages"
                / f"livespec_dev_tooling-1.{index}.0.dist-info"
            )
            dist.mkdir(parents=True)
            if direct_url is not None:
                _ = (dist / "direct_url.json").write_text(
                    direct_url if isinstance(direct_url, str) else json.dumps(direct_url)
                )
        return clone

    def probe(self) -> HostProbe:
        def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
            _ = cwd
            self.asked.append(args)
            return self.git.get(
                args[3], IOSuccess(CommandResult(returncode=0, stdout="", stderr=""))
            )

        return HostProbe(clones_root=self.root, proc_root=Path("/proc"), home=self.root, run=run)

    def read(self, *, name: str = "tooling") -> str | ServingReading | None:
        return read_gate_readers(probe=self.probe(), repository=f"example/{name}")


@pytest.fixture
def fleet(tmp_path: Path) -> _Fleet:
    return _Fleet(root=tmp_path)


def _text_ok(stdout: str) -> CommandOutcome:
    return IOSuccess(CommandResult(returncode=0, stdout=stdout, stderr=""))


def test_a_vcs_install_serves_its_recorded_revision_not_its_version_label(fleet: _Fleet) -> None:
    _ = fleet.install(name="tooling", direct_url={"vcs_info": {"commit_id": COMMIT}})
    assert fleet.read() == COMMIT
    assert fleet.asked == []


def test_a_consumer_with_no_clone_or_no_venv_is_unverified_without_a_crash(fleet: _Fleet) -> None:
    assert fleet.read(name="openbrain") is None
    (fleet.root / "resume").mkdir()
    assert fleet.read(name="resume") is None


def test_a_venv_without_exactly_one_install_is_unverified(fleet: _Fleet) -> None:
    _ = fleet.install(name="tooling", direct_url={"vcs_info": {"commit_id": COMMIT}}, dists=2)
    assert fleet.read() is None


@pytest.mark.parametrize(
    "direct_url",
    [
        None,
        "not json",
        "[]",
        '{"vcs_info": {"commit_id": "'
        + "a" * 40
        + '"}, "vcs_info": {"commit_id": "'
        + "a" * 40
        + '"}}',
        {"vcs_info": {"commit_id": "v1.2.3"}},
        {"vcs_info": {"commit_id": 5}},
        {"vcs_info": "x"},
        {"url": "https://example.test/x", "archive_info": {"hash": "sha256=abc"}},
    ],
)
def test_an_install_that_is_not_a_recorded_revision_is_unverified(
    fleet: _Fleet, direct_url: object | None
) -> None:
    _ = fleet.install(name="tooling", direct_url=direct_url)
    assert fleet.read() is None


def _editable(*, clone: Path, url: str | None = None) -> dict[str, object]:
    return {"url": url or clone.as_uri(), "dir_info": {"editable": True}}


def test_a_consumer_running_its_own_clean_source_is_keyed_to_a_release_not_its_head(
    fleet: _Fleet,
) -> None:
    # Its HEAD can never be named by a committed claim; with no release tag it serves nothing.
    clone = fleet.root / "tooling"
    _ = fleet.install(name="tooling", direct_url=_editable(clone=clone))
    fleet.git["rev-parse"] = _text_ok(COMMIT + "\n")
    fleet.git["status"] = _text_ok("")
    assert fleet.read() == ServingReading(
        build="",
        detail=f"no release tag is an ancestor of {COMMIT}",
        head=COMMIT,
        releases=frozenset(),
    )
    assert {"git", "-C", str(clone)} <= set(fleet.asked[0])
    assert ["git", "-C", str(clone), "status", "--porcelain", "--untracked-files=no"] in fleet.asked


@pytest.mark.parametrize(
    ("head", "status"),
    [
        (_text_ok(COMMIT + "\n"), _text_ok(" M livespec_dev_tooling/x.py\n")),
        (_text_ok("short\n"), _text_ok("")),
        (_text_ok(""), _text_ok("")),
        (IOSuccess(CommandResult(returncode=128, stdout=COMMIT, stderr="")), _text_ok("")),
        (_text_ok(COMMIT), IOSuccess(CommandResult(returncode=128, stdout="", stderr=""))),
        (
            _text_ok(COMMIT),
            IOFailure(InvocationNotPerformed(argv=("git",), kind=BINARY_ABSENT, detail="x")),
        ),
    ],
)
def test_an_own_source_install_that_is_dirty_or_unreadable_is_unverified(
    fleet: _Fleet, head: CommandOutcome, status: CommandOutcome
) -> None:
    clone = fleet.root / "tooling"
    _ = fleet.install(name="tooling", direct_url=_editable(clone=clone))
    fleet.git["rev-parse"] = head
    fleet.git["status"] = status
    reading = fleet.read()
    assert isinstance(reading, ServingReading)
    assert reading.build == ""
    assert reading.detail


def test_an_editable_install_of_another_checkout_is_unverified(fleet: _Fleet) -> None:
    other = fleet.root / "elsewhere"
    other.mkdir()
    _ = fleet.install(name="tooling", direct_url=_editable(clone=other))
    fleet.git["rev-parse"] = _text_ok(COMMIT)
    fleet.git["status"] = _text_ok("")
    assert fleet.read() is None
    _ = fleet.install(
        name="plain", direct_url={"url": (fleet.root / "plain").as_uri(), "dir_info": {}}
    )
    assert fleet.read(name="plain") is None
    _ = fleet.install(name="nourl", direct_url={"dir_info": {"editable": True}})
    assert fleet.read(name="nourl") is None


# --- templates ---
SHA = "d" * 40
TAG_SHA = "e" * 40
SELF_SHA = "f" * 40
TEMPLATE = "thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-check-matrix.yml"
ACTION = "thewoolleyman/livespec-dev-tooling/.github/actions/publish-flake-retries"
WORKFLOWS = ".github/workflows/"


def _workflow(*uses: str) -> str:
    steps = "".join(f"      - uses: {u}\n" for u in uses)
    return f"name: ci\njobs:\n  gate:\n    runs-on: x\n    steps:\n{steps}"


class _Remote:
    """A consumer's default branch over the git transport: its workflow files and its refs."""

    def __init__(
        self, *, workflows: dict[str, str] | None, remote: dict[str, str] | None = None
    ) -> None:
        self.workflows = workflows
        self.remote = remote or {}
        self.asked: list[list[str]] = []
        self.unreadable: frozenset[str] = frozenset()
        self.ls_remote_status = 0
        self.ls_remote_runs = True

    def probe(self) -> HostProbe:
        def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
            _ = cwd
            self.asked.append(args)
            files = self.workflows or {}
            if "clone" in args:
                return IOSuccess(CommandResult(returncode=0, stdout="", stderr=""))
            if "ls-tree" in args:
                status = 128 if self.workflows is None else 0
                listing = "".join(f"{WORKFLOWS}{name}\0" for name in files)
                return IOSuccess(CommandResult(returncode=status, stdout=listing, stderr=""))
            if "show" in args:
                name = args[-1].removeprefix(f"HEAD:{WORKFLOWS}")
                status = 128 if name in self.unreadable else 0
                return IOSuccess(CommandResult(returncode=status, stdout=files[name], stderr=""))
            assert args[1] == "ls-remote"
            if not self.ls_remote_runs:
                return IOFailure(
                    InvocationNotPerformed(argv=tuple(args), kind=BINARY_ABSENT, detail="x")
                )
            lines = "".join(
                f"{sha}\t{ref}\n" for ref, sha in self.remote.items() if ref in args[3:]
            )
            return IOSuccess(
                CommandResult(returncode=self.ls_remote_status, stdout=lines, stderr="")
            )

        return HostProbe(clones_root=None, proc_root=Path("/proc"), home=Path("/"), run=run)

    def read(self) -> str | ServingReading | None:
        return read_templates(probe=self.probe(), repository="thewoolleyman/consumer")

    def shown(self) -> list[str]:
        return [a[-1] for a in self.asked if "show" in a]


def _ci(*uses: str) -> dict[str, str]:
    return {"ci.yml": _workflow(*uses)}


def test_a_pinned_commit_is_the_serving_build_and_is_read_from_the_remote_default_branch() -> None:
    remote = _Remote(workflows=_ci("actions/checkout@v5", f"{TEMPLATE}@{SHA}"))
    assert remote.read() == f"livespec-dev-tooling@{SHA}"
    listed = next(a for a in remote.asked if "ls-tree" in a)
    assert listed[-1] == WORKFLOWS
    assert remote.shown() == [f"HEAD:{WORKFLOWS}ci.yml"]
    assert any("thewoolleyman/consumer.git" in part for a in remote.asked for part in a)
    assert sum("clone" in a for a in remote.asked) == 1
    assert not any("ls-remote" in a for a in remote.asked)


def test_a_pinned_tag_is_resolved_to_the_commit_it_points_at() -> None:
    remote = _Remote(
        workflows=_ci(f"{TEMPLATE}@v1.2.3"),
        remote={"refs/tags/v1.2.3": "1" * 40, "refs/tags/v1.2.3^{}": TAG_SHA},
    )
    assert remote.read() == f"livespec-dev-tooling@{TAG_SHA}"


def test_a_lightweight_tag_resolves_to_its_own_commit() -> None:
    remote = _Remote(workflows=_ci(f"{TEMPLATE}@v1.2.3"), remote={"refs/tags/v1.2.3": TAG_SHA})
    assert remote.read() == f"livespec-dev-tooling@{TAG_SHA}"


@pytest.mark.parametrize(
    "remote",
    [{}, {"refs/tags/v1.2.3": "short"}, {"refs/tags/other": TAG_SHA}],
)
def test_a_ref_that_names_no_tag_is_unverified(remote: dict[str, str]) -> None:
    assert _Remote(workflows=_ci(f"{TEMPLATE}@v1.2.3"), remote=remote).read() is None


def test_an_unanswered_tag_lookup_is_unverified() -> None:
    remote = _Remote(workflows=_ci(f"{TEMPLATE}@v1.2.3"), remote={"refs/tags/v1.2.3": TAG_SHA})
    remote.ls_remote_status = 128
    assert remote.read() is None


def test_a_tag_lookup_that_cannot_run_is_unverified() -> None:
    remote = _Remote(workflows=_ci(f"{TEMPLATE}@v1.2.3"), remote={"refs/tags/v1.2.3": TAG_SHA})
    remote.ls_remote_runs = False
    assert remote.read() is None


def test_pins_that_disagree_are_unverified() -> None:
    assert _Remote(workflows=_ci(f"{TEMPLATE}@{SHA}", f"{TEMPLATE}@{TAG_SHA}")).read() is None


def test_the_same_pin_repeated_is_one_serving_build() -> None:
    remote = _Remote(workflows=_ci(f"{TEMPLATE}@{SHA}", f"{TEMPLATE}@{SHA}"))
    assert remote.read() == f"livespec-dev-tooling@{SHA}"


def test_only_this_librarys_templates_count_as_pins() -> None:
    ci = _ci("thewoolleyman/livespec/.github/workflows/x.yml@v9.9.9", "actions/cache@v5")
    assert _Remote(workflows=ci).read() is None


def test_a_pinned_composite_action_of_this_library_is_a_template_pin() -> None:
    # The fleet's ci.yml files pin this library's composite actions, not only its
    # reusable workflows (for example `.github/actions/publish-flake-retries@v1.189.1`).
    remote = _Remote(workflows=_ci(f"{ACTION}@v1.2.3"), remote={"refs/tags/v1.2.3": TAG_SHA})
    assert remote.read() == f"livespec-dev-tooling@{TAG_SHA}"


def test_pins_in_every_workflow_file_are_read_not_only_ci() -> None:
    # A consumer's release-dispatch, pin-freshness and bump-pin workflows run this
    # library's reusable workflows; ci.yml alone does not name them.
    workflows = {
        "ci.yml": _workflow("actions/checkout@v5"),
        "release-dispatch.yml": _workflow(f"{TEMPLATE}@{SHA}"),
        "pin-freshness.yaml": _workflow(f"{ACTION}@{SHA}"),
    }
    remote = _Remote(workflows=workflows)
    assert remote.read() == f"livespec-dev-tooling@{SHA}"
    assert sorted(remote.shown()) == sorted(f"HEAD:{WORKFLOWS}{name}" for name in workflows)
    assert sum("clone" in a for a in remote.asked) == 1


def test_pins_that_disagree_across_workflow_files_are_unverified() -> None:
    workflows = {
        "ci.yml": _workflow(f"{ACTION}@{SHA}"),
        "pin-freshness.yml": _workflow(f"{TEMPLATE}@{TAG_SHA}"),
    }
    assert _Remote(workflows=workflows).read() is None


def test_a_file_that_is_not_a_workflow_is_never_read() -> None:
    workflows = {
        "README.md": f"uses: {TEMPLATE}@{TAG_SHA}\n",
        "ci.yaml": _workflow(f"{TEMPLATE}@{SHA}"),
    }
    remote = _Remote(workflows=workflows)
    assert remote.read() == f"livespec-dev-tooling@{SHA}"
    assert remote.shown() == [f"HEAD:{WORKFLOWS}ci.yaml"]


def test_an_unreadable_workflow_file_leaves_the_consumer_unverified() -> None:
    workflows = {
        "ci.yml": _workflow(f"{TEMPLATE}@{SHA}"),
        "release-dispatch.yml": _workflow(f"{TEMPLATE}@{TAG_SHA}"),
    }
    remote = _Remote(workflows=workflows)
    remote.unreadable = frozenset({"release-dispatch.yml"})
    assert remote.read() is None


def test_a_consumer_running_its_own_local_workflows_is_read_from_its_default_branch() -> None:
    remote = _Remote(
        workflows=_ci("./.github/actions/budget", "actions/checkout@v5"),
        remote={"HEAD": SELF_SHA},
    )
    assert remote.read() == ServingReading(
        build="", detail="no clone of consumer on this host", head=SELF_SHA
    )
    lookup = next(a for a in remote.asked if "ls-remote" in a)
    assert any("thewoolleyman/consumer.git" in part for part in lookup)


def test_a_local_workflow_consumer_with_an_unreadable_head_is_unverified() -> None:
    remote = _Remote(workflows=_ci("./.github/actions/budget"), remote={"HEAD": "bad"})
    assert remote.read() is None


def test_a_consumer_with_no_workflows_or_no_template_use_is_unverified() -> None:
    assert _Remote(workflows=None).read() is None
    assert _Remote(workflows={}).read() is None
    assert _Remote(workflows=_ci("actions/checkout@v5")).read() is None


def test_an_unreachable_remote_is_unverified() -> None:
    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        _ = cwd
        return IOFailure(InvocationNotPerformed(argv=tuple(args), kind=BINARY_ABSENT, detail="x"))

    probe = HostProbe(clones_root=None, proc_root=Path("/proc"), home=Path("/"), run=run)
    assert read_templates(probe=probe, repository="thewoolleyman/consumer") is None


def _library(
    *, workflows: dict[str, str], remote: dict[str, str]
) -> tuple[str | ServingReading | None, _Remote]:
    remote_ = _Remote(workflows=workflows, remote=remote)
    served = read_templates(probe=remote_.probe(), repository="thewoolleyman/livespec-dev-tooling")
    return served, remote_


def test_this_librarys_own_ci_serves_its_local_templates_not_its_release_lane_self_pins() -> None:
    # Its ci.yml runs `./.github/...` at the audited revision; its release-lane workflows
    # pin an older release of itself. The CI surfaces are served by the local templates.
    workflows = {
        "ci.yml": _workflow("./.github/workflows/reusable-check-matrix.yml"),
        "release-dispatch.yml": _workflow(f"{TEMPLATE}@v1.183.0"),
    }
    served, remote = _library(
        workflows=workflows, remote={"HEAD": SELF_SHA, "refs/tags/v1.183.0": TAG_SHA}
    )
    assert served == ServingReading(
        build="", detail="no clone of livespec-dev-tooling on this host", head=SELF_SHA
    )
    lookup = next(a for a in remote.asked if "ls-remote" in a)
    assert "https://github.com/thewoolleyman/livespec-dev-tooling.git" in lookup
    assert "HEAD" in lookup


def test_this_library_with_no_local_workflows_is_read_from_its_pins() -> None:
    served, _ = _library(
        workflows={"release-dispatch.yml": _workflow(f"{TEMPLATE}@v1.183.0")},
        remote={"HEAD": SELF_SHA, "refs/tags/v1.183.0": TAG_SHA},
    )
    assert served == f"livespec-dev-tooling@{TAG_SHA}"


def test_another_consumer_with_local_workflows_and_this_librarys_pins_is_read_from_its_pins() -> (
    None
):
    workflows = {
        "ci.yml": _workflow("./.github/actions/setup", f"{ACTION}@v1.2.3"),
    }
    remote = _Remote(workflows=workflows, remote={"HEAD": SELF_SHA, "refs/tags/v1.2.3": TAG_SHA})
    assert remote.read() == f"livespec-dev-tooling@{TAG_SHA}"


# --- recovery authorization ---
CONTROLLER = "v1.2.3@" + "c" * 40
APP = {"actor_id": 987, "actor_type": "Integration", "bypass_mode": "always"}
REPO = "repos/example/tooling"
BASE = f"{REPO}/rulesets"


def _ruleset(
    *,
    include: list[str] | None = None,
    actors: Sequence[object] | None = None,
    enforcement: str = "active",
    target: str = "branch",
) -> dict[str, object]:
    return {
        "id": 7,
        "enforcement": enforcement,
        "target": target,
        "conditions": {"ref_name": {"include": include or ["~DEFAULT_BRANCH"]}},
        "bypass_actors": [APP] if actors is None else list(actors),
    }


class _Forge:
    def __init__(self, *, rulesets: list[dict[str, object]]) -> None:
        self.answers: dict[str, GhRead] = {BASE: _json_ok([{"id": r["id"], **r} for r in rulesets])}
        self.answers[REPO] = _json_ok({"default_branch": "master"})
        for ruleset in rulesets:
            self.answers[f"{BASE}/{ruleset['id']}"] = _json_ok(ruleset)
        self.asked: list[list[str]] = []

    def read(self, *, controller: str | None = CONTROLLER) -> str | None:
        def read_forge(*, args: list[str]) -> GhRead:
            self.asked.append(args)
            return self.answers.get(args[1], GhRead(returncode=1, stdout="", stderr="HTTP 404"))

        return read_recovery_authorization(
            repository="example/tooling", controller=controller, read_forge=read_forge
        )


def _json_ok(document: object) -> GhRead:
    return GhRead(returncode=0, stdout=json.dumps(document), stderr="")


def test_the_released_principal_and_one_always_bypass_app_are_the_serving_build() -> None:
    forge = _Forge(rulesets=[_ruleset()])
    assert forge.read() == f"{CONTROLLER}+bypass-app-987"
    assert ["api", BASE] in forge.asked


def test_without_a_verified_controller_nothing_is_asked_and_nothing_is_served() -> None:
    forge = _Forge(rulesets=[_ruleset()])
    assert forge.read(controller=None) is None
    assert forge.asked == []


def test_a_ruleset_naming_the_master_branch_directly_counts() -> None:
    assert _Forge(rulesets=[_ruleset(include=["refs/heads/master"])]).read() is not None


@pytest.mark.parametrize(
    "ruleset",
    [
        _ruleset(enforcement="evaluate"),
        _ruleset(enforcement="disabled"),
        _ruleset(target="tag"),
        _ruleset(include=["refs/heads/feature"]),
        _ruleset(actors=[]),
        _ruleset(actors=[APP, {**APP, "actor_id": 5}]),
        _ruleset(actors=[{**APP, "actor_type": "RepositoryRole"}]),
        _ruleset(actors=[{**APP, "bypass_mode": "pull_request"}]),
        _ruleset(actors=[{**APP, "actor_id": "987"}]),
        _ruleset(actors=["not-an-object"]),
    ],
)
def test_a_default_branch_without_exactly_one_always_bypass_app_is_unverified(
    ruleset: dict[str, object],
) -> None:
    assert _Forge(rulesets=[ruleset]).read() is None


def test_bypass_actors_spread_across_default_branch_rulesets_are_counted_together() -> None:
    other = {**_ruleset(), "id": 8}
    assert _Forge(rulesets=[_ruleset(), other]).read() is None


def test_a_ruleset_that_does_not_guard_the_default_branch_does_not_add_an_actor() -> None:
    other = {**_ruleset(include=["refs/heads/feature"]), "id": 8}
    assert _Forge(rulesets=[_ruleset(), other]).read() == f"{CONTROLLER}+bypass-app-987"


def test_a_ruleset_with_no_conditions_or_bypass_list_adds_nothing() -> None:
    bare: dict[str, object] = {"id": 7, "enforcement": "active", "target": "branch"}
    assert _Forge(rulesets=[bare]).read() is None


def test_unreadable_rulesets_are_unverified() -> None:
    forge = _Forge(rulesets=[_ruleset()])
    forge.answers[BASE] = GhRead(returncode=1, stdout="", stderr="HTTP 403")
    assert forge.read() is None
    forge.answers[BASE] = GhRead(returncode=0, stdout="not json", stderr="")
    assert forge.read() is None
    forge.answers[BASE] = _json_ok({"message": "not a list"})
    assert forge.read() is None


def test_a_ruleset_detail_with_a_duplicate_key_is_unverified() -> None:
    forge = _Forge(rulesets=[_ruleset()])
    forge.answers[f"{BASE}/7"] = GhRead(
        returncode=0, stdout='{"id": 7, ' + json.dumps(_ruleset())[1:], stderr=""
    )
    assert forge.read() is None


def test_a_ruleset_whose_detail_cannot_be_read_adds_no_actor() -> None:
    forge = _Forge(rulesets=[_ruleset()])
    forge.answers[f"{BASE}/7"] = GhRead(returncode=1, stdout="", stderr="x")
    assert forge.read() is None


def test_a_failed_forge_read_is_unverified_even_when_its_body_parses() -> None:
    # `gh api` exits non-zero on an HTTP error yet can still print a JSON body; a
    # failed read is never evidence, whatever that body says (review mutant M14).
    forge = _Forge(rulesets=[_ruleset()])
    for path in (BASE, f"{BASE}/7"):
        answer = forge.answers[path]
        forge.answers[path] = GhRead(returncode=1, stdout=answer.stdout, stderr="HTTP 502")
        assert forge.read() is None
        forge.answers[path] = answer
    assert forge.read() == f"{CONTROLLER}+bypass-app-987"


def _with(ruleset: dict[str, object], **changes: object) -> dict[str, object]:
    return {**ruleset, **changes}


def _ref_names(*, include: list[object], exclude: list[object] | None = None) -> dict[str, object]:
    return {"ref_name": {"include": include, "exclude": exclude or []}}


ROLE = {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
ORG_ADMIN = {"actor_id": 1, "actor_type": "OrganizationAdmin", "bypass_mode": "always"}


def test_an_unreadable_ruleset_detail_is_unverified_not_skipped() -> None:
    # The review's probe: ruleset 7 has the App, ruleset 8 has a role bypass and its
    # detail read fails. Skipping 8 would read verified; it must read unverified.
    other = _with(_ruleset(actors=[ROLE]), id=8)
    forge = _Forge(rulesets=[_ruleset(), other])
    assert forge.read() is None
    forge.answers[f"{BASE}/8"] = GhRead(returncode=1, stdout="", stderr="HTTP 502")
    assert forge.read() is None


def test_an_unreadable_default_branch_is_unverified() -> None:
    forge = _Forge(rulesets=[_ruleset()])
    forge.answers[REPO] = GhRead(returncode=1, stdout="", stderr="HTTP 404")
    assert forge.read() is None
    forge.answers[REPO] = _json_ok({"default_branch": ""})
    assert forge.read() is None


def test_a_listed_entry_that_is_not_a_ruleset_is_unverified() -> None:
    forge = _Forge(rulesets=[_ruleset()])
    forge.answers[BASE] = _json_ok(["not-a-ruleset", _ruleset()])
    assert forge.read() is None


@pytest.mark.parametrize(
    "include",
    [["~ALL"], ["refs/heads/*"], ["refs/heads/ma*"], ["refs/heads/m?ster"], ["refs/heads/**"]],
)
def test_a_ruleset_guarding_the_default_branch_by_any_spelling_adds_its_actors(
    include: list[object],
) -> None:
    other = _with(_ruleset(actors=[ORG_ADMIN]), id=8, conditions=_ref_names(include=include))
    assert _Forge(rulesets=[_ruleset(), other]).read() is None


@pytest.mark.parametrize(
    "include",
    [["~ALL"], ["refs/heads/*"], ["refs/heads/ma*"], ["refs/heads/m?ster"], ["refs/heads/**"]],
)
def test_the_app_is_counted_when_its_ruleset_guards_the_default_branch_by_any_spelling(
    include: list[object],
) -> None:
    only = _with(_ruleset(), conditions=_ref_names(include=include))
    assert _Forge(rulesets=[only]).read() == f"{CONTROLLER}+bypass-app-987"


@pytest.mark.parametrize(
    "conditions",
    [
        _ref_names(include=["refs/heads/release/**"]),
        _ref_names(include=["refs/heads/main"]),
        _ref_names(include=["~ALL"], exclude=["~DEFAULT_BRANCH"]),
        _ref_names(include=["~ALL"], exclude=["refs/heads/master"]),
        _ref_names(include=["refs/heads/*"], exclude=["refs/heads/ma*"]),
    ],
)
def test_a_ruleset_that_leaves_the_default_branch_out_adds_no_actor(
    conditions: dict[str, object],
) -> None:
    other = _with(_ruleset(actors=[ORG_ADMIN]), id=8, conditions=conditions)
    assert _Forge(rulesets=[_ruleset(), other]).read() == f"{CONTROLLER}+bypass-app-987"


@pytest.mark.parametrize(
    "conditions",
    [
        _ref_names(include=["refs/heads/[a-m]*"]),
        _ref_names(include=["refs/tags/*"]),
        _ref_names(include=["master"]),
        _ref_names(include=["~ALL"], exclude=["refs/heads/{a,b}"]),
        _ref_names(include=[7]),
        {"ref_name": {"include": "~ALL"}},
        {"ref_name": {"include": ["~ALL"], "exclude": "x"}},
        {"ref_name": "~ALL"},
        {"ref_name": {"include": ["~ALL"]}, "unknown_condition": {}},
        "not-a-mapping",
    ],
)
def test_conditions_that_cannot_be_evaluated_are_unverified(conditions: object) -> None:
    # The second ruleset has no actors: any guess about its conditions reads verified.
    other = _with(_ruleset(actors=[]), id=8, conditions=conditions)
    assert _Forge(rulesets=[_ruleset(), other]).read() is None


def test_an_organization_rulesets_repository_scope_is_already_satisfied() -> None:
    scoped = {**_ref_names(include=["~DEFAULT_BRANCH"]), "repository_name": {"include": ["~ALL"]}}
    forge = _Forge(rulesets=[_with(_ruleset(), conditions=scoped)])
    assert forge.read() == f"{CONTROLLER}+bypass-app-987"


def test_a_pattern_that_may_or_may_not_cross_a_slash_is_unverified() -> None:
    # `*` either stops at `/` or crosses it depending on the matcher; a default branch
    # with a `/` makes the two disagree, so the reader refuses rather than guess.
    forge = _Forge(rulesets=[_with(_ruleset(), conditions=_ref_names(include=["refs/heads/*"]))])
    forge.answers[REPO] = _json_ok({"default_branch": "team/main"})
    assert forge.read() is None
    other = _with(
        _ruleset(actors=[ORG_ADMIN]), id=8, conditions=_ref_names(include=["refs/heads/*"])
    )
    beside = _Forge(rulesets=[_ruleset(), other])
    beside.answers[REPO] = _json_ok({"default_branch": "team/main"})
    assert beside.read() is None
    forge.answers[REPO] = _json_ok({"default_branch": "master"})
    assert forge.read() == f"{CONTROLLER}+bypass-app-987"


def test_a_guarding_ruleset_without_a_readable_bypass_list_is_unverified() -> None:
    bare = {key: value for key, value in _ruleset().items() if key != "bypass_actors"}
    assert _Forge(rulesets=[bare]).read() is None
    assert _Forge(rulesets=[_ruleset(), _with(bare, id=8)]).read() is None
    leaves_out = _with(bare, id=8, conditions=_ref_names(include=["refs/heads/main"]))
    assert _Forge(rulesets=[_ruleset(), leaves_out]).read() == f"{CONTROLLER}+bypass-app-987"


# --- driver hooks ---

PLUGIN_SHA = "9" * 40
OTHER_SHA = "8" * 40


class _Harness:
    """A consumer clone whose settings enable plugins, and the harness's install registry."""

    def __init__(self, *, root: Path) -> None:
        self.root = root
        self.clone = root / "clones" / "tooling"
        (self.clone / ".claude").mkdir(parents=True)
        (root / "home" / ".claude" / "plugins").mkdir(parents=True)
        self.plugins: dict[str, str] = {}
        self.records: dict[str, list[object]] = {}

    def enable(
        self, *, name: str, sha: str | None = PLUGIN_SHA, project: Path | None = None
    ) -> None:
        marketplace = name.split("@")[1]
        self.plugins[name] = marketplace
        if sha is not None:
            cache = self.root / "cache" / name
            cache.mkdir(parents=True, exist_ok=True)
            record: dict[str, object] = {
                "projectPath": str(project or self.clone),
                "gitCommitSha": sha,
                "installPath": str(cache),
            }
            self.records.setdefault(name, []).append(record)

    def write(self, *, registry: str | None = None, settings: str | None = None) -> HostProbe:
        document = {
            "enabledPlugins": {name: True for name in self.plugins},
            "extraKnownMarketplaces": {
                marketplace: {
                    "source": {"source": "github", "repo": f"acme/{marketplace}", "ref": "release"}
                }
                for marketplace in self.plugins.values()
            },
        }
        _ = (self.clone / ".claude" / "settings.json").write_text(
            json.dumps(document) if settings is None else settings, encoding="utf-8"
        )
        _ = (self.root / "home" / ".claude" / "plugins" / "installed_plugins.json").write_text(
            json.dumps({"version": 2, "plugins": self.records}) if registry is None else registry,
            encoding="utf-8",
        )
        return HostProbe(
            clones_root=self.root / "clones",
            proc_root=Path("/proc"),
            home=self.root / "home",
            run=_asking_probe(asked=[]).run,
        )

    def read(self, **write: str | None) -> str | None:
        return read_driver_hooks(probe=self.write(**write), repository="example/tooling")


@pytest.fixture
def harness(tmp_path: Path) -> _Harness:
    return _Harness(root=tmp_path)


def test_each_enabled_plugin_serves_the_commit_the_harness_installed_for_this_project(
    harness: _Harness,
) -> None:
    harness.enable(name="alpha@alpha")
    assert harness.read() == f"alpha@alpha={PLUGIN_SHA}"
    harness.enable(name="beta@beta", sha=OTHER_SHA)
    assert harness.read() == f"alpha@alpha={PLUGIN_SHA},beta@beta={OTHER_SHA}"


def test_a_registry_with_a_duplicate_key_serves_nothing(harness: _Harness) -> None:
    harness.enable(name="alpha@alpha")
    registry = json.dumps({"version": 2, "plugins": harness.records})
    assert harness.read(registry=registry) == f"alpha@alpha={PLUGIN_SHA}"
    assert (
        harness.read(registry='{"version": 2, "version": 2,' + registry[1:].split(",", 1)[1])
        is None
    )
    plugins = json.dumps(harness.records["alpha@alpha"])
    assert (
        harness.read(
            registry='{"plugins": {"alpha@alpha": ' + plugins + ', "alpha@alpha": ' + plugins + "}}"
        )
        is None
    )


def test_an_install_for_another_project_does_not_serve_this_one(harness: _Harness) -> None:
    harness.enable(name="alpha@alpha", project=harness.root / "elsewhere")
    assert harness.read() is None


def test_an_enabled_plugin_that_is_not_installed_leaves_the_consumer_unverified(
    harness: _Harness,
) -> None:
    harness.enable(name="alpha@alpha")
    harness.enable(name="beta@beta", sha=None)
    assert harness.read() is None


@pytest.mark.parametrize("sha", ["abc", "G" * 40, ""])
def test_an_install_without_a_full_commit_is_unverified(harness: _Harness, sha: str) -> None:
    harness.enable(name="alpha@alpha", sha=sha)
    assert harness.read() is None


def test_an_install_whose_plugin_cache_is_gone_is_unverified(harness: _Harness) -> None:
    harness.enable(name="alpha@alpha")
    record = cast("dict[str, object]", harness.records["alpha@alpha"][0])
    shutil.rmtree(str(record["installPath"]))
    assert harness.read() is None
    del record["installPath"]
    assert harness.read() is None
    record["installPath"] = 7
    assert harness.read() is None


def test_unreadable_registry_or_settings_leave_the_consumer_unverified(harness: _Harness) -> None:
    harness.enable(name="alpha@alpha")
    assert harness.read(registry="not json") is None
    assert harness.read(settings="not json") is None
    assert harness.read(registry='{"version": 2, "version": 2, "plugins": {}}') is None
    assert harness.read(settings=json.dumps({"enabledPlugins": {}})) is None
    (harness.root / "home" / ".claude" / "plugins" / "installed_plugins.json").unlink()
    probe = HostProbe(
        clones_root=harness.root / "clones",
        proc_root=Path("/proc"),
        home=harness.root / "home",
        run=_asking_probe(asked=[]).run,
    )
    assert read_driver_hooks(probe=probe, repository="example/tooling") is None
    (harness.clone / ".claude" / "settings.json").unlink()
    assert read_driver_hooks(probe=probe, repository="example/tooling") is None


def test_a_consumer_with_no_clone_is_unverified_without_a_crash(harness: _Harness) -> None:
    probe = harness.write()
    assert read_driver_hooks(probe=probe, repository="example/openbrain") is None


# --- composition ---
def _asking_probe(*, asked: list[list[str]]) -> HostProbe:
    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        _ = cwd
        asked.append(args)
        return IOSuccess(CommandResult(returncode=3, stdout="", stderr="unavailable"))

    return HostProbe(clones_root=None, proc_root=Path("/proc"), home=Path("/"), run=run)


def test_the_production_table_names_one_distinct_reader_for_every_capability() -> None:
    assert set(PRODUCTION_READERS) == set(CAPABILITIES)
    assert PRODUCTION_READERS["gate-readers"] is read_gate_readers
    assert PRODUCTION_READERS["templates"] is read_templates
    assert PRODUCTION_READERS["driver-hooks"] is read_driver_hooks
    assert PRODUCTION_READERS["independent-controller"] is read_controller_serving
    assert len({id(reader) for reader in PRODUCTION_READERS.values()}) == len(CAPABILITIES)


def test_recovery_authorization_is_read_only_through_a_verified_controller() -> None:
    asked: list[list[str]] = []
    recovery = PRODUCTION_READERS["recovery-authorization"]
    assert (
        recovery(probe=_asking_probe(asked=asked), repository="thewoolleyman/livespec-dev-tooling")
        is None
    )
    assert recovery(probe=_asking_probe(asked=asked), repository="thewoolleyman/livespec") is None
    assert all(args[0] == "systemctl" for args in asked)
    assert not any("gh" in args for args in asked)


def test_the_reader_dispatches_by_capability_with_the_probe_and_repository() -> None:
    seen: list[tuple[HostProbe, str, str]] = []

    def reader(name: str) -> Reader:
        def read(*, probe: HostProbe, repository: str) -> str | None:
            seen.append((probe, repository, name))
            return f"{name}-version"

        return read

    probe = _asking_probe(asked=[])
    read = host_serving_reader(
        probe=probe, readers={"gate-readers": reader("gate"), "templates": reader("tmpl")}
    )
    assert read(repository="example/tooling", capability="gate-readers") == "gate-version"
    assert read(repository="example/other", capability="templates") == "tmpl-version"
    assert seen == [(probe, "example/tooling", "gate"), (probe, "example/other", "tmpl")]


def test_a_capability_without_a_reader_is_unverified() -> None:
    read = host_serving_reader(probe=_asking_probe(asked=[]), readers={})
    assert read(repository="example/tooling", capability="gate-readers") is None
    assert read(repository="example/tooling", capability="") is None


def test_a_controller_install_record_with_a_duplicate_key_is_unverified(host: Any) -> None:
    commit = controller_tests.COMMIT
    assert host.read() == f"v1.2.3@{commit}"
    vcs = '{"commit_id": "' + commit + '"}'
    record = '{"vcs_info": ' + vcs + ', "vcs_info": ' + vcs + "}"
    _ = (host.dist / "direct_url.json").write_text(record)
    host.write_process(started_at=time.time() + 60)
    assert host.read() is None


def test_claims_with_a_duplicate_key_or_a_non_finite_number_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "claims.json"
    for text in (
        '{"schema": 1, "schema": 1, "evidence": []}',
        '{"schema": 1, "evidence": [], "n": NaN}',
    ):
        _ = path.write_text(text, encoding="utf-8")
        assert isinstance(load_claims(path=path), Failure)
