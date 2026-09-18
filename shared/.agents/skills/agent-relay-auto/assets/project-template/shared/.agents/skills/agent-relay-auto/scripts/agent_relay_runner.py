#!/usr/bin/env python3
"""Console entry point; service installation is handled by setup_runner.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent
sys.path.insert(0, str(RUNTIME))

from agent_relay_runtime.registry import ProjectRegistry  # noqa: E402
from agent_relay_runtime.runner import RelayRunner  # noqa: E402
from agent_relay_runtime.adapters.factory import (  # noqa: E402
    AdapterConfigurationError,
    create_adapter_factory,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="~/.config/agent-relay-auto/projects.json")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args(argv)
    registry = ProjectRegistry(Path(args.registry).expanduser())
    runner = RelayRunner(registry, create_adapter_factory())
    try:
        if args.once:
            decisions = runner.run_once()
            print(json.dumps([decision.__dict__ for decision in decisions], ensure_ascii=False))
            return 0
        runner.serve(poll_interval_seconds=args.poll_interval)
        return 0
    except AdapterConfigurationError as error:
        print(f"Agent Relay Auto configuration error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
