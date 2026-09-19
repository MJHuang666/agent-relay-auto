# Automated Runner v1.6.3 Verification

Date: 2026-09-19

## Incident closure

This release upstreams the runtime repairs proven in `test-agent-relay-ayto` and closes the misleading manual-handoff behavior:

- automatic handoffs wait for Runner instead of asking the user to type `continue`;
- Codex can run in a non-Git checkout without an interactive approval prompt;
- continuous JSONL output is drained without filling a pipe and retained as bounded, redacted run logs;
- every exited role process closes its durable run claim;
- `CHANGES_REQUESTED` returns to Implementer;
- one broken project no longer stops other registered projects;
- launchd receives `HOME`, `CODEX_HOME`, and the Codex executable PATH;
- status distinguishes a healthy process, project configuration block, unloaded service, and crash loop.

## Verification commands

```text
python3 -m unittest discover -s tests -v
bash .github/scripts/validate-release.sh
git diff --check
```

The release check validates canonical/mirrored Skill scripts, bilingual templates, local links, the generated archive, and SHA-256 output.

Observed results:

```text
79 tests passed
Skill source and bootstrap mirror: valid
release-equivalent validation: passed
test-agent-relay-ayto: status=running, service_status=running, configuration=complete
legacy incomplete project: status=blocked, service_status=running
launchd after five seconds: active_count=1, no new stderr bytes
release archive SHA-256: 511b3a02915abc7e147b26afb0328bd91012feb7bc2fc431c4c1f2fcd2c87a35
```

## Boundary

macOS Full Disk Access cannot be granted by this package. The installer supplies the correct launchd environment and the health command identifies a failed service plus its stderr log. If a project on an external volume is denied, the user must grant access to the Python executable in the launchd plist and restart Runner.

Automatic `DONE` remains acceptance only. It does not authorize merge, push, release, deployment, production writes, or risk acceptance.
