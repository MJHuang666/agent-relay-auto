# Automated Runner v1.6.2 Verification

Date: 2026-09-19

## Corrected startup contract

Version 1.6.2 closes the gap between the initialization dialogue and the installed Runner:

1. The Skill collects explicit participant, Agent, model, and reasoning settings for all three roles.
2. `configure_runtime.py` rejects incomplete automatic configuration and writes provider-specific settings.
3. `runnerctl.py start` validates the policy before project registration or launchctl changes.
4. `agent_relay_runner.py` uses the real project Adapter factory in both one-shot and service modes.
5. The role router selects Codex, OpenCode, or Claude Code and applies the configured model and reasoning value.

Users do not configure an Adapter factory directly.

## Automated evidence

```text
python3 -m unittest discover -s tests -v
71 tests passed

bash .github/scripts/validate-release.sh
source and generated release archive validated

git diff --check
passed
```

The new tests cover incomplete configuration rejection, provider-specific role settings, model discovery output, inline confirmed configuration, role routing, participant mismatch detection, real one-shot entry wiring, configuration-aware Runner startup, project registration, and absolute launchd paths.

Read-only checks against the locally installed CLIs also confirmed that Codex model discovery completes its required app-server initialization handshake and that OpenCode returns only provider/model IDs rather than verbose metadata. Claude Code returned no discoverable model catalog, so its stable model ID remains a guided manual choice with `pending` validation until first launch.

## Validation boundary

No real model request or user launchd service was started during this source verification. Codex, OpenCode, and Claude Code command construction is covered by local CLI contract fixtures. A selected model's authentication and executable launch remain subject to first-launch validation. Automatic `DONE` still does not authorize merge, push, release, deployment, production writes, or risk acceptance.
