"""The `otel_collector` role fetches every file at a commit sha, never at a branch name.

WHY IT EXISTS (2026-10-27, livespec-dev-tooling-aqzi32). The role fetched
`raw.githubusercontent.com/thewoolleyman/otel-collector/<ref>/...` with the ref
defaulting to `main`. That CDN serves a branch name with `cache-control:
max-age=300`, so a converge started within five minutes of a merge read the
pre-merge copy, installed nothing, and reported `changed=0` on every host — a
green converge that reads as "already converged". The drift run reads through the
same cache and cannot catch it. A sha URL is immutable, so the CDN can never
serve a stale copy of one.

WHAT THESE TESTS HOLD THE ROLE TO.
- Every raw URL the role declares is addressed by `otel_collector_config_commit`,
  and the defaults do not declare that variable, so a run that skipped the
  resolution fails on an undefined variable instead of quietly falling back to the
  branch name.
- The ref is resolved to a commit by the first task of the role, on the control
  node, through `git ls-remote` (which does not go through the CDN), before any
  fetch or write.
- The resolution is exercised for real against a local git repository: a branch
  follows each new commit, an annotated tag resolves to its commit rather than to
  the tag object, and an unknown ref resolves to nothing for the following
  assertion to refuse.
"""

from __future__ import annotations

import itertools
import re
import subprocess
import tempfile
from pathlib import Path
from typing import cast

import jinja2

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "otel_collector"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_ANSIBLE_README = _REPO_ROOT / "ansible" / "README.md"
_HOST_VARS_DOC = _ROLE / "HOST_VARS.md"

_RAW_SOURCE = "https://raw.githubusercontent.com/thewoolleyman/otel-collector/"
_COMMIT_VARIABLE = "otel_collector_config_commit"
_REF_VARIABLE = "otel_collector_config_ref"

_RESOLVE_TASK = "Resolve the collector ref to the commit every fetch is made at"
_PASS_THROUGH_TASK = "Take a collector ref that is already a full commit sha as the commit"
_NAME_TASK = "Name the commit the collector ref resolves to"
_REFUSE_TASK = "Refuse a collector ref that did not resolve to a commit"

_WRITING_MODULES = (
    "ansible.builtin.copy:",
    "ansible.builtin.file:",
    "ansible.builtin.include_tasks:",
    "ansible.builtin.lineinfile:",
    "ansible.builtin.systemd_service:",
    "ansible.builtin.template:",
)


def _task_blocks(*, body: str) -> list[str]:
    """Each `- name:`-introduced task of a role file, comments stripped, in file order."""
    return [
        "\n".join(
            line for line in f"- name: {chunk}".splitlines() if not line.lstrip().startswith("#")
        )
        for chunk in body.split("\n- name: ")[1:]
    ]


def _task(*, name: str) -> str:
    matches = [
        block
        for block in _task_blocks(body=_TASKS.read_text(encoding="utf-8"))
        if block.startswith(f"- name: {name}\n")
    ]
    assert len(matches) == 1, f"tasks/main.yml must carry exactly one task named {name!r}"
    return matches[0]


def _task_index(*, name: str) -> int:
    blocks = _task_blocks(body=_TASKS.read_text(encoding="utf-8"))
    return next(
        index for index, block in enumerate(blocks) if block.startswith(f"- name: {name}\n")
    )


def _argv(*, block: str) -> list[str]:
    """The list items under a command task's `argv:` key, unquoted."""
    section = block.split("    argv:\n", 1)[1]
    matches = itertools.takewhile(
        lambda match: match is not None,
        (re.match(r"^      - (?P<item>.+)$", line) for line in section.splitlines()),
    )
    return [cast("re.Match[str]", match)["item"].strip().strip('"') for match in matches]


def _folded_value(*, block: str, key: str) -> str:
    """A `key: >-` folded scalar's value, folded the way YAML folds it."""
    section = block.split(f"    {key}: >-\n", 1)[1]
    indented = itertools.takewhile(lambda line: line.startswith("      "), section.splitlines())
    return " ".join(line.strip() for line in indented)


def _environment() -> jinja2.Environment:
    return jinja2.Environment(
        trim_blocks=True,
        lstrip_blocks=False,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
        autoescape=False,
    )


