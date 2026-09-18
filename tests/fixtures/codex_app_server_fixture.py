#!/usr/bin/env python3
import json
import sys

initialized = False

for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if method == "initialize":
        print(json.dumps({"id": request.get("id"), "result": {"serverInfo": {"name": "fixture", "version": "1"}}}), flush=True)
    elif method == "initialized":
        initialized = True
    elif method == "model/list" and initialized:
        print(
            json.dumps(
                {
                    "id": request.get("id"),
                    "result": {"data": [{"id": "gpt-test", "displayName": "GPT Test"}]},
                }
            ),
            flush=True,
        )
