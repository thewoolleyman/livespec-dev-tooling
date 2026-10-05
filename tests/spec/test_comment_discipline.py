"""Comment discipline, per `SPECIFICATION/non-functional-requirements.md`.

Two halves of that file's comment rules are asserted here: the `ERA` ban, held
ARMED over the trees it judges, and the form a comment may use to cite the spec
at all.

The comment rules' first sentence ("comments explain the WHY, not the WHAT") is
a judgement a linter cannot make, and the rules know it: the sentence is
followed by the two mechanical halves that CAN be enforced — "The `ERA` ruff
rule bans commented-out code; LLM-author scaffolding artifacts MUST be
deleted before commit." Commented-out code and scaffolding leftovers are
precisely the WHAT-comments a machine can recognise, and `ERA` is the
mechanism they name for them.

Selecting a rule is not the same as arming it, and this repository has
already paid for the difference. `pyproject.toml` records it at the
`per-file-ignores` block: the PreToolUse guard hook was once excluded from
ruff WHOLESALE via `extend-exclude`, "and that exclusion took the `BLE001`
backstop down with it". The exclusion was made for one rule and silently
disarmed every other rule over those files. Nothing failed; ruff kept
reporting a clean tree, over a smaller tree than anyone intended.

So the assertion is not "`ERA` appears in `select`" — that is necessary but
convicts nothing that matters. It is that `ERA` still REACHES every
first-party file: no `extend-exclude` glob swallows one, and no
`per-file-ignores` entry that lists `ERA` matches one. The probe set is the
actual `.py` files of the two declared trees (the package and `tests/`)
rather than a synthetic path, so a subtree exclusion cannot slip past a
probe that happens to sit above it.

The companion `comment_line_anchors` check enforces the other recorded
failure mode — a comment anchored to a LINE NUMBER, which rots silently on
the next edit above it — and is covered by its own paired unit suite; its
membership in `just check` is asserted with every other shipped slug by
`tests.spec.test_definition_of_done_gates`.

The citation-FORM half is the second assertion here, and it is pinned in this
repository because nothing else in this repository's gate path will convict
it. Comments may carry "references to spec sections", and pinned livespec core
bounds how: a reference MAY address the spec FILE, and MUST NOT name a heading
inside it, because a file-level address survives a heading rename and a
heading-level one rots silently. Core enforces that as its static-doctor
`doctor-no-spec-section-citation-in-code` check, which this repository
deliberately does NOT wire into `just check` (see the justfile's decision
note: a gate whose verdict depends on a host-level plugin install, aimed at
core master while `.livespec.jsonc` pins core at a tag, closing a dependency
loop). The accepted residual risk the same note names is that such a finding
sits in tree until the next `/livespec:revise` — and when it does, the revise
wrapper exits 3 with every spec-tree check green, which trains its readers to
ignore the one exit code that would report a REAL ratification failure. It
cost exactly that twice (livespec-dev-tooling-bvbe, then -r2h5js).

So the rule is replicated here, hermetic and repo-local, over the SAME walk
set core scans: this is the local half of the mitigation that note prescribes.
It is repo-WIDE rather than per-module on purpose. `bvbe` pinned two files and
left 59 carrying 102 further occurrences, which is possible because core's
check SHORT-CIRCUITS on the first hit in sorted path order — so each narrow
fix merely renames the next finding, and the revise wrapper stays at 3. Only a
walk-set-wide assertion can report the whole set at once.
"""

from __future__ import annotations

import ast
import fnmatch
import io
import re
import tokenize
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# The rule the section names, and the sub-rule ruff reports it under. Either
# spelling in an ignore list disarms commented-out-code detection.
_ERA = "ERA"
_ERA_SUBRULE = "ERA001"

# The trees whose comments the section governs: the shipped package and the
# suite that mirrors it.
_GOVERNED_TREES = ("livespec_dev_tooling", "tests")

# Vendored and generated trees are legitimately excluded — they are not this
# repository's comments to police.
_UNGOVERNED_PARTS = ("_vendor", "__pycache__")

# The marker pinned-core's citation check forbids in source prose: a section
# sign directly followed by a double quote, i.e. the opening of a heading-level
# spec citation. It is held here as a STRING LITERAL and is never written into
# a comment or a docstring anywhere in this file, because this file is itself
# inside the walk set and the rule ignores the marker only outside prose.
_SECTION_SIGN_CITATION = '§"'

# Core's own exclusions, copied so this replica reads the same tree it does:
# frozen history, vendored third-party code, byte caches, the git db, the
# project virtualenv, node deps, and a consuming repo's vendored core checkout.
_UNSCANNED_SEGMENTS = frozenset(
    {
        ".git",
        ".livespec-core",
        ".venv",
        "__pycache__",
        "_vendor",
        "archive",
        "node_modules",
    },
)

# The spec tree is the domain of core's `no_cross_spec_reference` check, not of
# its code-side citation rule, so the walk stops at this boundary. Core also
# scans `crates/**/src/*.rs` and `skills/<name>/SKILL.md`; this repository ships
# neither, so a `.py` walk covers every walk-set member it actually has.
_SPEC_TREE = _REPO_ROOT / "SPECIFICATION"

_TOML_HEADER = re.compile(r"^\[(?P<name>[^\]]+)\]$")
_ARRAY = re.compile(r"^(?P<key>[a-z_-]+) = \[(?P<body>[^\]]*)\]$", re.MULTILINE)
_QUOTED = re.compile(r'"([^"]+)"')
_PER_FILE_IGNORE = re.compile(r'^"?(?P<glob>[^"\s=]+)"? = \[(?P<rules>[^\]]*)\]$', re.MULTILINE)


