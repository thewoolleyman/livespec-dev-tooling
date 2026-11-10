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

    def read(self, *, name: str = "tooling") -> str | None:
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


def test_a_consumer_running_its_own_clean_source_serves_its_head(fleet: _Fleet) -> None:
    clone = fleet.root / "tooling"
    _ = fleet.install(name="tooling", direct_url=_editable(clone=clone))
    fleet.git["rev-parse"] = _text_ok(COMMIT + "\n")
    fleet.git["status"] = _text_ok("")
    assert fleet.read() == COMMIT
    assert {"git", "-C", str(clone)} <= set(fleet.asked[0])


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
    assert fleet.read() is None


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


def _workflow(*uses: str) -> str:
    steps = "".join(f"      - uses: {u}\n" for u in uses)
    return f"name: ci\njobs:\n  gate:\n    runs-on: x\n    steps:\n{steps}"


class _Remote:
    def __init__(self, *, ci: str | None, remote: dict[str, str] | None = None) -> None:
        self.ci = ci
        self.remote = remote or {}
        self.asked: list[list[str]] = []
        self.ls_remote_status = 0
        self.ls_remote_runs = True

    def probe(self) -> HostProbe:
        def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
            _ = cwd
            self.asked.append(args)
            if "clone" in args:
                return IOSuccess(CommandResult(returncode=0, stdout="", stderr=""))
            if "show" in args:
                if self.ci is None:
                    return IOSuccess(
                        CommandResult(returncode=128, stdout="", stderr="no such path")
                    )
                return IOSuccess(CommandResult(returncode=0, stdout=self.ci, stderr=""))
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

    def read(self) -> str | None:
        return read_templates(probe=self.probe(), repository="thewoolleyman/consumer")


def test_a_pinned_commit_is_the_serving_build_and_is_read_from_the_remote_default_branch() -> None:
    remote = _Remote(ci=_workflow("actions/checkout@v5", f"{TEMPLATE}@{SHA}"))
    assert remote.read() == f"livespec-dev-tooling@{SHA}"
    shown = next(a for a in remote.asked if "show" in a)
    assert shown[-1] == "HEAD:.github/workflows/ci.yml"
    assert any("thewoolleyman/consumer.git" in part for a in remote.asked for part in a)
    assert not any("ls-remote" in a for a in remote.asked)


def test_a_pinned_tag_is_resolved_to_the_commit_it_points_at() -> None:
    remote = _Remote(
        ci=_workflow(f"{TEMPLATE}@v1.2.3"),
        remote={"refs/tags/v1.2.3": "1" * 40, "refs/tags/v1.2.3^{}": TAG_SHA},
    )
    assert remote.read() == f"livespec-dev-tooling@{TAG_SHA}"


def test_a_lightweight_tag_resolves_to_its_own_commit() -> None:
    remote = _Remote(ci=_workflow(f"{TEMPLATE}@v1.2.3"), remote={"refs/tags/v1.2.3": TAG_SHA})
    assert remote.read() == f"livespec-dev-tooling@{TAG_SHA}"


@pytest.mark.parametrize(
    "remote",
    [{}, {"refs/tags/v1.2.3": "short"}, {"refs/tags/other": TAG_SHA}],
)
def test_a_ref_that_names_no_tag_is_unverified(remote: dict[str, str]) -> None:
    assert _Remote(ci=_workflow(f"{TEMPLATE}@v1.2.3"), remote=remote).read() is None


def test_an_unanswered_tag_lookup_is_unverified() -> None:
    remote = _Remote(ci=_workflow(f"{TEMPLATE}@v1.2.3"), remote={"refs/tags/v1.2.3": TAG_SHA})
    remote.ls_remote_status = 128
    assert remote.read() is None


def test_a_tag_lookup_that_cannot_run_is_unverified() -> None:
    remote = _Remote(ci=_workflow(f"{TEMPLATE}@v1.2.3"), remote={"refs/tags/v1.2.3": TAG_SHA})
    remote.ls_remote_runs = False
    assert remote.read() is None


def test_pins_that_disagree_are_unverified() -> None:
    ci = _workflow(f"{TEMPLATE}@{SHA}", f"{TEMPLATE}@{TAG_SHA}")
    assert _Remote(ci=ci).read() is None


def test_the_same_pin_repeated_is_one_serving_build() -> None:
    ci = _workflow(f"{TEMPLATE}@{SHA}", f"{TEMPLATE}@{SHA}")
    assert _Remote(ci=ci).read() == f"livespec-dev-tooling@{SHA}"


def test_only_this_librarys_templates_count_as_pins() -> None:
    ci = _workflow("thewoolleyman/livespec/.github/workflows/x.yml@v9.9.9", "actions/cache@v5")
    assert _Remote(ci=ci).read() is None


def test_a_consumer_running_its_own_local_workflows_serves_its_default_branch_commit() -> None:
    remote = _Remote(
        ci=_workflow("./.github/actions/budget", "actions/checkout@v5"),
        remote={"HEAD": SELF_SHA},
    )
    assert remote.read() == f"consumer@{SELF_SHA}"
    lookup = next(a for a in remote.asked if "ls-remote" in a)
    assert any("thewoolleyman/consumer.git" in part for part in lookup)


def test_a_local_workflow_consumer_with_an_unreadable_head_is_unverified() -> None:
    assert _Remote(ci=_workflow("./.github/actions/budget"), remote={"HEAD": "bad"}).read() is None


def test_a_consumer_with_no_ci_or_no_template_use_is_unverified() -> None:
    assert _Remote(ci=None).read() is None
    assert _Remote(ci=_workflow("actions/checkout@v5")).read() is None


def test_an_unreachable_remote_is_unverified() -> None:
    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        _ = cwd
        return IOFailure(InvocationNotPerformed(argv=tuple(args), kind=BINARY_ABSENT, detail="x"))

    probe = HostProbe(clones_root=None, proc_root=Path("/proc"), home=Path("/"), run=run)
    assert read_templates(probe=probe, repository="thewoolleyman/consumer") is None


# --- recovery authorization ---
CONTROLLER = "v1.2.3@" + "c" * 40
APP = {"actor_id": 987, "actor_type": "Integration", "bypass_mode": "always"}
BASE = "repos/example/tooling/rulesets"


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
    assert forge.asked[0] == ["api", BASE]


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
