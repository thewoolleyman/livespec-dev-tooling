"""`ansible/reboot-ci-server.yml` must grant PRIVILEGE ESCALATION to every task that touches the host.

THE DEFECT THIS FILE EXISTS FOR (work-item livespec-dev-tooling-rh6io2, measured
2026-10-13). livespec-dev-tooling-a3uvyu (PR #2409, release v1.96.0) added the
committed reboot playbook. Its idle-read task carries `become: true`; its final
task — the `ansible.builtin.reboot` the whole playbook exists for — did not. The
play connects as the pool's unprivileged login user, so the reboot was refused.
Measured 2026-10-13T02:39:00Z from the vps with the runner pool idle (0 busy
pods at 02:37:45Z and at 02:38:45Z): the idle read returned ok, then the reboot
task failed with `Failed to schedule shutdown: Access denied as the requested
operation requires interactive authentication`, PLAY RECAP read
`poweredge-xubuntu ok=1 changed=0 failed=1 skipped=1`, and poweredge's
`/proc/sys/kernel/random/boot_id` stayed 6f755fe9. The approved reboot drills 4
and 5 of livespec plan livespec-sab5gn are blocked on it.

WHY THE GAP SURVIVED a3uvyu'S OWN TESTS, AND WHY THIS FILE READS RATHER THAN
RUNS. The sibling suite `test_reboot_ci_server_playbook.py` RUNS the playbook,
against a one-host LOCAL inventory with a stand-in `sudo` that drops its flags
and execs the rest — so it SATISFIES become instead of observing it. Worse,
`ansible.builtin.reboot` refuses a local connection before it would escalate
anything, which is precisely the belt that keeps that suite from rebooting
whoever ran pytest. No run-based test in this tree can therefore see whether the
reboot task asked for root. That is not a defect in the sibling suite: its
claims are claims about ansible's `when` / `until` / check-mode SEMANTICS, which
only a run establishes. The claim here is a claim about the playbook's SHAPE, so
this file READS the committed playbook, exactly as
`test_node_status_credential_host_key_trust.py` reads its role, and text-slices
it because no YAML library is importable from this suite.

THE ASSERTION IS GENERAL, NOT A SPOT-CHECK OF THE REBOOT TASK. A test that only
pinned `become: true` onto `ansible.builtin.reboot` would leave the NEXT task
added to this play free to repeat the gap — which is how this one arrived. So
the reader walks EVERY entry in the file and the requirement is FAIL-CLOSED: a
module is exempt only by appearing in `_CONTROLLER_SIDE_MODULES` below, and
anything else — including a module this test has never heard of — must
escalate. A task whose module acts on the host cannot land here silently; it
carries `become: true` or it reddens this test.

ESCALATION IS READ WITH INHERITANCE, because ansible grants it that way: a
`become: true` on the play or on an enclosing `block:` covers the tasks beneath
it. So the reader records each entry's own `become` and then asks the entry's
whole enclosing chain, which means hoisting the grant to the play would satisfy
this test as legitimately as declaring it per task. `true` is the only spelling
accepted, because `ansible-lint`'s `yaml[truthy]` rule — wired into
`just check-ansible-lint` — is what keeps `yes` / `True` out of this tree.

THE SHAPE THE READER CAN READ IS ASSERTED, NOT ASSUMED. `_entries` refuses a
file it cannot model rather than reporting a short task list that would pass by
seeing nothing: every entry must be the play, a `block:` container, or a leaf
task with exactly ONE fully-qualified module key. FQCN is what makes the module
key distinguishable from a task directive by shape alone, and
`just check-ansible-lint`'s `fqcn` rule is what guarantees it.

Work-item: livespec-dev-tooling-rh6io2. Plan: livespec `k3s-on-gmktec-for-vps-usage`
(epic livespec-sab5gn). Follow-up to livespec-dev-tooling-a3uvyu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAYBOOK = _REPO_ROOT / "ansible" / "reboot-ci-server.yml"

# A play or a task opens with a `- name:` entry, and its indentation is what
# places it in the file's nesting: the play sits at column zero, this playbook's
# own tasks four columns in, and the tasks inside its `block:` / `rescue:` four
# further in again.
_OPENING = re.compile(r"^(?P<indent> *)- name: (?P<name>.+)$")

# A mapping key. Read at ONE indentation per entry — the entry's own — so a
# container's nested tasks and a module's own arguments are never mistaken for
# directives of the entry being read.
_KEY = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z_][A-Za-z0-9_.]*):")

# A fully-qualified collection name, which is how a module key is told apart
# from a task directive: `ansible.builtin.reboot` has the shape, `become` and
# `when` cannot. `just check-ansible-lint`'s `fqcn` rule is what keeps every
# module in this tree spelled this way, so the discrimination is enforced
# elsewhere rather than hoped for here.
_FQCN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+$")

_BECOME = "become"
# The ONLY accepted spelling of the grant — see the header: `ansible-lint`'s
# `yaml[truthy]` rule is what keeps `yes` and `True` out of this tree, so
# narrowing to `true` here cannot reject a form the linter would admit.
_BECOME_GRANTED = "true"
_BLOCK = "block"
_PLAY_TASKS = "tasks"

# Modules that execute on the CONTROLLER and reach the target host with
# nothing, so escalation on the host would be meaningless for them. This is an
# ALLOWLIST and it is the whole fail-closed property: a module absent from it is
# assumed to act on the host and must escalate. Keep it to modules that
# genuinely cannot touch the host — `ansible.builtin.include_tasks` is
# deliberately NOT here, because the reader cannot see through an include and a
# play that grew one should redden this test until someone decides what that
# means.
_CONTROLLER_SIDE_MODULES = frozenset(
    {
        # Prints on the controller; the unconfirmed-run note.
        "ansible.builtin.debug",
        # Raises on the controller; the never-went-idle refusal.
        "ansible.builtin.fail",
        # Evaluates on the controller.
        "ansible.builtin.assert",
        # Writes into the controller's own variable store.
        "ansible.builtin.set_fact",
        # Waits on the controller.
        "ansible.builtin.pause",
        # Instructs the controller's executor.
        "ansible.builtin.meta",
    }
)

# The task the Definition of Done names explicitly, and the one the measured
# failure was on. Asserted to be AMONG the host-acting tasks the loop below
# grades, so a reader that silently classified it as controller-side — and
# therefore checked nothing at all — fails rather than passes.
_REBOOT_TASK = "Reboot the confirmed host and run nothing afterwards"


@dataclass(frozen=True, kw_only=True)
class _Entry:
    """One `- name:` entry of the playbook: the play, a `block:` container, or a task."""

    name: str
    indent: int
    start: int
    stop: int
    keys: tuple[str, ...]
    grants_become: bool


def _indent_of(*, line: str) -> int | None:
    """The line's indentation, or None for a blank line or a comment.

    Blank and comment lines carry no structure, so they must not END an entry's
    scope: this playbook's rationale lives in comment blocks indented with the
    code they explain, and a reader that treated one as a dedent would slice an
    entry in half.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    return len(line) - len(line.lstrip())


