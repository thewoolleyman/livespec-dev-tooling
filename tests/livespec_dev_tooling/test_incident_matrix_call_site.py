"""Only the CALLING workflow's parsed call site, at the trusted base, can authorize an omission.

Work-item livespec-dev-tooling-hlxbsv, finding 1 of the re-review of
livespec-dev-tooling#3966 (issuecomment-6758823282). The earlier rule matched
text anywhere in the repository; valid YAML spellings got past it, and a
guarded line in any file vouched for every caller. `incident_matrix_call_site`
parses the workflow with `yaml.safe_load`, reads only the workflow that
`github.workflow_ref` names, at the pull request's BASE commit, and requires
the copy GitHub ran to equal it. Every call site of the matrix in that
workflow must pass `with.incident-omitted` and `with.incident-ci-result`
exactly as the guarded expressions and `needs:` an existing `incident-ci` job.

The end-to-end cases drive the decision step's entry point, `main()`, with the
runner's environment, the payload file, the workspace copy and a forge read of
the base copy, and each sits beside the authorized negative control.
Finding 2 is here too: every omittable member names an existing check module.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from livespec_dev_tooling import budgeted_gh, incident_matrix_omission
from livespec_dev_tooling import incident_matrix_call_site as call_site
from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.incident_matrix_call_site import (
    GUARDED_OMITTED,
    GUARDED_RESULT,
    call_site_findings,
    call_site_reason,
    caller_path,
    check_callers,
    fetch_at,
    load_workflow,
)

__all__: list[str] = []

_REPOSITORY = "owner/repo"
_BASE = "b" * 40
_USES = "thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-check-matrix.yml@v1.191.0"
_GUARDED_WITH = (
    f"      incident-omitted: {GUARDED_OMITTED}\n      incident-ci-result: {GUARDED_RESULT}\n"
)


def _workflow(*, with_block: str = _GUARDED_WITH, needs: str = "[incident-ci]", extra: str = ""):
    return (
        "on: pull_request\njobs:\n  incident-ci:\n    runs-on: ubuntu-latest\n"
        "    steps: [{run: 'true'}]\n"
        f"  shared:\n    needs: {needs}\n    uses: {_USES}\n    with:\n"
        "      checks: '[\"heading_coverage\"]'\n" + with_block + extra
    )


_GOOD = _workflow()
_LITERAL = '\'["check-heading-coverage", "check-per-file-coverage"]\''
# Valid YAML spellings that the old text rule let through (re-review finding 1).
_BYPASSES = {
    "space before the colon": _workflow(
        with_block=f"      incident-omitted : {_LITERAL}\n      incident-ci-result : success\n"
    ),
    "quoted keys": _workflow(
        with_block=f'      "incident-omitted": {_LITERAL}\n      "incident-ci-result": success\n'
    ),
    "value on the next line": _workflow(
        with_block=f"      incident-omitted:\n        {_LITERAL}\n"
        f"      incident-ci-result:\n        success\n"
    ),
    "an odd key beside the guarded pair": _workflow(
        with_block=_GUARDED_WITH + f"      incident_omitted: {_LITERAL}\n"
    ),
    "no needs on incident-ci": _workflow(needs="[]"),
}


def _decision(tmp_path: Path, monkeypatch, capsys, *, base: str, running: str, caller="ci.yml"):
    """One decision-step run: (omit written, printed lines, forge requests made)."""
    workflows = tmp_path / "workspace" / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (workflows / caller).write_text(running, encoding="utf-8")
    (workflows / "decoy.yml").write_text(_GOOD, encoding="utf-8")
    event = tmp_path / "event.json"
    payload = {
        "pull_request": {
            "labels": [{"name": "expedited-incident-response"}],
            "head": {"repo": {"full_name": _REPOSITORY}},
            "base": {"repo": {"full_name": _REPOSITORY}, "sha": _BASE},
        }
    }
    event.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    read = Mock(return_value=GhRead(returncode=0, stdout=base, stderr=""))
    monkeypatch.setattr(budgeted_gh, "gh_read", read)
    environ = {
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_REPOSITORY": _REPOSITORY,
        "GITHUB_WORKSPACE": str(workflows.parents[1]),
        "GITHUB_OUTPUT": str(output),
        "CALLER_WORKFLOW_REF": f"{_REPOSITORY}/.github/workflows/{caller}@refs/pull/7/merge",
        "INCIDENT_OMITTED": '["check-heading-coverage", "check-per-file-coverage"]',
        "INCIDENT_CI_RESULT": "success",
        "MATRIX_CHECK": "per_file_coverage",
    }
    for name, value in environ.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, "argv", ["incident_matrix_omission"])
    _ = incident_matrix_omission.main()
    lines = capsys.readouterr().out.splitlines()
    return output.read_text(encoding="utf-8"), lines, read.call_args_list


def test_an_authorized_call_site_at_the_base_omits(tmp_path, monkeypatch, capsys):
    omit, lines, requests = _decision(tmp_path, monkeypatch, capsys, base=_GOOD, running=_GOOD)
    facts = [
        omit == "omit=true\n",
        lines[-1].startswith("::notice title=omitted-by-incident-policy::"),
        [r.kwargs["args"][-1] for r in requests]
        == [f"repos/{_REPOSITORY}/contents/.github/workflows/ci.yml?ref={_BASE}"],
    ]
    assert all(facts), (omit, lines, requests)


@pytest.mark.parametrize("spelling", sorted(_BYPASSES))
def test_each_yaml_bypass_spelling_omits_nothing(tmp_path, monkeypatch, capsys, spelling):
    text = _BYPASSES[spelling]
    omit, lines, _ = _decision(tmp_path, monkeypatch, capsys, base=text, running=text)
    assert omit == "omit=false\n"
    assert any("fails the call-site rule" in line for line in lines), lines


def test_a_guarded_decoy_workflow_never_vouches_for_the_caller(tmp_path, monkeypatch, capsys):
    text = _BYPASSES["quoted keys"]
    omit, _, _ = _decision(
        tmp_path, monkeypatch, capsys, base=text, running=text, caller="second.yml"
    )
    assert omit == "omit=false\n"


def test_one_unguarded_call_site_among_several_omits_nothing(tmp_path, monkeypatch, capsys):
    second = (
        f"  zz-again:\n    needs: [incident-ci]\n    uses: {_USES}\n    with:\n"
        f"      checks: '[\"per_file_coverage\"]'\n      incident-omitted: {_LITERAL}\n"
        f"      incident-ci-result: {GUARDED_RESULT}\n"
    )
    text = _workflow(extra=second)
    omit, lines, _ = _decision(tmp_path, monkeypatch, capsys, base=text, running=text)
    assert omit == "omit=false\n"
    assert any('job "zz-again": with.incident-omitted' in line for line in lines), lines


def test_a_pull_request_that_edits_its_calling_workflow_omits_nothing(
    tmp_path, monkeypatch, capsys
):
    running = _GOOD.replace(GUARDED_OMITTED, _LITERAL)
    omit, lines, _ = _decision(tmp_path, monkeypatch, capsys, base=_GOOD, running=running)
    assert omit == "omit=false\n"
    assert any("the pull request changes the calling workflow" in line for line in lines)


def test_every_omittable_member_names_an_existing_check_module():
    modules = {
        member: f"livespec_dev_tooling.checks.{member.removeprefix('check-').replace('-', '_')}"
        for member in incident_matrix_omission.OMITTABLE_MEMBERS
    }
    missing = [name for name in modules.values() if importlib.util.find_spec(name) is None]
    assert modules
    assert missing == []
    # Negative control: the controller-only member has no module, so no leg is it.
    assert importlib.util.find_spec("livespec_dev_tooling.checks.coverage") is None
    assert "check-coverage" in incident_matrix_omission.CONTROLLER_ONLY_MEMBERS


def test_the_controller_only_member_is_never_omitted_and_never_warned():
    authority = incident_matrix_omission.IncidentAuthority(
        payload=None,
        repository=_REPOSITORY,
        incident_ci_result="success",
        caller=None,
        base_text=None,
        running_text=None,
    )
    decision = incident_matrix_omission.decide(
        event_name="pull_request", raw='["check-coverage"]', check="coverage", authority=authority
    )
    assert (decision.omit, decision.lines) == (False, ('incident-omission: "coverage" runs',))


# --- The call-site rule, unit by unit ----------------------------------------


def test_the_guarded_call_site_passes_in_every_mode():
    workflow = load_workflow(text=_GOOD)
    assert call_site_findings(workflow=workflow, required=True) == []
    assert call_site_findings(workflow=workflow, required=False) == []


@pytest.mark.parametrize("spelling", sorted(_BYPASSES))
def test_each_bypass_spelling_is_a_finding_in_every_mode(spelling):
    workflow = load_workflow(text=_BYPASSES[spelling])
    assert call_site_findings(workflow=workflow, required=True)
    assert call_site_findings(workflow=workflow, required=False)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            _workflow(with_block=f"      Incident-Omitted: {GUARDED_OMITTED}\n"),
            [
                'job "shared": "Incident-Omitted" is not an incident input of '
                "reusable-check-matrix.yml",
                f'job "shared": with.incident-omitted is not exactly {GUARDED_OMITTED}',
                f'job "shared": with.incident-ci-result is not exactly {GUARDED_RESULT}',
            ],
        ),
        (
            _workflow(needs="incident-ci"),
            [],
        ),
        (
            _workflow(needs="{a: b}"),
            ['job "shared" does not need incident-ci'],
        ),
        (
            _GOOD.replace("  incident-ci:\n", "  other:\n"),
            ["the workflow has no incident-ci job"],
        ),
    ],
)
def test_the_per_job_findings_name_what_is_wrong(text, expected):
    findings = call_site_findings(workflow=load_workflow(text=text), required=True)
    assert findings == expected


@pytest.mark.parametrize("order", [("aa", "zz"), ("zz", "aa")])
def test_every_call_site_is_checked_whatever_its_order(order):
    guarded, unguarded = order
    text = (
        "jobs:\n  incident-ci:\n    runs-on: ubuntu-latest\n"
        f"  {guarded}:\n    needs: [incident-ci]\n    uses: {_USES}\n    with:\n{_GUARDED_WITH}"
        f"  {unguarded}:\n    needs: [incident-ci]\n    uses: {_USES}\n    with:\n"
        f"      incident-omitted: {_LITERAL}\n      incident-ci-result: {GUARDED_RESULT}\n"
    )
    findings = call_site_findings(workflow=load_workflow(text=text), required=True)
    assert findings == [
        f'job "{unguarded}": with.incident-omitted is not exactly {GUARDED_OMITTED}'
    ]


def test_a_workflow_with_no_call_site_passes_only_when_not_required():
    workflow = load_workflow(text="on: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n")
    assert call_site_findings(workflow=workflow, required=False) == []
    assert call_site_findings(workflow=workflow, required=True) == [
        "no job of the workflow uses reusable-check-matrix.yml"
    ]
    assert call_site_findings(workflow=None, required=True) == [
        "no job of the workflow uses reusable-check-matrix.yml"
    ]


def test_a_call_site_that_passes_no_incident_input_is_not_a_check_callers_finding():
    text = _workflow(with_block="")
    assert call_site_findings(workflow=load_workflow(text=text), required=False) == []
    # Negative control: at run time the same call site cannot authorize an omission.
    assert call_site_findings(workflow=load_workflow(text=text), required=True)


@pytest.mark.parametrize("text", ["- a\n- b\n", "a: [\n", "x: !!python/object:os.system {}\n"])
def test_a_text_that_is_not_a_safe_yaml_mapping_loads_as_none(text):
    assert load_workflow(text=text) is None
    # Negative control: a mapping loads.
    assert load_workflow(text="a: 1\n") == {"a": 1}


def test_without_pyyaml_nothing_loads(monkeypatch):
    monkeypatch.setitem(sys.modules, "yaml", None)
    assert load_workflow(text=_GOOD) is None
    monkeypatch.setitem(sys.modules, "yaml", yaml)
    assert load_workflow(text=_GOOD) is not None


@pytest.mark.parametrize(
    ("ref", "path"),
    [
        (f"{_REPOSITORY}/.github/workflows/ci.yml@refs/pull/7/merge", ".github/workflows/ci.yml"),
        (
            f"{_REPOSITORY}/.github/workflows/a.b-c_d.yaml@refs/heads/x",
            ".github/workflows/a.b-c_d.yaml",
        ),
        ("other/repo/.github/workflows/ci.yml@refs/heads/x", None),
        (f"{_REPOSITORY}/.github/workflows/ci.yml", None),
        (f"{_REPOSITORY}/.github/workflows/sub/ci.yml@x", None),
        (f"{_REPOSITORY}/../ci.yml@x", None),
        (".github/workflows/ci.yml@refs/heads/x", None),
        ("", None),
    ],
)
def test_the_calling_workflow_path_comes_only_from_this_repository_workflow_ref(ref, path):
    assert caller_path(workflow_ref=ref, repository=_REPOSITORY) == path


def _read(*, returncode=0, stdout="jobs: {}\n"):
    return Mock(return_value=GhRead(returncode=returncode, stdout=stdout, stderr=""))


def _fetch(*, read, repository=_REPOSITORY, path=".github/workflows/ci.yml", sha=_BASE):
    return fetch_at(repository=repository, path=path, sha=sha, read=read)


def test_the_base_copy_is_read_through_the_sanctioned_client_at_the_exact_commit():
    read = _read()
    text = _fetch(read=read)
    assert text == "jobs: {}\n"
    assert read.call_args.kwargs == {
        "args": [
            "api",
            "-H",
            "Accept: application/vnd.github.raw",
            f"repos/{_REPOSITORY}/contents/.github/workflows/ci.yml?ref={_BASE}",
        ],
        "timeout": 30,
    }


_BOUND = 1048576


@pytest.mark.parametrize(
    ("returncode", "size"),
    [(1, 9), (0, _BOUND + 1), (124, 0)],
    ids=["failed-read", "over-the-size-bound", "unspawned"],
)
def test_an_unreadable_base_copy_is_none(returncode, size):
    # Sizes, not megabyte strings, reach the assertions: a diff of two would stall the run.
    assert _fetch(read=_read(returncode=returncode, stdout="x" * size)) is None
    # Negative control: a successful read at the size bound is the text.
    assert len(_fetch(read=_read(stdout="x" * _BOUND)) or "") == _BOUND


@pytest.mark.parametrize(
    ("repository", "path", "sha"),
    [
        ("owner/repo/x", ".github/workflows/ci.yml", _BASE),
        (_REPOSITORY, "ci.yml", _BASE),
        (_REPOSITORY, ".github/workflows/ci.yml", "HEAD"),
        (_REPOSITORY, ".github/workflows/../ci.yml", _BASE),
    ],
)
def test_an_invalid_read_request_never_reaches_the_forge(repository, path, sha):
    read = _read()
    assert _fetch(read=read, repository=repository, path=path, sha=sha) is None
    assert read.call_count == 0


@pytest.mark.parametrize(
    ("caller", "base", "running", "reason"),
    [
        (None, _GOOD, _GOOD, 'the calling workflow "" could not be read'),
        (".github/workflows/ci.yml", None, _GOOD, "could not be read at the pull request's base"),
        (".github/workflows/ci.yml", _GOOD, None, "the pull request changes the calling workflow"),
        (".github/workflows/ci.yml", _GOOD, _GOOD + "\n", "the pull request changes"),
        (".github/workflows/ci.yml", "a: [\n", "a: [\n", "fails the call-site rule: no job"),
        (".github/workflows/ci.yml", _GOOD, _GOOD, None),
    ],
)
def test_the_call_site_reason_trusts_only_the_base_copy(caller, base, running, reason):
    found = call_site_reason(caller=caller, base_text=base, running_text=running)
    assert found == reason if reason is None else reason in (found or "")


def test_check_callers_parses_every_workflow_per_job(tmp_path):
    good, bad, broken = tmp_path / "good.yml", tmp_path / "bad.yml", tmp_path / "broken.yml"
    good.write_text(_GOOD, encoding="utf-8")
    bad.write_text(_BYPASSES["value on the next line"], encoding="utf-8")
    broken.write_text("a: [\n", encoding="utf-8")
    assert check_callers(paths=[good]) == []
    findings = check_callers(paths=[good, bad, broken])
    assert findings[0].startswith(f'{bad}: job "shared": with.incident-omitted is not exactly')
    assert findings[-1] == f"{broken}: not a YAML mapping (PyYAML is required to check it)"


def test_quoted_values_are_one_inert_line():
    assert call_site.quoted(value="a\n::error::b%0A") == '"a\\n::error::b%250A"'


# --- Round 3: nested reusable workflows and ambiguous YAML -------------------

_NESTED_HARMLESS = "on: workflow_call\njobs:\n  build:\n    runs-on: ubuntu-latest\n"


@pytest.mark.parametrize(
    "text",
    [
        "a: 1\nA: 2\n",
        "jobs:\n  x: {with: {incident-omitted: 1, Incident-Omitted: 2}}\n",
        "base: &b {k: 1}\nmerged:\n  <<: *b\n",
        "list:\n  - {a: 1, a: 2}\n",
    ],
    ids=["case-folded-duplicate", "nested-duplicate", "merge-key", "duplicate-in-a-sequence"],
)
def test_an_ambiguous_workflow_loads_as_none(text):
    assert load_workflow(text=text) is None
    # Negative control: an alias reused twice, with no merge key, is unambiguous.
    assert load_workflow(text="a: &x {k: 1}\nb: *x\nc: *x\n") == {
        "a": {"k": 1},
        "b": {"k": 1},
        "c": {"k": 1},
    }


def test_no_copies_reads_nothing():
    assert call_site.no_copies(path=".github/workflows/ci.yml") == (None, None)


def test_workflow_copies_reads_the_base_from_the_forge_and_the_ran_copy_from_disk(tmp_path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("ran\n", encoding="utf-8")
    (workflows / "bad.yml").write_bytes(b"\xff\xfe")
    read = _read(stdout="base\n")

    def copies(*, path, workspace=str(tmp_path)):
        return call_site.workflow_copies(
            path=path, repository=_REPOSITORY, sha=_BASE, workspace=workspace, read=read
        )

    facts = [
        copies(path=".github/workflows/ci.yml") == ("base\n", "ran\n"),
        copies(path=".github/workflows/missing.yml") == ("base\n", None),
        copies(path=".github/workflows/bad.yml") == ("base\n", None),
        copies(path=".github/workflows/ci.yml", workspace="") == ("base\n", None),
        copies(path="../ci.yml") == (None, None),
    ]
    assert all(facts), facts


def _reader(**copies_by_name: tuple[str | None, str | None]):
    def read(*, path):
        return copies_by_name.get(path.removeprefix(".github/workflows/"), (None, None))

    return read


def _caller(*uses: object) -> dict:
    return {"jobs": {f"j{i}": {"uses": u} for i, u in enumerate(uses)}}


@pytest.mark.parametrize(
    ("workflow", "copies", "reason"),
    [
        (_caller(_USES), _reader(), None),
        (
            _caller(_USES, "./.github/workflows/h.yml"),
            _reader(**{"h.yml": (_NESTED_HARMLESS,) * 2}),
            None,
        ),
        (_caller("org/x/.github/workflows/r.yml@v1"), _reader(), "may reach the matrix unchecked"),
        (_caller(["./.github/workflows/h.yml"]), _reader(), "may reach the matrix unchecked"),
        (_caller("./ci.yml"), _reader(), "may reach the matrix unchecked"),
        (
            _caller("./.github/workflows/h.yml"),
            _reader(),
            "which is unreadable at the base or changed",
        ),
        (
            _caller("./.github/workflows/h.yml"),
            _reader(**{"h.yml": (_NESTED_HARMLESS, _NESTED_HARMLESS + "\n")}),
            "which is unreadable at the base or changed",
        ),
        (
            _caller("./.github/workflows/h.yml"),
            _reader(**{"h.yml": ("- x\n",) * 2}),
            "which is unreadable",
        ),
        (
            _caller("./.github/workflows/w.yml"),
            _reader(**{"w.yml": (f"jobs:\n  m:\n    uses: {_USES}\n",) * 2}),
            "may reach the matrix unchecked",
        ),
    ],
    ids=[
        "direct-site-only",
        "harmless-local",
        "remote",
        "non-string-uses",
        "local-outside-workflows",
        "unreadable",
        "changed-by-the-pr",
        "nested-not-a-mapping",
        "nested-calls-the-matrix",
    ],
)
def test_nested_reason_walks_every_other_reusable_workflow(workflow, copies, reason):
    found = call_site.nested_reason(workflow=workflow, copies=copies)
    assert found == reason if reason is None else reason in (found or ""), found


def test_nested_reason_stops_at_four_levels_of_workflows():
    chain = {
        n: (f"jobs:\n  next:\n    uses: ./.github/workflows/{m}.yml\n",) * 2
        for n, m in (("a.yml", "b"), ("b.yml", "c"), ("c.yml", "d"))
    }
    found = call_site.nested_reason(
        workflow=_caller("./.github/workflows/a.yml"),
        copies=_reader(**chain, **{"d.yml": (_NESTED_HARMLESS,) * 2}),
    )
    assert "beyond GitHub's 4 levels" in (found or ""), found
    # Negative control: the same chain one level shorter is within the limit.
    shorter = {**chain, "c.yml": (_NESTED_HARMLESS,) * 2}
    assert (
        call_site.nested_reason(
            workflow=_caller("./.github/workflows/a.yml"), copies=_reader(**shorter)
        )
        is None
    )


def test_the_call_site_reason_names_the_nested_route():
    text = _GOOD + "  wrapped:\n    uses: org/x/.github/workflows/r.yml@v1\n"
    found = call_site_reason(caller=".github/workflows/ci.yml", base_text=text, running_text=text)
    assert (found or "").startswith(
        'the calling workflow ".github/workflows/ci.yml" calls a reusable workflow that may reach'
    )
    # Negative control: the same workflow without the nested job passes.
    assert (
        call_site_reason(caller=".github/workflows/ci.yml", base_text=_GOOD, running_text=_GOOD)
        is None
    )
