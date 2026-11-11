"""The CI job warm pre-pulls every python-v* tag the fleet's ci.yml files pin.

livespec-dev-tooling-e2gv6n, Definition of Done bullet 3: on every node that takes
CI runner pods, each CI python-v* sandbox image that the current ci.yml of each
fleet repository pins is already in the node's containerd store before a job pulls
it. The fleet does not pin one release (measured 2026-11-11: python-v1.183.1,
python-v1.189.1 and python-v1.194.0 at once, against a v1.194.0 release manifest),
so the warm reads the workflows' own pins rather than the release pin.

What is RUN here: the committed warm script, against a stub `curl` serving
workflow files and a stub `crictl` over a marker-file store; and the role's
URL default, rendered through the same pinned ansible-core the `ansible-apply`
recipe runs. What is READ: the committed play's second warm entry, and the scale
sets the repository list must cover. The pull on a real node stays host-captured.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "sandbox_image_warm"
_SCRIPT = _ROLE / "files" / "sandbox-image-warm.sh"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_SERVICE = _ROLE / "templates" / "livespec-sandbox-image-warm.service.j2"
_CI_POOL = _REPO_ROOT / "ansible" / "ci-pool.yml"
_JUSTFILE = _REPO_ROOT / "justfile"
_ARC = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "arc"

_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox"
_TIMEOUT_SECONDS = 120
_PLAYBOOK_TIMEOUT_SECONDS = 600
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_RENDERED = re.compile(r'^\s*"msg": (?P<msg>"RENDERED=.*")$', re.MULTILINE)
# A scale set whose repository's default branch carries no ci.yml, so it pins no
# sandbox tag for a CI job. Stated, so a new exception has to be argued here.
_NO_CI_WORKFLOW = frozenset({"fabro"})

_CURL_STUB = """#!/usr/bin/env bash
# Serves STUB_FILES/<last path segment but one>/<basename>, so two repositories'
# ci.yml stay distinct; a repository listed in STUB_UNREADABLE refuses.
set -uo pipefail
url="${!#}"
repo="${url#https://raw.invalid/}"
repo="${repo%%/*}"
for refused in ${STUB_UNREADABLE:-}; do
    [[ "$repo" == "$refused" ]] && exit 22
done
[[ -f "$STUB_FILES/$repo/ci.yml" ]] || exit 22
cat "$STUB_FILES/$repo/ci.yml"
"""

_CRICTL_STUB = """#!/usr/bin/env bash
set -uo pipefail
key() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'; }
case "${1:-}" in
    inspecti) [[ -f "$STUB_STORE/$(key "${2:-}")" ]] || exit 1 ;;
    pull)
        printf 'crictl-pull %s\\n' "${2:-}" >>"$STUB_LOG"
        : >"$STUB_STORE/$(key "${2:-}")"
        ;;
    *) exit 2 ;;
esac
"""

_WORKFLOW_A = f"""name: ci
jobs:
  check:
    container:
      image: {_IMAGE}:python-v1.183.1
  lint:
    container:
      # image: {_IMAGE}:python-v1.100.0
      image: "{_IMAGE}:python-v1.183.1"  # same tag twice
  rust:
    container: {_IMAGE}:python-rust-v1.183.1
  agent:
    container: {_IMAGE}:python-agent-v1.183.1
  other:
    container: docker.io/library/python:3.12
"""
_WORKFLOW_B = f"""jobs:
  check:
    container:
      image: {_IMAGE}:python-v1.194.0
"""
_WORKFLOW_RUST_ONLY = f"""jobs:
  check:
    container:
      image: {_IMAGE}:python-rust-v1.171.0
