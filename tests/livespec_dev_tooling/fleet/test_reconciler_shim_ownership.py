"""The reusable reconciler asks the incident observer before it performs its step.

Review findings F1, F3 and F5 on livespec-dev-tooling#3915
(livespec-dev-tooling-ariayn): nothing in the reconciler called the ownership
transport, so a deployed pass reran, classified and reverted an incident's
failed run exactly as before. These tests pin where the question is asked
(after the decision, immediately before the one side effect), that only an
`ordinary` answer lets the step run, that the step is time-bounded, and they
execute the ownership step's own shell under bash.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from livespec_dev_tooling.fleet._reconciler_shim import REUSABLE_RECONCILER_BODY

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ariayn
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DECIDE = "      - name: Decide the ONE step this run takes\n"
_OWNERSHIP = "      - name: Ask the incident observer who owns this step\n"
_PERFORM = "      - name: Perform the ONE step\n"
_GATE = "        if: steps.ownership.outputs.status == 'ordinary'\n"
_MUTATIONS = (
    "gh run rerun",
    "gh api graphql",
    "gh label create",
    "gh pr edit",
    "gh pr merge",
    "gh pr close",
    "gh issue comment",
    "gh issue create",
)


def _step(*, body: str, name: str) -> str:
    """One step's text, from its `- name:` line to the next step or the end."""
    start = body.index(name)
    following = body.find("\n      - name: ", start + len(name))
    return body[start : len(body) if following == -1 else following + 1]


def _script(*, step: str) -> str:
    """A step's `run: |` block, dedented."""
    lines = step.partition("        run: |\n")[2].splitlines()
    return "\n".join(line.removeprefix("          ") for line in lines) + "\n"


def test_the_ownership_question_sits_between_the_decision_and_the_side_effect():
    body = REUSABLE_RECONCILER_BODY
    decide, ownership, perform = (body.find(name) for name in (_DECIDE, _OWNERSHIP, _PERFORM))
    first_mutation = min(body.find(command) for command in _MUTATIONS)

    assert -1 not in (decide, ownership, perform)
    assert decide < ownership < perform < first_mutation


def test_only_an_ordinary_answer_lets_the_one_step_run():
    """incident-owned and a failed question both leave the perform step skipped."""
    perform = _step(body=REUSABLE_RECONCILER_BODY, name=_PERFORM)

    assert perform.startswith(_PERFORM + _GATE)
    assert all(command in perform for command in _MUTATIONS)


def test_the_question_is_bounded_and_reads_the_callers_observer_configuration():
    ownership = _step(body=REUSABLE_RECONCILER_BODY, name=_OWNERSHIP)
    bound = re.search(r"(?m)^        timeout-minutes: (\d+)$", ownership)

    assert "        id: ownership\n" in ownership
    assert bound is not None
    assert 0 < int(bound.group(1)) <= 10
    assert "LIVESPEC_INCIDENT_OBSERVER_URL: ${{ vars.LIVESPEC_INCIDENT_OBSERVER_URL }}" in ownership
    assert (
        "LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR: "
        "${{ vars.LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR }}" in ownership
    )
    assert (
        "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN: "
        "${{ secrets.LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN }}" in ownership
    )


def test_the_transport_mirrors_the_perform_steps_rerun_target_rule():
    """The window adds the run the perform step reruns: the first failed gating run."""
    perform = _step(body=REUSABLE_RECONCILER_BODY, name=_PERFORM)

    assert (
        "run_id=$(jq -r '[ .[] | select(.conclusion == \"failure\") ] | first | .id' runs.json)"
        in perform
    )


# The ownership step's two jq programs, pinned so the stand-in below cannot drift
# from them. The stand-in lets the step's own shell run where jq is absent (the
# delegated gate's container), so the run is never skipped.
_JQ_OWNER = "jq -r '\"owner=\\(.status) reason=\\(.reason) receipt=\\(.receipt)\"' ownership.json"
_JQ_STATUS = "jq -r '.status' ownership.json"
_FAKE_JQ = """#!/usr/bin/env python3
import json
import sys

program, path = sys.argv[-2], sys.argv[-1]
with open(path, encoding="utf-8") as stream:
    answer = json.load(stream)
receipt = "null" if answer["receipt"] is None else answer["receipt"]
if program == ".status":
    print(answer["status"])
else:
    print("owner=" + answer["status"] + " reason=" + answer["reason"] + " receipt=" + receipt)
"""


def test_the_stand_in_jq_implements_exactly_the_steps_two_programs():
    script = _script(step=_step(body=REUSABLE_RECONCILER_BODY, name=_OWNERSHIP))

    assert [line.strip() for line in script.splitlines() if "jq " in line] == [
        _JQ_OWNER,
        'echo "status=$(' + _JQ_STATUS + ')" >> "${GITHUB_OUTPUT}"',
    ]


def _run_ownership_step(*, tmp_path: Path, repository: str, url: str) -> tuple[int, str, str]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = tmp_path / "bin"
    tools.mkdir()
    _ = (tools / "jq").write_text(_FAKE_JQ, encoding="utf-8")
    (tools / "jq").chmod(0o755)
    (workspace / ".livespec-dev-tooling").symlink_to(_REPO_ROOT)
    _ = (workspace / "state.json").write_text(
        json.dumps({"head_sha": "a" * 40, "commits": []}), encoding="utf-8"
    )
    _ = (workspace / "runs.json").write_text("[]", encoding="utf-8")
    _ = (workspace / "step.json").write_text(json.dumps({"kind": "open-revert"}), encoding="utf-8")
    output = workspace / "github-output"
    script = _script(step=_step(body=REUSABLE_RECONCILER_BODY, name=_OWNERSHIP))
    environment = {
        "PATH": str(tools) + os.pathsep + os.environ["PATH"],
        "REPO": repository,
        "LIVESPEC_INCIDENT_OBSERVER_URL": url,
        "LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR": "",
        "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": "",
        "GITHUB_OUTPUT": str(output),
    }
    completed = subprocess.run(
        [shutil.which("bash") or "bash", "-c", script],
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    written = output.read_text(encoding="utf-8") if output.exists() else ""
    return completed.returncode, completed.stdout + completed.stderr, written


def test_the_ownership_step_lets_an_unobserved_repository_run_its_policy(tmp_path):
    status, log, written = _run_ownership_step(
        tmp_path=tmp_path, repository="thewoolleyman/livespec", url=""
    )

    assert (status, written) == (0, "status=ordinary\n")
    assert "owner=ordinary reason=no incident observer is configured" in log


def test_the_ownership_step_stops_an_observed_repository_with_no_answer(tmp_path):
    status, log, written = _run_ownership_step(
        tmp_path=tmp_path, repository="thewoolleyman/livespec-dev-tooling", url=""
    )

    assert (status, written) == (1, "")
    assert "LIVESPEC_INCIDENT_OBSERVER_URL is empty in this run" in log
