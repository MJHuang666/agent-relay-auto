#!/usr/bin/env python3
import argparse
import subprocess
import sys
import time
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--sleep", type=float, default=0)
parser.add_argument("--exit-code", type=int, default=0)
parser.add_argument("--output-bytes", type=int, default=0)
parser.add_argument("--repo")
parser.add_argument("--task")
parser.add_argument("--role", choices=("implementer", "reviewer"))
parser.add_argument("--participant-id")
parser.add_argument("--run-id")
args = parser.parse_args()
print("fake-agent-start", flush=True)
if args.output_bytes:
    print("x" * args.output_bytes, flush=True)
time.sleep(args.sleep)
print("fake-agent-finish", flush=True)
if args.role:
    repo = Path(args.repo).resolve()
    task = repo / "docs/agent/tasks" / args.task
    state_text = (task / "STATE.md").read_text(encoding="utf-8")
    revision = int(next(line.split(":", 1)[1] for line in state_text.splitlines() if line.startswith("revision:")))
    relay = repo / ".agents/skills/agent-relay-auto/scripts/relay_state.py"
    if not relay.is_file():
        relay = Path(__file__).resolve().parents[2] / "shared/.agents/skills/agent-relay-auto/scripts/relay_state.py"
    if args.role == "implementer":
        execution = task / "execution.md"
        execution.write_text("# Execution\n\ndelivery_id: delivery-1\n\nTests passed\n", encoding="utf-8")
        progress = task / "progress-implementer.md"
        progress.write_text("implementation completed\n", encoding="utf-8")
        command = [
            sys.executable, str(relay), "--repo", str(repo), "implementation-done",
            "--task", args.task, "--expected-revision", str(revision),
            "--participant-id", args.participant_id, "--run-id", args.run_id,
            "--execution", str(execution), "--delivery-ref", "execution.md#delivery-1",
            "--progress", str(progress),
        ]
    else:
        review = task / "review.md"
        review.write_text("# Review\n\nPASS with test evidence\n", encoding="utf-8")
        command = [
            sys.executable, str(relay), "--repo", str(repo), "verdict",
            "--task", args.task, "--expected-revision", str(revision),
            "--participant-id", args.participant_id, "--run-id", args.run_id,
            "--verdict", "PASS", "--evidence", str(review),
            "--delivery-ref", "execution.md#delivery-1",
        ]
    completed = subprocess.run(command, cwd=repo, text=True)
    if completed.returncode:
        raise SystemExit(completed.returncode)
raise SystemExit(args.exit_code)
