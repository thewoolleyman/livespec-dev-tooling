"""The host-wide local-gate slot limit — at most N pytest sessions, the rest queue.

Governed by `SPECIFICATION/non-functional-requirements.md` section "Local gate
concurrency limit" and the four `SPECIFICATION/scenarios.md` scenarios beneath
it. Nothing here reads the host's own `/etc/livespec/local-gate-slots` or its
`/run` slot store: every assertion is taken against `tmp_path`, so the suite
answers the same on the dev VPS, which carries a limit, as in a factory sandbox,
which never will.

THE LOCKS ARE REAL, and that is the point rather than an accident of
convenience. `flock` is owned by the OPEN FILE DESCRIPTION, not by the process,
so two descriptors opened separately in ONE process contend exactly as two
sessions on the host do — measured, not assumed, and it is what lets the
at-most-N and queueing properties be proved without a second interpreter. The
two properties that genuinely need a second process — a slot holder dying by
SIGKILL, and a nested session inheriting the marker — fork one, because what
they assert IS process death and environment inheritance.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "local_gate_slots.py"
_SYNTHETIC_NAME = "local_gate_slots_under_test"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# The `pytest11` table and its entries, read as TEXT rather than parsed: stdlib
# `tomllib` lands in 3.11 and this repo's floor is 3.10.16, which is the same
# reason every other pyproject assertion in this suite reads text.
_PYTEST11_TABLE = re.compile(
    r"^\[project\.entry-points\.pytest11\][ \t]*$(?P<body>.*?)(?=^\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
_ENTRY_POINT = re.compile(
    r'^[ \t]*(?P<name>[A-Za-z0-9_.-]+)[ \t]*=[ \t]*"(?P<target>[^"]+)"[ \t]*$',
    re.MULTILINE,
)

# How long the no-busy-loop probe watches a waiting session, and the CPU it is
# allowed to have burned over that window. The ceiling discriminates by an order
# of magnitude rather than by a hair: a spin loop would consume a whole core for
# the probe's full duration, so a reading anywhere near the elapsed wall time
# convicts and a genuinely sleeping waiter lands three orders of magnitude below
# the ceiling. It is deliberately NOT tight — a tight one would convict a loaded
# host instead of a busy loop.
_CPU_PROBE_SECONDS = 1.5
_CPU_CEILING_SECONDS = 0.2

# How long the probe is willing to wait for a freed slot to be picked up before
# calling the waiter wedged. Generous because a loaded host may schedule the
# waiter late, and a false "wedged" here would read as a broken queue.
_HANDOFF_TIMEOUT_SECONDS = 30.0

# The environment marker a slot holder leaves for its children, spelled HERE and
# asserted against the module's own constant rather than read from it. A test
# that read the name from the subject could not notice it being renamed, and the
# name is the whole interface: a nested session recognises its parent's hold by
# this variable and by nothing else.
_MARKER_ENV_VAR = "LIVESPEC_LOCAL_GATE_SLOT_HELD"

# Fixed-width answers a forked child writes back, so one blocking read is
# unambiguous about which of the three things happened.
_CHILD_TOOK_A_SLOT = b"took-1"
_CHILD_TOOK_NOTHING = b"none--"
_CHILD_QUEUED = b"queued"


@pytest.fixture(autouse=True)
def _forget_any_inherited_slot_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every assertion here as a session that holds no slot, and leave none.

    Autouse in BOTH directions and both matter. A suite run on a converged host
    may itself hold a slot, which would make every nested-session assertion here
    vacuously true; and a test that acquires one marks this process, which would
    silently switch off throttling for every test that followed it on this
    worker. `monkeypatch` records the variable's state on the way in and
    restores it on the way out, so neither can happen.
    """
    monkeypatch.delenv(_MARKER_ENV_VAR, raising=False)