def _toml_sections() -> dict[str, str]:
    """Each `[section]` of `pyproject.toml` mapped to its raw body text.

    Text rather than a parse: stdlib `tomllib` lands in 3.11 and this
    repository's floor is 3.10.
    """
    bodies: dict[str, list[str]] = {}
    current = ""
    for line in _PYPROJECT.read_text(encoding="utf-8").splitlines():
        header = _TOML_HEADER.match(line)
        current = header.group("name") if header else current
        bodies.setdefault(current, []).append(line)
    return {name: "\n".join(lines) for name, lines in bodies.items()}


def _array_values(*, section: str, key: str) -> list[str]:
    """The quoted elements of one single-line array key in one section."""
    matched = [
        match for match in _ARRAY.finditer(_toml_sections()[section]) if match.group("key") == key
    ]
    assert len(matched) == 1, f"`[{section}]` must declare exactly one `{key}` array"
    return _QUOTED.findall(matched[0].group("body"))


def _governed_files() -> list[str]:
    """Every first-party `.py` file whose comments the section governs."""
    return sorted(
        str(path.relative_to(_REPO_ROOT))
        for tree in _GOVERNED_TREES
        for path in (_REPO_ROOT / tree).rglob("*.py")
        if not any(part in _UNGOVERNED_PARTS for part in path.relative_to(_REPO_ROOT).parts)
    )


def _disarming_globs() -> list[str]:
    """Every `per-file-ignores` glob whose rule list disarms the `ERA` ban."""
    body = _toml_sections()["tool.ruff.lint.per-file-ignores"]
    return [
        matched.group("glob")
        for matched in _PER_FILE_IGNORE.finditer(body)
        if {_ERA, _ERA_SUBRULE} & set(_QUOTED.findall(matched.group("rules")))
    ]


def _prose_spans(*, source: str) -> list[tuple[int, str]]:
    """Return every comment and docstring in `source` as `(1-indexed line, text)`.

    Mirrors pinned-core's per-file walk: `tokenize` surfaces COMMENT tokens and
    `ast` surfaces module, class and function docstrings. The marker anywhere
    else is a string literal — fixture content, a regex, a diagnostic message,
    or this file's own `_SECTION_SIGN_CITATION` — and is not prose the rule
    reads.
    """
    spans = [
        (token.start[0], token.string)
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    ]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            docstring = ast.get_docstring(node, clean=False)
            if docstring is not None:
                spans.append((node.body[0].lineno, docstring))
    return spans


def _scanned_sources() -> list[Path]:
    """Every `.py` file pinned-core's citation check reads prose from."""
    return sorted(
        path
        for path in _REPO_ROOT.rglob("*.py")
        if not any(part in _UNSCANNED_SEGMENTS for part in path.parts)
        and _SPEC_TREE not in path.parents
    )


def test_no_source_prose_cites_a_spec_heading_via_the_section_sign_form() -> None:
    """No comment or docstring in the walk set addresses a spec HEADING."""
    scanned = _scanned_sources()
    assert scanned, "the walk set must contain files for the citation rule to reach"

    offenders = sorted(
        f"{path.relative_to(_REPO_ROOT)}:{line}"
        for path in scanned
        for line, text in _prose_spans(source=path.read_text(encoding="utf-8"))
        if _SECTION_SIGN_CITATION in text
    )

    assert not offenders, (
        f"a comment or docstring addresses a spec heading via the section-sign form, which "
        f"pinned livespec core forbids in source prose: a heading-level address rots silently "
        f"when the heading is renamed, so name the spec FILE (and, cross-repo, its owning "
        f"repository) and carry the heading's subject as prose instead. Core's check "
        f"short-circuits on the first hit in sorted path order, so fixing one of these only "
        f"renames the next finding and leaves `/livespec:revise` exiting 3; "
        f"offenders={offenders}"
    )


def test_the_commented_out_code_ban_is_selected() -> None:
    """`ERA` — the rule the section names — is in the lint selection."""
    lint_select = _toml_sections()["tool.ruff.lint"]
    assert f'"{_ERA}"' in lint_select, (
        f"the section names `{_ERA}` as the mechanism that bans commented-out code and "
        f"LLM scaffolding leftovers; unselected, it reports nothing and the ban exists "
        f"only as prose"
    )


def test_no_exclusion_disarms_the_ban_over_a_governed_file() -> None:
    """`ERA` reaches every first-party `.py` — no wholesale exclusion, no rule carve-out."""
    governed = _governed_files()
    assert governed, "the governed trees must contain files for the ban to reach"

    excluded = _array_values(section="tool.ruff", key="extend-exclude")
    swallowed = sorted(
        f"{path} (by {glob})"
        for glob in excluded
        for path in governed
        if fnmatch.fnmatch(path, glob)
    )
    assert not swallowed, (
        f"a ruff `extend-exclude` glob removes a governed file from EVERY rule at once, "
        f"not just the one it was added for — this repository has already lost the "
        f"`BLE001` backstop that way, with nothing failing and ruff reporting a clean "
        f"tree over a smaller tree than intended; swallowed={swallowed}"
    )

    carved = sorted(
        f"{path} (by {glob})"
        for glob in _disarming_globs()
        for path in governed
        if fnmatch.fnmatch(path, glob)
    )
    assert not carved, (
        f"no `per-file-ignores` entry may disarm `{_ERA}` over a governed file: "
        f"commented-out code and LLM-author scaffolding are exactly the WHAT-comments "
        f"the section deletes before commit, and a per-path carve-out re-admits them "
        f"where nobody is reading for them; carved={carved}"
    )
