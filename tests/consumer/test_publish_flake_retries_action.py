"""Static contract test for the `publish-flake-retries` composite Action.

Per `SPECIFICATION/constraints.md` §"Testing approach" ("Flake-retry record
delivery", v156) and `SPECIFICATION/scenarios.md` "a re-run test's record
reaches the host-side reader as a CI artifact" / "a CI job that re-ran no
test publishes no flake-retry artifact", each consumer's coverage job
publishes `tmp/flake-retries/` through this repository's shared
`.github/actions/publish-flake-retries` composite Action at a released tag,
so the artifact contract lives in one place.

The Action owns the artifact name (`flake-retries`, or
`flake-retries-<suffix>` for a job that runs more than once in one CI run),
the path, `if-no-files-found: ignore` (a job that re-ran no test uploads
nothing and does not fail) and the 7-day retention. The caller's step
carries the not-cancelled condition, because a composite step cannot read
the caller's `needs` context or override the caller's own status check.

Like the bump-pin-rewrite Action's test, these assertions are text-based
pattern matches against the YAML source, because PyYAML is intentionally
absent from the project's dependencies.

Owning work item: livespec-dev-tooling-ljea46.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACTION_PATH = _REPO_ROOT / ".github" / "actions" / "publish-flake-retries" / "action.yml"


def _action_text() -> str:
    assert _ACTION_PATH.is_file(), f"composite Action missing at {_ACTION_PATH}"
    return _ACTION_PATH.read_text(encoding="utf-8")


def _upload_step(text: str) -> str:
    match = re.search(r"uses: actions/upload-artifact@v4\n(?P<body>(?:\s{8,}.*\n?)+)", text)
    assert match is not None, "the Action must run exactly one actions/upload-artifact@v4 step"
    return match.group("body")


def test_the_action_is_a_composite_named_publish_flake_retries() -> None:
    text = _action_text()
    assert re.search(r"^name: publish-flake-retries$", text, re.MULTILINE)
    assert re.search(r"^runs:\n\s+using: composite$", text, re.MULTILINE)
    assert text.count("uses: actions/upload-artifact@v4") == 1


def test_the_suffix_input_is_optional_and_defaults_to_empty() -> None:
    text = _action_text()
    match = re.search(
        r"^  suffix:\n(?P<body>(?:    .*\n)+)",
        text,
        re.MULTILINE,
    )
    assert match is not None, "the Action must declare a `suffix` input"
    body = match.group("body")
    assert "required: false" in body
    assert 'default: ""' in body


def test_the_artifact_is_named_flake_retries_or_flake_retries_dash_suffix() -> None:
    body = _upload_step(_action_text())
    assert (
        "name: ${{ inputs.suffix == '' && 'flake-retries' "
        "|| format('flake-retries-{0}', inputs.suffix) }}"
    ) in body


def test_the_upload_publishes_the_records_directory_with_seven_day_retention() -> None:
    body = _upload_step(_action_text())
    assert "path: tmp/flake-retries/" in body
    assert "retention-days: 7" in body


def test_a_job_that_re_ran_no_test_uploads_nothing_and_does_not_fail() -> None:
    body = _upload_step(_action_text())
    assert "if-no-files-found: ignore" in body