@dataclass(frozen=True, kw_only=True)
class _Holder:
    """A forked process holding one slot, and the pipe that lets it go."""

    pid: int
    release: int

    def kill(self) -> int:
        """SIGKILL this holder and reap it, returning its wait status.

        SIGKILL rather than a release byte, because the ratified clause names
        that signal: it runs no handler, no `finally`, no `atexit` and no
        interpreter shutdown, so nothing the holder could have been written to
        do on the way out can be what frees the slot.
        """
        os.kill(self.pid, signal.SIGKILL)
        _, status = os.waitpid(self.pid, 0)
        return status


def _load_module() -> ModuleType:
    """Import the slot module fresh from its file path.

    Loaded BY PATH rather than as `livespec_dev_tooling.local_gate_slots` so the
    assertions read the on-disk module the Red→Green hook inspects, and so this
    file's first assertion can be a genuine one about the module's existence
    instead of a collection error.
    """
    spec = importlib.util.spec_from_file_location(_SYNTHETIC_NAME, str(_MODULE_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _limit_file(*, root: Path, text: str) -> Path:
    """One host limit file carrying `text`."""
    path = root / "local-gate-slots"
    path.write_text(text, encoding="utf-8")
    return path


def _slot_store(*, root: Path) -> Path:
    """An empty slot store, as the host's converge provisions it."""
    store = root / "slots"
    store.mkdir()
    return store


def _emitted_lines(*, captured: str) -> list[dict[str, object]]:
    """Every structured line a queued session emitted, parsed.

    Parsed rather than substring-matched, because the ratified clause asks for a
    line that NAMES THE LIMIT: a bare "waiting" string would satisfy a substring
    match and tell an operator nothing about how many slots the host has. The
    parse is TOTAL — every line a queued session writes is one of these
    announcements, so a line that is not one fails here rather than being
    filtered away where no assertion would ever see it.
    """
    return [json.loads(line) for line in captured.splitlines() if line.strip()]


def _fork_slot_holder(*, module: ModuleType, slot_dir: Path, limit: int) -> _Holder:
    """Fork a process that takes one slot through the module and holds it.

    A SECOND PROCESS is the only thing that can prove the death properties: the
    question is what the KERNEL does with a lock when its holder stops existing,
    and no in-process construction can stop a process from existing. It is
    FORKED rather than spawned because the holder must take its slot through
    this module's own `take_slot` — a lock taken by some command-line tool would
    prove a fact about that tool — and it leaves through `os._exit`, so no
    pytest teardown and no coverage write ever runs inside it.
    """
    holding_read, holding_write = os.pipe()
    release_read, release_write = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover — the forked child, which reports to nobody
        held = module.take_slot(slot_dir=slot_dir, limit=limit)
        _ = os.write(holding_write, b"held" if held is not None else b"none")
        _ = os.read(release_read, 2)
        os._exit(0)
    assert os.read(holding_read, 4) == b"held"
    return _Holder(pid=pid, release=release_write)


def _fork_queued_session(*, module: ModuleType, slot_dir: Path, limit: int) -> int:
    """Fork a process that queues for a slot and is left standing in the queue.

    The child reports from INSIDE its own inter-round sleep, which is what makes
    the kill deterministic rather than timed: when the parent reads the byte the
    child has provably attempted every slot, taken none, and not yet come back
    round. A parent that instead slept "long enough" would be asserting about a
    child whose state it had guessed.
    """
    queued_read, queued_write = os.pipe()
    hang_read, _hang_write = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover — the forked child, which reports to nobody

        def _report_from_inside_the_wait(_seconds: float) -> None:
            _ = os.write(queued_write, b"queued")
            _ = os.read(hang_read, 1)

        _ = module.await_slot(slot_dir=slot_dir, limit=limit, sleep=_report_from_inside_the_wait)
        os._exit(0)
    assert os.read(queued_read, 6) == b"queued"
    return pid


@pytest.mark.integration
def test_a_hosts_limit_of_n_admits_n_slot_holders_and_queues_the_next(*, tmp_path: Path) -> None:
    """SCENARIO: a host at its local-gate slot limit queues the next pytest session.

    The at-most-N half of the ratified clause, proved against real `flock`
    holds: with the limit set to 2, two takes succeed, the third finds nothing
    free, and releasing ONE frees exactly one — not the store.
    """
    assert _MODULE_PATH.is_file(), (
        f"{_MODULE_PATH.relative_to(_REPO_ROOT)} must exist: it is the pytest "
        f"plugin that bounds how many fleet gate test runs execute at once on "
        f"one host, per SPECIFICATION/non-functional-requirements.md "
        f'section "Local gate concurrency limit"'
    )
    module = _load_module()
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir()

    limit = module.configured_limit(limit_file=_limit_file(root=tmp_path, text="2\n"))
    assert limit == 2

    first = module.take_slot(slot_dir=slot_dir, limit=limit)
    second = module.take_slot(slot_dir=slot_dir, limit=limit)
    assert first is not None
    assert second is not None
    assert (
        module.take_slot(slot_dir=slot_dir, limit=limit) is None
    ), "a third session must find no free slot on a host whose limit is 2"

    os.close(first)
    third = module.take_slot(slot_dir=slot_dir, limit=limit)
    assert third is not None, "the slot the first holder released must be takeable"
    assert (
        module.take_slot(slot_dir=slot_dir, limit=limit) is None
    ), "releasing one slot must free exactly one, never the whole store"
    os.close(second)
    os.close(third)


@pytest.mark.integration
def test_the_limit_is_read_from_one_host_file_and_every_absence_is_unlimited(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SCENARIO: a host with no local-gate slot limit runs pytest sessions unchanged.

    The limit lives in ONE host file, and every way of not carrying a usable one
    collapses to the same unlimited answer. That collapse is deliberate and is
    the fail-OPEN direction: a throttle that cannot read its own setting must
    not be able to stop a gate, so an absent file, a value that will not parse,
    a negative, an explicit zero and an unreadable file all read as no limit.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()

    assert module.configured_limit(limit_file=tmp_path / "absent") is None
    assert module.configured_limit(limit_file=tmp_path) is None
    assert module.configured_limit(limit_file=_limit_file(root=tmp_path, text="")) is None
    assert module.configured_limit(limit_file=_limit_file(root=tmp_path, text="lots")) is None
    assert module.configured_limit(limit_file=_limit_file(root=tmp_path, text="-1")) is None
    assert module.configured_limit(limit_file=_limit_file(root=tmp_path, text="0\n")) is None
    assert module.configured_limit(limit_file=_limit_file(root=tmp_path, text=" 3 \n")) == 3

    unreadable = _limit_file(root=tmp_path, text="3\n")

    def _refuse(*_args: object, **_kwargs: object) -> str:
        raise OSError(5, "simulated I/O error reading the host limit file")

    monkeypatch.setattr(Path, "read_text", _refuse)
    assert module.configured_limit(limit_file=unreadable) is None, (
        "a limit file that cannot be read must leave the host unthrottled "
        "rather than fail a gate that has nothing to do with it"
    )


@pytest.mark.integration
def test_a_slot_file_that_cannot_be_opened_is_not_handed_out(*, tmp_path: Path) -> None:
    """A slot whose file will not open is never reported as taken.

    The slot store is provisioned by the same converge that sets the limit, so
    this is the broken-host edge rather than an expected state. It is asserted
    because the alternative — handing back a descriptor for a path no lock was
    taken on — would let two sessions believe they each held the same slot.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()
    slot_dir = tmp_path / "slots"
    slot_dir.mkdir()
    (slot_dir / "slot-1").mkdir()

    assert module.take_slot(slot_dir=slot_dir, limit=1) is None


@pytest.mark.integration
def test_a_waiting_session_names_the_limit_and_repeats_itself_each_half_minute(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: a host at its local-gate slot limit queues the next pytest session.

    The ANNOUNCEMENT half of that scenario: a queued session says so, names the
    limit it is queued behind, and keeps saying so at least once a minute. A
    queue nobody can see is indistinguishable from a wedged gate, which is the
    whole reason the clause requires the repeat rather than one line at the
    start.

    The sleeping is stubbed so the cadence can be read in simulated seconds
    rather than waited out; that the wait SLEEPS at all is asserted separately
    by the no-busy-loop probe, against the real clock.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()
    assert hasattr(module, "await_slot"), (
        "the module must expose await_slot: a session that finds every slot "
        "held has to queue for one, and queueing is what the ratified clause "
        "requires instead of starting a further test run"
    )
    slot_dir = _slot_store(root=tmp_path)
    holder = module.take_slot(slot_dir=slot_dir, limit=1)
    assert holder is not None

    rounds_per_heartbeat = round(module.HEARTBEAT_SECONDS / module.POLL_SECONDS)
    naps: list[float] = []

    def _nap(seconds: float) -> None:
        naps.append(seconds)
        if len(naps) == rounds_per_heartbeat + 1:
            os.close(holder)

    waited = module.await_slot(slot_dir=slot_dir, limit=1, sleep=_nap)
    assert waited is not None
    os.close(waited)

    assert module.HEARTBEAT_SECONDS <= 60.0, (
        "the clause requires a waiting session to repeat its line at least once "
        "a minute, so the heartbeat interval cannot exceed sixty seconds"
    )
    assert naps == [module.POLL_SECONDS] * (
        rounds_per_heartbeat + 1
    ), "every round of the wait must sleep, and sleep the same poll interval"

    announced = _emitted_lines(captured=capsys.readouterr().err)
    assert len(announced) == 2, (
        f"a wait of {len(naps) * module.POLL_SECONDS} simulated seconds must "
        f"announce itself once at the start and again one heartbeat later, "
        f"got {len(announced)} lines"
    )
    for record in announced:
        assert record["limit"] == 1, "the announcement must name the host's limit"
        assert "waiting" in str(record["event"]), (
            "the announcement must say the session is waiting, so a queue is "
            "never mistaken for a wedged gate"
        )


@pytest.mark.integration
def test_a_wait_of_several_poll_rounds_adds_no_measurable_cpu_load(*, tmp_path: Path) -> None:
    """The wait is not a busy loop, measured against the real clock.

    Read as process CPU time over a real wall-clock window while a real waiter
    is queued on a real lock. A spin loop would burn a core for the whole
    window; a sleeping one burns the handful of syscalls its polls cost.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()
    assert hasattr(module, "await_slot")
    slot_dir = _slot_store(root=tmp_path)
    holder = module.take_slot(slot_dir=slot_dir, limit=1)
    assert holder is not None

    acquired: list[int] = []

    def _queue_for_the_slot() -> None:
        acquired.append(module.await_slot(slot_dir=slot_dir, limit=1))

    waiter = threading.Thread(target=_queue_for_the_slot, daemon=True)
    waiter.start()
    before = time.process_time()
    time.sleep(_CPU_PROBE_SECONDS)
    burned = time.process_time() - before

    os.close(holder)
    waiter.join(timeout=_HANDOFF_TIMEOUT_SECONDS)
    assert not waiter.is_alive(), "the waiter must take the slot once it frees"
    assert len(acquired) == 1
    os.close(acquired[0])

    assert burned < _CPU_CEILING_SECONDS, (
        f"a {_CPU_PROBE_SECONDS}s wait burned {burned:.3f}s of CPU, which is a "
        f"busy loop rather than a poll that sleeps"
    )


@pytest.mark.integration
def test_a_session_that_queued_runs_once_a_slot_frees_and_reaches_no_verdict(
    *, tmp_path: Path
) -> None:
    """Waiting produces no verdict: the queued session proceeds and reports its own.

    The session-level entry point either hands back a slot or keeps waiting. It
    has no third answer, and that is the property: a throttle able to report a
    FAILURE would turn a busy host into a red tree, so queueing can only ever
    delay a session's own tests, never stand in for their result.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()
    assert hasattr(module, "take_session_slot"), (
        "the module must expose take_session_slot: it is what a pytest session "
        "calls at start, and what has to resolve the host's limit, queue when "
        "the host is full, and then let the session run its own tests"
    )
    slot_dir = _slot_store(root=tmp_path)
    limit_file = _limit_file(root=tmp_path, text="1\n")
    occupying = module.take_slot(slot_dir=slot_dir, limit=1)
    assert occupying is not None

    outcome: list[int | None] = []

    def _queue_as_a_session() -> None:
        outcome.append(module.take_session_slot(limit_file=limit_file, slot_dir=slot_dir))

    session = threading.Thread(target=_queue_as_a_session, daemon=True)
    session.start()
    os.close(occupying)
    session.join(timeout=_HANDOFF_TIMEOUT_SECONDS)

    assert not session.is_alive(), "the queued session must proceed once a slot frees"
    assert len(outcome) == 1, (
        "the queued session must return rather than raise: a wait that could "
        "raise would be a verdict about a tree it never looked at"
    )
    held = outcome[0]
    assert held is not None
    os.close(held)


@pytest.mark.integration
def test_a_slot_holder_killed_with_sigkill_frees_its_slot_without_cleanup(
    *, tmp_path: Path
) -> None:
    """SCENARIO: a slot holder that is killed frees its slot without cleanup.

    The kernel releases a `flock` when the last descriptor of its open file
    description closes, and a dying process's descriptors close whatever killed
    it. So there is no cleanup step to run, none runs, and the evidence that
    none ran is that the slot FILE is still sitting there afterwards: a sweep
    would have removed or rewritten it.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()
    slot_dir = _slot_store(root=tmp_path)
    holder = _fork_slot_holder(module=module, slot_dir=slot_dir, limit=1)
    slot_file = slot_dir / "slot-1"

    assert (
        module.take_slot(slot_dir=slot_dir, limit=1) is None
    ), "the forked holder must hold the only slot before it is killed"

    status = holder.kill()
    assert os.WIFSIGNALED(status), "the holder must have died of the signal"
    assert os.WTERMSIG(status) == signal.SIGKILL

    assert slot_file.is_file(), (
        "the slot file must still be there: nothing swept it, which is what "
        "makes this a release with no cleanup step rather than one with a sweep"
    )
    regained = module.take_slot(slot_dir=slot_dir, limit=1)
    assert regained is not None, "the killed holder's slot must be takeable again"
    os.close(regained)


@pytest.mark.integration
def test_a_session_killed_while_queued_holds_no_slot(*, tmp_path: Path) -> None:
    """A session killed while waiting holds nothing, because it took nothing.

    Asserted by COUNTING the store afterwards rather than by inspecting the dead
    process: with the limit at one, the surviving session must be able to take
    one slot and then find none, which is only true if the killed waiter left no
    hold behind it.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()
    slot_dir = _slot_store(root=tmp_path)
    occupying = module.take_slot(slot_dir=slot_dir, limit=1)
    assert occupying is not None

    queued = _fork_queued_session(module=module, slot_dir=slot_dir, limit=1)
    os.kill(queued, signal.SIGKILL)
    _, status = os.waitpid(queued, 0)
    assert os.WTERMSIG(status) == signal.SIGKILL

    os.close(occupying)
    freed = module.take_slot(slot_dir=slot_dir, limit=1)
    assert freed is not None, "the host's one slot must be free again"
    assert module.take_slot(slot_dir=slot_dir, limit=1) is None, (
        "and there must be exactly one: a second free slot would mean the "
        "killed waiter had been holding something after all"
    )
    os.close(freed)


@pytest.mark.integration
def test_a_session_on_a_host_with_no_usable_slot_store_is_not_throttled(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A store that cannot be created leaves the session unthrottled, and says so.

    Fail-OPEN, for the reason the module records: a gate decides whether a tree
    is sound, and a concurrency stopgap that cannot reach its own slot store
    must not be what refuses one. It is ANNOUNCED because a silent fail-open is
    indistinguishable from a host that was never provisioned.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()
    assert hasattr(module, "take_session_slot")
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("", encoding="utf-8")

    held = module.take_session_slot(
        limit_file=_limit_file(root=tmp_path, text="2\n"),
        slot_dir=blocking_file / "slots",
    )

    assert held is None
    announced = _emitted_lines(captured=capsys.readouterr().err)
    assert len(announced) == 1
    assert str(announced[0]["slots"]).endswith("slots")


@pytest.mark.integration
def test_a_session_on_a_host_with_no_limit_takes_no_slot_and_touches_no_store(
    *, tmp_path: Path
) -> None:
    """SCENARIO: a host with no local-gate slot limit runs pytest sessions unchanged.

    The session-level half of that scenario. The store is not merely left empty
    but never CREATED, which is the stronger statement and the one that matters
    for a factory sandbox: an unprovisioned host is not a host with a limit of
    infinity, it is a host this module does not touch.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()
    assert hasattr(module, "take_session_slot")
    store = tmp_path / "slots"

    assert module.take_session_slot(limit_file=tmp_path / "absent", slot_dir=store) is None
    assert not store.exists(), (
        "a host that sets no limit must not even have a slot store created "
        "under it: nothing about an unprovisioned host may change"
    )


@pytest.mark.integration
def test_a_session_nested_under_a_slot_holder_takes_no_second_slot(*, tmp_path: Path) -> None:
    """SCENARIO: a pytest session nested under a slot holder takes no second slot.

    The DEADLOCK case, and the reason the marker exists at all: a suite that
    starts pytest in a child process on a host whose limit is one would
    otherwise have its child queue behind its own parent, which never finishes
    because it is waiting for the child. The child must therefore run
    IMMEDIATELY rather than queue, which is what the pipe answer distinguishes.

    The marker reaches the child through the real process environment, asserted
    in both halves: that an exec'd child sees the variable at all, and that a
    session which sees it takes nothing.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()
    assert hasattr(module, "MARKER_ENV_VAR"), (
        "the module must name the environment marker a slot holder leaves for "
        "its children: without it a nested pytest session queues behind its own "
        "parent, which is a deadlock rather than a throttle"
    )
    assert module.MARKER_ENV_VAR == _MARKER_ENV_VAR
    slot_dir = _slot_store(root=tmp_path)
    limit_file = _limit_file(root=tmp_path, text="1\n")

    parent_slot = module.take_session_slot(limit_file=limit_file, slot_dir=slot_dir)
    assert parent_slot is not None, "the first session must take the host's one slot"
    assert os.environ[_MARKER_ENV_VAR], "a slot holder must mark its environment"
    assert module.take_session_slot(limit_file=limit_file, slot_dir=slot_dir) is None, (
        "a further session in THIS process, which now carries the marker, must "
        "take nothing — and must answer before it looks at the store, which is "
        "what keeps a nested session off a queue its own parent is at the head of"
    )

    exported = subprocess.run(["env"], capture_output=True, text=True, check=True)
    assert _MARKER_ENV_VAR in exported.stdout, (
        "the marker must reach the REAL process environment, because the nested "
        "session this protects is an exec'd child rather than a fork"
    )

    answer_read, answer_write = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover — the forked child, which reports to nobody

        def _refuse_to_queue(_seconds: float) -> None:
            _ = os.write(answer_write, _CHILD_QUEUED)
            os._exit(2)

        nested = module.take_session_slot(
            limit_file=limit_file, slot_dir=slot_dir, sleep=_refuse_to_queue
        )
        _ = os.write(
            answer_write,
            _CHILD_TOOK_A_SLOT if nested is not None else _CHILD_TOOK_NOTHING,
        )
        os._exit(0)
    answer = os.read(answer_read, 6)
    _, status = os.waitpid(pid, 0)

    assert answer == _CHILD_TOOK_NOTHING, (
        f"a session nested under a slot holder must run at once holding " f"nothing, got {answer!r}"
    )
    assert os.waitstatus_to_exitcode(status) == 0
    assert module.take_slot(slot_dir=slot_dir, limit=1) is None, (
        "the host's one slot must still be the parent's: a nested session that "
        "had taken a second one would have found this free"
    )
    os.close(parent_slot)


@pytest.mark.integration
def test_the_plugin_hook_leaves_an_unprovisioned_host_completely_untouched(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SCENARIO: a host with no local-gate slot limit runs pytest sessions unchanged.

    Asserted at the HOOK, which is the only thing a host without this feature
    would not be running. "Unchanged" is read as four separate absences — no
    slot store, no marker, no output, no delay — because any one of them
    appearing on a factory sandbox or a delegated gate pod would be this
    module's footprint on a host the clause says it must not touch.
    """
    assert _MODULE_PATH.is_file()
    module = _load_module()
    assert hasattr(module, "pytest_configure"), (
        "the module must implement the pytest_configure hook: it is what makes "
        "the limit apply to every pytest session a fleet gate runs, with no "
        "per-repository wiring to forget"
    )
    assert not inspect.signature(module.pytest_configure).parameters, (
        "the hook must declare no arguments: pluggy passes a hook only what it "
        "names, so declaring none keeps it callable across pytest versions"
    )
    store = tmp_path / "slots"
    monkeypatch.setattr(module, "LIMIT_FILE", tmp_path / "absent")
    monkeypatch.setattr(module, "SLOT_DIR", store)

    assert module.pytest_configure() is None

    assert not store.exists(), "no slot store may be created on an unlimited host"
    assert _MARKER_ENV_VAR not in os.environ, "and no marker may be left behind"
    assert capsys.readouterr().err == "", "and nothing may be said about it"


@pytest.mark.integration
def test_one_declared_entry_point_governs_every_fleet_gate_surface() -> None:
    """Every pytest session a fleet gate runs is governed, with no per-repo wiring.

    The ratified clause names four surfaces — the pre-commit check aggregate,
    the commit-msg replay gate, a local pre-push `just check` and a hand-run
    `just check` — and this is the one declaration that covers all four. Each of
    them runs pytest, and a `pytest11` entry point is loaded by EVERY pytest
    session in any environment where this package is installed, so there is no
    fourth place to remember and no repository that can forget.

    The declared target is held against this module's own path rather than
    restated, because the failure it guards is silent in the worst way: an entry
    point naming a module that moved loads nothing, every session starts
    unthrottled, and the only symptom is a host that quietly contends again.
    """
    table = _PYTEST11_TABLE.search(_PYPROJECT.read_text(encoding="utf-8"))
    assert table is not None, (
        "pyproject.toml must declare a [project.entry-points.pytest11] table: "
        "it is how the limit reaches every fleet gate's pytest session"
    )
    targets = [found.group("target") for found in _ENTRY_POINT.finditer(table.group("body"))]
    assert targets, "the pytest11 table must declare at least one plugin module"

    expected = str(_MODULE_PATH.relative_to(_REPO_ROOT).with_suffix("")).replace("/", ".")
    assert expected in targets, (
        f"the pytest11 table must name {expected}, got {targets}: an entry "
        f"point naming a module that moved loads nothing and leaves every "
        f"session unthrottled with no symptom but a contending host"
    )
