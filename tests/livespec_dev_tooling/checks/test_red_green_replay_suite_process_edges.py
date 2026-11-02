"""Edge coverage for suite-green subprocess output draining."""

from __future__ import annotations

import codecs
import importlib.util
import os
import sys
from pathlib import Path

__all__: list[str] = []

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "_red_green_replay_suite_process.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("_rgr_suite_process_edges", str(_MODULE_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_closed_pipe_retains_a_decoder_final_partial_character() -> None:
    """A final partial UTF-8 sequence is retained after the process exits."""
    mod = _load()
    reader, writer = os.pipe()
    try:
        _ = os.write(writer, b"\xc3")
    finally:
        os.close(writer)
    with os.fdopen(reader, "rb") as stream:
        progress = mod.SuiteProgress(clock=lambda: 0.0)
        mod._drain_after_exit(  # noqa: SLF001
            stream=stream,
            decoder=codecs.getincrementaldecoder("utf-8")(errors="replace"),
            progress=progress,
        )
    assert progress.output == "\ufffd"
