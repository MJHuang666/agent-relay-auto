from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime"


def load_runtime_module(name: str, relative_path: str | None = None):
    path = (RUNTIME / (relative_path or f"{name}.py")).resolve()
    spec = importlib.util.spec_from_file_location(f"agent_relay_runtime_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load runtime module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
