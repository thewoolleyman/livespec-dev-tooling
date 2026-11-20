"""Consumer-tier proof for the dev_tooling_checkout role (a control node's own checkout).

Runs the role with the same pinned ``ansible-core`` as ``just ansible-drift`` against a
fixture git origin and checkout; nothing touches a real host. Static cases pin the
role's shape (flag guard, ``--ff-only``, the named refusals, ``changed_when``, and no
destructive git verb) and the per-host opt-in.
"""

from __future__ import annotations

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
_ROLE = _ANSIBLE / "roles" / "dev_tooling_checkout"
_HOST = "fixture-host"
_TIMEOUT_SECONDS = 600


def _tasks_text() -> str:
    return (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")


def _flatten(tasks: list[dict[str, object]]) -> list[dict[str, object]]:
    flat: list[dict[str, object]] = []
    for task in tasks:
        flat.append(task)
        inner = task.get("block")
        if isinstance(inner, list):
            flat.extend(_flatten(inner))
    return flat


def test_the_whole_role_is_guarded_by_the_per_host_flag_that_defaults_false() -> None:
    tasks = yaml.safe_load(_tasks_text())
    assert len(tasks) == 1
    assert "dev_tooling_checkout_enabled" in str(tasks[0]["when"])
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert defaults["dev_tooling_checkout_enabled"] is False
    assert defaults["dev_tooling_checkout_path"] == "/data/projects/livespec-dev-tooling"


def test_the_role_fetches_then_merges_ff_only_and_names_both_refusals() -> None:
    text = _tasks_text()
    assert text.index("- fetch") < text.index("- --ff-only")
    assert "REFUSED dirty-tree" in text
    assert "REFUSED diverged" in text
    assert "--porcelain" in text
    assert "--is-ancestor" in text


def test_the_only_task_that_can_change_anything_is_the_guarded_ff_merge() -> None:
    flat = _flatten(yaml.safe_load(_tasks_text())[0]["block"])
    changing = [task for task in flat if task.get("changed_when") is True]
    assert [task["name"] for task in changing] == [
        "Fast-forward the checkout",
        "Report the fast-forward a check run would make",
    ]
    report = changing[1]
    assert report["when"] == "ansible_check_mode"
    assert report["ansible.builtin.command"]["argv"][-3:] == ["rev-parse", "--verify", "HEAD"]
    guard = next(task for task in flat if task.get("name") == "Move the checkout to the remote tip")
    assert "!=" in str(guard["when"])
    others = [task for task in flat if "ansible.builtin.command" in task]
    assert all(task.get("changed_when") is not None for task in others)


def test_no_destructive_git_verb_appears() -> None:
    flat = _flatten(yaml.safe_load(_tasks_text())[0]["block"])
    argvs = [
        task["ansible.builtin.command"]["argv"]
        for task in flat
        if "ansible.builtin.command" in task
    ]
    verbs = {"reset", "clean", "stash", "checkout", "switch", "rebase", "restore", "--force", "-f"}
    assert argvs
    for argv in argvs:
        assert all(str(word) not in verbs for word in argv), argv
        assert argv[0] == "git"
    merges = [argv for argv in argvs if "merge" in argv]
    assert len(merges) == 1
    assert "--ff-only" in merges[0]


def test_only_the_vps_opts_in_and_the_play_applies_the_role() -> None:
    host_vars = _ANSIBLE / "inventory" / "host_vars"
    enabled = {
        path.stem
        for path in host_vars.glob("*.yml")
        if not path.is_symlink()
        and (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(
            "dev_tooling_checkout_enabled"
        )
    }
    assert enabled == {"vps"}
    play = yaml.safe_load((_ANSIBLE / "caam-role-holder.yml").read_text(encoding="utf-8"))
    assert "dev_tooling_checkout" in [role["role"] for role in play[0]["roles"]]


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
    _ = (work / "file.txt").write_text(text, encoding="utf-8")
    _ = _git("add", "-A", cwd=work)
    _ = _git("commit", "-q", "-m", text.strip(), cwd=work)
    return _git("rev-parse", "HEAD", cwd=work)


def _fixture(*, root: Path) -> tuple[Path, str, str]:
    """A bare origin at B (A < B) and a checkout cloned at A, on master."""
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "-q", "-b", "master", cwd=seed)
    first = _commit(work=seed, text="one\n")
    origin = root / "origin.git"
    _ = _git("clone", "-q", "--bare", str(seed), str(origin), cwd=root)
    checkout = root / "checkout"
    _ = _git("clone", "-q", str(origin), str(checkout), cwd=root)
    second = _commit(work=seed, text="two\n")
    _ = _git("push", "-q", str(origin), "master", cwd=seed)
    return checkout, first, second


def _apply(*, root: Path, checkout: Path, enabled: bool = True, check: bool = False) -> str:
    inventory = root / "inventory.yml"
    _ = inventory.write_text(
        f"---\nall:\n  hosts:\n    {_HOST}:\n      ansible_connection: local\n", encoding="utf-8"
    )
    play = root / "play.yml"
    _ = play.write_text(
        "---\n- name: fixture\n  hosts: all\n  gather_facts: false\n"
        "  roles:\n    - role: dev_tooling_checkout\n",
        encoding="utf-8",
    )
    variables = {
        "dev_tooling_checkout_enabled": enabled,
        "dev_tooling_checkout_path": str(checkout),
    }
    command = ["uvx", "--from", _ansible_core_pin(), "ansible-playbook"]
    command += ["--check"] if check else []
    command += ["-i", str(inventory), "-e", json.dumps(variables), str(play)]
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    } | {
        "ANSIBLE_NOCOWS": "1",
        "ANSIBLE_RETRY_FILES_ENABLED": "False",
        "ANSIBLE_ROLES_PATH": str(_ANSIBLE / "roles"),
    }
    done = subprocess.run(
        command,
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    return f"rc={done.returncode}\n{done.stdout}{done.stderr}"


def _changed(*, output: str) -> int:
    assert output.startswith("rc=0\n"), output
    recap = re.search(rf"^{_HOST}\s*:.*?\bchanged=(?P<count>\d+)", output, re.MULTILINE)
    assert recap is not None, output
    return int(recap["count"])


def test_an_apply_fast_forwards_and_a_second_apply_changes_nothing(*, tmp_path: Path) -> None:
    checkout, _, second = _fixture(root=tmp_path)

    assert _changed(output=_apply(root=tmp_path, checkout=checkout)) > 0
    assert _git("rev-parse", "HEAD", cwd=checkout) == second
    assert _changed(output=_apply(root=tmp_path, checkout=checkout)) == 0


def test_check_mode_reports_a_change_and_touches_nothing(*, tmp_path: Path) -> None:
    checkout, first, _ = _fixture(root=tmp_path)

    assert _changed(output=_apply(root=tmp_path, checkout=checkout, check=True)) > 0
    assert _git("rev-parse", "HEAD", cwd=checkout) == first


def test_a_disabled_host_is_left_alone(*, tmp_path: Path) -> None:
    checkout, first, _ = _fixture(root=tmp_path)

    assert _changed(output=_apply(root=tmp_path, checkout=checkout, enabled=False)) == 0
    assert _git("rev-parse", "HEAD", cwd=checkout) == first


def test_a_dirty_tree_is_refused_by_name_and_left_untouched(*, tmp_path: Path) -> None:
    checkout, first, _ = _fixture(root=tmp_path)
    _ = (checkout / "local-edit.txt").write_text("draft\n", encoding="utf-8")

    output = _apply(root=tmp_path, checkout=checkout)

    assert not output.startswith("rc=0\n"), output
    assert "REFUSED dirty-tree" in output
    assert _git("rev-parse", "HEAD", cwd=checkout) == first
    assert (checkout / "local-edit.txt").read_text(encoding="utf-8") == "draft\n"


def test_a_diverged_branch_is_refused_by_name_and_left_untouched(*, tmp_path: Path) -> None:
    checkout, _, _ = _fixture(root=tmp_path)
    local = _commit(work=checkout, text="local only\n")

    output = _apply(root=tmp_path, checkout=checkout)

    assert not output.startswith("rc=0\n"), output
    assert "REFUSED diverged" in output
    assert _git("rev-parse", "HEAD", cwd=checkout) == local
