# livespec-dev-tooling — constraints

This file enumerates the architecture-level constraints the library MUST satisfy. Each constraint is an invariant — changing a constraint MUST flow through the propose-change loop, and every downstream rule depending on it MUST be re-evaluated.

## Runtime

The library MUST target Python 3.10 or later, matching livespec's floor per `livespec/SPECIFICATION/non-functional-requirements.md` §"Toolchain pins". A check module MAY use Python 3.10 syntactic features (structural pattern matching, `X | Y` union types in annotations, `dataclass(kw_only=True)`); it MUST NOT use any feature introduced after 3.10 unless the introducing release is explicitly added to the floor via a propose-change.

## Dependencies

The library MUST declare NO runtime dependencies (no `[project].dependencies` entries) in `pyproject.toml`. Every check shells out to project-local tools via `subprocess.run` with fixed argv lists. The current tool set is `ruff`, `pyright`, `pytest`, and `git`; the broader permitted envelope per §"No network I/O" additionally includes `mise`. Tool versions are pinned by each consuming repo's own `.mise.toml` and `[dependency-groups].dev`, not by this library.

Dev dependencies under `[dependency-groups].dev` MUST mirror livespec's pins exactly per `non-functional-requirements.md` §"Toolchain pins"; drift is a propose-change-worthy event.

## No network I/O

No check module under `livespec_dev_tooling/checks/` MAY perform network I/O. Reading the local filesystem and invoking project-local subprocesses (git, ruff, pyright, pytest, mise) is permitted; reaching out to a remote HTTP/HTTPS/SSH endpoint, opening a socket, or invoking a tool that does any of the above is forbidden. The constraint exists so that every check is deterministic against the consuming repo's working tree alone, regardless of network availability.

Reusable workflows under `.github/workflows/` and composite Actions under `.github/actions/` MAY perform network I/O. The cross-repo coordination automation surface (per `contracts.md` §"Cross-repo coordination automation surface") depends on `gh api` invocations for sibling discovery, repository dispatch, and bump-PR creation. The no-network-I/O constraint is scoped specifically to Python check modules because their determinism guarantee is load-bearing for the consumer's local `just check` and CI gates; workflow-level network I/O runs in GitHub-Actions-managed environments where network availability is itself part of the runtime contract.

## Semver discipline

The canonical semver-stable surface enumeration, the MAJOR/MINOR/PATCH bump rules, and the Conventional Commits → semver mapping live in `contracts.md` §"Semver discipline", the location mandated by `livespec/SPECIFICATION/non-functional-requirements.md` §"Shared code sync — livespec-dev-tooling". The constraint-level invariant is: NO breaking change to any enumerated surface element may land outside a MAJOR version bump.

## CLI shape

Every check MUST follow the wrapper-shape contract codified in `contracts.md` §"CLI surface": zero positional args by default, `--help` / `-h` exits `0` with stdout usage, structured findings on stderr for non-zero exits. Checks that need configuration MUST read from `pyproject.toml`'s `[tool.livespec_dev_tooling]` block per `contracts.md` §"Consumer configuration schema"; configuration MUST NOT flow through positional argv.

## Self-application

The library MUST apply its own checks to itself. Specifically, `just check` in this repo MUST run every shared check this library ships, against this repo's own source tree. Self-application is the dogfood loop that guarantees the shared checks are usable in practice — a check that the library cannot apply to itself is a check that no consumer can apply either.

Self-application is bootstrap-ordered: at library-bootstrap time, `just check` runs only the tool-backed subset (ruff, pyright, pytest); structural checks come online as each migrates from livespec-core.

## CI matrix shape

CI workflows shipped by this library MUST mirror the per-target matrix shape with zero-`.py` subsetting on `pull_request` events and unconditional full-aggregate on `master` and `merge_group` events. The constraint is consumer-observable: any reusable workflow this library ships expects matrix consumers to see the same per-event shape on their own CI status checks. Deviating from the shape on a release would break consumers' branch-protection wiring that names individual matrix entries as required checks.

Under the fleet's current hosted-only posture, this repository's merge-gating CI and the reusable check workflows execute on GitHub-hosted runners and MUST NOT require the shared factory host's self-hosted labels. The matrix and required-check semantics are unchanged; only the execution capacity moves off the factory host.
