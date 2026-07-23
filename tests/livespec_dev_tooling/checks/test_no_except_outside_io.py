"""Outside-in test for `livespec_dev_tooling/checks/no_except_outside_io.py` — catch breadth + position.

Per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Supervisor discipline": narrow at the seam; broad only at
the boundary; at most one boundary per process. A NARROW
handler names specific exception types and is permitted
anywhere. A BROAD handler (`except Exception`, `except
BaseException`, bare `except:`) is permitted ONLY as a direct
child of `main()` in a declared supervisor entry file, and
only when it carries one of the closed set of sanctioned
markers.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_NO_EXCEPT_OUTSIDE_IO = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_except_outside_io.py"

_SUPERVISOR_MARKER = "# noqa: BLE001 — sole supervisor bug-catcher: log traceback, exit 1"
_FOREIGN_CODE_MARKER = (
    "# noqa: BLE001 — foreign-code isolation: "
    "custom doctor check crash captured as SyntaxError, reported"
)


def _run(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_NO_EXCEPT_OUTSIDE_IO)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _write_module(*, tmp_path: Path, rel: str, body: str) -> None:
    """Materialize a fixture module under livespec-core's default layout."""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n\n\n" + body,
        encoding="utf-8",
    )


def test_no_except_outside_io_accepts_narrow_catch_in_pure_layer(*, tmp_path: Path) -> None:
    """A NARROW catch in `livespec/parse/foo.py` passes (exit 0).

    Narrow-at-the-seam is how a pure layer handles an expected
    failure; naming the exception type is the whole point. The
    check polices breadth and position, never the mere presence
    of a `try` statement.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/parse/foo.py",
        body=(
            "def parse_thing() -> None:\n"
            "    try:\n"
            "        x = 1\n"
            "    except ValueError:\n"
            "        x = 2\n"
            "    _ = x\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_except_outside_io should accept a narrow catch in parse/ with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_broad_catch_in_pure_layer(*, tmp_path: Path) -> None:
    """A BROAD catch in `livespec/parse/foo.py` fails the check.

    No position outside a declared supervisor `main()` can host
    a broad catch, so a pure layer is always an offense. The
    check must surface the offending file plus line number.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/parse/foo.py",
        body=(
            "def parse_thing() -> None:\n"
            "    try:\n"
            "        x = 1\n"
            "    except Exception:\n"
            "        x = 2\n"
            "    _ = x\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject a broad catch in parse/; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/livespec/parse/foo.py"
    assert expected_path in combined, (
        f"no_except_outside_io diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_bare_except_in_pure_layer(*, tmp_path: Path) -> None:
    """A bare `except:` is broad and fails outside a marked boundary."""
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/parse/foo.py",
        body=(
            "def parse_thing() -> None:\n"
            "    try:\n"
            "        x = 1\n"
            "    except:\n"
            "        x = 2\n"
            "    _ = x\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject a bare except in parse/; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_accepts_broad_catch_in_io_layer(*, tmp_path: Path) -> None:
    """A broad catch inside `livespec/io/fs.py` passes (exit 0).

    Files under `io_trees` are wholesale exempt — io/ is the
    side-effect boundary that lifts exceptions onto the IOResult
    railway.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/io/fs.py",
        body=(
            "def read_text() -> None:\n"
            "    try:\n"
            "        x = 1\n"
            "    except Exception:\n"
            "        x = 2\n"
            "    _ = x\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_except_outside_io should accept a broad catch in io/ with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_accepts_marked_supervisor_bug_catcher(*, tmp_path: Path) -> None:
    """A MARKED broad catch in `commands/seed.py::main()` passes (exit 0).

    The sole-boundary exemption: a direct child of `main()` in a
    supervisor entry file, carrying a sanctioned marker.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            f"    except Exception:  {_SUPERVISOR_MARKER}\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_except_outside_io should accept a marked supervisor bug-catcher; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_accepts_marked_boundary_in_entry_file(*, tmp_path: Path) -> None:
    """A MARKED broad catch in `doctor/run_static.py::main()` passes (exit 0).

    The second route into the boundary exemption: a file named
    directly in `supervisor_entry_files` rather than one living
    under a `commands_trees` tree.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/doctor/run_static.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            f"    except Exception:  {_SUPERVISOR_MARKER}\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_except_outside_io should accept a marked boundary in a supervisor entry file; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_unmarked_supervisor_bug_catcher(*, tmp_path: Path) -> None:
    """An UNMARKED broad catch in `commands/seed.py::main()` fails the check.

    Position alone does not legalize a broad catch: the boundary
    must declare which flavor's contract it discharges.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            "    except Exception:\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject an unmarked supervisor bug-catcher; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_freeform_marker_on_boundary(*, tmp_path: Path) -> None:
    """A broad catch at a sanctioned position with a FREE-FORM reason fails.

    The marker set is closed. Any other reason wording — however
    plausible it reads — marks a violation rather than an escape.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            "    except Exception:  # noqa: BLE001 — fail-open by contract, never wedge\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject a free-form marker on a boundary catch; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_marker_with_trailing_junk(*, tmp_path: Path) -> None:
    """A sanctioned wording with APPENDED text fails: the set is exact.

    The closed set admits no suffix. Text appended after a sanctioned
    wording can invert its meaning wholesale, so a substring match
    would let `… exit 1 -- but actually swallows silently` legalize
    the very swallow the wording denies.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            f"    except Exception:  {_SUPERVISOR_MARKER} -- but actually swallows silently\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject a sanctioned marker with trailing junk; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_marker_with_leading_junk(*, tmp_path: Path) -> None:
    """A sanctioned wording EMBEDDED in a larger comment fails.

    A comment that merely CONTAINS the wording is not the directive
    plus that wording. Ruff would not read it as a `noqa` directive
    at all, so honoring it here would legalize a broad catch on the
    strength of prose alone.
    """
    embedded = _SUPERVISOR_MARKER.removeprefix("# ")
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            f"    except Exception:  # see hook contract; {embedded}\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject a sanctioned wording embedded in prose; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_accepts_filled_foreign_code_marker(*, tmp_path: Path) -> None:
    """A foreign-code marker with BOTH template slots filled passes.

    The fifth sanctioned wording is a template: `<surface>` and
    `<ErrorType>` are filled per site and the wording ends at the
    literal `, reported`. A filled instance at a sanctioned position
    is conforming.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            f"    except Exception:  {_FOREIGN_CODE_MARKER}\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_except_outside_io should accept a filled foreign-code isolation marker; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_foreign_code_marker_with_trailing_junk(
    *, tmp_path: Path
) -> None:
    """A foreign-code marker with text after `, reported` fails.

    The template's tail is literal: `, reported` ends the wording.
    Anything appended dilutes the reported-upward claim the marker
    exists to pin down.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            f"    except Exception:  {_FOREIGN_CODE_MARKER} and retried\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject a foreign-code marker with trailing junk; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_accepts_foreign_code_marker_with_dotted_error_type(
    *, tmp_path: Path
) -> None:
    """A foreign-code marker whose `<ErrorType>` is a dotted identifier passes.

    Exception types are named by (possibly dotted) identifiers —
    `json.JSONDecodeError` is as legitimate a captured type as a
    bare builtin name.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            "    except Exception:  # noqa: BLE001 — foreign-code isolation:"
            " template render crash captured as json.JSONDecodeError, reported\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_except_outside_io should accept a dotted-identifier ErrorType; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_foreign_code_marker_with_unfilled_placeholders(
    *, tmp_path: Path
) -> None:
    """A foreign-code marker shipping the LITERAL template placeholders fails.

    The spec writes the template with `<surface>` / `<ErrorType>`
    placeholders to be filled per site. A site that ships them
    verbatim has filled nothing, names no surface and no captured
    type, and so asserts nothing.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            "    except Exception:  # noqa: BLE001 — foreign-code isolation:"
            " <surface> crash captured as <ErrorType>, reported\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject literal unfilled template placeholders; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_foreign_code_marker_with_prose_error_type(
    *, tmp_path: Path
) -> None:
    """A foreign-code marker whose `<ErrorType>` slot holds prose fails.

    `<ErrorType>` names the captured exception type — an identifier,
    optionally dotted — not free prose. Prose there can dilute or
    invert the captured-and-reported claim the marker exists to pin
    down (e.g. `… captured as SyntaxError but swallowed silently`).
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            "    except Exception:  # noqa: BLE001 — foreign-code isolation:"
            " custom doctor check crash captured as SyntaxError but swallowed"
            " silently, reported\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject prose in the ErrorType slot; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_foreign_code_marker_with_empty_segments(
    *, tmp_path: Path
) -> None:
    """A foreign-code marker with EMPTY template slots fails.

    `<surface>` and `<ErrorType>` are per-site facts; an instance
    that fills neither names no surface and no captured type, so it
    asserts nothing and conforms to nothing.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            "    except Exception:  # noqa: BLE001 — foreign-code isolation:"
            "  crash captured as , reported\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject a foreign-code marker with empty segments; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_sanctioned_marker_at_wrong_position(
    *, tmp_path: Path
) -> None:
    """A sanctioned marker on a broad catch in a HELPER still fails.

    The marker is not a portable licence: it legalizes a broad
    catch only where the position rule already allows one. A
    helper of a supervisor entry file is not that position.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def _helper() -> None:\n"
            "    try:\n"
            "        x = 1\n"
            f"    except Exception:  {_SUPERVISOR_MARKER}\n"
            "        x = 2\n"
            "    _ = x\n"
            "\n"
            "\n"
            "def main() -> int:\n"
            "    _helper()\n"
            "    return 0\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject a sanctioned marker in a helper; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_accepts_narrow_catch_in_helper(*, tmp_path: Path) -> None:
    """A narrow catch in a helper of a supervisor entry file passes.

    Position rules bind broad catches only; a narrow catch needs
    no exemption anywhere.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def _helper() -> None:\n"
            "    try:\n"
            "        x = 1\n"
            "    except ValueError:\n"
            "        x = 2\n"
            "    _ = x\n"
            "\n"
            "\n"
            "def main() -> int:\n"
            "    _helper()\n"
            "    return 0\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_except_outside_io should accept a narrow catch in a helper; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_marker_on_handler_body(*, tmp_path: Path) -> None:
    """A sanctioned marker on the handler BODY does not legalize the catch.

    Only the `except …:` clause itself carries the declaration;
    a marker one line lower is inert, matching where ruff would
    require the suppression to sit.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            "    except Exception:\n"
            f"        return 1  {_SUPERVISOR_MARKER}\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject a marker sitting on the handler body; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_dotted_broad_catch(*, tmp_path: Path) -> None:
    """`except builtins.Exception` is broad despite its dotted spelling.

    Reading the operand's whole rendering would classify the dotted form
    as a narrow seam catch. Ruff still treats it as broad, so its
    `BLE001` suppression counts as USED and `RUF100` stays silent —
    meaning both halves of the enforcement split would fall together and
    any marker wording at all would pass unread.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/parse/foo.py",
        body=(
            "import builtins\n"
            "\n"
            "\n"
            "def parse_thing() -> int:\n"
            "    try:\n"
            "        return 1\n"
            "    except builtins.Exception:  # noqa: BLE001 — lifts onto the IO rail\n"
            "        return 2\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject a dotted broad catch; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_aliased_broad_catch(*, tmp_path: Path) -> None:
    """A broad builtin rebound by an aliased import is still broad."""
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/parse/foo.py",
        body=(
            "from builtins import Exception as Broad\n"
            "\n"
            "\n"
            "def parse_thing() -> int:\n"
            "    try:\n"
            "        return 1\n"
            "    except Broad:  # noqa: BLE001 — lifts onto the IO rail\n"
            "        return 2\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject an aliased broad catch; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_marker_on_body_comment(*, tmp_path: Path) -> None:
    """A marker on a COMMENT line inside the handler body does not legalize it.

    A body comment is not a statement, so a span ending at the first body
    STATEMENT still contains it. The span must end at the clause's
    closing colon instead.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            "    except Exception:\n"
            f"        {_SUPERVISOR_MARKER}\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject a marker on a handler-body comment; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_marker_in_string_literal(*, tmp_path: Path) -> None:
    """Marker text inside a STRING LITERAL on the clause line is inert.

    Only a real comment token declares a boundary contract; scanning raw
    source text cannot tell the two apart.
    """
    marker_text = _SUPERVISOR_MARKER.split("# noqa: BLE001 ", maxsplit=1)[1]
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            f'    except Exception: reason = "{marker_text}"; return 1\n'
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject marker text inside a string literal; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_accepts_narrow_dotted_catch(*, tmp_path: Path) -> None:
    """Resolving the operand's tail must not misread a narrow dotted catch.

    `json.JSONDecodeError` shares the dotted SHAPE with the broad form
    but names a specific exception, so it stays a permitted seam catch.
    """
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/parse/foo.py",
        body=(
            "import json\n"
            "\n"
            "\n"
            "def parse_thing() -> int:\n"
            "    try:\n"
            "        return 1\n"
            "    except json.JSONDecodeError:\n"
            "        return 2\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_except_outside_io should accept a narrow dotted catch; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_rejects_broad_member_of_catch_tuple(*, tmp_path: Path) -> None:
    """`except (ValueError, Exception)` is broad — the tuple does not narrow it."""
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/parse/foo.py",
        body=(
            "def parse_thing() -> None:\n"
            "    try:\n"
            "        x = 1\n"
            "    except (ValueError, Exception):\n"
            "        x = 2\n"
            "    _ = x\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io should reject a tuple containing Exception; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_accepts_multiline_clause_marker(*, tmp_path: Path) -> None:
    """A marker on the closing line of a MULTI-LINE `except` clause is honored."""
    _write_module(
        tmp_path=tmp_path,
        rel=".claude-plugin/scripts/livespec/commands/seed.py",
        body=(
            "def main() -> int:\n"
            "    try:\n"
            "        return 0\n"
            "    except (\n"
            "        Exception\n"
            f"    ):  {_SUPERVISOR_MARKER}\n"
            "        return 1\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_except_outside_io should honor a marker on a multi-line except clause; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_runs_when_io_trees_unset(*, tmp_path: Path) -> None:
    """With `io_trees` unset the check RUNS rather than no-opping.

    A flat-layout consumer declares `source_trees` and no
    `io_trees`. Nothing is wholesale exempt, so a broad catch in
    the source tree is still an offense — the check must not
    short-circuit to exit 0 on the absent role key.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
        encoding="utf-8",
    )
    _write_module(
        tmp_path=tmp_path,
        rel="pkg/thing.py",
        body=(
            "def do_thing() -> None:\n"
            "    try:\n"
            "        x = 1\n"
            "    except Exception:\n"
            "        x = 2\n"
            "    _ = x\n"
        ),
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_except_outside_io must inspect the source tree when io_trees is unset; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "pkg/thing.py" in combined, (
        f"no_except_outside_io diagnostic does not surface `pkg/thing.py`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_reports_inspected_file_count(*, tmp_path: Path) -> None:
    """A passing run reports how many files it inspected.

    An inspected count of zero is otherwise indistinguishable
    from a clean pass, so the count is emitted on every run.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["pkg"]\n',
        encoding="utf-8",
    )
    _write_module(
        tmp_path=tmp_path,
        rel="pkg/thing.py",
        body="def do_thing() -> None:\n    return None\n",
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_except_outside_io should pass a catch-free source tree; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert '"files_inspected": 1' in combined, (
        f"no_except_outside_io should report the inspected file count; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_announces_absent_source_trees(*, tmp_path: Path) -> None:
    """An unset `source_trees` is announced, never silently walked as zero files.

    A zero-iteration walk exits 0 and reads exactly like a pass,
    so the absent role key is named explicitly in the log.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\ntarget_dirs = ["pkg"]\n',
        encoding="utf-8",
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_except_outside_io should exit 0 when source_trees is unset; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "source_trees" in combined, (
        f"no_except_outside_io should name the absent `source_trees` role key; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_accepts_empty_tree(*, tmp_path: Path) -> None:
    """An empty repo cwd passes the check (exit 0)."""
    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_except_outside_io should accept empty tree with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_except_outside_io_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "no_except_outside_io_for_import_test",
        str(_NO_EXCEPT_OUTSIDE_IO),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"
