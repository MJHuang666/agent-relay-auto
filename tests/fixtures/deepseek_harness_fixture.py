#!/usr/bin/env python3
"""Minimal NDJSON ACP server fixture for the Planner wake bridge."""

import json
import sys


for raw in sys.stdin:
    message = json.loads(raw)
    request_id = message.get("id")
    method = message.get("method")
    if request_id is None:
        continue
    if method == "initialize":
        result = {
            "protocolVersion": 1,
            "agentInfo": {"name": "fixture", "version": "1"},
            "agentCapabilities": {"sessionCapabilities": {"resume": {}}},
            "authMethods": [],
        }
    elif method == "session/resume":
        result = {"configOptions": []}
    elif method == "session/prompt":
        result = {"stopReason": "end_turn"}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": method}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}), flush=True)
