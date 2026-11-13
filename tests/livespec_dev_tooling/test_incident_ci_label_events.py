"""Incident label events hold ci-green until CI has re-run on the head; nothing else reacts.

Work-item livespec-dev-tooling-6xyc42 (plan expedited-incident-response-flag,
epic livespec-dev-tooling-bqnzcm), carrying what livespec-dev-tooling-egy3ri
left undone. `SPECIFICATION/contracts.md`, in its expedited incident execution
contract, requires that "Head and mode changes MUST invalidate stale verdicts",
and its scenario requires that "label events reconcile mode before permitting
merge". The live behaviour is host-captured (a real label event and the runs it
starts exist only on the forge), so this file holds the workflow SHAPE as exact
rules, because each rule here is a security or merge-safety property:

- **Only an incident label event of a same-repository PR acts.** The trigger
  set, the job set and the job's `if:` are pinned exactly, so a widened
  condition (`|| true`), a dropped fork guard or an added trigger is a finding.
- **Only incident label events share a concurrency group.** A non-incident
  label in the same edit must never cancel an incident restart in flight.
- **Least privilege, no injection.** The workflow grants nothing; the job holds
  exactly `actions: write`, `checks: write` and `pull-requests: read`, and no
  `run:` script interpolates an expression (`${{ ... }}`) of any kind.
- **The hold comes first and stays until the re-run has completed.** The
  restart selects the newest pull_request CI run of THIS PR (by number) on the
  current head and stops green when none is listed yet. It posts an
  in-progress `ci-green` check run, stops an unfinished run (the cancel
  retried, the stop waited for, both bounded), re-runs it, and waits, bounded
  and within the job's timeout, for the re-run to complete. Only then does it
  release, as neutral, the holds of this label on the head up to its own.
- **auto-enable-merge cannot race the hold.** Its gate skips the unlabeled
  event of the incident label, and `ci.yml` still does not trigger on labels.
- **Every forge call retries an unusable answer under one rule.** The job's
  first step puts livespec-forge-read on its path through the composite Action
  `forge-read` at a release tag of this library (the workflow checks nothing
  out), and the script makes no bare `gh api` call. The hold create carries an
  external_id naming this job, and the two writes whose outcome can be unknown
  (exit 75), the hold create and the re-run, are repeated only after the step
  re-reads the forge state they change (work item livespec-dev-tooling-pwabtl).

Each rule is exercised twice, as the sibling `test_incident_ci_workflow_wiring`
does: against the committed workflow (expecting silence) and against a copy
mutated to break exactly that rule (expecting the finding).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

__all__: list[str] = []


_WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
_LABEL_WORKFLOW = _WORKFLOWS / "incident-label-ci.yml"
_CI_YML = _WORKFLOWS / "ci.yml"
_AUTO_MERGE = _WORKFLOWS / "auto-enable-merge.yml"

_JOB = "restart-ci-on-head"
_JOB_TIMEOUT_MINUTES = 250
_LABEL_TYPES = frozenset({"labeled", "unlabeled"})
_INCIDENT_LABEL_TEST = "github.event.label.name == 'expedited-incident-response'"
_FORK_GUARD = "github.event.pull_request.head.repo.full_name == github.repository"
_JOB_IF = "${{ " + _INCIDENT_LABEL_TEST + " && " + _FORK_GUARD + " }}"
_GROUP_KEY = "${{ " + _INCIDENT_LABEL_TEST + " && 'incident' || github.run_id }}"
_CONCURRENCY = {
    "group": "incident-label-ci-${{ github.event.pull_request.number }}-" + _GROUP_KEY,
    "cancel-in-progress": "true",
}
_JOB_PERMISSIONS = {"actions": "write", "checks": "write", "pull-requests": "read"}
_EXPRESSION = "${{"

# The forge reads and writes the restart must make.
_HEAD_READ = """livespec-forge-read incident-label-head-read "repos/${repo}/pulls/${PR_NUMBER}" | jq -r '.head.sha'"""
_RUNS_ON_HEAD = "actions/workflows/ci.yml/runs?event=pull_request&head_sha=${head}"
_SELECT_BY_PR = "select(any(.pull_requests[]; .number == (env.PR_NUMBER | tonumber)))"
_NO_RUN = re.compile(r'if \[ -z "\$run_id" \]; then\n(?P<body>(?:.*\n)*?)[ ]*fi\n')
_HOLD_POST = 'created="$(livespec-forge-read incident-label-hold-create --method POST "repos/${repo}/check-runs"'
_HOLD_FIELDS = '--field name=ci-green --field head_sha="$head" --field status=in_progress'
_HOLD_EXPORT = 'export HOLD_ID="$hold_id"'
_CANCEL = '/actions/runs/${run_id}/cancel"'
_RERUN = '/actions/runs/${run_id}/rerun"'
_LOOP_BREAK = '[ "$status" = "completed" ] && break'
_RETRY_HEAD = r"for attempt in \$\(seq 1 (?P<bound>\d+)\); do\n"
_RETRY_CANCEL = "".join(
    (
        r"[ ]*if livespec-forge-read incident-label-run-cancel --method POST --idempotent ",
        r'"repos/\$\{repo\}/actions/runs/\$\{run_id\}/cancel"',
    )
)
_RETRY = re.compile(_RETRY_HEAD + _RETRY_CANCEL + r" >/dev/null; then\n[ ]*break\n")
_UNTIL_COMPLETED = r'(?P<body>(?:.*\n)*?)[ ]*done\n[ ]*if \[ "\$status" != "completed" \]; then\n'
_THEN_EXIT = r"(?P<after>(?:.*\n)*?)[ ]*fi\n"
_STOP_WAIT = re.compile(
    r"for _ in \$\(seq 1 (?P<bound>\d+)\); do\n" + _UNTIL_COMPLETED + _THEN_EXIT
)
_RERUN_WAIT = re.compile(
    r"for poll in \$\(seq 1 (?P<bound>\d+)\); do\n[ ]*sleep (?P<every>\d+)\n"
    + _UNTIL_COMPLETED
    + _THEN_EXIT
)
_HELD_TITLE = 'startswith("held: expedited-incident-response")'
_HOLDS_SELECT = (
    'select(.status != "completed" and ((.output.title // "") | '
    + _HELD_TITLE
    + ") and .id <= (env.HOLD_ID | tonumber))"
)
_RELEASE = "".join(
    (
        "livespec-forge-read incident-label-hold-release --method PATCH --idempotent ",
        '"repos/${repo}/check-runs/${id}"',
    )
)
_RELEASE_FIELDS = "--field status=completed --field conclusion=neutral"

# The forge-read rule (livespec-dev-tooling-pwabtl): the Action at a release tag,
# no bare forge call, and a re-read of the state before a write whose outcome is
# unknown (exit 75) is repeated.
_FORGE_READ_USES = re.compile(
    r"thewoolleyman/livespec-dev-tooling/\.github/actions/forge-read@v\d+\.\d+\.\d+"
)
_BARE_GH = re.compile(r"(?<![\w-])gh api\b")
_HOLD_REF = '--field external_id="$hold_ref"'
_HOLD_REREAD = re.compile(
    "".join(
        (
            r'\[ "\$created_rc" -eq 75 \] \|\| exit "\$created_rc"\n',
            r'[ ]*hold_id="\$\(livespec-forge-read incident-label-hold-read "\$holds" \| ',
            r"jq -r --arg ref \"\$hold_ref\" '\[\.check_runs\[\] \| select\(\.external_id == \$ref\)\]",
            r"[^\n]*\n",
            r'[ ]*\[ -n "\$hold_id" \] && break\n',
        )
    )
)
_RERUN_REREAD = re.compile(
    "".join(
        (
            r'\[ "\$rerun_rc" -eq 75 \] \|\| exit "\$rerun_rc"\n',
            r'[ ]*after="\$\(livespec-forge-read incident-label-run-read "repos/\$\{repo\}/actions/runs/',
            r"\$\{run_id\}\" \| jq -r '\.run_attempt'\)\"\n",
            r'[ ]*if \[ "\$after" -gt "\$before" \]; then\n',
        )
    )
)

_AUTO_MERGE_SKIP = "&& !(github.event.action == 'unlabeled' && " + _INCIDENT_LABEL_TEST + ")"


def _map(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _seq(*, value: object) -> list[Any]:
    return cast("list[Any]", value) if isinstance(value, list) else []


def _load(*, source: str) -> dict[str, Any]:
    # BaseLoader keeps every scalar a string, so the bare key `on` stays "on"
    # rather than becoming the boolean True, and `true` stays "true".
    return _map(value=yaml.load(source, Loader=yaml.BaseLoader))  # noqa: S506


def _triggers(*, workflow: dict[str, Any]) -> dict[str, Any]:
    return _map(value=workflow.get("on"))


def _bounded(*, match: re.Match[str] | None) -> bool:
    """A wait loop with a real bound that breaks on completion and exits non-zero after."""
    return (
        match is not None
        and int(match.group("bound")) >= 1
        and _LOOP_BREAK in match.group("body")
        and "exit 1" in match.group("after")
    )


def _workflow_findings(*, workflow: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    triggers = _triggers(workflow=workflow)
    types = frozenset(
        str(t) for t in _seq(value=_map(value=triggers.get("pull_request")).get("types"))
    )
    if set(triggers) != {"pull_request"} or types != _LABEL_TYPES:
        findings.append("the label workflow does not trigger on exactly labeled/unlabeled PRs")
    if workflow.get("permissions") != {}:
        findings.append("the label workflow grants workflow-level permissions")
    if workflow.get("concurrency") != _CONCURRENCY:
        findings.append("the concurrency group is not keyed to incident label events only")
    return findings


def _job_findings(*, jobs: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if set(jobs) != {_JOB}:
        findings.append(f"the label workflow's jobs are not exactly {_JOB}")
    job = _map(value=jobs.get(_JOB))
    if job.get("if") != _JOB_IF:
        findings.append(f"job {_JOB} is not gated on exactly the incident label and the fork guard")
    if job.get("permissions") != _JOB_PERMISSIONS:
        findings.append(f"job {_JOB} holds permissions other than {_JOB_PERMISSIONS}")
    if job.get("timeout-minutes") != str(_JOB_TIMEOUT_MINUTES):
        findings.append(f"job {_JOB} does not time out at {_JOB_TIMEOUT_MINUTES} minutes")
    return findings


def _selection_findings(*, script: str) -> list[str]:
    findings: list[str] = []
    if _EXPRESSION in script:
        findings.append("a run: script interpolates an expression")
    if _HEAD_READ not in script:
        findings.append("the restart does not read the current head from the forge")
    if _RUNS_ON_HEAD not in script or _SELECT_BY_PR not in script:
        findings.append("the restart does not select THIS PR's pull_request CI run on the head")
    no_run = _NO_RUN.search(script)
    if no_run is None or "exit 0" not in no_run.group("body"):
        findings.append("a PR with no CI run listed yet does not stop green")
    return findings


def _order_findings(*, script: str) -> list[str]:
    """hold < retried cancel < stop wait < re-run < re-run wait < release."""
    findings: list[str] = []
    if _HOLD_POST not in script or _HOLD_FIELDS not in script or _HOLD_EXPORT not in script:
        findings.append("the hold is not an in-progress ci-green check run on the head")
        return findings
    retry, stop = _RETRY.search(script), _STOP_WAIT.search(script)
    rerun, release = script.find(_RERUN), script.find(_RELEASE)
    if retry is None or int(retry.group("bound")) < 1 or not _bounded(match=stop):
        findings.append("an unfinished run is not stopped by a retried, waited-for cancel")
    if rerun < 0:
        findings.append("the restart does not re-run the CI run")
        return findings
    touched = [i for i in (script.find(_CANCEL), rerun) if i >= 0]
    if script.index(_HOLD_POST) > min(touched):
        findings.append("ci-green is not held before the run is touched")
    if stop is not None and stop.end() > rerun:
        findings.append("the run is re-run before the stop has been waited for")
    wait = _RERUN_WAIT.search(script)
    if not _bounded(match=wait) or wait is None or wait.start() < rerun:
        findings.append("the hold is not kept until the re-run completes")
    elif int(wait.group("bound")) * int(wait.group("every")) > (_JOB_TIMEOUT_MINUTES - 20) * 60:
        findings.append("the re-run wait outlasts the job's timeout")
    if release < 0 or _RELEASE_FIELDS not in script or _HOLDS_SELECT not in script:
        findings.append("the holds up to this job's own are not released as neutral")
    elif wait is not None and release < wait.end():
        findings.append("the hold is released before the re-run completes")
    return findings


def _forge_read_findings(*, jobs: dict[str, Any], script: str) -> list[str]:
    findings: list[str] = []
    steps = _seq(value=_map(value=jobs.get(_JOB)).get("steps"))
    first = str(_map(value=steps[0] if steps else {}).get("uses", ""))
    if _FORGE_READ_USES.fullmatch(first) is None:
        findings.append("livespec-forge-read is not put on the path from a release tag first")
    if _BARE_GH.search(script) is not None:
        findings.append("a forge call bypasses livespec-forge-read")
    if _HOLD_REF not in script or _HOLD_REREAD.search(script) is None:
        findings.append(
            "the hold create is repeated without re-reading the hold by its external_id"
        )
    if _RERUN_REREAD.search(script) is None:
        findings.append("the re-run is repeated without re-reading the run's attempt")
    return findings


def label_workflow_findings(*, source: str) -> list[str]:
    """Every way the label workflow departs from its pinned, merge-safe shape."""
    workflow = _load(source=source)
    jobs = _map(value=workflow.get("jobs"))
    script = "\n".join(
        str(_map(value=step).get("run", ""))
        for job in jobs.values()
        for step in _seq(value=_map(value=job).get("steps"))
    )
    return [
        *_workflow_findings(workflow=workflow),
        *_job_findings(jobs=jobs),
        *_selection_findings(script=script),
        *_order_findings(script=script),
        *_forge_read_findings(jobs=jobs, script=script),
    ]


def ci_label_trigger_findings(*, source: str) -> list[str]:
    """ci.yml must not start its full matrix on every label event."""
    pull_request = _map(value=_triggers(workflow=_load(source=source)).get("pull_request"))
    types = {str(t) for t in _seq(value=pull_request.get("types"))}
    if types & _LABEL_TYPES:
        return ["ci.yml starts its full matrix on every label event"]
    return []


def auto_merge_findings(*, source: str) -> list[str]:
    """auto-enable-merge must not arm on the incident label's unlabeled event."""
    jobs = _map(value=_load(source=source).get("jobs"))
    gate = str(_map(value=jobs.get("enable-auto-merge")).get("if", ""))
    if _AUTO_MERGE_SKIP not in gate:
        return ["auto-enable-merge arms on the incident label's unlabeled event"]
    return []


