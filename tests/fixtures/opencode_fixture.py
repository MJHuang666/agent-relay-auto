#!/usr/bin/env python3
import sys

if "models" in sys.argv:
    if "--verbose" in sys.argv:
        print('openai/gpt-test\n  "url": "https://opencode.ai/zen/v1"\n  "npm": "@ai-sdk/openai-compatible"')
    else:
        print("openai/gpt-test\nanthropic/claude-test")
else:
    print('{"sessionID":"session-opencode-1","type":"result","usage":{"input":2,"output":3}}')
