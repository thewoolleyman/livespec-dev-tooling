"""A `--check` converge of `otel_collector` REPORTS a rebuilt node, never fails on it.

WHY IT EXISTS (work-item livespec-dev-tooling-hrdj6s, plan
kubernetes-node-observability). The runner-pool node telemetry heading in
`SPECIFICATION/non-functional-requirements.md` requires that "the drift report `just ansible-drift
ansible/ci-pool.yml` MUST report a node whose collector differs from the merged
configuration", and the runner-pool node rebuild recipe heading hands that drift report a
node the role has NOT yet converged: its node-provisioning stage is this very
playbook, applied to a machine that came up from empty storage. The scenario
heading about a pool node rebuilt by the recipe and its profile
closes the loop — re-running the procedure against the finished node must change
nothing — so the same report has to read `changed=0` once the node is converged.

Measured 2026-10-24 18:30Z, the first `just ansible-drift ansible/ci-pool.yml
--tags otel_collector` after livespec-dev-tooling-ool6ws merged, the drift report
FAILED on both nodes the role had not yet converged — and failed for a check-mode
ARTEFACT rather than for anything true about the hosts, since the apply minutes
later converged both and the post-apply reports read `changed=0 failed=0`:

- gmktec-xubuntu: a `--check` run writes nothing, so "Create the directory the
  verified release tarball is unpacked in" was simulated and "Download the pinned
  collector release tarball" then failed with `Destination
  /var/cache/otel-collector does not exist`.
- hp-xubuntu: the same emptiness simulated "Append each ingest key this host's
  environment file does not already set", so "Refuse an environment file set
  missing a key the merged configuration reads" refused with `none of
  /etc/otel-collector/.env sets HONEYCOMB_INGEST_KEY_LIVESPEC`.

Both are one defect: a task that consumes state an EARLIER task creates is wrong
under `--check`, because under `--check` that earlier task created nothing. The
node a drift report has most to say about was the one node it could not describe.

WHAT THESE TESTS READ, AND WHAT THEY DO NOT. They read the committed task files
and assert the GATES that make the four Definition-of-Done runs come out as they
do. They do not drive `ansible-playbook`: `check-tests-no-subprocess-spawn`
forbids a test from spawning one, and this suite installs no Ansible — so the
live four-run evidence is the work-item's Proof of Done (`ansible-playbook --check
--diff` with `ansible_connection=local` against the factory sandbox, which is
itself a host with no service account, no `/var/cache/otel-collector` and no
collector binary), and what stands here is the regression net under it.

EVERY STRUCTURAL CLAIM IS READ OFF CODE, NEVER OFF PROSE. Both task files carry
long comments about the trap each task closes, and that prose necessarily NAMES
the very directives and facts these assertions look for — `ansible_check_mode`,
`changed_when`, the two gating facts. So `_task_blocks` strips comment lines
before anything is matched. Skipping that fails in both directions at once: a
presence claim passes on a sentence merely mentioning the gate, and an absence
claim fails on the comment explaining why that task does not carry it.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "otel_collector"
_TASKS = _ROLE / "tasks" / "main.yml"
_BINARY_TASKS = _ROLE / "tasks" / "binary.yml"

# The measurement every install step already rested on: the version the host
# itself REPORTS. A node already carrying the pinned release reaches no install
# or report task below.
_INSTALL_NEEDED = "otel_collector_binary_install_needed"

# The two modules whose success depends on state an earlier task of the same file
# creates — a destination directory, an archive to unpack — plus the install,
# matched by the destination only this role's one install task writes.
_UNSIMULATABLE_MODULES = ("ansible.builtin.get_url:", "ansible.builtin.unarchive:")
_INSTALLS_THE_BINARY = 'dest: "{{ otel_collector_binary }}"'
_WITHHELD_FROM_A_DRY_RUN = 3

# The read whose non-zero results ARE the append's loop: the keys `grep --quiet`
# could not find in this host's environment file.
_CONTROLLER_KEYS_READ = "otel_collector_controller_keys_read"
_KEYS_GREP_MISSED = "rejectattr('rc', 'equalto', 0)"
# The keys an apply's append really placed and a dry run's placed nowhere, and
# the set the refusal reads. The first must be subtracted from the second, and
# only under `--check`.
_APPENDED_KEYS = "otel_collector_appended_environment_keys"
_MISSING_KEYS = "otel_collector_missing_environment_keys"
_ONLY_UNDER_CHECK_MODE = "if ansible_check_mode else []"

_WRITES_THE_CONFIGURATION = 'dest: "{{ otel_collector_config_path }}"'


def _task_blocks(*, body: str) -> list[str]:
    """Each `- name:`-introduced task of a role file, COMMENTS STRIPPED, in file order.

    The stripping is the load-bearing half — see this module's docstring for what
    reading a task's own prose as its code costs in both directions.
    """
    return [
        "\n".join(
            line for line in f"- name: {chunk}".splitlines() if not line.lstrip().startswith("#")
        )
        for chunk in body.split("\n- name: ")[1:]
    ]


def _only_block(*, blocks: list[str], carrying: str, source: str) -> str:
    """The ONE task carrying a needle, refusing both absence and ambiguity.

    Refusing a second match matters as much as refusing none: these assertions
    read one gate off one task, and a needle that matched two tasks would be
    asserted against whichever the scan happened to reach first — a claim about
    a task nobody chose.
    """
    found = [block for block in blocks if carrying in block]
    assert len(found) == 1, (
        f"{source} must carry exactly ONE task whose code contains "
        f"`{carrying}`; it carries {len(found)}. These assertions read one gate off "
        f"one task, so neither an absent nor a duplicated match establishes anything"
    )
    return found[0]


def test_a_dry_run_withholds_the_install_it_cannot_simulate_and_reports_it() -> None:
    """Definition of Done assertion 1: a rebuilt node's dry run fails nothing and reports the install.

    The host is the one the rebuild recipe hands back: no service account, no
    `/var/cache/otel-collector` and no collector binary, with a managed-install
    host's variables. The account, the download directory, the configuration and
    the unit are each written by a module `--check` simulates faithfully and so
    each report themselves; the fetch, the extraction and the install are the
    three that cannot, so they are withheld and ONE task reports the change they
    would have made.
    """
    blocks = _task_blocks(body=_BINARY_TASKS.read_text(encoding="utf-8"))
    source = _BINARY_TASKS.name

    withheld = [
        block
        for block in blocks
        if any(module in block for module in _UNSIMULATABLE_MODULES)
        or _INSTALLS_THE_BINARY in block
    ]
    assert len(withheld) == _WITHHELD_FROM_A_DRY_RUN, (
        f"{source} must carry exactly the three tasks a dry run cannot simulate — the fetch, "
        f"the extraction and the install — and it carries {len(withheld)}. A fourth added "
        f"without a gate is the defect this test exists for, so the count is stated"
    )
    for block in withheld:
        assert f"when: {_INSTALL_NEEDED} | bool and not ansible_check_mode" in block, (
            f"this task consumes state an EARLIER task of {source} creates, and under `--check` "
            f"that task created nothing — so it must be withheld from a dry run rather than "
            f"left to fail on the dry run's own emptiness:\n{block}"
        )

    directory = _only_block(blocks=blocks, carrying="state: directory", source=source)
    assert f"when: {_INSTALL_NEEDED} | bool" in directory, directory
    assert "not ansible_check_mode" not in directory, (
        f"the download directory must stay gated on `{_INSTALL_NEEDED}` alone: `file` simulates "
        f"faithfully under `--check`, so this is the task that REPORTS the directory as a "
        f"change, which the Definition of Done requires of a rebuilt node's drift report;\n"
        f"{directory}"
    )

    account = _only_block(blocks=blocks, carrying="ansible.builtin.user:", source=source)
    assert "when:" not in account, (
        f"the service account must stay ungated so a dry run over a node that has none reports "
        f"it as a change; `user` simulates faithfully under `--check`:\n{account}"
    )

    report = _only_block(blocks=blocks, carrying="changed_when: true", source=source)
    assert f"when: {_INSTALL_NEEDED} | bool and ansible_check_mode" in report, (
        f"the install a dry run withheld must be REPORTED as the change it is — a node with no "
        f"collector differs from its profile's declared state, and failing said nothing about "
        f"the difference. The report stands exactly where the withheld tasks would have run, "
        f"so it is gated on `{_INSTALL_NEEDED}` and check mode;\n{report}"
    )
    assert "ansible.builtin.debug:" in report, (
        f"there is nothing for a module to simulate here — the statement IS the output — so the "
        f"report is a `debug` whose `changed_when: true` puts it in the run's changed count;\n"
        f"{report}"
    )
    assert "{{ otel_collector_binary }}" in report, (
        f"the report must name the binary it would have installed, so an operator reading a "
        f"rebuilt node's drift report is told what the apply will place;\n{report}"
    )
