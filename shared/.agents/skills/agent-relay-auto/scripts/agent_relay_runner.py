#!/usr/bin/env python3
"""Console entry point; service installation is handled by setup_runner.py."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent
sys.path.insert(0, str(RUNTIME))

from agent_relay_runtime.registry import ProjectRegistry  # noqa: E402
from agent_relay_runtime.runner import RelayRunner  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="~/.config/agent-relay-auto/projects.json")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    registry = ProjectRegistry(Path(args.registry).expanduser())
    if args.once:
        RelayRunner(registry, lambda repo: None).run_once()
        return 0
    parser.error("a concrete adapter factory is required for service mode")


if __name__ == "__main__":
    raise SystemExit(main())
