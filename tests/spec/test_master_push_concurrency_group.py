"""B' master-push concurrency, `SPECIFICATION/constraints.md`, "CI matrix shape" (v182).

The scenarios "a pending superseded master push run is dropped while the run in progress
completes", "a release or expedited master push run is never dropped from the master concurrency
group" and "the master concurrency group never holds or cancels a pull-request run"
(livespec-dev-tooling-qzw2gf). These read this repository's committed `.github/workflows/ci.yml`
and EVALUATE its top-level `concurrency.group` expression for each event shape, the way GitHub
Actions resolves it at run time, then assert:

- every ordinary `master` push resolves to ONE shared group, and `cancel-in-progress` is false, so
  the run in progress completes and GitHub keeps only the newest pending run in the group;
- a `chore(master): release` push and a push whose head commit carries the
  `Factory-Override: EXPEDITED_INCIDENT_RESPONSE` trailer resolve to a group of their own;
- a pull-request run and an incident-scratch push resolve to a group of their own;
- the workflow declares no `merge_group` trigger, so no merge-group run can join the group.

The evaluator below implements exactly the GitHub expression subset the committed group uses
(context property reads with the `.*.` object filter, string literals, `==`, `!`, `&&`, `||`,
`startsWith`, `contains`, `join`). It
REFUSES any token outside that subset, so an edit that widens the expression fails here loudly
instead of being evaluated wrongly.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_CI = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
_EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
_TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<op>&&|\|\||==|!|\(|\)|,)|(?P<name>[A-Za-z_][A-Za-z0-9_.\-*]*))"
)


def _workflow() -> dict[Any, Any]:
    loaded = yaml.safe_load(_CI.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _tokens(*, source: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    source = source.strip()
    pos = 0
    while pos < len(source):
        match = _TOKEN.match(source, pos)
        assert match is not None, f"token outside the evaluated subset at {source[pos:]!r}"
        kind = match.lastgroup
        assert kind is not None
        out.append((kind, match.group(kind)))
        pos = match.end()
    return out


class _Parser:
    def __init__(self, *, tokens: list[tuple[str, str]], context: dict[str, Any]) -> None:
        self._tokens = tokens
        self._at = 0
        self._context = context

    def parse(self) -> Any:
        value = self._or()
        assert self._at == len(self._tokens), f"unparsed tail: {self._tokens[self._at:]!r}"
        return value

    def _peek(self) -> tuple[str, str] | None:
        return self._tokens[self._at] if self._at < len(self._tokens) else None

    def _take(self, *, op: str) -> None:
        assert self._peek() == ("op", op), f"expected {op!r}, found {self._peek()!r}"
        self._at += 1

    def _or(self) -> Any:
        value = self._and()
        while self._peek() == ("op", "||"):
            self._at += 1
            right = self._and()
            value = value or right
        return value

    def _and(self) -> Any:
        value = self._eq()
        while self._peek() == ("op", "&&"):
            self._at += 1
            right = self._eq()
            value = value and right
        return value

    def _eq(self) -> Any:
        value = self._unary()
        while self._peek() == ("op", "=="):
            self._at += 1
            value = value == self._unary()
        return value

    def _unary(self) -> Any:
        if self._peek() == ("op", "!"):
            self._at += 1
            return not self._unary()
        return self._primary()

    def _primary(self) -> Any:
        token = self._peek()
        assert token is not None, "expression ended early"
        self._at += 1
        kind, text = token
        if kind == "str":
            return text[1:-1].replace("''", "'")
        if token == ("op", "("):
            value = self._or()
            self._take(op=")")
            return value
        assert kind == "name", f"unexpected token {token!r}"
        if self._peek() == ("op", "("):
            return self._call(name=text)
        return self._read(path=text)

    def _call(self, *, name: str) -> Any:
        self._take(op="(")
        haystack = self._or()
        self._take(op=",")
        needle = self._or()
        self._take(op=")")
        if name == "join":
            assert isinstance(haystack, list), f"join over a non-array: {haystack!r}"
            return str(needle).join("" if item is None else str(item) for item in haystack)
        text = "" if haystack is None else str(haystack).lower()
        if name == "startsWith":
            return text.startswith(str(needle).lower())
        assert name == "contains", f"function outside the evaluated subset: {name}"
        return str(needle).lower() in text

    def _read(self, *, path: str) -> Any:
        node: Any = self._context
        for part in path.split("."):
            if part == "*":
                node = list(node) if isinstance(node, list) else []
            elif isinstance(node, list):
                node = [item.get(part) if isinstance(item, dict) else None for item in node]
            else:
                node = node.get(part) if isinstance(node, dict) else None
        return node


def _group(*, github: dict[str, Any]) -> str:
    raw = _workflow()["concurrency"]["group"]
    assert isinstance(raw, str)
    context = {"github": github}

    def resolve(match: re.Match[str]) -> str:
        value = _Parser(tokens=_tokens(source=match.group(1)), context=context).parse()
        return "" if value is None else str(value)

    return _EXPR.sub(resolve, raw)


def _push(*, ref: str, message: str, run_id: str, earlier: tuple[str, ...] = ()) -> dict[str, Any]:
    """A push event whose head commit carries ``message``, after the ``earlier`` commits it also pushed."""
    commits = [{"message": text} for text in (*earlier, message)]
    return {
        "workflow": _workflow()["name"],
        "event_name": "push",
        "ref": ref,
        "run_id": run_id,
        "event": {"head_commit": {"message": message}, "commits": commits},
    }


_MASTER = "refs/heads/master"


def test_ordinary_master_pushes_share_one_group_that_never_cancels_the_run_in_progress() -> None:
    first = _group(
        github=_push(
            ref=_MASTER, message="fix: one thing (livespec-dev-tooling-aaaaaa)", run_id="101"
        )
    )
    second = _group(github=_push(ref=_MASTER, message="chore: another thing", run_id="102"))
    third = _group(
        github=_push(ref=_MASTER, message="feat: a third thing\n\nBody text.", run_id="103")
    )
    assert first == second == third == "CI-master-push"
    assert _workflow()["concurrency"]["cancel-in-progress"] is False


def test_a_release_or_expedited_master_push_runs_in_a_group_of_its_own() -> None:
    release = _group(
        github=_push(ref=_MASTER, message="chore(master): release 1.193.0", run_id="201")
    )
    expedited = _group(
        github=_push(
            ref=_MASTER,
            message=(
                "fix: repair the incident path\n\n"
                "Factory-Override: EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-e62ss6\n"
            ),
            run_id="202",
        ),
    )
    expedited_below_head = _group(
        github=_push(
            ref=_MASTER,
            message="test: cover the repaired path",
            run_id="204",
            earlier=(
                "fix: repair the incident path\n\n"
                "Factory-Override: EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-e62ss6\n",
            ),
        ),
    )
    principal_revert = _group(
        github=_push(
            ref=_MASTER,
            message=(
                "Revert complete incident PR #4100\n\n"
                "Incident-Action: act-1\nIncident-Owner: incident-controller\n"
            ),
            run_id="205",
        ),
    )
    ordinary = _group(github=_push(ref=_MASTER, message="fix: ordinary", run_id="203"))
    assert release == "CI-201"
    assert expedited == "CI-202"
    assert expedited_below_head == "CI-204"
    assert principal_revert == "CI-205"
    assert ordinary not in {release, expedited, expedited_below_head, principal_revert}


def test_pull_request_and_incident_scratch_runs_never_join_the_master_group() -> None:
    pull_request = _group(
        github={
            "workflow": _workflow()["name"],
            "event_name": "pull_request",
            "ref": "refs/pull/4010/merge",
            "run_id": "301",
            "event": {"pull_request": {"number": 4010}},
        },
    )
    scratch = _group(
        github=_push(ref="refs/heads/incident-scratch/drill", message="fix: drill", run_id="302")
    )
    assert pull_request == "CI-301"
    assert scratch == "CI-302"
    triggers = _workflow()[True]  # PyYAML reads the bare `on:` key as boolean True.
    assert "merge_group" not in triggers
