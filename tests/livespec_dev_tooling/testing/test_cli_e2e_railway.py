"""The harness entry point is railway-typed — `u4ij` conversion 3 of 3.

Lives in its own file rather than beside the other `cli_e2e` tests, and the
reason is a Red-leg constraint worth stating: this repo enforces 100% per-file
coverage, and at the RED moment every line AFTER the first failing assertion is
unexecuted and therefore UNCOVERED. `test_cli_e2e.py`'s happy-path test makes
eight assertions on the returned result, so converting it in the Red leg would
have left its whole body uncovered. Here each Red assertion is the LAST
statement of its test, `test_cli_e2e.py` is untouched and still passes, and its
two call sites move in the Green leg where they pass again.
"""

from __future__ import annotations

import sys
from pathlib import Path

from test_cli_e2e import _FakeCliRunner, _make_fixture, _make_plugin, _two_skill_config

from livespec_dev_tooling.testing import cli_e2e

_VENDOR_DIR = Path(cli_e2e.__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = []


def test_round_trip_success_unwraps_to_the_workflow_result(*, tmp_path: Path) -> None:
    """A passing round trip yields a `Success` CARRYING the `WorkflowResult`.

    The `unwrap()` half is the load-bearing half. A conversion bug that hands the
    CONTAINER to the caller satisfies every assertion that only checks the call
    succeeded — dev-tooling shipped exactly that in `frozenset(IOResult.unwrap())`,
    which silently produced a set holding the wrapper. Reading `.discovered_skills`
    off the unwrapped value is what makes this test able to fail on that bug.
    """
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={"seed": True})
    fixtures_root = tmp_path / "fixtures"
    _make_fixture(root=fixtures_root, skill="seed", prompt="/seed", expected=("out.md",))
    runner = _FakeCliRunner(creates={"/seed": ("out.md",)})

    outcome = cli_e2e.test_workflow_full_round_trip(
        config=_two_skill_config(plugin=plugin, fixtures_root=fixtures_root),
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
        injected_runner=runner,
    )

    assert isinstance(outcome, Success) and outcome.unwrap().discovered_skills == (
        "seed",
    ), f"a passing round trip must yield a Success carrying the WorkflowResult; got {outcome!r}"


def test_round_trip_failure_is_a_value_not_a_raise(*, tmp_path: Path) -> None:
    """A failing step lands on the FAILURE track instead of raising.

    *** THIS CONVERSION WAS ONLY SAFE BECAUSE FOUR SIBLING WIRINGS LANDED FIRST.
    *** `bool(Failure(...))` is TRUE and a `Failure` carries no `.passed`, so
    every pre-existing consumer wrapper would have kept running WITHOUT raising
    — it would simply have STOPPED CHECKING, and four sibling suites would have
    reported success on a broken round trip. That measurement is what made
    doctrine step 3 load-bearing here rather than ceremonial.

    The call sits INSIDE the assert so the statement still executes at the Red
    moment, where the pre-conversion code raises `WorkflowFailedError` instead of
    returning. Without that the assertion line would be unexecuted and the Red
    leg would fail the 100% per-file coverage gate.
    """
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={"seed": True})
    fixtures_root = tmp_path / "fixtures"
    _make_fixture(root=fixtures_root, skill="seed", prompt="/seed", expected=("never.md",))
    runner = _FakeCliRunner(creates={})  # never.md is never created → the step fails

    assert isinstance(
        cli_e2e.test_workflow_full_round_trip(
            config=_two_skill_config(plugin=plugin, fixtures_root=fixtures_root),
            home=tmp_path / "home",
            project_root=tmp_path / "proj",
            injected_runner=runner,
        ),
        Failure,
    ), "a failing step must be carried as a value on the failure track, not raised"