def _scope_end(*, lines: list[str], start: int, indent: int) -> int:
    """The line index where the entry opened at `start` ends.

    An entry's scope runs to the first structural line indented no deeper than
    its own opening — the next sibling, the enclosing `rescue:`, or the end of
    the file. Nested entries stay INSIDE the scope, which is what lets an
    enclosing `block:` be asked for an inherited `become`.
    """
    return next(
        (
            index
            for index in range(start + 1, len(lines))
            if (depth := _indent_of(line=lines[index])) is not None and depth <= indent
        ),
        len(lines),
    )


def _own_keys(*, lines: list[str], start: int, stop: int, indent: int) -> dict[str, str]:
    """The entry's OWN mapping keys, each with whatever followed its colon inline.

    Read at exactly `indent + 2` — the column a `- name:` entry's siblings sit
    at — so a nested task's directives, a module's arguments and a block
    scalar's body all fall outside and cannot be read as this entry's own.
    """
    keys: dict[str, str] = {}
    for line in lines[start:stop]:
        match = _KEY.match(line)
        if match is not None and len(match["indent"]) == indent + 2:
            keys[match["key"]] = line[match.end() :].strip()
    return keys


def _entries() -> tuple[_Entry, ...]:
    """Every `- name:` entry of the committed playbook, in file order.

    Refuses a file it cannot model rather than returning a short list: an entry
    this reader does not recognise is a task whose escalation nobody is
    checking, and that reads exactly like a clean pass.
    """
    assert _PLAYBOOK.is_file(), (
        f"{_PLAYBOOK} must exist — it is the only committed way to reboot the "
        f"k3s CI server, and the escalation this file grades is a property of "
        f"that playbook and of nothing else"
    )
    lines = _PLAYBOOK.read_text(encoding="utf-8").splitlines()
    openings = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := _OPENING.match(line)) is not None
    ]
    assert openings, (
        f"{_PLAYBOOK} must declare its play and its tasks as `- name:` entries; "
        f"this reader cannot grade a task it cannot find, and an ungraded task "
        f"is an escalation decision nothing is checking"
    )
    entries: list[_Entry] = []
    for index, match in openings:
        indent = len(match["indent"])
        stop = _scope_end(lines=lines, start=index, indent=indent)
        own = _own_keys(lines=lines, start=index, stop=stop, indent=indent)
        entries.append(
            _Entry(
                name=match["name"].strip(),
                indent=indent,
                start=index,
                stop=stop,
                keys=tuple(own),
                grants_become=own.get(_BECOME) == _BECOME_GRANTED,
            )
        )
    play = entries[0]
    assert play.indent == 0 and _PLAY_TASKS in play.keys, (
        f"the first `- name:` entry of {_PLAYBOOK} must be the play itself, "
        f"carrying `{_PLAY_TASKS}:` at column two; this reader derives the "
        f"inherited `{_BECOME}` from the play downward and cannot do that for a "
        f"file shaped some other way. Read: indent {play.indent}, keys "
        f"{list(play.keys)}"
    )
    for entry in entries[1:]:
        assert len(_modules_of(entry=entry)) == 1 or _BLOCK in entry.keys, (
            f"task `{entry.name}` of {_PLAYBOOK} must either invoke exactly one "
            f"fully-qualified module or be a `{_BLOCK}:` container; it carries "
            f"modules {list(_modules_of(entry=entry))} and keys "
            f"{list(entry.keys)}. A task this reader cannot classify is a task "
            f"whose privilege escalation nothing is checking"
        )
    return tuple(entries)


