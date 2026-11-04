"""The committed CI-pool apply converges a changed stack exactly once.

The control plane's k3s datastore is volatile, while the cluster stack lives in
the installed converge tree.  Updating that tree without running the converge
means a merged scale-set or Kueue change waits for a reboot.  The play must
therefore run the unit when that tree changes, wait for the oneshot outcome,
and make a failed outcome diagnosable from the apply output.  Conversely, a
second apply with unchanged inputs must leave the unit alone so it reports no
change.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TASKS = _REPO_ROOT / "ansible" / "roles" / "ci_converge_unit" / "tasks" / "main.yml"


def _tasks_text() -> str:
    """Return the committed converge-unit role tasks."""
    return _TASKS.read_text(encoding="utf-8")


def test_changed_ci_stack_inputs_run_and_wait_for_the_converge() -> None:
    """A normal apply runs the unit after it refreshes the installed tree."""
    tasks = _tasks_text()
    assert "ci_converge_unit_inputs_changed" in tasks, (
        "the role must derive whether the installed converge inputs changed, so a committed "
        "ci-pool apply starts converge-ci-stack.service without an operator-only switch"
    )
    assert "ci_converge_unit_run_now" not in tasks, (
        "the live converge must not remain behind the retired per-apply run-now switch; a "
        "merged runner-pool change needs one ordinary committed apply to reach the cluster"
    )
    assert "state: started" in tasks, (
        "the changed-input path must start converge-ci-stack.service rather than merely "
        "enabling it for a future reboot"
    )
    assert (
        "Wait for the converge to exit" in tasks
    ), "the apply must wait for the oneshot converge rather than returning after it starts"


def test_failed_converge_names_its_result_and_journal_tail() -> None:
    """A failed unit leaves the apply with its result and useful diagnosis."""
    tasks = _tasks_text()
    assert "Read the failed converge journal tail" in tasks, (
        "the failure path must read the converge unit journal instead of directing the "
        "operator to perform a separate host inspection"
    )
    assert (
        "ci_converge_unit_journal_tail.stdout" in tasks
    ), "the assertion failure must include the journal tail captured from the failed unit"
    assert (
        "Result={{ ci_converge_unit_converge_result }}" in tasks
    ), "the assertion failure must name the systemd Result, not only systemctl's exit code"


def test_failed_prior_converge_is_retried_on_unchanged_inputs() -> None:
    """A tree installed by a failed converge is not reported as converged."""
    tasks = _tasks_text()
    read = tasks.index("- name: Read the converge unit's last result")
    decide = tasks.index("- name: Decide whether the installed CI stack inputs changed")
    run = tasks.index("- name: Run the CI stack converge after changed inputs")
    assert read < decide < run, (
        "the unit's last result must be read before the start gate is decided, and the "
        "gate must precede the start"
    )
    gate = tasks[decide:run]
    assert "ci_converge_unit_prior_state" in gate, (
        "the start gate must treat the unit's last result as an input, so inputs that "
        "were installed by a failed converge are retried instead of reported unchanged"
    )
    assert "!= 'success'" in gate, "a last result other than success must start the converge"


def test_unchanged_inputs_skip_the_live_converge() -> None:
    """The second apply stays unchanged instead of re-running a successful stack."""
    tasks = _tasks_text()
    start = tasks.index("- name: Run the CI stack converge after changed inputs")
    block = tasks[start:]
    assert "ci_converge_unit_inputs_changed | bool" in block, (
        "the live converge block must be gated by changed installed inputs, so a second "
        "apply reports no change when the host already carries the successful tree"
    )


def test_converge_still_running_at_the_wait_bound_fails_the_apply() -> None:
    """A unit still active at timeout must fail the play, not read as success."""
    tasks = _tasks_text()
    start = tasks.index("- name: Wait for the converge to exit")
    end = tasks.index("- name: Read the converge's result")
    wait = tasks[start:end]
    assert "failed_when" not in wait, (
        "the bounded wait must not suppress its exhausted-retry failure, or a converge "
        "still running at the bound would let the apply return as if it had finished"
    )
    assert "ci_converge_unit_converge_active" in tasks, (
        "the converge's terminal ActiveState must be read so Result=success on a unit "
        "that is still active is not mistaken for a finished converge"
    )
    assert (
        "['inactive', 'failed']" in tasks[end:]
    ), "the assertion must require a terminal ActiveState as well as Result=success"


def test_only_the_production_converge_is_enabled_for_boot() -> None:
    """A scratch unit a host-captured proof points the role at never runs at boot."""
    tasks = _tasks_text()
    enable = tasks.index("- name: Enable the converge unit for the next boot")
    gate = tasks[enable : tasks.index("register: ci_converge_unit_enabled", enable)]
    assert "ci_converge_unit_service == ci_converge_unit_production_service" in gate, (
        "the role must enable only the production converge unit, so a scratch oneshot "
        "installed for a negative-control capture leaves no boot hook behind it"
    )


def test_retired_scratch_units_and_dirs_are_removed_by_the_apply() -> None:
    """A capture's leftover scratch unit is removed by the committed apply, not by hand."""
    tasks = _tasks_text()
    defaults = (_TASKS.parents[1] / "defaults" / "main.yml").read_text(encoding="utf-8")
    assert "un3zhi-negative-20261103t233754z.service" in defaults, (
        "the un3zhi negative control's scratch unit must be listed for removal, since "
        "fleet_host_guard refuses removing it by hand"
    )
    for name in (
        "Stop and disable each retired scratch unit",
        "Remove each retired scratch unit file",
        "Remove each retired scratch directory",
    ):
        assert name in tasks, f"the role must carry the task {name!r}"