def _git(*, repo: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _commit(*, repo: Path, message: str) -> str:
    _git(
        repo=repo,
        args=[
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "--allow-empty",
            "--message",
            message,
        ],
    )
    return _git(repo=repo, args=["rev-parse", "HEAD"])


def _resolved_commit(*, repo: Path, ref: str) -> str:
    """What the role's two resolution tasks leave in the commit variable for `ref`."""
    environment = _environment()
    variables: dict[str, object] = {
        "otel_collector_repository_url": str(repo),
        _REF_VARIABLE: ref,
    }
    argv = [
        environment.from_string(item).render(**variables)
        for item in _argv(block=_task(name=_RESOLVE_TASK))
    ]
    listing = subprocess.run(
        argv,
        check=True,
        capture_output=True,
        text=True,
    )
    variables["otel_collector_ref_listing"] = {"stdout_lines": listing.stdout.splitlines()}
    expression = _folded_value(block=_task(name=_NAME_TASK), key=_COMMIT_VARIABLE)
    return environment.from_string(expression).render(**variables).strip()


def test_every_raw_url_is_addressed_by_the_resolved_commit_and_not_the_ref() -> None:
    """A URL built from the branch name is the one the CDN caches for five minutes."""
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    code = "\n".join(line for line in defaults.splitlines() if not line.lstrip().startswith("#"))
    raw_urls = [line for line in code.splitlines() if _RAW_SOURCE in line]
    assert len(raw_urls) == 4, raw_urls
    for line in raw_urls:
        assert f"{{{{ {_COMMIT_VARIABLE} }}}}" in line, line
        assert _REF_VARIABLE not in line, line

    assert f"{_COMMIT_VARIABLE}:" not in code, (
        "the commit variable must not be declared in the defaults: a default would be a "
        "fallback to the branch name for any run that skipped the resolution"
    )
    assert re.search(r"^otel_collector_config_ref: main$", code, re.MULTILINE), code
    assert re.search(
        r"^otel_collector_repository_url: https://github\.com/thewoolleyman/otel-collector\.git$",
        code,
        re.MULTILINE,
    ), code


def test_the_ref_is_resolved_on_the_control_node_before_any_fetch_or_write() -> None:
    """The resolution is a read through git, not through the cached raw host."""
    resolve = _task(name=_RESOLVE_TASK)
    argv = _argv(block=resolve)
    assert argv[:3] == ["git", "ls-remote", "--"], argv
    assert "{{ otel_collector_repository_url }}" in argv, argv
    assert _RAW_SOURCE not in resolve, resolve
    assert "ansible.builtin.command:" in resolve, resolve
    assert "delegate_to: localhost" in resolve, resolve
    assert "become: false" in resolve, resolve
    assert "changed_when: false" in resolve, resolve
    assert "check_mode: false" in resolve, resolve
    assert "register: otel_collector_ref_listing" in resolve, resolve

    blocks = _task_blocks(body=_TASKS.read_text(encoding="utf-8"))
    resolved_at = _task_index(name=_NAME_TASK)
    assert _task_index(name=_RESOLVE_TASK) < resolved_at
    assert _task_index(name=_PASS_THROUGH_TASK) < resolved_at
    assert resolved_at < _task_index(name=_REFUSE_TASK)
    refused_at = _task_index(name=_REFUSE_TASK)
    for index, block in enumerate(blocks[:refused_at]):
        assert "lookup('ansible.builtin.url'" not in block, (index, block)
        assert not any(module in block for module in _WRITING_MODULES), (index, block)

    pass_through = _task(name=_PASS_THROUGH_TASK)
    assert "ansible.builtin.set_fact:" in pass_through, pass_through
    assert f'{_COMMIT_VARIABLE}: "{{{{ {_REF_VARIABLE} }}}}"' in pass_through, pass_through
    assert "is match('^[0-9a-f]{40}$')" in pass_through, pass_through
    assert "is match('^[0-9a-f]{40}$')" in resolve, resolve
    assert "not (" in resolve, resolve

    refuse = _task(name=_REFUSE_TASK)
    assert "ansible.builtin.assert:" in refuse, refuse
    assert f"{_COMMIT_VARIABLE} is match('^[0-9a-f]{{40}}$')" in refuse, refuse


def test_a_branch_resolves_to_each_new_commit_with_no_cache_between() -> None:
    """The merge-then-converge sequence: the second resolution sees the second commit."""
    with tempfile.TemporaryDirectory() as scratch:
        repo = Path(scratch)
        _git(repo=repo, args=["init", "--quiet", "--initial-branch", "main"])
        before = _commit(repo=repo, message="before the merge")
        assert _resolved_commit(repo=repo, ref="main") == before

        after = _commit(repo=repo, message="the merge")
        assert after != before
        assert _resolved_commit(repo=repo, ref="main") == after


def test_a_tag_resolves_to_its_commit_and_an_unknown_ref_to_nothing() -> None:
    """An annotated tag names a tag object; the fetch needs the commit it points at."""
    with tempfile.TemporaryDirectory() as scratch:
        repo = Path(scratch)
        _git(repo=repo, args=["init", "--quiet", "--initial-branch", "main"])
        tagged = _commit(repo=repo, message="tagged")
        _git(
            repo=repo,
            args=[
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@example.invalid",
                "tag",
                "--annotate",
                "--message",
                "annotated",
                "v-annotated",
            ],
        )
        _git(repo=repo, args=["tag", "v-light"])
        _commit(repo=repo, message="moves main past the tags")

        assert _resolved_commit(repo=repo, ref="v-annotated") == tagged
        assert _resolved_commit(repo=repo, ref="v-light") == tagged
        assert _resolved_commit(repo=repo, ref="no-such-ref") == ""


def test_a_full_sha_is_held_as_given_and_the_operator_docs_say_how_the_ref_is_read() -> None:
    """Pinning a host to a sha keeps working; the docs name the resolution."""
    for path in (_ANSIBLE_README, _HOST_VARS_DOC):
        text = path.read_text(encoding="utf-8")
        assert "git ls-remote" in text, f"{path.name} must say the ref is resolved to a commit"
        assert "max-age=300" in text or "five minutes" in text, path.name