def _modules_of(*, entry: _Entry) -> tuple[str, ...]:
    """The entry's module keys — empty for the play and for a `block:` container."""
    return tuple(key for key in entry.keys if _FQCN.match(key) is not None)


def _acts_on_host(*, entry: _Entry) -> bool:
    """Whether the entry reaches the target host, FAIL-CLOSED on an unknown module.

    Only a module named in `_CONTROLLER_SIDE_MODULES` is treated as reaching
    the host with nothing. Everything else — a module added tomorrow included —
    is assumed to read or change the host and must escalate.
    """
    return any(module not in _CONTROLLER_SIDE_MODULES for module in _modules_of(entry=entry))


def _escalates(*, entries: tuple[_Entry, ...], entry: _Entry) -> bool:
    """Whether the entry runs escalated, counting what the play and its blocks grant.

    Ansible inherits `become` downward, so a grant on the play or on an
    enclosing `block:` covers the task as surely as one written on the task.
    """
    return entry.grants_become or any(
        enclosing.grants_become
        for enclosing in entries
        if enclosing.start < entry.start and enclosing.stop >= entry.stop
    )


def test_every_task_that_reads_or_changes_the_host_runs_with_privilege_escalation() -> None:
    """The Definition-of-Done assertion, over EVERY task rather than over the reboot alone.

    The playbook connects as the pool's unprivileged login user, so a task that
    reads the server's root-owned admin kubeconfig or schedules its shutdown
    must escalate or be refused by the host. The measured refusal was on the
    reboot task; the assertion is over all of them, so the next task added to
    this play cannot arrive the same way.
    """
    entries = _entries()
    host_acting = tuple(entry for entry in entries if _acts_on_host(entry=entry))

    assert _REBOOT_TASK in tuple(entry.name for entry in host_acting), (
        f"`{_REBOOT_TASK}` must be among the tasks graded here — it is the task "
        f"the measured refusal was on, and a reader that classified it as "
        f"controller-side would check nothing and still pass. Graded: "
        f"{[entry.name for entry in host_acting]}"
    )
    unescalated = tuple(
        entry.name for entry in host_acting if not _escalates(entries=entries, entry=entry)
    )
    assert not unescalated, (
        f"these tasks of {_PLAYBOOK} read or change the target host but do not "
        f"run escalated: {list(unescalated)}. The play connects as the pool's "
        f"unprivileged login user, so each is refused on the host — the reboot "
        f"task failed exactly this way on poweredge-xubuntu at "
        f"2026-10-13T02:39:00Z with `Access denied as the requested operation "
        f"requires interactive authentication`. Add `{_BECOME}: "
        f"{_BECOME_GRANTED}` to the task, or to a scope that encloses it"
    )
