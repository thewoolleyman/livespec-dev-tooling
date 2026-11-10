"""Tests for the tag adopt of `just adopt-orchestrator-build` and the adoption lock.

A canary clone adopts a published orchestrator release tag ahead of the
`release` branch. The tag adopt moves only the named clone's project-scope
install record, builds in a throwaway builder home, and never touches the
host's marketplace, marketplace clone or user-scope settings. Every `claude`,
`git ls-remote`, `gh api` and filesystem side effect here is a fake or lives
under a temporary directory.
"""

from __future__ import annotations

import dataclasses
import fcntl
import json
import threading
from collections.abc import Mapping
from pathlib import Path

import pytest
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.fleet import (
    _tag_adopt,
    _tag_adopt_build,
    adopt_orchestrator_build,
    ensure_plugins_fleet,
)
from livespec_dev_tooling.fleet._adoption_lock import adoption_lock_path, holding_adoption_lock
from livespec_dev_tooling.fleet._invocation_failure import BINARY_ABSENT, InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import (
    CommandOutcome,
    CommandResult,
    command_answer,
)
from livespec_dev_tooling.fleet._tag_adopt import TagAdoptHost, tag_adopt
from livespec_dev_tooling.fleet._tag_adopt_build import builder_env, land_build
from livespec_dev_tooling.fleet._tag_adopt_checks import (
    HOLD_PROBE_MODULE,
    AdoptionOutcome,
    is_full_commit,
    json_object,
    marketplace_remote,
)
from livespec_dev_tooling.fleet._tag_adopt_record import (
    RecordCheck,
    differs_only_in_clone,
    verify_record,
    write_record,
)
from livespec_dev_tooling.fleet.adopt_orchestrator_build import adopt_build
from livespec_dev_tooling.fleet.orchestrator_hold_probe import main as hold_probe_main
from livespec_dev_tooling.fleet.plugin_adoption_path import source_adoption_findings

__all__: list[str] = []

_ORCH = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
_MARKET = "livespec-orchestrator-beads-fabro"
_REPO = "thewoolleyman/livespec-orchestrator-beads-fabro"
_URL = f"https://github.com/{_REPO}.git"
_TAG = "v0.311.0"
_TAG_COMMIT = "e" * 40
_REF_COMMIT = "a" * 40
_OTHER_COMMIT = "c" * 40
_SHORT = _TAG_COMMIT[:12]
_NOW = "2026-11-10T05:00:00.000Z"
_REQUIRED = "skills/next/SKILL.md"
_HOOK = {
    "SessionStart": [
        {
            "matcher": "",
            "hooks": [{"type": "command", "command": "mise exec -- just ensure-plugins"}],
        }
    ]
}
_LS_REMOTE = f"{_TAG_COMMIT}\trefs/tags/{_TAG}\n{_REF_COMMIT}\trefs/heads/release\n"
_MARKERS = {
    "release": "/releases/tags/",
    "compare": "/compare/",
    "probe": HOLD_PROBE_MODULE,
    "ls-remote": "ls-remote",
    "marketplace-update": "marketplace update",
    "update": "plugin update",
}


def _ok(*, stdout: str = "") -> CommandOutcome:
    return IOSuccess(CommandResult(returncode=0, stdout=stdout, stderr=""))


def _exit(*, code: int) -> CommandOutcome:
    return IOSuccess(CommandResult(returncode=code, stdout="", stderr="boom"))


def _unperformed() -> CommandOutcome:
    return IOFailure(InvocationNotPerformed(argv=("x",), kind=BINARY_ABSENT, detail="absent"))


def _write(*, path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(value, indent=2), encoding="utf-8")


