# Automated Runner v1.7.0 Verification

Date: 2026-09-20

## Result

- Source tests: 111 passed with `ResourceWarning` promoted to errors.
- Release validation: passed, including canonical/bootstrap byte equality and v1.7 contract checks.
- Hybrid E2E: foreground Planner → background Implementer → background Reviewer → foreground Planner → `DONE`.
- Restart E2E: a recreated Runner consumed the durable Worker exit and did not duplicate the claim.
- Safety: no E2E run used role `planner`; no merge, push, release, or deploy artifact was created.
- Package: `dist/agent-relay-auto-skill-pack-v1.7.0.zip` passed `unzip -t` and checksum verification.
- Package SHA-256: `bd08cf9ce160c0c1b875e12bdf733ebedd9c73df07d68ba01d6a2a9aea4c9273`.

## Installed State

- Personal Codex Skill source and installed copy each contain 148 files.
- Runner `current` points to `/Users/mj/.local/share/agent-relay-auto/versions/1.7.0`.
- The installed `MANIFEST.sha256.json` contains 148 entries and exactly matches the 148 source file hashes.
- launchd service reached `state = running`, `active count = 1`, with a v1.7 workflow-aware status response.
- Startup verification found and fixed a transient `xpcproxy` health-check race; the controller now waits briefly for stable health and still fails immediately on a crash loop.

## Upgrade Preflight Evidence

A manifest refresh was initially and intentionally refused because the already-registered repository `/Volumes/HP P900/mjwork/test-auto-relay2` had live run `run-ee8cf7b100f1`. The run was observed read-only and remained active for at least 30 seconds. It was not interrupted, killed, repaired, or unregistered. After it finished naturally and the project had no active run, the same upgrade succeeded and the installed manifest matched the source exactly.

This refusal is a successful safety check: installation does not replace runtime files while a registered project has a live background run.

## Adapter Verification

- Deterministic Fake Adapter: full hybrid and restart sessions passed.
- Codex CLI: an existing registered Codex run was observed, but this release verification did not take ownership or claim its business result.
- OpenCode and Claude Code: pending real-session verification; no credentials or paid runs were assumed.

## Commands

```text
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py' -q
bash .github/scripts/validate-release.sh
git diff --check
unzip -tqq dist/agent-relay-auto-skill-pack-v1.7.0.zip
cd dist && shasum -a 256 -c agent-relay-auto-skill-pack-v1.7.0.zip.sha256
python3 ~/.local/share/agent-relay-auto/current/scripts/runnerctl.py status --repo <repo>
launchctl print gui/$(id -u)/com.agent-relay-auto.runner
```

`DONE` remains acceptance only. This verification did not merge, push, create a GitHub Release, publish, or deploy.
