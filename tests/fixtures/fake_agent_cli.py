#!/usr/bin/env python3
import argparse
import time


parser = argparse.ArgumentParser()
parser.add_argument("--sleep", type=float, default=0)
parser.add_argument("--exit-code", type=int, default=0)
parser.add_argument("--output-bytes", type=int, default=0)
args = parser.parse_args()
print("fake-agent-start", flush=True)
if args.output_bytes:
    print("x" * args.output_bytes, flush=True)
time.sleep(args.sleep)
print("fake-agent-finish", flush=True)
raise SystemExit(args.exit_code)
