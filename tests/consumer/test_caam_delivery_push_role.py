"""Consumer-tier proof for the caam role holder's push-service play and the launch probe.

Runs the caam_delivery_push role, and shared_credentials_host's value-free probe
tasks, with the same pinned ``ansible-core`` as ``just ansible-drift`` against local
fixtures: a fixture git origin and checkout, a stand-in install command and unit
state, and a stand-in launcher. Nothing touches a real host, service or credential.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLES = _ANSIBLE / "roles"
_HOST = "fixture-host"
_TIMEOUT_SECONDS = 600
_SWEEP = "overseer/remote_control_sweep.py"
_SECRET = "fixture-secret-value-never-printed"


def _ansible_core_pin() -> str:
    recipe = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    match = re.search(r"^ansible-drift \*args:\n(?P<body>(?:    .*\n)+)", recipe, re.MULTILINE)
    assert match is not None, "justfile must define the ansible-drift recipe"
    pin = re.search(r"ansible-core==[0-9][0-9A-Za-z.]*", match["body"])
    assert pin is not None, "ansible-drift must pin ansible-core"
    return pin[0]


def _git(*args: str, cwd: Path) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _commit(*, work: Path, text: str) -> str:
    sweep = work / _SWEEP
    sweep.parent.mkdir(parents=True, exist_ok=True)
    _ = sweep.write_text(text, encoding="utf-8")
    _ = _git("add", "-A", cwd=work)
    _ = _git("commit", "-q", "-m", text.strip(), cwd=work)
    return _git("rev-parse", "HEAD", cwd=work)


def _fixture(*, root: Path) -> tuple[Path, str, str, str]:
    """A bare origin with commits A < B < C, and a checkout cloned at A."""
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "-q", "-b", "master", cwd=seed)
    first = _commit(work=seed, text="sweep one\n")
    second = _commit(work=seed, text="sweep two\n")
    third = _commit(work=seed, text="sweep three\n")
    origin = root / "origin.git"
    _ = _git("clone", "-q", "--bare", str(seed), str(origin), cwd=root)
    checkout = root / "checkout"
    _ = _git("clone", "-q", str(origin), str(checkout), cwd=root)
    _ = _git("reset", "-q", "--hard", first, cwd=checkout)
    return checkout, first, second, third


def _environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    } | {
        "ANSIBLE_NOCOWS": "1",
        "ANSIBLE_RETRY_FILES_ENABLED": "False",
        "ANSIBLE_ROLES_PATH": str(_ROLES),
    }


def _playbook(*, root: Path, play: str, variables: dict[str, object]) -> str:
    inventory = root / "inventory.yml"
    _ = inventory.write_text(
        f"---\nall:\n  hosts:\n    {_HOST}:\n      ansible_connection: local\n", encoding="utf-8"
    )
    path = root / "play.yml"
    _ = path.write_text(play, encoding="utf-8")
    command = ["uvx", "--from", _ansible_core_pin(), "ansible-playbook"]
    command += ["-i", str(inventory), "-e", json.dumps(variables), str(path)]
    done = subprocess.run(
        command,
        cwd=root,
        env=_environment(),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    return f"rc={done.returncode}\n{done.stdout}{done.stderr}"


_CAAM_VERSION = "0.1.25"
_CAAM_BINARY = (
    "#!/bin/sh\n"
    'echo "$@" >> "$(dirname "$0")/caam-invocations"\n'
    'echo "caam version {version} (fixture)"\n'
)


def _caam_asset(*, root: Path, version: str = _CAAM_VERSION) -> tuple[Path, str]:
    """A stand-in release asset: a shell script that reports a version and logs its argv."""
    asset = root / "release" / "caam"
    asset.parent.mkdir(parents=True, exist_ok=True)
    _ = asset.write_text(_CAAM_BINARY.replace("{version}", version), encoding="utf-8")
    return asset, hashlib.sha256(asset.read_bytes()).hexdigest()


def _caam_variables(*, root: Path, sha256: str | None = None) -> dict[str, object]:
    asset, digest = _caam_asset(root=root)
    return {
        "caam_delivery_push_caam_version": _CAAM_VERSION,
        "caam_delivery_push_caam_url": asset.as_uri(),
        "caam_delivery_push_caam_sha256": sha256 or digest,
        "caam_delivery_push_caam_dest": str(root / "home" / ".local" / "bin" / "caam"),
    }


def _deploy(
    *,
    root: Path,
    checkout: Path,
    ref: str,
    unit: str = "active",
    caam: dict[str, object] | None = None,
) -> tuple[str, Path]:
    marker = root / "installs"
    variables: dict[str, object] = {
        **(caam if caam is not None else _caam_variables(root=root)),
        "caam_delivery_push_ref": ref,
        "caam_delivery_push_checkout": str(checkout),
        "caam_delivery_push_install_command": ["sh", "-c", f"echo install >> {marker}"],
        "caam_delivery_push_active_command": ["printf", unit],
        "caam_delivery_push_stamp": str(root / "state" / "deployed"),
    }
    play = (
        "---\n- name: fixture\n  hosts: all\n  gather_facts: false\n"
        "  roles:\n    - role: caam_delivery_push\n"
    )
    return _playbook(root=root, play=play, variables=variables), marker


def _changed(*, output: str) -> int:
    assert output.startswith("rc=0\n"), output
    recap = re.search(rf"^{_HOST}\s*:.*?\bchanged=(?P<count>\d+)", output, re.MULTILINE)
    assert recap is not None, output
    return int(recap["count"])


def _installs(*, marker: Path) -> int:
    return len(marker.read_text(encoding="utf-8").splitlines()) if marker.exists() else 0


def test_an_apply_moves_the_checkout_installs_once_and_a_second_apply_changes_nothing(
    *, tmp_path: Path
) -> None:
    checkout, _, second, _ = _fixture(root=tmp_path)

    output, marker = _deploy(root=tmp_path, checkout=checkout, ref=second)

    assert _changed(output=output) > 0
    assert _git("rev-parse", "HEAD", cwd=checkout) == second
    assert _installs(marker=marker) == 1
    pinned = re.search(r"pinned_sweep_sha256=(\w+)", output)
    deployed = re.search(r"sweep_sha256=(\w+)", output)
    assert pinned is not None and deployed is not None, output
    assert pinned[1] == deployed[1]

    again, _ = _deploy(root=tmp_path, checkout=checkout, ref=second)
    assert _changed(output=again) == 0
    assert _installs(marker=marker) == 1


def _preinstall_caam(*, root: Path) -> None:
    asset, _ = _caam_asset(root=root)
    dest = root / "home" / ".local" / "bin" / "caam"
    dest.parent.mkdir(parents=True, exist_ok=True)
    _ = dest.write_bytes(asset.read_bytes())
    dest.chmod(0o755)


def _stamp(*, root: Path, commit: str) -> None:
    path = root / "state" / "deployed"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(f"{commit}\n", encoding="utf-8")


def test_a_checkout_past_the_pin_installed_from_its_head_is_left_alone(*, tmp_path: Path) -> None:
    checkout, _, second, third = _fixture(root=tmp_path)
    _ = _git("merge", "-q", "--ff-only", third, cwd=checkout)
    _stamp(root=tmp_path, commit=third)
    _preinstall_caam(root=tmp_path)

    output, marker = _deploy(root=tmp_path, checkout=checkout, ref=second)

    assert _changed(output=output) == 0
    assert _git("rev-parse", "HEAD", cwd=checkout) == third
    assert _installs(marker=marker) == 0


@pytest.mark.parametrize("stamped", ["absent", "stale"])
def test_a_checkout_that_contains_the_pin_but_was_not_installed_from_is_installed(
    *, tmp_path: Path, stamped: str
) -> None:
    """The running service can be older than its checkout: the stamp, not the move, decides."""
    checkout, first, second, third = _fixture(root=tmp_path)
    _ = _git("merge", "-q", "--ff-only", third, cwd=checkout)
    if stamped == "stale":
        _stamp(root=tmp_path, commit=first)

    output, marker = _deploy(root=tmp_path, checkout=checkout, ref=second)

    assert _changed(output=output) > 0
    assert _git("rev-parse", "HEAD", cwd=checkout) == third
    assert _installs(marker=marker) == 1
    stamp = (tmp_path / "state" / "deployed").read_text(encoding="utf-8")
    assert stamp == f"{third}\n"
    again, _ = _deploy(root=tmp_path, checkout=checkout, ref=second)
    assert _changed(output=again) == 0
    assert _installs(marker=marker) == 1


def test_a_checkout_with_uncommitted_changes_is_refused_and_left_untouched(
    *, tmp_path: Path
) -> None:
    checkout, first, second, _ = _fixture(root=tmp_path)
    _ = (checkout / "local-edit.txt").write_text("draft\n", encoding="utf-8")

    output, marker = _deploy(root=tmp_path, checkout=checkout, ref=second)

    assert not output.startswith("rc=0\n"), output
    assert "uncommitted changes" in output
    assert _git("rev-parse", "HEAD", cwd=checkout) == first
    assert _installs(marker=marker) == 0


@pytest.mark.parametrize("ref", ["", "6fa9b40f", "master", "G" * 40])
def test_a_ref_that_is_not_a_full_commit_sha_is_refused_before_any_change(
    *, tmp_path: Path, ref: str
) -> None:
    checkout, first, _, _ = _fixture(root=tmp_path)

    output, marker = _deploy(root=tmp_path, checkout=checkout, ref=ref)

    assert not output.startswith("rc=0\n"), output
    assert _git("rev-parse", "HEAD", cwd=checkout) == first
    assert _installs(marker=marker) == 0


def test_a_service_that_is_not_active_fails_the_converge(*, tmp_path: Path) -> None:
    checkout, _, second, _ = _fixture(root=tmp_path)

    output, _ = _deploy(root=tmp_path, checkout=checkout, ref=second, unit="inactive")

    assert not output.startswith("rc=0\n"), output


def test_the_play_selects_the_role_holder_by_its_inventory_group() -> None:
    """Moving the role is a group-membership change; no play names a machine."""
    play = yaml.safe_load((_ANSIBLE / "caam-role-holder.yml").read_text(encoding="utf-8"))
    assert [entry["hosts"] for entry in play] == [
        "{{ caam_role_holder_group | default('caam_role_holder') }}"
    ]
    inventory = yaml.safe_load((_ANSIBLE / "inventory" / "legacy.yml").read_text(encoding="utf-8"))
    holders = inventory["all"]["children"]["caam_role_holder"]["hosts"]
    assert len(holders) == 1
    pinned = yaml.safe_load(
        (_ANSIBLE / "inventory" / "group_vars" / "caam_role_holder.yml").read_text(encoding="utf-8")
    )
    assert re.fullmatch(r"[0-9a-f]{40}", pinned["caam_delivery_push_ref"])


def test_the_staged_next_holder_is_a_separate_group_never_a_second_holder() -> None:
    """The holder group stays one entry; the next holder is selected only by an explicit group."""
    inventory = yaml.safe_load((_ANSIBLE / "inventory" / "legacy.yml").read_text(encoding="utf-8"))
    children = inventory["all"]["children"]
    assert set(children["caam_role_holder"]["hosts"]) == {"vps"}
    staged = children["caam_role_holder_next"]["hosts"]
    assert len(staged) == 1
    entry = next(iter(staged.values()))
    assert entry["caam_role_holder_machine_id"] == "0cba40e2d13946e8a1605ab5f0236046"
    assert "REFUSED" in entry["ansible_connection"]
    group_vars = _ANSIBLE / "inventory" / "group_vars"
    link = group_vars / "caam_role_holder_next.yml"
    assert link.is_symlink()
    assert link.resolve() == (group_vars / "caam_role_holder.yml").resolve()


def _probe(*, root: Path, child_env: dict[str, str], names: list[str]) -> str:
    launcher = root / "launcher.py"
    _ = launcher.write_text(
        "import os, sys\n"
        "argv = sys.argv[sys.argv.index('--') + 1:]\n"
        f"env = {{k: v for k, v in os.environ.items() if not k.startswith('AWS_')}}\n"
        f"env.update({child_env!r})\n"
        "os.execvpe(argv[0], argv, env)\n",
        encoding="utf-8",
    )
    variables: dict[str, object] = {
        "shared_credentials_host_artifact_dest": str(launcher),
        "shared_credentials_host_manifest_dest": str(root / "manifest.json"),
        "shared_credentials_host_probe_consumer": "fixture-consumer",
        "shared_credentials_host_probe_names": names,
    }
    play = (
        "---\n- name: fixture\n  hosts: all\n  gather_facts: false\n  tasks:\n"
        "    - name: probe\n      ansible.builtin.include_role:\n"
        "        name: shared_credentials_host\n        tasks_from: probe.yml\n"
    )
    return _playbook(root=root, play=play, variables=variables)


_NAMES = ["FIXTURE_APP_ID", "FIXTURE_PRIVATE_KEY"]


def test_the_probe_reports_names_and_byte_counts_and_never_a_value(*, tmp_path: Path) -> None:
    output = _probe(
        root=tmp_path,
        child_env={"FIXTURE_APP_ID": "12345", "FIXTURE_PRIVATE_KEY": _SECRET},
        names=_NAMES,
    )

    assert _changed(output=output) == 0
    assert "name=FIXTURE_APP_ID bytes=6" in output
    assert f"name=FIXTURE_PRIVATE_KEY bytes={len(_SECRET) + 1}" in output
    assert "aws_names=0" in output
    assert _SECRET not in output and "12345" not in output


def test_a_multi_line_value_is_not_counted_as_an_aws_name(*, tmp_path: Path) -> None:
    """A PEM-shaped value whose continuation line looks like `AWS_X=1` is not a name."""
    pem = f"-----BEGIN KEY-----\nAWS_SMUGGLED=1\n{_SECRET}\n-----END KEY-----"
    output = _probe(
        root=tmp_path,
        child_env={"FIXTURE_APP_ID": "12345", "FIXTURE_PRIVATE_KEY": pem},
        names=_NAMES,
    )

    assert _changed(output=output) == 0
    assert "aws_names=0" in output
    assert _SECRET not in output


@pytest.mark.parametrize(
    "child_env",
    [
        {"FIXTURE_APP_ID": "12345"},
        {"FIXTURE_APP_ID": "12345", "FIXTURE_PRIVATE_KEY": _SECRET, "AWS_ACCESS_KEY_ID": "x"},
    ],
)
def test_the_probe_fails_on_a_missing_variable_or_any_aws_variable(
    *, tmp_path: Path, child_env: dict[str, str]
) -> None:
    output = _probe(root=tmp_path, child_env=child_env, names=_NAMES)

    assert not output.startswith("rc=0\n"), output
    assert _SECRET not in output


# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gtx5nl
def _caam_dest(*, root: Path) -> Path:
    return root / "home" / ".local" / "bin" / "caam"


def test_the_pinned_caam_binary_is_installed_once_and_a_second_apply_changes_nothing(
    *, tmp_path: Path
) -> None:
    checkout, _, second, _ = _fixture(root=tmp_path)
    dest = _caam_dest(root=tmp_path)

    output, _ = _deploy(root=tmp_path, checkout=checkout, ref=second)

    assert _changed(output=output) > 0
    assert dest.is_file() and os.access(dest, os.X_OK)
    assert dest.read_bytes() == (tmp_path / "release" / "caam").read_bytes()

    again, _ = _deploy(root=tmp_path, checkout=checkout, ref=second)
    assert _changed(output=again) == 0


def test_the_role_only_ever_asks_caam_for_its_version_and_touches_no_vault_or_state(
    *, tmp_path: Path
) -> None:
    checkout, _, second, _ = _fixture(root=tmp_path)

    output, _ = _deploy(root=tmp_path, checkout=checkout, ref=second)
    _ = _deploy(root=tmp_path, checkout=checkout, ref=second)

    assert _changed(output=output) > 0
    invocations = (_caam_dest(root=tmp_path).parent / "caam-invocations").read_text(
        encoding="utf-8"
    )
    assert set(invocations.split("\n")) == {"--version", ""}
    assert sorted(path.name for path in (tmp_path / "home").rglob("*") if path.is_file()) == [
        "caam",
        "caam-invocations",
    ]


def test_a_caam_that_already_reports_the_pinned_version_is_not_downloaded_again(
    *, tmp_path: Path
) -> None:
    checkout, _, second, _ = _fixture(root=tmp_path)
    first, _ = _deploy(root=tmp_path, checkout=checkout, ref=second)
    assert _changed(output=first) > 0
    unreachable = _caam_variables(root=tmp_path) | {
        "caam_delivery_push_caam_url": (tmp_path / "release" / "gone").as_uri()
    }

    output, _ = _deploy(root=tmp_path, checkout=checkout, ref=second, caam=unreachable)

    assert _changed(output=output) == 0


def test_a_caam_of_another_version_is_replaced_by_the_pinned_one(*, tmp_path: Path) -> None:
    checkout, _, second, _ = _fixture(root=tmp_path)
    dest = _caam_dest(root=tmp_path)
    dest.parent.mkdir(parents=True)
    _ = dest.write_text(_CAAM_BINARY.replace("{version}", "0.1.0"), encoding="utf-8")
    dest.chmod(0o755)

    output, _ = _deploy(root=tmp_path, checkout=checkout, ref=second)

    assert _changed(output=output) > 0
    assert (
        "0.1.25"
        in subprocess.run(
            [str(dest), "--version"], capture_output=True, text=True, check=True
        ).stdout
    )


@pytest.mark.parametrize("sha256", ["0" * 64, "not-a-sha"])
def test_a_caam_asset_that_does_not_match_the_pinned_sha256_is_refused_and_not_installed(
    *, tmp_path: Path, sha256: str
) -> None:
    checkout, first, second, _ = _fixture(root=tmp_path)

    output, marker = _deploy(
        root=tmp_path,
        checkout=checkout,
        ref=second,
        caam=_caam_variables(root=tmp_path, sha256=sha256),
    )

    assert not output.startswith("rc=0\n"), output
    assert not _caam_dest(root=tmp_path).exists()
    assert _git("rev-parse", "HEAD", cwd=checkout) == first
    assert _installs(marker=marker) == 0
