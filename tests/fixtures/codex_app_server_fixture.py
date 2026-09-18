#!/usr/bin/env python3
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    if request.get("method") == "model/list":
        print(json.dumps({"id": request.get("id"), "result": {"data": [{"id": "gpt-test", "display_name": "GPT Test"}]}}), flush=True)
