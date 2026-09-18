#!/usr/bin/env python3
import signal
import sys
import time


def handle_sigint(signum, frame):
    print("checkpoint-written", flush=True)
    raise SystemExit(130)


signal.signal(signal.SIGINT, handle_sigint)
print("started", flush=True)
time.sleep(10)
