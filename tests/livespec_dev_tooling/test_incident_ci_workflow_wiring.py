"""The incident CI entrance is wired into ci.yml ADDITIVELY — asserted by test.

Work-item livespec-dev-tooling-yf7gq2 (plan expedited-incident-response-flag,
step D): `.github/workflows/ci.yml` carries an `incident-ci` job that runs the
RELEASED incident CI entrance, and `ci-green` requires it IN ADDITION to every
job it already required — never instead of one. The rules live in
`wiring_findings`, a pure function over the workflow TEXT parsed through the
repository's shared workflow parser (`checks/_ci_matrix_parse.parse_ci_jobs`,
the one `check-ci-matrix-completeness` and `check-ci-gate-parity` read), so
this test and those gates cannot disagree about what a job, a `needs:` entry
or a forbidden `if:` is.

Each rule is exercised twice, as the sibling wiring tests do: against the
committed workflow (expecting silence) and against a MUTATED copy that breaks
exactly that rule (expecting the finding). Without the negative control a
"substring is present" assertion would pass against wiring that is subtly
wrong — a job that exists but is not required, a required job that was
silently dropped, or an `if:` that makes the job skip on one event.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from livespec_dev_tooling.checks._ci_matrix_parse import parse_ci_jobs

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

_INCIDENT_JOB = "incident-ci"
_GATE_JOB = "ci-green"

# The gate's `needs:` exactly as it stood BEFORE the incident job was added:
# the additive baseline. Every member must still exist and still be required.
_BASELINE_REQUIRED = frozenset(
    {
        "check-python",
        "check-per-file-coverage",
        "check-coverage",
        "check-python-batch",
        "check-fleet-conformance",
        "check-metadata",
        "check-metadata-batch",
    }
)


def wiring_findings(*, source: str) -> list[str]:
    """Every way the workflow text fails the additive incident-CI wiring."""
    jobs = {job.name: job for job in parse_ci_jobs(source=source)}
    gate = jobs.get(_GATE_JOB)
    if gate is None:
        return [f"gate job {_GATE_JOB} is absent"]
    findings: list[str] = []
    incident = jobs.get(_INCIDENT_JOB)
    if incident is None:
        findings.append(f"job {_INCIDENT_JOB} is absent")
    else:
        if incident.contributed_check_slugs:
            findings.append(f"job {_INCIDENT_JOB} names a canonical check slug literally")
        if incident.changeset_py_conditioned or incident.event_conditioned:
            findings.append(f"job {_INCIDENT_JOB} conditions its steps on the event or changeset")
    if _INCIDENT_JOB not in gate.needs:
        findings.append(f"job {_INCIDENT_JOB} is not required by {_GATE_JOB}")
    for name in sorted(_BASELINE_REQUIRED):
        if name not in jobs:
            findings.append(f"previously required job {name} is absent")
        if name not in gate.needs:
            findings.append(f"previously required job {name} is no longer required by {_GATE_JOB}")
    return findings


def _mutated(*, source: str, old: str, new: str) -> str:
    """Replace exactly one occurrence, so a mutation never lands twice or nowhere."""
    assert source.count(old) == 1, old
    return source.replace(old, new)


def test_committed_ci_yml_wires_the_incident_job_additively() -> None:
    assert wiring_findings(source=_CI_YML.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            f"\n  {_GATE_JOB}:\n",
            f"\n  {_GATE_JOB}-renamed:\n",
            f"gate job {_GATE_JOB} is absent",
        ),
        (
            f"\n  {_INCIDENT_JOB}:\n",
            f"\n  {_INCIDENT_JOB}-renamed:\n",
            f"job {_INCIDENT_JOB} is absent",
        ),
        (
            "      - name: Select incident work from an authenticated PR read\n",
            "      - run: just check-lint\n"
            "      - name: Select incident work from an authenticated PR read\n",
            f"job {_INCIDENT_JOB} names a canonical check slug literally",
        ),
        (
            "        if: steps.select.outputs.block == 'present'\n",
            "        if: steps.select.outputs.block == 'present' && github.event_name == 'push'\n",
            f"job {_INCIDENT_JOB} conditions its steps on the event or changeset",
        ),
        (
            f", {_INCIDENT_JOB}]\n    if: always()",
            "]\n    if: always()",
            f"job {_INCIDENT_JOB} is not required by {_GATE_JOB}",
        ),
        (
            "\n  check-metadata-batch:\n",
            "\n  check-metadata-batch-renamed:\n",
            "previously required job check-metadata-batch is absent",
        ),
        (
            f"check-metadata-batch, {_INCIDENT_JOB}]\n    if: always()",
            f"{_INCIDENT_JOB}]\n    if: always()",
            f"previously required job check-metadata-batch is no longer required by {_GATE_JOB}",
        ),
    ],
)
def test_each_rule_has_a_negative_control(*, old: str, new: str, expected: str) -> None:
    source = _mutated(source=_CI_YML.read_text(encoding="utf-8"), old=old, new=new)
    assert expected in wiring_findings(source=source)


# The select step's prefilter, read out of the workflow text: ONE anchored
# `grep -qE '<pattern>'` whose pattern opens with `^<!-- livespec-incident-ci`.
# The first run of livespec-dev-tooling#3524 took the incident path because a
# bare substring test matched the PR DESCRIPTION, which quotes the marker in
# prose. The shell is not executed here; the pattern is lifted from the file
# and evaluated with its POSIX class rendered for `re`, so the test pins the
# committed pattern rather than a copy of it.
_PREFILTER = re.compile(r"grep -qE '(?P<pattern>\^<!-- livespec-incident-ci[^']*)'")

_BODY_MENTIONING_THE_MARKER = (
    "With no `<!-- livespec-incident-ci` body block, or on a push, it records\n"
    '"selected nothing" and exits 0. The marker is <!-- livespec-incident-ci inline.\n'
)
_BODY_WITH_A_BLOCK = (
    "Repair for incident x.\n\n<!-- livespec-incident-ci\n"
    '{"schema":1,"arm":{},"observer_arm_id":"0"}\n-->\n'
)


def _prefilter_pattern(*, source: str) -> re.Pattern[str]:
    found = _PREFILTER.findall(source)
    assert len(found) == 1, found
    return re.compile(found[0].replace("[[:space:]]", r"\s"), re.MULTILINE)


def test_prefilter_is_anchored_to_the_block_line_not_a_substring() -> None:
    source = _CI_YML.read_text(encoding="utf-8")
    assert "*'<!-- livespec-incident-ci'*" not in source
    pattern = _prefilter_pattern(source=source)
    assert pattern.search(_BODY_MENTIONING_THE_MARKER) is None
    assert pattern.search(_BODY_WITH_A_BLOCK) is not None
    assert pattern.search(_BODY_WITH_A_BLOCK.replace("\n", "\r\n")) is not None
