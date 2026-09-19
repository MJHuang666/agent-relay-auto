#!/usr/bin/env python3
import argparse
import sys
import time


parser = argparse.ArgumentParser()
parser.add_argument("--sleep", type=float, default=0.05)
parser.add_argument("--exit", type=int, default=0)
args = parser.parse_args()
print("fixture stdout", flush=True)
print("fixture stderr", file=sys.stderr, flush=True)
time.sleep(args.sleep)
raise SystemExit(args.exit)
