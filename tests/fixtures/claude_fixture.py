#!/usr/bin/env python3
import json
import sys

print(json.dumps({"type": "result", "session_id": "session-claude-1", "usage": {"input_tokens": 2, "output_tokens": 3}}))
