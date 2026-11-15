"""Shape tests for the package-manager store and cache locations in the Fabro layers.

The sandbox working directory ``/workspace`` is the pod's only volume, a
hostPath mount, while ``HOME`` (``/root``) sits on the container filesystem.
pnpm hard-links from its store, so when the default store is on another device
it falls back to ``<mount root>/.pnpm-store``, which is ``/workspace/.pnpm-store``
and gets swept into a commit. Every layer therefore names its stores and caches
explicitly, outside ``/workspace``.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAYERS_ROOT = _REPO_ROOT / "docker" / "fabro-sandbox"
_WORKSPACE = PurePosixPath("/workspace")
_STORE_VARIABLES = (
    "npm_config_store_dir",
    "npm_config_cache",
    "BUN_INSTALL_CACHE_DIR",
    "UV_CACHE_DIR",
    "PIP_CACHE_DIR",
)


def _env_values(*, layer: str) -> dict[str, str]:
    """Return the ``ENV`` key/value pairs one layer's Dockerfile declares."""
    text = (_LAYERS_ROOT / layer / "Dockerfile").read_text(encoding="utf-8")
    values: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("ENV "):
            for pair in line.removeprefix("ENV ").split():
                key, _, value = pair.partition("=")
                values[key] = value
    return values


def test_base_layer_names_every_store_and_cache_outside_the_workspace() -> None:
    """Each package-manager store/cache is an absolute path that is not under /workspace."""
    values = _env_values(layer="base")

    for variable in _STORE_VARIABLES:
        assert variable in values, f"base layer does not set {variable}"
        location = PurePosixPath(values[variable])
        assert location.is_absolute(), f"{variable}={location} is not absolute"
        assert location != _WORKSPACE
        assert _WORKSPACE not in location.parents, f"{variable}={location} is under /workspace"


def test_base_layer_copies_into_the_pnpm_store_instead_of_hard_linking() -> None:
    """A store on another device than the checkout cannot be hard-linked from."""
    values = _env_values(layer="base")

    assert values.get("npm_config_package_import_method") == "copy"


def test_no_stacked_layer_points_a_store_back_into_the_workspace() -> None:
    """A toolchain layer may restate a location, but never move it under /workspace."""
    for layer in ("base", "python", "python-rust", "python-rust-fuzz", "agent"):
        stated = [
            PurePosixPath(value)
            for variable, value in _env_values(layer=layer).items()
            if variable in _STORE_VARIABLES
        ]
        assert all(_WORKSPACE not in (path, *path.parents) for path in stated), layer


def test_base_build_probes_the_locations_it_publishes() -> None:
    """The image build fails when a published location is missing or under /workspace."""
    text = (_LAYERS_ROOT / "base" / "Dockerfile").read_text(encoding="utf-8")

    for variable in _STORE_VARIABLES:
        assert f"${{{variable}:?" in text, f"base build does not probe {variable}"
    assert "/workspace|/workspace/*" in text
