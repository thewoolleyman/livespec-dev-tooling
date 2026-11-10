"""reusable-check-matrix omits only an authorized, allowlisted leg, only on a pull request.

Work-item livespec-dev-tooling-hlxbsv (plan expedited-incident-response-flag,
epic livespec-dev-tooling-bqnzcm): finding 4 of the independent review of
livespec-dev-tooling#3911, and the six findings of the review of
livespec-dev-tooling#3966. The live behaviour is a GitHub Actions run, so this
file holds the workflow's SHAPE, plus a step-by-step simulation of one leg that
evaluates the committed `if:` expressions and runs the real
`incident_matrix_omission` decision:

- **Pinned steps.** The consumer checkout, the Actions checkout
  (`thewoolleyman/livespec-dev-tooling` at `inputs.ref`), the release
  resolution, the released checkout (`thewoolleyman/livespec-dev-tooling` at
  the resolved tag), the decision (run from the released checkout), the report
  (with its step-summary write) and the job name are each pinned exactly, in
  order. A checkout moved to the PR head or to the consumer's repository fails
  here by name.
- **Readers.** The `incident-omitted` input is read by the decision step's env
  and by the exact `!= '[]'` gate of the three incident steps, and nowhere
  else: no `contains()` ever sees the raw input.
- **The master-push guard.** The three incident steps run on a pull_request
  event only; the report, setup and run-check guards repeat that test.

The simulation then proves the outcomes: a push, pull_request_target,
merge_group or workflow_dispatch runs every check whatever the input; a
non-incident PR omits nothing and resolves no release; an authorized incident
omits only allowlisted module-slug legs; a fork, an unlabeled PR, a failed
incident-ci or a miswired caller omits nothing; a malformed input fails every
leg before any reports an omission.

Each rule is exercised twice: against the committed workflow (expecting
silence) and against a copy mutated to break exactly that rule (expecting the
finding).
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from livespec_dev_tooling.incident_matrix_call_site import GUARDED_OMITTED, GUARDED_RESULT
from livespec_dev_tooling.incident_matrix_omission import IncidentAuthority, decide

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "reusable-check-matrix.yml"

_INPUTS = ("incident-omitted", "incident-ci-result")
_CONSUMER_CHECKOUT = "Checkout consumer repo"
_ACTIONS_CHECKOUT = "Checkout livespec-dev-tooling Actions"
_RELEASE = "Resolve the latest livespec-dev-tooling release for the incident decision"
_RELEASED_CHECKOUT = "Checkout the released livespec-dev-tooling incident decision"
_DECISION = "Decide incident omission for this leg"
_REPORT = "omitted-by-incident-policy (per the caller's incident CI aggregate)"
_SETUP = "Setup toolchain"
_RUN = "Run check"
_ORDER = (
    _CONSUMER_CHECKOUT,
    _ACTIONS_CHECKOUT,
    _RELEASE,
    _RELEASED_CHECKOUT,
    _DECISION,
    _REPORT,
    _SETUP,
    _RUN,
)
_INVOCATION = "-m livespec_dev_tooling.incident_matrix_omission"
_DECISION_RUN = "python3 -m livespec_dev_tooling.incident_matrix_omission"
_DEV_TOOLING = "thewoolleyman/livespec-dev-tooling"

_GATE = "${{ github.event_name == 'pull_request' && inputs.incident-omitted != '[]' }}"
_OMIT = "github.event_name == 'pull_request' && steps.incident.outputs.omit == 'true'"
_REPORT_IF = "${{ " + _OMIT + " }}"
_RUN_IF = "${{ !(" + _OMIT + ") }}"
_GUARDS = {
    _CONSUMER_CHECKOUT: None,
    _ACTIONS_CHECKOUT: None,
    _RELEASE: _GATE,
    _RELEASED_CHECKOUT: _GATE,
    _DECISION: _GATE,
    _REPORT: _REPORT_IF,
    _SETUP: _RUN_IF,
    _RUN: _RUN_IF,
}
_RELEASE_RUN = (
    'tag="$(gh api repos/thewoolleyman/livespec-dev-tooling/releases/latest --jq .tag_name)"\n'
    'if ! [[ "$tag" =~ ^v[0-9]+[.][0-9]+[.][0-9]+$ ]]; then\n'
    '  echo "::error::could not resolve the latest livespec-dev-tooling release tag"\n'
    "  exit 1\n"
    "fi\n"
    'echo "tag=${tag}" >> "$GITHUB_OUTPUT"\n'
)
_REPORT_RUN = (
    "echo \"omitted-by-incident-policy: ${MEMBER} was not executed. The caller's passed "
    'incident CI aggregate defers it for this pull request head." | tee -a "$GITHUB_STEP_SUMMARY"\n'
)
_PINNED = {
    _CONSUMER_CHECKOUT: {"name": _CONSUMER_CHECKOUT, "uses": "actions/checkout@v5"},
    _ACTIONS_CHECKOUT: {
        "name": _ACTIONS_CHECKOUT,
        "uses": "actions/checkout@v5",
        "with": {
            "repository": _DEV_TOOLING,
            "ref": "${{ inputs.ref }}",
            "path": ".livespec-dev-tooling-actions",
        },
    },
    _RELEASE: {
        "name": _RELEASE,
        "id": "release",
        "if": _GATE,
        "shell": "bash",
        "env": {"GH_TOKEN": "${{ github.token }}"},
        "run": _RELEASE_RUN,
    },
    _RELEASED_CHECKOUT: {
        "name": _RELEASED_CHECKOUT,
        "if": _GATE,
        "uses": "actions/checkout@v5",
        "with": {
            "repository": _DEV_TOOLING,
            "ref": "refs/tags/${{ steps.release.outputs.tag }}",
            "path": ".livespec-dev-tooling-released",
            "persist-credentials": False,
        },
    },
    _DECISION: {
        "name": _DECISION,
        "id": "incident",
        "if": _GATE,
        "shell": "bash",
        "working-directory": ".livespec-dev-tooling-released",
        "env": {
            "GH_TOKEN": "${{ github.token }}",
            "CALLER_WORKFLOW_REF": "${{ github.workflow_ref }}",
            "INCIDENT_OMITTED": "${{ inputs.incident-omitted }}",
            "INCIDENT_CI_RESULT": "${{ inputs.incident-ci-result }}",
            "MATRIX_CHECK": "${{ matrix.check }}",
        },
        "run": _DECISION_RUN,
    },
    _REPORT: {
        "name": _REPORT,
        "if": _REPORT_IF,
        "shell": "bash",
        "env": {"MEMBER": "${{ matrix.check }}"},
        "run": _REPORT_RUN,
    },
}

_ALL_SIX = json.dumps(
    [
        "check-check-coverage-incremental",
        "check-coverage",
        "check-heading-coverage",
        "check-heading-coverage-debt-register",
        "check-no-todo-registry",
        "check-per-file-coverage",
    ]
)
_ALLOWLISTED_LEGS = ("heading_coverage", "per_file_coverage", "no_todo_registry")
_OTHER_LEGS = ("lint", "types", "coverage", "check-heading-coverage")
_LEGS = _ALLOWLISTED_LEGS + _OTHER_LEGS
# Every leg slug as a list: a guard that reads the raw input would omit them all.
_EVERY_LEG = json.dumps(list(_LEGS))
_NOT_ALLOWLISTED = '["check-lint", "check-types", "lint", "types"]'

_REPOSITORY = "owner/repo"
_PAYLOAD = {
    "pull_request": {
        "labels": [{"name": "expedited-incident-response"}],
        "head": {"repo": {"full_name": _REPOSITORY}},
        "base": {"repo": {"full_name": _REPOSITORY}},
    }
}
_CALLER = (
    "jobs:\n  incident-ci:\n    runs-on: ubuntu-latest\n  shared:\n    needs: [incident-ci]\n"
    "    uses: thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-check-matrix.yml@v1\n"
    f"    with:\n      incident-omitted: {GUARDED_OMITTED}\n"
    f"      incident-ci-result: {GUARDED_RESULT}\n"
)
# A quoted, spaced key with a literal list: valid YAML the old text rule let through.
_QUOTED_KEY_BYPASS = _CALLER.replace(
    f"incident-omitted: {GUARDED_OMITTED}", '"incident-omitted" : \'["check-heading-coverage"]\''
)
_AUTHORIZED = IncidentAuthority(
    payload=_PAYLOAD,
    repository=_REPOSITORY,
    incident_ci_result="",
    caller=".github/workflows/ci.yml",
    base_text=_CALLER,
    running_text=_CALLER,
)
_UNAUTHORIZED = (
    replace(_AUTHORIZED, payload={"pull_request": {**_PAYLOAD["pull_request"], "labels": []}}),
    replace(
        _AUTHORIZED,
        payload={
            "pull_request": {**_PAYLOAD["pull_request"], "head": {"repo": {"full_name": "f/r"}}}
        },
    ),
    replace(_AUTHORIZED, running_text=_CALLER.replace(GUARDED_OMITTED, "'[\"x\"]'")),
    replace(
        _AUTHORIZED,
        base_text=_QUOTED_KEY_BYPASS,
        running_text=_QUOTED_KEY_BYPASS,
    ),
)


def _load() -> dict[Any, Any]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _inputs(*, workflow: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML reads the bare `on:` key as the boolean True.
    return workflow[True]["workflow_call"]["inputs"]


def _steps(*, workflow: dict[Any, Any]) -> list[dict[str, Any]]:
    return workflow["jobs"]["check"]["steps"]


def _step(*, workflow: dict[Any, Any], name: str) -> dict[str, Any]:
    return next((s for s in _steps(workflow=workflow) if s.get("name") == name), {})


# --- A minimal evaluator for the GitHub expression subset the workflow uses ----

_TOKEN = re.compile(r"\s*(==|!=|&&|\|\||!|\(|\)|,|'(?:[^']|'')*'|[A-Za-z_][\w.\-]*)")


def _tokens(*, text: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    text = text.strip()
    while position < len(text):
        match = _TOKEN.match(text, position)
        assert match is not None, f"unsupported expression text at {text[position:]!r}"
        tokens.append(match.group(1))
        position = match.end()
    return tokens


def _truthy(*, value: object) -> bool:
    return value not in (None, "", False, 0)


def _contains(*, haystack: object, needle: object) -> bool:
    if isinstance(haystack, list):
        return any(str(item).lower() == str(needle).lower() for item in haystack)
    return str(needle).lower() in str(haystack).lower()


class _Parser:
    """Recursive descent over `||`, `&&`, `==`/`!=`, `!`, calls and literals."""

    def __init__(self, *, text: str, context: dict[str, object], status: bool) -> None:
        self.tokens = _tokens(text=text)
        self.context = context
        self.status = status
        self.position = 0
        self.functions: dict[str, Callable[[list[object]], object]] = {
            "success": lambda _args: self.status,
            "always": lambda _args: True,
            "cancelled": lambda _args: False,
            "failure": lambda _args: not self.status,
            "contains": lambda args: _contains(haystack=args[0], needle=args[1]),
            "fromJSON": lambda args: json.loads(str(args[0])),
            "startsWith": lambda args: str(args[0]).lower().startswith(str(args[1]).lower()),
        }

    def peek(self) -> str | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self) -> str:
        token = self.tokens[self.position]
        self.position += 1
        return token

    def parse(self) -> object:
        value = self.disjunction()
        assert self.peek() is None, f"trailing tokens {self.tokens[self.position :]}"
        return value

    def disjunction(self) -> object:
        value = self.conjunction()
        while self.peek() == "||":
            _ = self.take()
            right = self.conjunction()
            value = value if _truthy(value=value) else right
        return value

    def conjunction(self) -> object:
        value = self.comparison()
        while self.peek() == "&&":
            _ = self.take()
            right = self.comparison()
            value = right if _truthy(value=value) else value
        return value

    def comparison(self) -> object:
        value = self.unary()
        while self.peek() in ("==", "!="):
            operator = self.take()
            equal = str(value).lower() == str(self.unary()).lower()
            value = equal if operator == "==" else not equal
        return value

    def unary(self) -> object:
        if self.peek() == "!":
            _ = self.take()
            return not _truthy(value=self.unary())
        return self.primary()

    def primary(self) -> object:
        token = self.take()
        if token == "(":
            value = self.disjunction()
            assert self.take() == ")"
            return value
        if token.startswith("'"):
            return token[1:-1].replace("''", "'")
        if self.peek() == "(":
            _ = self.take()
            args: list[object] = []
            while self.peek() != ")":
                args.append(self.disjunction())
                if self.peek() == ",":
                    _ = self.take()
            _ = self.take()
            return self.functions[token](args)
        return self.context.get(token, "")


_STATUS_FUNCTIONS = re.compile(r"\b(success|always|cancelled|failure)\(")


def _evaluate(*, expression: str, context: dict[str, object], status: bool) -> object:
    text = expression.strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2]
    if not _STATUS_FUNCTIONS.search(text):
        text = f"success() && ({text})"
    return _Parser(text=text, context=context, status=status).parse()


def _render(*, value: str, context: dict[str, object]) -> str:
    return re.sub(
        r"\$\{\{(.*?)\}\}",
        lambda m: str(
            _evaluate(expression="always() && " + m.group(1), context=context, status=True)
        ),
        value,
    )


def _simulate(
    *,
    workflow: dict[Any, Any],
    event: str,
    raw: str,
    check: str,
    result: str = "success",
    authority: IncidentAuthority = _AUTHORIZED,
) -> tuple[bool, list[str]]:
    """One leg, step by step: (the leg succeeded, the steps that executed)."""
    context: dict[str, object] = {
        "github.event_name": event,
        "inputs.incident-omitted": raw,
        "inputs.incident-ci-result": result,
        "matrix.check": check,
    }
    status, executed = True, []
    for step in _steps(workflow=workflow):
        condition = str(step.get("if", "success()"))
        try:
            runs = _truthy(value=_evaluate(expression=condition, context=context, status=status))
        except ValueError:
            # GitHub fails the job when an `if:` cannot be evaluated (a fromJSON error).
            status = False
            continue
        if not runs:
            continue
        executed.append(step["name"])
        if _INVOCATION in str(step.get("run", "")):
            env = {k: _render(value=str(v), context=context) for k, v in step["env"].items()}
            decision = decide(
                event_name=event,
                raw=env["INCIDENT_OMITTED"],
                check=env["MATRIX_CHECK"],
                authority=replace(authority, incident_ci_result=env.get("INCIDENT_CI_RESULT", "")),
            )
            if decision.code == 0:
                context[f"steps.{step['id']}.outputs.omit"] = "true" if decision.omit else "false"
            elif not step.get("continue-on-error", False):
                status = False
    return status, executed


# --- The rules --------------------------------------------------------------


def _input_findings(*, workflow: dict[Any, Any]) -> list[str]:
    expected = {"incident-omitted": "[]", "incident-ci-result": ""}
    findings: list[str] = []
    for name, default in expected.items():
        declared = dict(_inputs(workflow=workflow).get(name, {}))
        _ = declared.pop("description", None)
        if declared != {"required": False, "type": "string", "default": default}:
            findings.append(f"input {name} is not an optional string defaulting to {default!r}")
    return findings


def _reader_findings(*, workflow: dict[Any, Any]) -> list[str]:
    readers = [
        (step.get("name"), key)
        for step in _steps(workflow=workflow)
        for key, value in {**step.get("env", {}), **step}.items()
        if key != "env" and "inputs.incident-omitted" in json.dumps(value)
    ]
    allowed = [(_RELEASE, "if"), (_RELEASED_CHECKOUT, "if"), (_DECISION, "INCIDENT_OMITTED")]
    allowed.insert(2, (_DECISION, "if"))
    findings: list[str] = []
    if sorted(readers, key=str) != sorted(allowed, key=str):
        findings.append(f"the incident-omitted input is read outside the decision: {readers}")
    job = {k: v for k, v in workflow["jobs"]["check"].items() if k != "steps"}
    if any(f"inputs.{name}" in json.dumps(job) for name in _INPUTS):
        findings.append("the job definition itself reads an incident input")
    return findings


def _pinned_findings(*, workflow: dict[Any, Any]) -> list[str]:
    names = [s.get("name") for s in _steps(workflow=workflow)]
    if any(n not in names for n in _ORDER):
        return [f"the leg lacks a pinned step: {names}"]
    findings = [
        f"step <{name}> is not its pinned form: {_step(workflow=workflow, name=name)}"
        for name, pinned in _PINNED.items()
        if _step(workflow=workflow, name=name) != pinned
    ]
    order = [names.index(n) for n in _ORDER]
    if order != sorted(order):
        findings.append(f"the leg's steps are out of order: {names}")
    if workflow["jobs"]["check"].get("name") != "${{ matrix.check }}":
        findings.append("the check job is not named by its matrix slug")
    return findings


def _guard_findings(*, workflow: dict[Any, Any]) -> list[str]:
    job = workflow["jobs"]["check"]
    findings: list[str] = []
    if "if" in job:
        findings.append("the check job carries a job-level if:")
    for step in _steps(workflow=workflow):
        if step.get("if") != _GUARDS.get(step.get("name")):
            findings.append(f"step <{step.get('name')}> has guard <{step.get('if')}>")
    if any("continue-on-error" in s for s in _steps(workflow=workflow)):
        findings.append("a step continues on error")
    return findings


_EVERY_CHECK = [_ACTIONS_CHECKOUT, _SETUP, _RUN]
_INCIDENT_STEPS = {_RELEASE, _RELEASED_CHECKOUT, _DECISION, _REPORT}


def _push_findings(*, workflow: dict[Any, Any], check: str) -> list[str]:
    """A non-pull_request event runs the check whatever the input says."""
    findings: list[str] = []
    for event in ("push", "pull_request_target", "merge_group", "workflow_dispatch"):
        for raw in (_ALL_SIX, _EVERY_LEG, '"check-coverage-incremental"', "{"):
            ok, steps = _simulate(workflow=workflow, event=event, raw=raw, check=check)
            if not ok or _INCIDENT_STEPS & set(steps) or not set(_EVERY_CHECK) <= set(steps):
                findings.append(f"a {event} with {raw} does not run {check}")
    return findings


def _runs(*, workflow: dict[Any, Any], raw: str, check: str, **scenario: Any) -> bool:
    ok, steps = _simulate(workflow=workflow, event="pull_request", raw=raw, check=check, **scenario)
    return ok and _REPORT not in steps and _RUN in steps


def _pull_request_findings(*, workflow: dict[Any, Any], check: str) -> list[str]:
    """On a pull request only an authorized, allowlisted, listed leg is omitted."""
    _, steps = _simulate(workflow=workflow, event="pull_request", raw="[]", check=check)
    findings = [] if _runs(workflow=workflow, raw="[]", check=check) else [f"[] skips {check}"]
    if _INCIDENT_STEPS & set(steps):
        findings.append(f"a non-incident pull request runs incident steps for {check}")
    ok, steps = _simulate(workflow=workflow, event="pull_request", raw=_ALL_SIX, check=check)
    omitted = ok and _REPORT in steps and _SETUP not in steps and _RUN not in steps
    if omitted != (check in _ALLOWLISTED_LEGS):
        findings.append(f"an incident pull request omits {check}: {omitted}")
    unauthorized = [{"result": "failure"}] + [{"authority": a} for a in _UNAUTHORIZED]
    for raw, scenario in [(_NOT_ALLOWLISTED, {}), ("", {})] + [(_ALL_SIX, u) for u in unauthorized]:
        if not _runs(workflow=workflow, raw=raw, check=check, **scenario):
            findings.append(f"an unauthorized or non-allowlisted request skips {check}")
    for raw in ('"check-coverage-incremental"', '"check-heading-coverage"', "{"):
        ok, steps = _simulate(workflow=workflow, event="pull_request", raw=raw, check=check)
        if ok or _REPORT in steps or _RUN in steps:
            findings.append(f"a malformed input {raw} does not fail {check} before any report")
    return findings


def _behaviour_findings(*, workflow: dict[Any, Any]) -> list[str]:
    return [
        finding
        for check in _LEGS
        for finding in (
            *_push_findings(workflow=workflow, check=check),
            *_pull_request_findings(workflow=workflow, check=check),
        )
    ]


def _findings(*, workflow: dict[Any, Any]) -> list[str]:
    return [
        *_input_findings(workflow=workflow),
        *_reader_findings(workflow=workflow),
        *_pinned_findings(workflow=workflow),
        *_guard_findings(workflow=workflow),
        *_behaviour_findings(workflow=workflow),
    ]


def test_the_committed_workflow_satisfies_every_rule():
    assert _findings(workflow=_load()) == []


# --- Negative controls: each mutation breaks exactly one guard -----------------

# The saved pre-review shape: guards read the raw input with contains().
_RAW_OMIT = "contains(fromJSON(inputs.incident-omitted || '[]'), matrix.check)"
_HEAD = "${{ github.event.pull_request.head.sha }}"


def _set(*, workflow: dict[Any, Any], name: str, key: str, value: object) -> None:
    _step(workflow=workflow, name=name)[key] = value


def _raw_contains(workflow: dict[Any, Any]) -> None:
    """The saved pre-review shape: no decision step, the guards read the raw input."""
    _steps(workflow=workflow).remove(_step(workflow=workflow, name=_DECISION))
    _set(
        workflow=workflow,
        name=_REPORT,
        key="if",
        value="${{ github.event_name == 'pull_request' && " + _RAW_OMIT + " }}",
    )
    for name in (_SETUP, _RUN):
        guard = "${{ !(github.event_name == 'pull_request' && " + _RAW_OMIT + ") }}"
        _set(workflow=workflow, name=name, key="if", value=guard)


def _no_push_guard(workflow: dict[Any, Any]) -> None:
    """The raw shape without the pull_request test: a master push can omit."""
    _raw_contains(workflow)
    _set(workflow=workflow, name=_REPORT, key="if", value="${{ " + _RAW_OMIT + " }}")
    for name in (_SETUP, _RUN):
        _set(workflow=workflow, name=name, key="if", value="${{ !(" + _RAW_OMIT + ") }}")


def _gate_widened(workflow: dict[Any, Any]) -> None:
    widened = "${{ startsWith(github.event_name, 'pull_request') }}"
    for name in (_RELEASE, _RELEASED_CHECKOUT, _DECISION):
        _set(workflow=workflow, name=name, key="if", value=widened)


def _decision_continues_on_error(workflow: dict[Any, Any]) -> None:
    _set(workflow=workflow, name=_DECISION, key="continue-on-error", value=True)


def _report_without_event_test(workflow: dict[Any, Any]) -> None:
    guard = "${{ steps.incident.outputs.omit == 'true' }}"
    _set(workflow=workflow, name=_REPORT, key="if", value=guard)


def _run_check_unguarded(workflow: dict[Any, Any]) -> None:
    del _step(workflow=workflow, name=_RUN)["if"]


def _decision_after_run_check(workflow: dict[Any, Any]) -> None:
    steps = _steps(workflow=workflow)
    decision = _step(workflow=workflow, name=_DECISION)
    steps.remove(decision)
    steps.append(decision)


def _decision_from_the_actions_checkout(workflow: dict[Any, Any]) -> None:
    _set(
        workflow=workflow,
        name=_DECISION,
        key="working-directory",
        value=".livespec-dev-tooling-actions",
    )


def _released_checkout_at_the_pr_head(workflow: dict[Any, Any]) -> None:
    _step(workflow=workflow, name=_RELEASED_CHECKOUT)["with"]["ref"] = _HEAD


def _released_checkout_of_the_consumer(workflow: dict[Any, Any]) -> None:
    released = _step(workflow=workflow, name=_RELEASED_CHECKOUT)
    released["with"]["repository"] = "${{ github.repository }}"


def _actions_checkout_at_the_pr_head(workflow: dict[Any, Any]) -> None:
    _step(workflow=workflow, name=_ACTIONS_CHECKOUT)["with"]["ref"] = _HEAD


def _actions_checkout_of_the_consumer(workflow: dict[Any, Any]) -> None:
    actions = _step(workflow=workflow, name=_ACTIONS_CHECKOUT)
    actions["with"]["repository"] = "${{ github.repository }}"


def _release_from_master(workflow: dict[Any, Any]) -> None:
    _set(
        workflow=workflow, name=_RELEASE, key="run", value='echo "tag=master" >> "$GITHUB_OUTPUT"\n'
    )


def _job_renamed(workflow: dict[Any, Any]) -> None:
    workflow["jobs"]["check"]["name"] = "check"


def _summary_dropped(workflow: dict[Any, Any]) -> None:
    run = _REPORT_RUN.replace(' | tee -a "$GITHUB_STEP_SUMMARY"', "")
    _set(workflow=workflow, name=_REPORT, key="run", value=run)


def _result_not_passed(workflow: dict[Any, Any]) -> None:
    del _step(workflow=workflow, name=_DECISION)["env"]["INCIDENT_CI_RESULT"]


def _required_input(workflow: dict[Any, Any]) -> None:
    _inputs(workflow=workflow)["incident-ci-result"]["required"] = True


def _job_level_if(workflow: dict[Any, Any]) -> None:
    workflow["jobs"]["check"]["if"] = "${{ inputs.incident-omitted == '[]' }}"


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_raw_contains, "an unauthorized or non-allowlisted request skips lint"),
        (
            _raw_contains,
            'a malformed input "check-coverage-incremental" does not fail coverage before',
        ),
        (_raw_contains, "the incident-omitted input is read outside the decision"),
        (_raw_contains, "the leg lacks a pinned step"),
        (_no_push_guard, "a push with " + _EVERY_LEG + " does not run heading_coverage"),
        (_gate_widened, "step <" + _RELEASE + "> has guard"),
        (_gate_widened, "a pull_request_target with " + _ALL_SIX + " does not run lint"),
        (
            _decision_continues_on_error,
            'a malformed input "check-heading-coverage" does not fail lint before any report',
        ),
        (_decision_continues_on_error, "a step continues on error"),
        (_report_without_event_test, "step <" + _REPORT + "> has guard"),
        (_run_check_unguarded, "an incident pull request omits heading_coverage: False"),
        (_run_check_unguarded, "step <Run check> has guard <None>"),
        (_decision_after_run_check, "the leg's steps are out of order"),
        (_decision_from_the_actions_checkout, "step <" + _DECISION + "> is not its pinned form"),
        (_released_checkout_at_the_pr_head, "step <" + _RELEASED_CHECKOUT + "> is not its pinned"),
        (_released_checkout_of_the_consumer, "step <" + _RELEASED_CHECKOUT + "> is not its"),
        (_actions_checkout_at_the_pr_head, "step <" + _ACTIONS_CHECKOUT + "> is not its pinned"),
        (_actions_checkout_of_the_consumer, "step <" + _ACTIONS_CHECKOUT + "> is not its pinned"),
        (_release_from_master, "step <" + _RELEASE + "> is not its pinned form"),
        (_job_renamed, "the check job is not named by its matrix slug"),
        (_summary_dropped, "step <" + _REPORT + "> is not its pinned form"),
        (_result_not_passed, "step <" + _DECISION + "> is not its pinned form"),
        (_required_input, "input incident-ci-result is not an optional string defaulting to ''"),
        (_job_level_if, "the check job carries a job-level if:"),
        (_job_level_if, "the job definition itself reads an incident input"),
    ],
)
def test_each_mutation_is_caught_by_name(mutate, expected):
    workflow = copy.deepcopy(_load())
    mutate(workflow)
    findings = _findings(workflow=workflow)
    assert any(f.startswith(expected) for f in findings), findings