class _Host:
    """A fake host home, a canary clone, a marketplace remote and a builder."""

    def __init__(self, *, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.plugins_root = tmp_path / "home" / ".claude" / "plugins"
        self.scratch = tmp_path / "scratch"
        self.clone = tmp_path / "clone"
        self.other_clone = tmp_path / "other"
        self.registry = self.plugins_root / "installed_plugins.json"
        self.known = self.plugins_root / "known_marketplaces.json"
        self.user_settings = tmp_path / "home" / ".claude" / "settings.json"
        self.marketplace_clone = self.plugins_root / "marketplaces" / _MARKET / "README.md"
        self.clone_settings: dict[str, object] = {"enabledPlugins": {_ORCH: True}, "hooks": _HOOK}
        _write(path=self.clone / ".claude" / "settings.json", value=self.clone_settings)
        _write(path=self.user_settings, value={"enabledPlugins": {}})
        _write(
            path=self.known,
            value={
                _MARKET: {
                    "source": {"source": "github", "repo": _REPO, "ref": "release"},
                    "installLocation": "/m",
                }
            },
        )
        self.marketplace_clone.parent.mkdir(parents=True)
        _ = self.marketplace_clone.write_text("shallow clone", encoding="utf-8")
        self.records: list[dict[str, object]] = [
            self._record(project=self.clone),
            self._record(project=self.other_clone),
        ]
        _write(
            path=self.registry, value={"version": 2, "plugins": {_ORCH: self.records, "x@x": []}}
        )
        self.answers: dict[str, CommandOutcome] = {
            "release": _ok(stdout=json.dumps({"tag_name": _TAG, "draft": False})),
            "compare": _ok(stdout="ahead\n"),
            "probe": _ok(),
            "ls-remote": _ok(stdout=_LS_REMOTE),
            "marketplace-update": _ok(),
            "update": _ok(),
        }
        self.env_answers: dict[str, CommandOutcome] = {}
        self.builder_sha = _TAG_COMMIT
        self.manifest: object = {"required_paths": [_REQUIRED]}
        self.calls: list[tuple[list[str], Path | None]] = []
        self.env_calls: list[tuple[list[str], Path, dict[str, str]]] = []
        self.sleeps: list[float] = []

    def _record(self, *, project: Path) -> dict[str, object]:
        return {
            "scope": "project",
            "projectPath": str(project),
            "installPath": str(self.plugins_root / "cache" / _MARKET / _MARKET / _REF_COMMIT[:12]),
            "version": _REF_COMMIT[:12],
            "installedAt": "2026-09-09T05:07:00.956Z",
            "lastUpdated": "2026-11-09T14:22:00.195Z",
            "gitCommitSha": _REF_COMMIT,
        }

    def run(self, *, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        self.calls.append((args, cwd))
        joined = " ".join(args)
        return self.answers[next(kind for kind, marker in _MARKERS.items() if marker in joined)]

    def gh(self, *, args: list[str]) -> GhRead:
        answer = command_answer(outcome=self.run(args=["gh", *args]))
        if isinstance(answer, InvocationNotPerformed):
            return GhRead(returncode=127, stdout="", stderr=answer.reason)
        return GhRead(returncode=answer.returncode, stdout=answer.stdout, stderr=answer.stderr)

    def run_env(self, *, args: list[str], cwd: Path, env: Mapping[str, str]) -> CommandOutcome:
        self.env_calls.append((args, cwd, dict(env)))
        if args[:3] == ["claude", "plugin", "install"]:
            self._build(home=Path(env["HOME"]), project=cwd)
        return self.env_answers.get(args[2], _ok())

    def _build(self, *, home: Path, project: Path) -> None:
        build = home / ".claude" / "plugins" / "cache" / _MARKET / _MARKET / self.builder_sha[:12]
        _write(path=build / "cache-manifest.json", value=self.manifest)
        _write(path=build / _REQUIRED, value="skill")
        _write(path=build / ".in_use" / "1234", value=1)
        _write(path=build / ".orphaned_at", value=1)
        record = {
            "scope": "project",
            "projectPath": str(project),
            "installPath": str(build),
            "gitCommitSha": self.builder_sha,
        }
        _write(
            path=home / ".claude" / "plugins" / "installed_plugins.json",
            value={"version": 2, "plugins": {_ORCH: [record]}},
        )

    def tag_host(self) -> TagAdoptHost:
        return TagAdoptHost(
            run=self.run,
            gh=self.gh,
            run_env=self.run_env,
            base_env={
                "PATH": "/usr/bin",
                "HOME": "/host-home",
                "CLAUDE_CONFIG_DIR": "/host-home/.claude",
            },
            plugins_root=self.plugins_root,
            scratch_root=self.scratch,
            read_text=lambda path: path.read_text(encoding="utf-8"),
            sleep=self.sleeps.append,
            settle_seconds=60.0,
            now=lambda: _NOW,
        )

    def adopt(self, *, tag: str = _TAG) -> AdoptionOutcome:
        return tag_adopt(clone=self.clone, tag=tag, host=self.tag_host())

    def clone_record(self) -> dict[str, object]:
        records = json.loads(self.registry.read_text(encoding="utf-8"))["plugins"][_ORCH]
        return next(record for record in records if record["projectPath"] == str(self.clone))

    def target(self) -> Path:
        return self.plugins_root / "cache" / _MARKET / _MARKET / _SHORT

    def untouched(self) -> tuple[bytes, ...]:
        return (
            self.user_settings.read_bytes(),
            self.known.read_bytes(),
            self.marketplace_clone.read_bytes(),
        )

    def kinds(self) -> list[str]:
        return [
            next(kind for kind, marker in _MARKERS.items() if marker in " ".join(args))
            for args, _cwd in self.calls
        ]


def test_a_tag_ahead_of_the_recorded_ref_moves_only_the_named_clones_record(
    *, tmp_path: Path
) -> None:
    host = _Host(tmp_path=tmp_path)
    untouched = host.untouched()

    outcome = host.adopt()

    record = host.clone_record()
    others = json.loads(host.registry.read_text(encoding="utf-8"))["plugins"]
    assert outcome.failure == ""
    assert record == {
        **host.records[0],
        "installPath": str(host.target()),
        "version": _SHORT,
        "gitCommitSha": _TAG_COMMIT,
        "lastUpdated": _NOW,
    }
    assert others[_ORCH][1] == host.records[1]
    assert others["x@x"] == []
    assert host.untouched() == untouched
    assert (host.target() / _REQUIRED).is_file()
    assert not (host.target() / ".in_use").exists()
    assert not (host.target() / ".orphaned_at").exists()
    assert not (host.plugins_root / _tag_adopt_build.STAGING_DIRNAME).exists()
    assert list(host.scratch.iterdir()) == []
    assert host.sleeps == [60.0]
    assert outcome.lines == (
        f"{host.clone} {_ORCH} before={_REF_COMMIT} after={_TAG_COMMIT} (tag {_TAG})",
    )


def test_the_tag_adopt_never_refreshes_the_marketplace_nor_runs_a_plugin_update(
    *, tmp_path: Path
) -> None:
    host = _Host(tmp_path=tmp_path)

    _ = host.adopt()

    assert host.kinds() == ["release", "probe", "ls-remote", "compare"]
    assert host.calls[0][0] == ["gh", "api", f"repos/{_REPO}/releases/tags/{_TAG}"]
    assert host.calls[1] == (
        ["uv", "run", "--no-sync", "python", "-m", HOLD_PROBE_MODULE],
        host.clone,
    )
    assert host.calls[2][0][:3] == ["git", "ls-remote", _URL]
    assert host.calls[3][0] == [
        "gh",
        "api",
        f"repos/{_REPO}/compare/{_REF_COMMIT}...{_TAG_COMMIT}",
        "--jq",
        ".status",
    ]


def test_every_builder_command_runs_with_home_set_to_the_builder_home(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path)

    _ = host.adopt()

    homes = {env["HOME"] for _args, _cwd, env in host.env_calls}
    builder = Path(next(iter(homes)))
    assert len(homes) == 1
    assert builder.parent == host.scratch
    assert all("CLAUDE_CONFIG_DIR" not in env for _args, _cwd, env in host.env_calls)
    assert [args for args, _cwd, _env in host.env_calls] == [
        ["claude", "plugin", "marketplace", "add", f"{_REPO}#{_TAG}"],
        ["git", "init", "-q"],
        ["claude", "plugin", "install", _ORCH, "-s", "project"],
    ]
    assert host.env_calls[2][1] == builder / "project"
    assert builder_env(base={"A": "1", "CLAUDE_CONFIG_DIR": "/c"}, home=builder) == {
        "A": "1",
        "HOME": str(builder),
    }


def test_an_identical_comparison_is_accepted(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path)
    host.answers["compare"] = _ok(stdout="identical\n")

    assert host.adopt().failure == ""


@pytest.mark.parametrize(
    "answer", [_ok(stdout="behind\n"), _ok(stdout="diverged\n"), _exit(code=1), _unperformed()]
)
def test_a_tag_not_identical_to_or_ahead_of_the_ref_moves_nothing_and_names_both_commits(
    *, tmp_path: Path, answer: CommandOutcome
) -> None:
    host = _Host(tmp_path=tmp_path)
    host.answers["compare"] = answer
    before = host.registry.read_bytes()

    outcome = host.adopt()

    assert _TAG_COMMIT in outcome.failure
    assert _REF_COMMIT in outcome.failure
    assert host.registry.read_bytes() == before
    assert host.env_calls == []


@pytest.mark.parametrize(
    "answer",
    [
        _exit(code=1),
        _unperformed(),
        _ok(stdout=json.dumps({"tag_name": _TAG, "draft": True})),
        _ok(stdout="not json"),
    ],
)
def test_an_argument_naming_no_published_release_is_refused_naming_it(
    *, tmp_path: Path, answer: CommandOutcome
) -> None:
    host = _Host(tmp_path=tmp_path)
    host.answers["release"] = answer
    before = host.registry.read_bytes()

    outcome = host.adopt()

    assert repr(_TAG) in outcome.failure
    assert host.registry.read_bytes() == before
    assert host.kinds() == ["release"]


def test_an_argument_that_is_neither_a_commit_nor_a_tag_shape_is_refused_without_a_read(
    *, tmp_path: Path
) -> None:
    host = _Host(tmp_path=tmp_path)

    outcome = adopt_orchestrator_build.adopt_named_build(
        clone=host.clone,
        build="main~1",
        run=host.run,
        read_registry=lambda: host.registry.read_text(encoding="utf-8"),
        read_known_marketplaces=lambda: host.known.read_text(encoding="utf-8"),
        tag_host=host.tag_host(),
    )

    assert "'main~1' is neither a full commit id nor a published release tag" in outcome.failure
    assert host.calls == []


def test_a_full_commit_id_routes_to_the_full_commit_adopt_step(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path)

    outcome = adopt_orchestrator_build.adopt_named_build(
        clone=host.clone,
        build=_OTHER_COMMIT,
        run=host.run,
        read_registry=lambda: host.registry.read_text(encoding="utf-8"),
        read_known_marketplaces=lambda: None,
        tag_host=host.tag_host(),
    )

    assert host.kinds() == ["marketplace-update"]
    assert "known_marketplaces.json" in outcome.failure


def test_the_full_commit_form_given_a_tag_runs_nothing_and_names_the_argument(
    *, tmp_path: Path
) -> None:
    host = _Host(tmp_path=tmp_path)

    outcome = adopt_build(
        clone=host.clone,
        build=_TAG,
        run=host.run,
        read_registry=lambda: None,
        read_known_marketplaces=lambda: None,
    )

    assert repr(_TAG) in outcome.failure
    assert host.calls == []
    assert is_full_commit(build=f" {_TAG_COMMIT.upper()} ")


@pytest.mark.parametrize("answer", [_exit(code=1), _unperformed()])
def test_a_clone_whose_package_fails_the_hold_probe_is_refused_naming_it(
    *, tmp_path: Path, answer: CommandOutcome
) -> None:
    host = _Host(tmp_path=tmp_path)
    host.answers["probe"] = answer

    outcome = host.adopt()

    assert outcome.failure.startswith(f"{host.clone}: ")
    assert "hold" in outcome.failure
    assert host.env_calls == []


def test_the_hold_probe_module_the_tag_adopt_runs_exits_zero_from_this_package() -> None:
    assert HOLD_PROBE_MODULE == "livespec_dev_tooling.fleet.orchestrator_hold_probe"
    assert hold_probe_main() == 0


@pytest.mark.parametrize(
    "hooks",
    [
        {},
        {"SessionStart": "junk"},
        {
            "SessionStart": [
                "junk",
                {"hooks": "junk"},
                {
                    "hooks": [
                        "junk",
                        {"type": "command"},
                        {"command": "mise exec -- just ensure-plugins-fleet x"},
                    ]
                },
            ]
        },
    ],
)
def test_a_clone_with_no_session_start_hook_running_ensure_plugins_is_refused_naming_it(
    *, tmp_path: Path, hooks: dict[str, object]
) -> None:
    host = _Host(tmp_path=tmp_path)
    _write(
        path=host.clone / ".claude" / "settings.json", value={**host.clone_settings, "hooks": hooks}
    )

    outcome = host.adopt()

    assert outcome.failure.startswith(f"{host.clone}: ")
    assert "SessionStart" in outcome.failure
    assert "probe" not in host.kinds()


def test_a_missing_clone_and_a_clone_not_enabling_the_plugin_are_refused(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path)
    missing = tag_adopt(clone=tmp_path / "absent", tag=_TAG, host=host.tag_host())
    _write(
        path=host.clone / ".claude" / "settings.json",
        value={"enabledPlugins": {"x@x": True}, "hooks": _HOOK},
    )

    disabled = host.adopt()

    assert str(tmp_path / "absent") in missing.failure
    assert "does not enable" in disabled.failure


@pytest.mark.parametrize("count", [0, 2])
def test_a_clone_without_exactly_one_project_record_is_refused(
    *, tmp_path: Path, count: int
) -> None:
    host = _Host(tmp_path=tmp_path)
    records = [host.records[0]] * count + [host.records[1]]
    _write(path=host.registry, value={"version": 2, "plugins": {_ORCH: records}})

    outcome = host.adopt()

    assert f"has {count} project-scope" in outcome.failure
    assert host.env_calls == []


def test_a_host_without_a_registry_or_a_marketplace_record_is_refused(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path)
    host.known.unlink()
    no_marketplace = host.adopt()
    host.registry.unlink()

    no_registry = host.adopt()

    assert "known_marketplaces.json records no remote" in no_marketplace.failure
    assert "has 0 project-scope" in no_registry.failure


@pytest.mark.parametrize(
    ("answer", "cause"),
    [
        (_exit(code=128), "git ls-remote exited 128"),
        (_unperformed(), "binary_absent"),
        (_ok(stdout=f"{_REF_COMMIT}\trefs/heads/release\n"), f"no commit for tag {_TAG}"),
    ],
)
def test_a_remote_that_does_not_name_both_commits_moves_nothing(
    *, tmp_path: Path, answer: CommandOutcome, cause: str
) -> None:
    host = _Host(tmp_path=tmp_path)
    host.answers["ls-remote"] = answer

    outcome = host.adopt()

    assert cause in outcome.failure
    assert "nothing was moved" in outcome.failure
    assert host.env_calls == []


def test_an_annotated_tag_resolves_to_its_peeled_commit_and_a_tag_ref_is_read(
    *, tmp_path: Path
) -> None:
    host = _Host(tmp_path=tmp_path)
    _write(
        path=host.known,
        value={
            _MARKET: {"source": {"source": "git", "url": "https://forge/o.git", "ref": "v0.310.0"}}
        },
    )
    listing = f"{'f' * 40}\trefs/tags/{_TAG}\n{_TAG_COMMIT}\trefs/tags/{_TAG}^{{}}\n{_REF_COMMIT}\trefs/tags/v0.310.0\n"
    host.answers["ls-remote"] = _ok(stdout=listing)

    outcome = host.adopt()

    assert outcome.failure == ""
    assert host.calls[2][0][2] == "https://forge/o.git"
    assert host.calls[3][0][2].endswith(f"/compare/{_REF_COMMIT}...{_TAG_COMMIT}")


def test_a_marketplace_record_without_a_ref_or_a_remote_is_unreadable() -> None:
    def known(source: dict[str, object]) -> str:
        return json.dumps({_MARKET: {"source": source}})

    assert marketplace_remote(known_marketplaces=known({"source": "github", "repo": _REPO})) is None
    assert (
        marketplace_remote(known_marketplaces=known({"source": "directory", "ref": "release"}))
        is None
    )
    assert marketplace_remote(known_marketplaces=None) is None
    assert json_object(text="[1]") == {}


@pytest.mark.parametrize(
    ("step", "answer"), [("marketplace", _exit(code=1)), ("install", _unperformed())]
)
def test_a_failed_builder_command_moves_nothing(
    *, tmp_path: Path, step: str, answer: CommandOutcome
) -> None:
    host = _Host(tmp_path=tmp_path)
    host.env_answers[step] = answer
    before = host.registry.read_bytes()

    outcome = host.adopt()

    assert "nothing was moved" in outcome.failure
    assert host.registry.read_bytes() == before
    assert not host.target().exists()
    assert list(host.scratch.iterdir()) == []


def test_a_builder_install_at_another_commit_moves_nothing(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path)
    host.builder_sha = _OTHER_COMMIT

    outcome = host.adopt()

    assert (
        f"the builder installed {_OTHER_COMMIT}, not the tag's commit {_TAG_COMMIT}"
        in outcome.failure
    )
    assert host.clone_record() == host.records[0]


@pytest.mark.parametrize(
    "manifest", [{}, {"required_paths": ["/etc/passwd"]}, {"required_paths": ["../x"]}]
)
def test_a_build_without_a_usable_cache_manifest_moves_nothing(
    *, tmp_path: Path, manifest: object
) -> None:
    host = _Host(tmp_path=tmp_path)
    host.manifest = manifest

    outcome = host.adopt()

    assert "cache-manifest.json" in outcome.failure
    assert not host.target().exists()
    assert host.clone_record() == host.records[0]


def test_a_complete_target_is_left_in_place_and_a_husk_is_replaced(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path)
    _write(path=host.target() / _REQUIRED, value="kept")
    _write(path=host.plugins_root / _tag_adopt_build.STAGING_DIRNAME / "staging" / "stale", value=1)
    kept = host.adopt()
    kept_text = (host.target() / _REQUIRED).read_text(encoding="utf-8")
    (host.target() / _REQUIRED).unlink()
    _write(path=host.target() / ".orphaned_at", value=1)
    _write(path=host.registry, value={"version": 2, "plugins": {_ORCH: host.records}})

    replaced = host.adopt()

    assert kept.failure == ""
    assert kept_text == json.dumps("kept", indent=2)
    assert replaced.failure == ""
    assert (host.target() / _REQUIRED).read_text(encoding="utf-8") == json.dumps("skill", indent=2)
    assert not (host.target() / ".orphaned_at").exists()
    assert not (host.plugins_root / _tag_adopt_build.STAGING_DIRNAME).exists()


def test_a_landed_copy_lacking_a_required_path_writes_no_record(*, tmp_path: Path) -> None:
    source = tmp_path / "build"
    _write(path=source / "cache-manifest.json", value={"required_paths": [".orphaned_at"]})
    _write(path=source / ".orphaned_at", value=1)

    landed = land_build(source=source, commit=_TAG_COMMIT, plugins_root=tmp_path / "plugins")

    assert "lacks a required path" in landed.failure
    assert landed.target == tmp_path / "plugins" / "cache" / _MARKET / _MARKET / _SHORT


def test_a_registry_that_keeps_changing_under_the_write_is_refused_through_the_tag_adopt(
    *, tmp_path: Path
) -> None:
    host = _Host(tmp_path=tmp_path)
    ticks: list[int] = []

    def read_text(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        if path == host.registry and host.target().exists():
            ticks.append(1)
            other = {**host.records[1], "lastUpdated": f"tick {len(ticks)}"}
            _write(
                path=host.registry,
                value={"version": 2, "plugins": {_ORCH: [host.records[0], other]}},
            )
        return text

    outcome = tag_adopt(
        clone=host.clone, tag=_TAG, host=dataclasses.replace(host.tag_host(), read_text=read_text)
    )

    assert "kept changing under the write; re-applied 3 times" in outcome.failure
    assert host.clone_record() == host.records[0]
    assert len(ticks) == 6


def test_a_concurrent_change_is_re_applied_onto_and_kept(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path)
    other = {**host.records[1], "lastUpdated": "another writer"}
    reads: list[str] = []

    def read_text(path: Path) -> str:
        reads.append(path.read_text(encoding="utf-8"))
        if len(reads) == 1:
            _write(
                path=host.registry,
                value={"version": 2, "plugins": {_ORCH: [host.records[0], other]}},
            )
        return reads[-1]

    failure = write_record(
        registry_path=host.registry,
        clone=str(host.clone),
        fields={"gitCommitSha": _TAG_COMMIT},
        read_text=read_text,
    )

    records = json.loads(host.registry.read_text(encoding="utf-8"))["plugins"][_ORCH]
    assert failure == ""
    assert records == [{**host.records[0], "gitCommitSha": _TAG_COMMIT}, other]
    assert not host.registry.with_name("installed_plugins.json.livespec-adopt.tmp").exists()


def test_a_concurrent_removal_of_the_clones_record_is_refused(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path)
    reads: list[str] = []

    def read_text(path: Path) -> str:
        reads.append(path.read_text(encoding="utf-8"))
        _write(path=host.registry, value={"version": 2, "plugins": {_ORCH: [host.records[1]]}})
        return reads[-1]

    failure = write_record(
        registry_path=host.registry, clone=str(host.clone), fields={}, read_text=read_text
    )

    assert "has 0 project-scope" in failure


def test_the_written_file_differs_from_the_read_only_in_the_clones_record() -> None:
    clone = {"scope": "project", "projectPath": "/c", "gitCommitSha": _REF_COMMIT}
    other = {"scope": "project", "projectPath": "/o", "gitCommitSha": _REF_COMMIT}
    before = {"plugins": {_ORCH: [clone, other, "junk"]}}

    assert differs_only_in_clone(
        before=before,
        after={"plugins": {_ORCH: [{**clone, "gitCommitSha": "x"}, other, "junk"]}},
        clone="/c",
    )
    assert not differs_only_in_clone(
        before=before,
        after={"plugins": {_ORCH: [clone, {**other, "gitCommitSha": "x"}, "junk"]}},
        clone="/c",
    )


def test_a_record_reverted_after_the_settle_period_exits_non_zero_naming_the_cause(
    *, tmp_path: Path
) -> None:
    host = _Host(tmp_path=tmp_path)

    def revert(seconds: float) -> None:
        host.sleeps.append(seconds)
        _write(path=host.registry, value={"version": 2, "plugins": {_ORCH: host.records}})

    outcome = tag_adopt(
        clone=host.clone, tag=_TAG, host=dataclasses.replace(host.tag_host(), sleep=revert)
    )

    assert "re-read after a 60 s settle period" in outcome.failure
    assert f"names {_REF_COMMIT}, not the tag's commit {_TAG_COMMIT}" in outcome.failure
    assert host.sleeps == [60.0]
    assert outcome.lines == (
        f"{host.clone} {_ORCH} before={_REF_COMMIT} after={_REF_COMMIT} (tag {_TAG})",
    )


def test_the_immediate_re_read_checks_the_record_count_and_the_required_paths(
    *, tmp_path: Path
) -> None:
    check = RecordCheck(clone="/c", commit=_TAG_COMMIT, required=(_REQUIRED,))
    record = {
        "scope": "project",
        "projectPath": "/c",
        "gitCommitSha": _TAG_COMMIT,
        "installPath": str(tmp_path),
    }
    texts = {
        "none": json.dumps({"plugins": {_ORCH: []}}),
        "husk": json.dumps({"plugins": {_ORCH: [record]}}),
    }

    sleeps: list[float] = []

    def verify(text: str) -> str:
        return verify_record(
            registry_path=tmp_path / "r.json",
            check=check,
            read_text=lambda _path: text,
            sleep=sleeps.append,
            settle_seconds=60.0,
        )

    assert (
        verify(texts["none"])
        == "re-read immediately after the write: /c has 0 project-scope install records"
    )
    assert (
        verify(texts["husk"])
        == f"re-read immediately after the write: {tmp_path} no longer carries every required path"
    )
    assert sleeps == []


def test_the_adoption_lock_is_one_fixed_path_held_exclusively_for_the_whole_run(
    *, tmp_path: Path
) -> None:
    path = adoption_lock_path(home=tmp_path)
    held: list[bool] = []

    def body() -> int:
        with path.open("a", encoding="utf-8") as other, pytest.raises(BlockingIOError):
            fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        held.append(True)
        return 7

    waits: list[int] = []
    status = holding_adoption_lock(path=path, body=body, on_wait=lambda: waits.append(1))

    with path.open("a", encoding="utf-8") as after:
        fcntl.flock(after.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert (
        path
        == tmp_path / ".local" / "state" / "livespec-dev-tooling" / "orchestrator-adoption.lock"
    )
    assert status == 7
    assert held == [True]
    assert waits == []


def test_a_second_adoption_waits_for_the_first_to_end(*, tmp_path: Path) -> None:
    path = adoption_lock_path(home=tmp_path)
    path.parent.mkdir(parents=True)
    waiting = threading.Event()
    order: list[str] = []
    with path.open("a", encoding="utf-8") as first:
        fcntl.flock(first.fileno(), fcntl.LOCK_EX)
        second = threading.Thread(
            target=lambda: order.append(
                str(holding_adoption_lock(path=path, body=lambda: len(order), on_wait=waiting.set))
            )
        )
        second.start()
        assert waiting.wait(timeout=10)
        order.append("first ends")
    second.join(timeout=10)

    assert order == ["first ends", "1"]


def test_each_entrypoint_takes_the_lock_once_and_the_in_process_steps_never_do() -> None:
    def source(module: object) -> str:
        return Path(str(getattr(module, "__file__", ""))).read_text(encoding="utf-8")

    assert source(adopt_orchestrator_build).count("holding_adoption_lock(") == 1
    assert source(ensure_plugins_fleet).count("holding_adoption_lock(") == 1
    assert "holding_adoption_lock" not in source(_tag_adopt)


def test_the_builder_install_is_a_sanctioned_adoption_path() -> None:
    path = "livespec_dev_tooling/fleet/_tag_adopt_build.py"
    text = Path(str(_tag_adopt_build.__file__)).read_text(encoding="utf-8")

    assert source_adoption_findings(path=path, text=text) == ()
