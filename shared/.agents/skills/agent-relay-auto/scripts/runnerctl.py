#!/usr/bin/env python3
"""Safe management command surface for the Runner service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def command_status(repo: Path, dry_run: bool = False) -> dict[str, object]:
    if dry_run:
        return {"status": "dry-run", "actions": [f"inspect runner for {Path(repo).resolve()}"]}
    return {"status": "unknown", "repo": str(Path(repo).resolve())}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("status", "start", "stop", "restart", "logs"))
    parser.add_argument("--repo", default=".")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(command_status(Path(args.repo), args.dry_run), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
