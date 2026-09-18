# Automated Runner v1.6.1 Verification

Date: 2026-09-19

## Static CLI checks

| Tool | Version | Read-only capability check | Status |
|---|---|---|---|
| Codex | `codex-cli 0.152.0` | `codex app-server --help`, `exec` available | static verification complete; real session not run |
| OpenCode | `1.3.17` | `run`, `--session`, `--model`, `models --verbose` available | static verification complete; real session not run |
| Claude Code | `2.1.250` | `-p/--print`, `--output-format`, `--model`, `--resume` available | static verification complete; real session not run |

No credentials were consumed and no real model session was started during this verification. Adapter fixtures and the fake Runner E2E passed in the local test suite.

## Automated checks

```text
python3 -m unittest discover -s tests -v
60 tests passed
bash .github/scripts/validate-release.sh
validated source and generated release archive
git diff --check
passed
```

The test suite verifies state CAS, task queue serialization, cross-project parallelism, fake Planner/Implementer/Reviewer reporting to `DONE`, CLI command contracts, interruption/recovery identity checks, installer dry-run, template mirrors, and the no-merge/no-push/no-release/no-deploy boundary.