"""


def _warm(
    *,
    tmp_path: Path,
    workflows: dict[str, str],
    unreadable: tuple[str, ...] = (),
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """One CI job warm of the committed script over `workflows` (repo -> ci.yml)."""
    assert _SCRIPT.is_file()
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name, body in (("curl", _CURL_STUB), ("crictl", _CRICTL_STUB)):
        (stubs / name).write_text(body, encoding="utf-8")
        (stubs / name).chmod(0o755)
    files = tmp_path / "files"
    for repo, body in workflows.items():
        (files / repo).mkdir(parents=True)
        (files / repo / "ci.yml").write_text(body, encoding="utf-8")
    (tmp_path / "store").mkdir()
    log = tmp_path / "pulls.log"
    log.touch()
    env = os.environ | {
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
        "STUB_FILES": str(files),
        "STUB_STORE": str(tmp_path / "store"),
        "STUB_LOG": str(log),
        "STUB_UNREADABLE": " ".join(unreadable),
        "LIVESPEC_SANDBOX_IMAGE_WARM_IMAGE": _IMAGE,
        "LIVESPEC_SANDBOX_IMAGE_WARM_TAG_PREFIXES": "python",
        "LIVESPEC_SANDBOX_IMAGE_WARM_PIN_URL": "https://pin.invalid/manifest.json",
        "LIVESPEC_SANDBOX_IMAGE_WARM_STORE": "containerd",
        "LIVESPEC_SANDBOX_IMAGE_WARM_CRICTL": "crictl",
        "LIVESPEC_SANDBOX_IMAGE_WARM_LOCK_DIR": str(tmp_path / "locks"),
        "LIVESPEC_SANDBOX_IMAGE_WARM_RECORD_DIR": str(tmp_path / "record"),
        "LIVESPEC_SANDBOX_IMAGE_WARM_REMOVE_SUPERSEDED": "false",
        "LIVESPEC_SANDBOX_IMAGE_WARM_WORKFLOW_URLS": " ".join(
            f"https://raw.invalid/{repo}/master/.github/workflows/ci.yml"
            for repo in [*workflows, *unreadable]
        ),
    }
    env |= extra_env or {}
    done = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
        env=env,
    )
    return done, [line for line in log.read_text(encoding="utf-8").splitlines() if line]


def test_the_ci_warm_pulls_every_python_v_tag_each_workflow_pins_once(*, tmp_path: Path) -> None:
    done, pulls = _warm(
        tmp_path=tmp_path,
        workflows={"repo-a": _WORKFLOW_A, "repo-b": _WORKFLOW_B, "repo-c": _WORKFLOW_RUST_ONLY},
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert pulls == [
        f"crictl-pull {_IMAGE}:python-v1.183.1",
        f"crictl-pull {_IMAGE}:python-v1.194.0",
    ], (
        "the CI warm must pull each pinned python-v* tag once, through crictl, across "
        "every workflow: not a commented-out pin, not python-rust-v* or python-agent-v* "
        f"(the prefix match is exact), not another repository's image: {done.stdout}"
    )


def test_an_unreadable_workflow_fails_the_warm_and_pulls_nothing(*, tmp_path: Path) -> None:
    done, pulls = _warm(
        tmp_path=tmp_path, workflows={"repo-a": _WORKFLOW_A}, unreadable=("repo-gone",)
    )
    assert done.returncode != 0, done.stdout + done.stderr
    assert pulls == [], "a partial read can omit the very pin that moved, so it pulls nothing"
    assert "could not read every workflow source" in done.stdout


def test_workflows_pinning_no_python_v_tag_fail_rather_than_fall_back(*, tmp_path: Path) -> None:
    done, pulls = _warm(tmp_path=tmp_path, workflows={"repo-c": _WORKFLOW_RUST_ONLY})
    assert done.returncode != 0, done.stdout + done.stderr
    assert pulls == [], "a read that finds no pin must not pull the release-pin tag instead"


def test_a_warm_declaring_two_reference_sources_refuses(*, tmp_path: Path) -> None:
    done, pulls = _warm(
        tmp_path=tmp_path,
        workflows={"repo-b": _WORKFLOW_B},
        extra_env={"LIVESPEC_SANDBOX_IMAGE_WARM_PROCESS_SPEC_URLS": "https://spec.invalid/a.yml"},
    )
    assert done.returncode != 0 and pulls == [], done.stdout + done.stderr
    assert "a warm reads one" in done.stdout


def test_ci_pool_arms_the_ci_warm_on_every_node_that_takes_ci_runner_pods() -> None:
    play = _CI_POOL.read_text(encoding="utf-8")
    entries = re.findall(r"^    - role: sandbox_image_warm\n((?:      .*\n)+)", play, re.MULTILINE)
    assert len(entries) == 2, "ci-pool.yml must carry the factory warm AND the CI job warm"
    factory, ci = entries
    assert "      when: ci_pool_factory_node == 'true'\n" in factory
    assert "      tags: [sandbox_image_warm_containerd]\n" in factory
    for line in (
        "      tags: [sandbox_image_warm_ci_containerd]\n",
        "      when: ci_pool_ci_node_facilities != 'none'\n",
        "      sandbox_image_warm_store: containerd\n",
        "      sandbox_image_warm_name: livespec-sandbox-image-warm-ci-containerd\n",
        "      sandbox_image_warm_tag_prefixes: [python]\n",
        '      sandbox_image_warm_workflow_urls: "{{ sandbox_image_warm_ci_workflow_urls }}"\n',
        '      sandbox_image_warm_k3s_data_dir: "{{ ci_pool_node_data_dir }}"\n',
    ):
        assert line in ci, f"the CI job warm entry must carry {line.strip()!r}:\n{ci}"
    service = _SERVICE.read_text(encoding="utf-8")
    assert "LIVESPEC_SANDBOX_IMAGE_WARM_WORKFLOW_URLS" in service
    tasks = _TASKS.read_text(encoding="utf-8")
    assert "Refuse a workflow-sourced warm that also names another source" in tasks


def _scale_set_repositories() -> set[str]:
    found: set[str] = set()
    for values in _ARC.glob("values-*.yaml"):
        if "EXAMPLE" in values.name:
            continue
        for match in re.finditer(
            r'^githubConfigUrl: "https://github\.com/thewoolleyman/([\w.-]+)"$',
            values.read_text(encoding="utf-8"),
            re.MULTILINE,
        ):
            found.add(match[1])
    assert found, "no scale set declares a githubConfigUrl"
    return found


def _declared_repositories() -> list[str]:
    block = re.search(
        r"^sandbox_image_warm_ci_workflow_repos:\n((?:  - .*\n)+)",
        _DEFAULTS.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert block is not None
    return [line.removeprefix("  - ").strip() for line in block[1].splitlines()]


def test_the_warm_reads_the_ci_workflow_of_every_repository_with_a_scale_set() -> None:
    """A scale set added without its repository here would pull cold, silently."""
    declared = _declared_repositories()
    assert declared == sorted(declared) and len(declared) == len(set(declared))
    expected = _scale_set_repositories() - _NO_CI_WORKFLOW
    assert set(declared) == expected, (
        f"sandbox_image_warm_ci_workflow_repos must list every scale-set repository but "
        f"{sorted(_NO_CI_WORKFLOW)}: missing {sorted(expected - set(declared))}, "
        f"extra {sorted(set(declared) - expected)}"
    )


def _ansible_core_pin() -> str:
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None
    return pin[0]


def _render(*, tmp_path: Path, expression: str, extra_vars: tuple[str, ...] = ()) -> object:
    """Render one expression over the role defaults through the pinned ansible-core."""
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("[sandbox_hosts]\nfactory-a\n", encoding="utf-8")
    playbook = tmp_path / "render.yml"
    playbook.write_text(
        "- hosts: localhost\n"
        "  connection: local\n"
        "  gather_facts: false\n"
        f"  vars_files: ['{_DEFAULTS}']\n"
        "  tasks:\n"
        "    - ansible.builtin.debug:\n"
        f'        msg: "RENDERED={{{{ {expression} | to_json }}}}"\n',
        encoding="utf-8",
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env |= {
        "ANSIBLE_NOCOWS": "1",
        "ANSIBLE_RETRY_FILES_ENABLED": "False",
        "ANSIBLE_LOCALHOST_WARNING": "False",
        "ANSIBLE_INVENTORY_UNPARSED_WARNING": "False",
        "ANSIBLE_STDOUT_CALLBACK": "default",
    }
    extra = [arg for value in extra_vars for arg in ("-e", value)]
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-playbook",
            "-i",
            str(inventory),
            *extra,
            str(playbook),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    found = _RENDERED.search(output)
    assert found is not None, output
    return json.loads(json.loads(found["msg"]).removeprefix("RENDERED="))


def test_the_ci_workflow_urls_render_one_raw_ci_yml_per_repository(*, tmp_path: Path) -> None:
    urls = _render(tmp_path=tmp_path, expression="sandbox_image_warm_ci_workflow_urls")
    assert urls == [
        f"https://raw.githubusercontent.com/thewoolleyman/{repo}/master/.github/workflows/ci.yml"
        for repo in _declared_repositories()
    ], f"rendered={urls!r}"


def test_a_workflow_sourced_containerd_warm_renders_no_process_spec_urls(*, tmp_path: Path) -> None:
    urls = _render(
        tmp_path=tmp_path,
        expression="sandbox_image_warm_process_spec_urls",
        extra_vars=(
            "sandbox_image_warm_store=containerd",
            '{"sandbox_image_warm_workflow_urls": ["https://raw.invalid/a/ci.yml"]}',
        ),
    )
    assert urls == [], "a warm reads ONE source; the workflow source displaces process_spec"
