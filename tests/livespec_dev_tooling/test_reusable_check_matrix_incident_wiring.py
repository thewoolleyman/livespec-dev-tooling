"""reusable-check-matrix omits only allowlisted legs, only on a pull request.

Work-item livespec-dev-tooling-hlxbsv (plan expedited-incident-response-flag,
epic livespec-dev-tooling-bqnzcm), carrying finding 4 of the independent review
of livespec-dev-tooling#3911. The live behaviour is a GitHub Actions run, so this
file holds the workflow's SHAPE, plus a step-by-step simulation of one leg that
evaluates the committed `if:` expressions and runs the real
`incident_matrix_omission` decision:

- **One reader.** The `incident-omitted` input is optional, defaults to `'[]'`,
  and is read by exactly one step: the leg's decision step, which runs
  `python3 -m livespec_dev_tooling.incident_matrix_omission` from the Actions
  checkout. No `contains()` ever sees the raw input, so a JSON string can never
  become a substring test, and no expression can omit a member the module's
  allowlist refuses.
- **The master-push guard.** The decision step runs on a pull_request event
  only, and the report, setup and run-check guards repeat that test.
- **Reported, never skipped silently.** One `omitted-by-incident-policy` step
  carries the omit guard; setup and run-check carry its exact negation.

The simulation then proves the outcomes the item's Definition of Done names: a
master push runs every check whatever the input; a non-incident PR omits
nothing; a listed `check-lint` runs; a malformed input fails every leg before
any reports an omission.

Each rule is exercised twice, as the sibling `test_incident_ci_omission_wiring`
does: against the committed workflow (expecting silence) and against a copy
mutated to break exactly that rule (expecting the finding).
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from livespec_dev_tooling.incident_matrix_omission import decide

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "reusable-check-matrix.yml"

_INPUT = "incident-omitted"
_DECISION = "Decide incident omission for this leg"
_REPORT = "omitted-by-incident-policy (per the caller's incident CI aggregate)"
_SETUP = "Setup toolchain"
_RUN = "Run check"
_ACTIONS_CHECKOUT = "Checkout livespec-dev-tooling Actions"
_INVOCATION = "python3 -m livespec_dev_tooling.incident_matrix_omission"

_PR_GUARD = "${{ github.event_name == 'pull_request' }}"
_OMIT = "github.event_name == 'pull_request' && steps.incident.outputs.omit == 'true'"
_REPORT_IF = "${{ " + _OMIT + " }}"
_RUN_IF = "${{ !(" + _OMIT + ") }}"
_DECISION_ENV = {
    "INCIDENT_OMITTED": "${{ inputs.incident-omitted }}",
    "MATRIX_CHECK": "${{ matrix.check }}",
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
_ALLOWLISTED_LEGS = ("heading_coverage", "per_file_coverage", "no_todo_registry", "check-coverage")
_OTHER_LEGS = ("lint", "types", "check-coverage-incremental")
_LEGS = _ALLOWLISTED_LEGS + _OTHER_LEGS
# Every leg slug as a list: a guard that reads the raw input would omit them all.
_EVERY_LEG = json.dumps(list(_LEGS))
_NOT_ALLOWLISTED = '["check-lint", "check-types", "lint", "types"]'


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
    *, workflow: dict[Any, Any], event: str, raw: str, check: str
) -> tuple[bool, list[str]]:
    """One leg, step by step: (the leg succeeded, the steps that executed)."""
    context: dict[str, object] = {
        "github.event_name": event,
        "inputs.incident-omitted": raw,
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
        if step.get("run") == _INVOCATION:
            env = {k: _render(value=str(v), context=context) for k, v in step["env"].items()}
            decision = decide(
                event_name=event, raw=env["INCIDENT_OMITTED"], check=env["MATRIX_CHECK"]
            )
            if decision.code == 0:
                context[f"steps.{step['id']}.outputs.omit"] = "true" if decision.omit else "false"
            elif not step.get("continue-on-error", False):
                status = False
    return status, executed


# --- The rules --------------------------------------------------------------


def _input_findings(*, workflow: dict[Any, Any]) -> list[str]:
    declared = dict(_inputs(workflow=workflow).get(_INPUT, {}))
    _ = declared.pop("description", None)
    if declared != {"required": False, "type": "string", "default": "[]"}:
        return [f"input {_INPUT} is not an optional string defaulting to '[]': {declared}"]
    return []


def _reader_findings(*, workflow: dict[Any, Any]) -> list[str]:
    readers = [
        (step.get("name"), key)
        for step in _steps(workflow=workflow)
        for key, value in {**step.get("env", {}), **step}.items()
        if key != "env" and "inputs.incident-omitted" in json.dumps(value)
    ]
    findings: list[str] = []
    if readers != [(_DECISION, "INCIDENT_OMITTED")]:
        findings.append(f"the {_INPUT} input is read outside the decision step's env: {readers}")
    if "inputs.incident-omitted" in json.dumps(
        {k: v for k, v in workflow["jobs"]["check"].items() if k != "steps"}
    ):
        findings.append(f"the job definition itself reads the {_INPUT} input")
    return findings


def _decision_findings(*, workflow: dict[Any, Any]) -> list[str]:
    names = [s.get("name") for s in _steps(workflow=workflow)]
    if any(n not in names for n in (_ACTIONS_CHECKOUT, _DECISION, _REPORT, _SETUP, _RUN)):
        return [f"the leg lacks a decision, report, setup or run step: {names}"]
    decision = _step(workflow=workflow, name=_DECISION)
    expected = {
        "name": _DECISION,
        "id": "incident",
        "if": _PR_GUARD,
        "shell": "bash",
        "working-directory": ".livespec-dev-tooling-actions",
        "env": _DECISION_ENV,
        "run": _INVOCATION,
    }
    findings: list[str] = []
    if decision != expected:
        findings.append(f"the decision step is not the guarded module invocation: {decision}")
    order = [names.index(n) for n in (_ACTIONS_CHECKOUT, _DECISION, _REPORT, _SETUP, _RUN)]
    if order != sorted(order):
        findings.append(f"the decision step does not precede the report, setup and run: {names}")
    return findings


def _guard_findings(*, workflow: dict[Any, Any]) -> list[str]:
    job = workflow["jobs"]["check"]
    findings: list[str] = []
    if "if" in job:
        findings.append("the check job carries a job-level if:")
    expected = {_DECISION: _PR_GUARD, _REPORT: _REPORT_IF, _SETUP: _RUN_IF, _RUN: _RUN_IF}
    for step in _steps(workflow=workflow):
        if step.get("if") != expected.get(step.get("name")):
            findings.append(f"step <{step.get('name')}> has guard <{step.get('if')}>")
    reports = [
        s for s in _steps(workflow=workflow) if "omitted-by-incident-policy" in s.get("run", "")
    ]
    if len(reports) != 1 or "${{" in reports[0]["run"]:
        findings.append("there is not exactly one report step free of ${{ }} in its run:")
    if any("continue-on-error" in s for s in _steps(workflow=workflow)):
        findings.append("a step continues on error")
    return findings


_EVERY_CHECK = [_ACTIONS_CHECKOUT, _SETUP, _RUN]


def _push_findings(*, workflow: dict[Any, Any], check: str) -> list[str]:
    """A non-pull_request event runs the check whatever the input says."""
    findings: list[str] = []
    for event in ("push", "merge_group", "workflow_dispatch"):
        for raw in (_ALL_SIX, _EVERY_LEG, '"check-coverage-incremental"', "{"):
            ok, steps = _simulate(workflow=workflow, event=event, raw=raw, check=check)
            if not ok or _REPORT in steps or not set(_EVERY_CHECK) <= set(steps):
                findings.append(f"a {event} with {raw} does not run {check}")
    return findings


def _runs(*, workflow: dict[Any, Any], raw: str, check: str) -> bool:
    ok, steps = _simulate(workflow=workflow, event="pull_request", raw=raw, check=check)
    return ok and _REPORT not in steps and _RUN in steps


def _pull_request_findings(*, workflow: dict[Any, Any], check: str) -> list[str]:
    """On a pull request only an allowlisted listed leg is omitted; bad input fails first."""
    findings = [
        f"a non-incident pull request ({raw!r}) does not run {check}"
        for raw in ("[]", "")
        if not _runs(workflow=workflow, raw=raw, check=check)
    ]
    ok, steps = _simulate(workflow=workflow, event="pull_request", raw=_ALL_SIX, check=check)
    omitted = ok and _REPORT in steps and _SETUP not in steps and _RUN not in steps
    if omitted != (check in _ALLOWLISTED_LEGS):
        findings.append(f"an incident pull request omits {check}: {omitted}")
    if not _runs(workflow=workflow, raw=_NOT_ALLOWLISTED, check=check):
        findings.append(f"a non-allowlisted list does not run {check}")
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
        *_decision_findings(workflow=workflow),
        *_guard_findings(workflow=workflow),
        *_behaviour_findings(workflow=workflow),
    ]


def test_the_committed_workflow_satisfies_every_rule():
    assert _findings(workflow=_load()) == []


# --- Negative controls: each mutation breaks exactly one guard -----------------

# The saved pre-review shape: guards read the raw input with contains().
_RAW_OMIT = "contains(fromJSON(inputs.incident-omitted || '[]'), matrix.check)"


def _set_guard(*, workflow: dict[Any, Any], name: str, guard: str) -> None:
    _step(workflow=workflow, name=name)["if"] = guard


def _raw_contains(workflow: dict[Any, Any]) -> None:
    """The saved pre-review shape: no decision step, the guards read the raw input."""
    _steps(workflow=workflow).remove(_step(workflow=workflow, name=_DECISION))
    _set_guard(
        workflow=workflow,
        name=_REPORT,
        guard="${{ github.event_name == 'pull_request' && " + _RAW_OMIT + " }}",
    )
    for name in (_SETUP, _RUN):
        _set_guard(
            workflow=workflow,
            name=name,
            guard="${{ !(github.event_name == 'pull_request' && " + _RAW_OMIT + ") }}",
        )


def _no_push_guard(workflow: dict[Any, Any]) -> None:
    """The raw shape without the pull_request test: a master push can omit."""
    _raw_contains(workflow)
    _set_guard(workflow=workflow, name=_REPORT, guard="${{ " + _RAW_OMIT + " }}")
    for name in (_SETUP, _RUN):
        _set_guard(workflow=workflow, name=name, guard="${{ !(" + _RAW_OMIT + ") }}")


def _decision_on_every_event(workflow: dict[Any, Any]) -> None:
    del _step(workflow=workflow, name=_DECISION)["if"]


def _decision_continues_on_error(workflow: dict[Any, Any]) -> None:
    _step(workflow=workflow, name=_DECISION)["continue-on-error"] = True


def _report_without_event_test(workflow: dict[Any, Any]) -> None:
    _set_guard(
        workflow=workflow, name=_REPORT, guard="${{ steps.incident.outputs.omit == 'true' }}"
    )


def _run_check_unguarded(workflow: dict[Any, Any]) -> None:
    del _step(workflow=workflow, name=_RUN)["if"]


def _decision_after_run_check(workflow: dict[Any, Any]) -> None:
    steps = _steps(workflow=workflow)
    decision = _step(workflow=workflow, name=_DECISION)
    steps.remove(decision)
    steps.append(decision)


def _decision_from_consumer_tree(workflow: dict[Any, Any]) -> None:
    del _step(workflow=workflow, name=_DECISION)["working-directory"]


def _required_input(workflow: dict[Any, Any]) -> None:
    _inputs(workflow=workflow)[_INPUT]["required"] = True


def _report_interpolates(workflow: dict[Any, Any]) -> None:
    step = _step(workflow=workflow, name=_REPORT)
    step["run"] = 'echo "omitted-by-incident-policy: ${{ matrix.check }}"'


def _job_level_if(workflow: dict[Any, Any]) -> None:
    workflow["jobs"]["check"]["if"] = "${{ inputs.incident-omitted == '[]' }}"


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_raw_contains, "a non-allowlisted list does not run lint"),
        (
            _raw_contains,
            'a malformed input "check-coverage-incremental" does not fail check-coverage before',
        ),
        (_raw_contains, "the leg lacks a decision, report, setup or run step"),
        (_raw_contains, "the incident-omitted input is read outside the decision step's env"),
        (_no_push_guard, "a push with " + _EVERY_LEG + " does not run heading_coverage"),
        (_decision_on_every_event, "the decision step is not the guarded module invocation"),
        (
            _decision_continues_on_error,
            'a malformed input "check-heading-coverage" does not fail lint before any report',
        ),
        (_decision_continues_on_error, "a step continues on error"),
        (
            _report_without_event_test,
            "step <omitted-by-incident-policy (per the caller's incident CI aggregate)> has guard",
        ),
        (_run_check_unguarded, "an incident pull request omits heading_coverage: False"),
        (_run_check_unguarded, "step <Run check> has guard <None>"),
        (_decision_after_run_check, "the decision step does not precede the report"),
        (_decision_from_consumer_tree, "the decision step is not the guarded module invocation"),
        (_required_input, "input incident-omitted is not an optional string defaulting to '[]'"),
        (_report_interpolates, "there is not exactly one report step free of ${{ }} in its run:"),
        (_job_level_if, "the check job carries a job-level if:"),
        (_job_level_if, "the job definition itself reads the incident-omitted input"),
    ],
)
def test_each_mutation_is_caught_by_name(mutate, expected):
    workflow = copy.deepcopy(_load())
    mutate(workflow)
    findings = _findings(workflow=workflow)
    assert any(f.startswith(expected) for f in findings), findings