def _mutated(*, source: str, old: str, new: str) -> str:
    """Replace exactly one occurrence, so a mutation never lands twice or nowhere."""
    assert source.count(old) == 1, old
    return source.replace(old, new)


def test_a_label_workflow_with_no_steps_is_a_finding() -> None:
    source = _LABEL_WORKFLOW.read_text(encoding="utf-8")
    cut = source[: source.index("    steps:\n")] + "    steps: []\n"
    assert _FIRST in label_workflow_findings(source=cut)


def test_committed_label_workflow_holds_until_ci_has_rerun_on_incident_events_only() -> None:
    assert label_workflow_findings(source=_LABEL_WORKFLOW.read_text(encoding="utf-8")) == []


def test_committed_ci_yml_does_not_trigger_on_label_events() -> None:
    assert ci_label_trigger_findings(source=_CI_YML.read_text(encoding="utf-8")) == []


def test_committed_auto_enable_merge_skips_the_incident_unlabeled_event() -> None:
    assert auto_merge_findings(source=_AUTO_MERGE.read_text(encoding="utf-8")) == []


_TRIGGERS = "the label workflow does not trigger on exactly labeled/unlabeled PRs"
_KEYED = "the concurrency group is not keyed to incident label events only"
_GATE = f"job {_JOB} is not gated on exactly the incident label and the fork guard"
_HOLD = "the hold is not an in-progress ci-green check run on the head"
_STOP = "an unfinished run is not stopped by a retried, waited-for cancel"
_KEPT = "the hold is not kept until the re-run completes"
_RELEASED = "the holds up to this job's own are not released as neutral"
_HOLD_LINE = '          holds="repos/'
_RERUN_LINE = (
    '            livespec-forge-read incident-label-run-rerun --method POST "repos/${repo}'
    + _RERUN
    + " >/dev/null || rerun_rc=$?\n"
)
_FIRST = "livespec-forge-read is not put on the path from a release tag first"
_BYPASS = "a forge call bypasses livespec-forge-read"
_HOLD_BLIND = "the hold create is repeated without re-reading the hold by its external_id"
_RERUN_BLIND = "the re-run is repeated without re-reading the run's attempt"
_USES = "uses: thewoolleyman/livespec-dev-tooling/.github/actions/forge-read@v1.203.0"


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("    types: [labeled, unlabeled]\n", "    types: [labeled]\n", _TRIGGERS),
        (
            "    types: [labeled, unlabeled]\n",
            "    types: [labeled, unlabeled]\n  pull_request_target:\n",
            _TRIGGERS,
        ),
        (
            "\npermissions: {}\n",
            "\npermissions:\n  actions: write\n",
            "the label workflow grants workflow-level permissions",
        ),
        (
            "concurrency:\n  group: " + _CONCURRENCY["group"] + "\n  cancel-in-progress: true\n",
            "",
            _KEYED,
        ),
        ("-" + _GROUP_KEY + "\n", "\n", _KEYED),
        (
            "  restart-ci-on-head:\n",
            "  restart-ci-on-head:\n    name: x\n  second:\n",
            f"the label workflow's jobs are not exactly {_JOB}",
        ),
        ("== github.repository }}\n", "== github.repository || true }}\n", _GATE),
        (" && " + _FORK_GUARD + " }}", " }}", _GATE),
        (
            "      pull-requests: read\n",
            "      pull-requests: write\n      contents: write\n",
            f"job {_JOB} holds permissions other than {_JOB_PERMISSIONS}",
        ),
        (
            "    timeout-minutes: 250\n",
            "    timeout-minutes: 15\n",
            f"job {_JOB} does not time out at {_JOB_TIMEOUT_MINUTES} minutes",
        ),
        (
            "          set -euo pipefail\n",
            '          set -euo pipefail\n          echo "${{ github.event.pull_request.title }}"\n',
            "a run: script interpolates an expression",
        ),
        (
            "jq -r '.head.sha'",
            "jq -r '.base.sha'",
            "the restart does not read the current head from the forge",
        ),
        (
            _SELECT_BY_PR,
            "select(true)",
            "the restart does not select THIS PR's pull_request CI run on the head",
        ),
        (
            "\n            exit 0\n",
            "\n            exit 1\n",
            "a PR with no CI run listed yet does not stop green",
        ),
        ("status=in_progress", "status=completed --field conclusion=success", _HOLD),
        (_HOLD_EXPORT + "\n", "\n", _HOLD),
        ("$(seq 1 30)", "$(seq 1 0)", _STOP),
        (
            '/cancel" >/dev/null; then\n                break\n',
            '/cancel" >/dev/null; then\n                true\n',
            _STOP,
        ),
        ('/cancel"', '/approve"', _STOP),
        ("$(seq 1 60)", "$(seq 1 0)", _STOP),
        (
            '[ "$status" = "completed" ] && break\n              sleep 10\n',
            "true\n              sleep 10\n",
            _STOP,
        ),
        (
            'it cannot be re-run, and ci-green stays held"\n              exit 1\n',
            'it cannot be re-run, and ci-green stays held"\n',
            _STOP,
        ),
        ('/rerun"', '/rerun-failed-jobs"', "the restart does not re-run the CI run"),
        (_HOLD_LINE, _RERUN_LINE + _HOLD_LINE, "ci-green is not held before the run is touched"),
        (
            _RERUN_LINE,
            "",
            "the restart does not re-run the CI run",
        ),
        ("$(seq 1 460)", "$(seq 1 0)", _KEPT),
        ("$(seq 1 460)", "$(seq 1 600)", "the re-run wait outlasts the job's timeout"),
        (
            '[ "$status" = "completed" ] && break\n            if [ $((poll',
            "true\n            if [ $((poll",
            _KEPT,
        ),
        (
            'toggling the label again retries"\n            exit 1\n',
            'toggling the label again retries"\n',
            _KEPT,
        ),
        ("conclusion=neutral", "conclusion=success", _RELEASED),
        (
            "            livespec-forge-read incident-label-hold-release",
            "            true incident-label-hold-release",
            _RELEASED,
        ),
        (" and .id <= (env.HOLD_ID | tonumber)", "", _RELEASED),
        (_HELD_TITLE, "true", _RELEASED),
        (
            _RERUN_LINE,
            "            " + _RELEASE + " " + _RELEASE_FIELDS + "\n" + _RERUN_LINE,
            "the hold is released before the re-run completes",
        ),
        (
            _USES,
            "uses: thewoolleyman/livespec-dev-tooling/.github/actions/forge-read@master",
            _FIRST,
        ),
        (_USES, "uses: ./.github/actions/forge-read", _FIRST),
        (
            "          set -euo pipefail\n",
            '          set -euo pipefail\n          gh api "repos/${GITHUB_REPOSITORY}" >/dev/null\n',
            _BYPASS,
        ),
        (' \\\n              --field external_id="$hold_ref"', "", _HOLD_BLIND),
        (
            '            [ -n "$hold_id" ] && break\n',
            "            true\n",
            _HOLD_BLIND,
        ),
        (
            '            [ "$created_rc" -eq 75 ] || exit "$created_rc"\n',
            "",
            _HOLD_BLIND,
        ),
        (
            '            if [ "$after" -gt "$before" ]; then\n',
            "            if false; then\n",
            _RERUN_BLIND,
        ),
        (
            '            [ "$rerun_rc" -eq 75 ] || exit "$rerun_rc"\n',
            "",
            _RERUN_BLIND,
        ),
    ],
)
def test_each_label_workflow_rule_has_a_negative_control(
    *, old: str, new: str, expected: str
) -> None:
    source = _mutated(source=_LABEL_WORKFLOW.read_text(encoding="utf-8"), old=old, new=new)
    assert expected in label_workflow_findings(source=source)


