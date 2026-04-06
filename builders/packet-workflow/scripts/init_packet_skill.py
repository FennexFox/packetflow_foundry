#!/usr/bin/env python3
"""Compatibility shim for the moved packet-workflow builder entrypoint."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def retained_entrypoint() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "retained-skills"
        / "scripts"
        / "init_packet_skill.py"
    )


def load_retained_module() -> ModuleType:
    script_path = retained_entrypoint()
    spec = importlib.util.spec_from_file_location(
        "packet_workflow_retained_init_packet_skill",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load retained entrypoint: {script_path}")

    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(script_path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(script_path.parent))
        except ValueError:
            pass
    return module


_RETAINED_MODULE = load_retained_module()
main = _RETAINED_MODULE.main


def __getattr__(name: str) -> object:
    return getattr(_RETAINED_MODULE, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_RETAINED_MODULE)))


if __name__ == "__main__":
    raise SystemExit(main())
