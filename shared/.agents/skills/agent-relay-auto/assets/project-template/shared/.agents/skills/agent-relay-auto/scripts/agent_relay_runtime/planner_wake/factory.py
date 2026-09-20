"""Build an exact Planner wake adapter without cross-tool fallback."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Callable, Mapping


class WakeAdapterUnavailable(ValueError):
    pass


def _adapter(module_name: str, class_name: str):
    path = Path(__file__).with_name(f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(f"planner_wake_factory_{module_name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return getattr(module, class_name)


def create_planner_wake_factory(
    builders: Mapping[str, Callable[[], object]] | None = None,
) -> Callable[[str], object]:
    configured = dict(builders) if builders is not None else {
        "codex": _adapter("codex", "CodexPlannerWakeAdapter"),
        "opencode": _adapter("opencode", "OpenCodePlannerWakeAdapter"),
        "claude-code": _adapter("claude_code", "ClaudeCodePlannerWakeAdapter"),
        "deepseek-harness": _adapter("deepseek_harness", "DeepSeekHarnessPlannerWakeAdapter"),
    }

    def build(tool: str) -> object:
        builder = configured.get(tool)
        if builder is None:
            raise WakeAdapterUnavailable(f"Planner wake adapter is unavailable for {tool}")
        return builder()

    return build