def test_a_rerun_before_the_stop_is_waited_for_is_a_finding() -> None:
    source = _LABEL_WORKFLOW.read_text(encoding="utf-8")
    moved = _mutated(source=source, old=_RERUN_LINE, new="")
    moved = _mutated(
        source=moved,
        old="            for _ in $(seq 1 60); do\n",
        new=_RERUN_LINE + "            for _ in $(seq 1 60); do\n",
    )
    assert "the run is re-run before the stop has been waited for" in label_workflow_findings(
        source=moved
    )


def test_a_rerun_wait_that_is_gone_entirely_is_a_finding() -> None:
    source = _LABEL_WORKFLOW.read_text(encoding="utf-8")
    start = source.index("          for poll in $(seq 1 460); do\n")
    end = source.index("          for id in $(")
    assert _KEPT in label_workflow_findings(source=source[:start] + source[end:])


def test_the_ci_label_trigger_rule_has_a_negative_control() -> None:
    source = _mutated(
        source=_CI_YML.read_text(encoding="utf-8"),
        old="\n  pull_request:\n  push:\n",
        new="\n  pull_request:\n    types: [opened, synchronize, reopened, labeled, unlabeled]\n  push:\n",
    )
    assert ci_label_trigger_findings(source=source) == [
        "ci.yml starts its full matrix on every label event"
    ]


def test_the_auto_merge_skip_rule_has_a_negative_control() -> None:
    source = _mutated(
        source=_AUTO_MERGE.read_text(encoding="utf-8"),
        old="      " + _AUTO_MERGE_SKIP + "\n",
        new="",
    )
    assert auto_merge_findings(source=source) == [
        "auto-enable-merge arms on the incident label's unlabeled event"
    ]
